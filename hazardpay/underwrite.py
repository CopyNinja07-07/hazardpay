"""The underwriter: turn one mission into a measured failure probability and a price.

A mission is a site (fixed hazards: curbs, ramps, aprons) plus the conditions
that might happen on the day (weather, a pedestrian bump, cargo). We run the
robot through many sampled days in the physics twin. The failure rate IS the
risk, so the premium is a measurement, not a guess:

    premium = P(fail) x cover x loading + fee

Risk attribution: we re-run with each hazard removed. The drop in failure
rate is that hazard's share of the premium ("62% of your price is the icy apron").
"""
import hashlib
import hmac
import json
import math
import os
import random
import time

from . import scenario as SC
from .search import pool
from .sim import rollout

SECRET = (os.getenv("POLICY_SECRET") or "dev-only-change-me").encode()
LOADING, FEE, MIN_PREMIUM = 1.25, 0.30, 0.50
RATED_CARGO = 10.0
WEATHER = {"dry": {"factor": 1.0}, "wet": {"factor": 0.45}, "ice": {"factor": 0.1}}

COVERED = ["weather (wet, ice, leaves)", "terrain on the declared route (curbs, ramps, aprons)",
           "pedestrian bumps up to 200 N", "cargo up to the rated 10 kg"]
EXCLUDED = ["cargo above 10 kg", "the operator raising speed above the quoted speed", "motor strength below 60% (unserviced robot)"]


def _with_weather(ops: list[dict], w: str) -> list[dict]:
    """Rain or ice lowers the grip of every surface on the route."""
    f = WEATHER[w]["factor"]
    out = []
    for o in ops:
        o = dict(o)
        if "mu" in o and o["op"] in ("ramp", "cross_slope", "ice", "wet", "leaves"):
            o["mu"] = round(max(0.05, min(o["mu"], o["mu"] * f if w != "dry" else o["mu"])), 3)
        out.append(o)
    if w != "dry":
        # the flat sidewalk itself gets slick too
        out.append({"op": "wet" if w == "wet" else "ice", "start": 0.5, "length": 6.0,
                    "mu": 0.4 if w == "wet" else 0.12})
    return out


def sample_day(mission: dict, rng: random.Random) -> tuple[list[dict], dict]:
    ws = mission.get("weather", {"dry": 1.0})
    w = rng.choices(list(ws), weights=list(ws.values()))[0]
    ops = _with_weather([dict(o) for o in mission["site"]], w)
    day = {"weather": w, "bump": None}
    if mission.get("cargo_kg"):
        ops.append({"op": "payload", "mass": mission["cargo_kg"], "dz": mission.get("cargo_dz", 0.1)})
    if rng.random() < mission.get("bump_prob", 0.15):
        f = rng.uniform(40, 130)
        t = rng.uniform(1.0, 5.0)
        ops.append({"op": "shove", "t": t, "dur": 0.4, "force": f, "angle": rng.choice([90.0, 70.0, 110.0])})
        day["bump"] = round(f)
    if mission.get("motor", 1.0) < 1.0:
        ops.append({"op": "motor", "strength": mission["motor"]})
    return ops, day


def _run(args):
    ops, ctrl, seed, speed = args
    r = rollout(SC.compile_ops(ops, speed=speed), ctrl, seed)
    return r["failed"], r["outcome"]


def failure_probability(mission: dict, ctrl=None, n: int = 120, seed: int = 7, drop: int | None = None) -> dict:
    rng = random.Random(seed)
    m = dict(mission)
    if drop is not None:
        m["site"] = [o for i, o in enumerate(mission["site"]) if i != drop]
    jobs, days = [], []
    for i in range(n):
        ops, day = sample_day(m, rng)
        jobs.append((ops, ctrl, 1000 + i, m.get("speed", 1.2)))
        days.append(day)
    res = list(pool().map(_run, jobs, chunksize=4))
    k = sum(f for f, _ in res)
    p = k / n
    z = 1.96  # Wilson interval
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    by_w = {}
    for (f, o), d in zip(res, days):
        b = by_w.setdefault(d["weather"], [0, 0])
        b[0] += f
        b[1] += 1
    modes = {}
    for f, o in res:
        if f:
            modes[o] = modes.get(o, 0) + 1
    return {"p": round(p, 4), "lo": round(max(0, c - h), 4), "hi": round(min(1, c + h), 4), "n": n, "fails": k,
            "modes": modes, "by_weather": {w: round(a / b, 3) for w, (a, b) in by_w.items()}}


def quote(mission: dict, ctrl=None, robot_version: str = "v1", n: int = 120) -> dict:
    risk = failure_probability(mission, ctrl, n)
    shares = []
    for i, o in enumerate(mission["site"]):
        r = failure_probability(mission, ctrl, n=max(40, n // 2), drop=i)
        shares.append({"hazard": SC.describe([SC.fill({"ops": [o]})[0]]), "op": o["op"],
                       "p_without": r["p"], "delta": round(max(0.0, risk["p"] - r["p"]), 4)})
    tot = sum(s["delta"] for s in shares) or 1
    for s in shares:
        s["share"] = round(s["delta"] / tot, 3) if risk["p"] > 0 else 0.0
    cover = float(mission.get("cover", 400.0))
    premium = max(MIN_PREMIUM, round(risk["p"] * cover * LOADING + FEE, 2))
    policy = {
        "mission": mission.get("name", "mission"), "robot_version": robot_version, "cover": cover,
        "premium": premium, "currency": "USD", "p_fail": risk["p"], "ci": [risk["lo"], risk["hi"]],
        "covered": COVERED, "excluded": EXCLUDED, "issued_at": int(time.time()),
        "mission_hash": hashlib.sha256(json.dumps(mission, sort_keys=True).encode()).hexdigest()[:16],
    }
    policy["signature"] = hmac.new(SECRET, json.dumps(policy, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    return {"risk": risk, "shares": sorted(shares, key=lambda s: -s["share"]), "policy": policy,
            "pricing": {"formula": "P(fail) x cover x 1.25 + $0.30", "expected_loss": round(risk["p"] * cover, 2)}}


def verify_policy(policy: dict) -> bool:
    body = {k: v for k, v in policy.items() if k != "signature"}
    good = hmac.new(SECRET, json.dumps(body, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, policy.get("signature", ""))


# ---- example missions (also the demo presets) ----
MISSIONS = [
    {"name": "Maple St back door", "description": "Back door delivery: sidewalk, then an 8 deg driveway apron, then a 5 cm curb.",
     "site": [{"op": "cross_slope", "start": 2.0, "length": 3.0, "roll": 8.0, "mu": 0.9},
              {"op": "curb", "at": 5.6, "height": 0.05}],
     "weather": {"dry": 0.6, "wet": 0.3, "ice": 0.1}, "cargo_kg": 6, "cover": 400, "bump_prob": 0.15, "speed": 1.2},
    {"name": "Campus library ramp", "description": "Campus run up an 8 deg accessible ramp, wet leaves in autumn.",
     "site": [{"op": "leaves", "start": 1.0, "length": 1.5, "mu": 0.4}, {"op": "ramp", "at": 2.5, "length": 2.5, "angle": 8.0, "mu": 0.8}],
     "weather": {"dry": 0.5, "wet": 0.45, "ice": 0.05}, "cargo_kg": 4, "cover": 250, "bump_prob": 0.25, "speed": 1.1},
    {"name": "Downtown flat block", "description": "Flat downtown sidewalk, busy at lunch.",
     "site": [{"op": "curb", "at": 4.0, "height": 0.03}],
     "weather": {"dry": 0.8, "wet": 0.2}, "cargo_kg": 3, "cover": 150, "bump_prob": 0.35, "speed": 1.2},
]
