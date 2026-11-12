"""Hazard Pay web server. Run: uvicorn server:app --port 8000"""
import copy
import os
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hazardpay import ROOT, attacker, claims, llm, paypal, prerun
from hazardpay import scenario as SC
from hazardpay.search import attack
from hazardpay.prerun import rollout
from hazardpay.sim import DEFAULT_CTRL
from hazardpay.train import GAUNTLET, GAUNTLET_HASH, gauntlet_rate, train
from hazardpay.underwrite import MISSIONS, quote

app = FastAPI(title="Hazard Pay", version="1.0.0")
HOSTED = os.getenv("HAZARDPAY_HOSTED", "").lower() in {"1", "true", "yes"}  # the public demo on Render

STATE = {
    "versions": [{"version": "v1", "ctrl": dict(DEFAULT_CTRL), "created": time.strftime("%H:%M:%S"), "gate": None}],
    "missions": {m["name"]: m for m in MISSIONS},
    "quotes": {},      # mission name -> latest quote (for the current version)
    "policies": [],    # bought policies
    "claims": [],
    "failures": [],    # adversary archive (confirmed failures)
    "attacks": [],     # every attack tried
    "webhooks": [],
}
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()
FRESH = copy.deepcopy(STATE)
SEEN = {"t": time.time()}


@app.middleware("http")
async def idle_reset(request, call_next):
    """Hosted demo: after 20 quiet minutes the next visitor gets a fresh robot v1 and empty ledgers."""
    if HOSTED and request.url.path.startswith("/api/") and time.time() - SEEN["t"] > 1200:
        STATE.clear()
        STATE.update(copy.deepcopy(FRESH))
    SEEN["t"] = time.time()
    return await call_next(request)


def current():
    return STATE["versions"][-1]


def job(kind, fn):
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {"id": jid, "kind": kind, "status": "running", "events": [], "result": None}

    def emit(e):
        JOBS[jid]["events"].append({"t": time.strftime("%H:%M:%S"), **e})

    def run():
        try:
            JOBS[jid]["result"] = fn(emit)
            JOBS[jid]["status"] = "done"
        except Exception as e:  # surfaced in the UI
            JOBS[jid]["status"] = "error"
            JOBS[jid]["error"] = str(e)[:400]
    threading.Thread(target=run, daemon=True).start()
    return {"job": jid}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/home")
def home():
    return FileResponse(ROOT / "static" / "landing.html")


@app.get("/api/status")
def status():
    return {"ai": llm.MODEL if llm.live() else "DEMO (hypothesis library)",
            "paypal": "SANDBOX" if paypal.live() else "DEMO (offline fake)",
            "robot": current()["version"], "hosted": HOSTED, "prerun": prerun.STATS, "gauntlet_hash": GAUNTLET_HASH, "gauntlet_size": len(GAUNTLET),
            "missions": list(STATE["missions"].values()), "ops": {k: {p: v[:4] for p, v in s.items()} for k, s in SC.OPS.items()}}


class ResetIn(BaseModel):
    v2: dict | None = None


@app.post("/api/reset")
def api_reset(body: ResetIn):
    """Back to robot v1 with empty ledgers (tools/prerun.py may start from a given v2 controller)."""
    if HOSTED and body.v2:
        raise HTTPException(403)
    STATE.clear()
    STATE.update(copy.deepcopy(FRESH))
    if body.v2:
        STATE["versions"].append({"version": "v2", "ctrl": body.v2, "created": time.strftime("%H:%M:%S"), "gate": None})
    return {"robot": current()["version"]}


@app.post("/api/prerun/save")
def api_prerun_save():
    if HOSTED:
        raise HTTPException(403)
    return {"saved": prerun.save(), "stats": prerun.STATS}


@app.get("/api/job/{jid}")
def get_job(jid: str):
    if jid not in JOBS:
        raise HTTPException(404)
    return JOBS[jid]


# ---------- underwriting ----------
class MissionIn(BaseModel):
    name: str
    n: int = 3
    library: bool = False  # skip Gemini, use the built-in hypothesis library


@app.post("/api/quote")
def api_quote(body: MissionIn):
    m = STATE["missions"].get(body.name)
    if not m:
        raise HTTPException(404, "unknown mission")

    def run(emit):
        emit({"msg": f"Simulating 120 days of '{m['name']}' with robot {current()['version']}…"})
        if HOSTED:
            time.sleep(1.2)  # pre-run physics returns at once; keep the log readable
        q = quote(m, current()["ctrl"], current()["version"])
        STATE["quotes"][m["name"]] = q
        emit({"msg": f"P(fail) {q['risk']['p'] * 100:.1f}% → premium ${q['policy']['premium']:.2f}"})
        return q
    return job("quote", run)


class SiteIn(BaseModel):
    text: str = ""
    image: str | None = None


@app.post("/api/site")
def api_site(body: SiteIn):
    if body.image and len(body.image) > 8_000_000:
        raise HTTPException(413, "image too large")
    m, engine = attacker.site_from(body.text, body.image)
    if not m:
        raise HTTPException(400, "Reading a site needs GEMINI_API_KEY; pick a preset mission instead.")
    base = m["name"]
    i = 2
    while m["name"] in STATE["missions"]:
        m["name"] = f"{base} ({i})"
        i += 1
    STATE["missions"][m["name"]] = m
    return {"mission": m, "engine": engine}


@app.get("/api/preview")
def preview(name: str, seed: int = 1):
    """A recorded rollout of the mission's site on a dry day, for the 3D view."""
    m = STATE["missions"].get(name)
    if not m:
        raise HTTPException(404)
    inc = claims.run_mission(m, current()["ctrl"], seed, overrides={"weather": "dry", "bump": None})
    return inc


# ---------- adversary ----------
@app.post("/api/adversary")
def api_adversary(body: MissionIn):
    m = STATE["missions"].get(body.name)
    if not m:
        raise HTTPException(404)

    def run(emit):
        hist = [{"name": a["name"], "hypothesis": a["hypothesis"], "confirmed_rate": a.get("confirmed_rate")}
                for a in STATE["attacks"][-10:]]
        n, off = max(1, min(body.n, 5)), len(STATE["attacks"])
        if HOSTED:  # Gemini's pre-run hypotheses for this mission (new ones would need minutes of live physics here)
            hit = prerun.get(prerun.key("propose", [m["name"], n, off]))
            progs, engine = (hit if hit is not prerun.MISS else attacker.propose(m, hist, n=n, offset=off, library=True))
            engine = engine + " · pre-run"
        else:
            progs, engine = attacker.propose(m, hist, n=n, offset=off, library=body.library)
            if not body.library:
                prerun.put(prerun.key("propose", [m["name"], n, off]), [progs, engine])
        emit({"msg": f"{engine} wrote {len(progs)} hypotheses"})
        out = []
        for p in progs:
            emit({"msg": f"Testing: {p['hypothesis']}", "program": p})
            if HOSTED:
                time.sleep(0.9)
            r = attack(p, current()["ctrl"], quick=True)
            if not r.get("ok"):
                emit({"msg": "invalid program: " + "; ".join(r["errors"])})
                continue
            r["engine"] = engine
            r["mission"] = m["name"]
            r["robot"] = current()["version"]
            STATE["attacks"].append(r)
            if r["confirmed"]:
                STATE["failures"].append(r)
                inc = rollout(SC.compile_ops(r["ops"]), current()["ctrl"], 101, record=True)
                r["clip"] = {k: inc[k] for k in ("frames", "scene", "outcome", "t")}
            emit({"msg": (f"BROKE IT: {r['describe']} → {r['confirmed_rate'] * 100:.0f}% fail on fresh seeds "
                          f"({', '.join(r['modes'])})") if r["confirmed"] else
                  f"Survived: best found {r['found'] * 100:.0f}%, confirmed {r['confirmed_rate'] * 100:.0f}%", "attack": r})
            out.append(r)
        return {"attacks": out}
    return job("adversary", run)


@app.post("/api/retrain")
def api_retrain(gens: int = 6):
    bank = [f["ops"] for f in STATE["failures"] if f["robot"] == current()["version"]][-8:]
    if not bank:
        raise HTTPException(400, "No confirmed failures for the current robot yet: run the adversary first.")

    g = max(2, min(gens, 8))
    tk = prerun.key("train", [current()["ctrl"], g])
    if HOSTED and prerun.get(tk) is prerun.MISS:
        raise HTTPException(400, "This hosted demo ships the pre-run retraining of v1. Run the app locally to train further.")

    def run(emit):
        emit({"msg": f"Retraining {current()['version']}'s driver on {len(bank)} failures…"})
        if HOSTED:  # replay the pre-run evolution (minutes of physics), then the gate re-checks it live from cache
            res, events = copy.deepcopy(prerun.get(tk))
            for e in events:
                time.sleep(0.5)
                emit({"msg": f"generation {e['gen']}: fails {e['bank_fail'] * 100:.0f}% of the bank", **e})
        else:
            events = []
            res = train(bank, current()["ctrl"], gens=g, progress=lambda e: (events.append(e), emit({"msg": f"generation {e['gen']}: fails {e['bank_fail'] * 100:.0f}% of the bank", **e})))
            prerun.put(tk, [res, events])
        for c in res["checks"]:
            emit({"msg": f"{'PASS' if c['ok'] else 'FAIL'} · {c['check']}: {c['before']} → {c['after']}"})
        if res["accepted"]:
            v = f"v{len(STATE['versions']) + 1}"
            STATE["versions"].append({"version": v, "ctrl": res["ctrl"], "created": time.strftime("%H:%M:%S"), "gate": res})
            emit({"msg": f"Gate passed: {v} is live. Re-quote your missions to see the new premium."})
        else:
            emit({"msg": "Gate rejected the update: the live robot stays as it is."})
        res["live"] = current()["version"]
        return res
    return job("retrain", run)


@app.get("/api/gauntlet")
def api_gauntlet():
    r, rows = gauntlet_rate(current()["ctrl"])
    return {"version": current()["version"], "rate": r, "rows": rows, "hash": GAUNTLET_HASH,
            "scenarios": [SC.describe(SC.fill({"ops": g})) for g in GAUNTLET]}


# ---------- policy + PayPal ----------
class Buy(BaseModel):
    name: str
    operator_email: str = "operator@personal.example.com"
    server_side: bool = False  # sandbox test card, no buyer login


@app.post("/api/buy")
def api_buy(body: Buy, request: Request):
    q = STATE["quotes"].get(body.name)
    if not q:
        raise HTTPException(400, "quote first")
    base = str(request.base_url).rstrip("/")
    try:
        if body.server_side:
            order = paypal.pay_premium_server_side(q["policy"])
        else:
            order = paypal.create_premium_order(q["policy"], f"{base}/?paid=1", f"{base}/?cancel=1")
    except Exception as e:
        raise HTTPException(502, str(e)[:300])
    paid = order.get("status") == "COMPLETED"
    pol = {"id": "POL-" + uuid.uuid4().hex[:8].upper(), "mission": body.name, "policy": q["policy"], "order": order,
           "status": "active" if paid else "awaiting approval",
           **({"capture": {"status": "COMPLETED", "capture_id": order.get("capture_id")}} if paid else {}), "operator_email": body.operator_email, "created": time.strftime("%H:%M:%S")}
    STATE["policies"].append(pol)
    return pol


class OrderIn(BaseModel):
    order_id: str


@app.post("/api/capture")
def api_capture(body: OrderIn):
    pol = next((p for p in STATE["policies"] if p["order"]["id"] == body.order_id), None)
    if not pol:
        raise HTTPException(404)
    try:
        cap = paypal.capture(body.order_id)
    except Exception as e:
        raise HTTPException(502, str(e)[:300])
    pol["capture"] = cap
    pol["status"] = "active" if cap.get("status") == "COMPLETED" else cap.get("status")
    return pol


class ClipIn(BaseModel):
    ops: list[dict]
    seed: int = 101


@app.post("/api/clip")
def api_clip(body: ClipIn):
    errs = SC.validate({"ops": body.ops}) if body.ops else []
    if errs:
        raise HTTPException(400, "; ".join(errs))
    r = rollout(SC.compile_ops(SC.fill({"ops": body.ops}) if body.ops else []), current()["ctrl"], body.seed, record=True)
    return r


FILM_V2 = {"speed_scale": 0.981, "k_heading": 3.826, "tilt_brake": 2.066, "slip_ctrl": 0.0, "stall_boost": 1.158}


@app.get("/api/film")
def api_film():
    """Every real physics recording the 3D film needs, in one call (cached)."""
    if "film" in CACHE_FILM:
        return CACHE_FILM["film"]
    import random as _r
    from hazardpay.underwrite import sample_day
    m = STATE["missions"]["Maple St back door"]
    v1 = STATE["versions"][0]["ctrl"]
    v2 = STATE["versions"][-1]["ctrl"] if len(STATE["versions"]) > 1 else FILM_V2

    def rec(ops, ctrl, seed, speed=1.2, every=2):
        r = rollout(SC.compile_ops(ops, speed=speed), ctrl, seed, record=True)
        return {"frames": r["frames"][::every], "scene": r["scene"], "outcome": r["outcome"], "t": r["t"]}

    site = [dict(o) for o in m["site"]]
    out = {}
    out["intro"] = rec(site + [{"op": "payload", "mass": 6, "dz": 0.1}], v1, 2)
    icy = [{"op": "cross_slope", "start": 2.0, "length": 3.0, "roll": 8.0, "mu": 0.12}, {"op": "curb", "at": 5.6, "height": 0.05}]
    out["fail"] = rec(icy, v1, 3)
    rng = _r.Random(11)
    days = []
    for i in range(30):
        ops, day = sample_day(m, rng)
        d = rec(ops, v1, 2000 + i, every=3)
        d.update(weather=day["weather"], bump=day["bump"])
        days.append(d)
    out["days"] = days
    attack = [{"op": "cross_slope", "start": 2.0, "length": 3.0, "roll": 7.0, "mu": 0.31},
              {"op": "shove", "t": 2.8, "dur": 0.4, "force": 100.0, "angle": 90.0}]
    out["attack"] = rec(attack, v1, 102)
    out["old"] = rec(attack, v1, 102)
    out["new"] = rec(attack, v2, 102)
    inc = claims.run_mission(m, v2, 7, {"weather": "ice", "bump": None})
    out["claim"] = {"frames": inc["frames"][::2], "scene": inc["scene"], "outcome": inc["outcome"], "t": inc["t"]}
    day = inc["day"]
    cf = []
    for label, d2, site2 in [("without ice", {**day, "weather": "dry"}, m["site"]),
                             ("without the sloped driveway", day, [o for o in m["site"] if o["op"] != "cross_slope"]),
                             ("without the curb", day, [o for o in m["site"] if o["op"] != "curb"]),
                             ("without the cargo", {**day, "cargo_kg": 0}, m["site"])]:
        ops = claims._ops_for(dict(m, site=site2), d2)
        r = rec(ops, v2, 7)
        r["label"] = label
        cf.append(r)
    out["counterfactuals"] = cf
    over = claims.run_mission(m, v1, 1, {"weather": "dry", "bump": None, "cargo_kg": 14})
    out["overload"] = {"frames": over["frames"][::2], "scene": over["scene"], "outcome": over["outcome"], "t": over["t"]}
    out["final"] = rec(site + [{"op": "payload", "mass": 6, "dz": 0.1}], v2, 2)
    CACHE_FILM["film"] = out
    return out


CACHE_FILM: dict = {}


@app.get("/api/days")
def api_days(name: str, n: int = 14, seed: int = 7):
    """A sample of the underwriting days, recorded, for the fast-forward montage."""
    import random as _r
    from hazardpay.underwrite import sample_day
    m = STATE["missions"].get(name)
    if not m:
        raise HTTPException(404)
    rng = _r.Random(seed)
    out = []
    for i in range(n):
        ops, day = sample_day(m, rng)
        r = rollout(SC.compile_ops(ops, speed=m.get("speed", 1.2)), current()["ctrl"], 1000 + i, record=True)
        r["frames"] = r["frames"][::2]
        out.append({"day": i + 1, "weather": day["weather"], "bump": day["bump"], **{k: r[k] for k in ("frames", "scene", "outcome", "t")}})
    return out


@app.post("/api/compare")
def api_compare(body: ClipIn):
    """The same run with the first and the current version of the robot, for a side-by-side replay."""
    ops = SC.fill({"ops": body.ops}) if body.ops else []
    site = SC.compile_ops(ops)
    old = rollout(site, STATE["versions"][0]["ctrl"], body.seed, record=True)
    new = rollout(site, current()["ctrl"], body.seed, record=True)
    return {"old": old, "new": new, "old_version": STATE["versions"][0]["version"], "new_version": current()["version"]}


@app.get("/api/order/{order_id}")
def api_order(order_id: str):
    try:
        return paypal.get_order(order_id)
    except Exception as e:
        raise HTTPException(502, str(e)[:300])


class RunIn(BaseModel):
    policy_id: str
    what_if: bool = False
    seed: int | None = None
    weather: str | None = None
    cargo_kg: float | None = None
    speed: float | None = None
    bump: int | None = None


@app.post("/api/run")
def api_run(body: RunIn):
    pol = next((p for p in STATE["policies"] if p["id"] == body.policy_id), None)
    if not pol:
        raise HTTPException(404)
    if pol["status"] != "active" and not body.what_if:
        raise HTTPException(400, "the premium isn't paid yet")
    m = STATE["missions"][pol["mission"]]
    ov = {k: v for k, v in {"weather": body.weather, "cargo_kg": body.cargo_kg, "speed": body.speed}.items() if v is not None}
    if body.bump == 0:
        ov["bump"] = None
    elif body.bump:
        ov.update(bump=body.bump, bump_t=3.0, bump_angle=90.0)
    inc = claims.run_mission(m, current()["ctrl"], body.seed if body.seed is not None else int(time.time()) % 10000, ov)
    pol["last_run"] = {k: inc[k] for k in ("outcome", "t", "x", "day", "describe", "seed")}
    return inc


class ClaimIn(BaseModel):
    policy_id: str
    what_if: bool = False
    seed: int
    weather: str | None = None
    cargo_kg: float | None = None
    speed: float | None = None
    bump: int | None = None


@app.post("/api/claim")
def api_claim(body: ClaimIn):
    pol = next((p for p in STATE["policies"] if p["id"] == body.policy_id), None)
    if not pol:
        raise HTTPException(404)
    m = STATE["missions"][pol["mission"]]
    ov = {k: v for k, v in {"weather": body.weather, "cargo_kg": body.cargo_kg, "speed": body.speed}.items() if v is not None}
    if body.bump == 0:
        ov["bump"] = None
    elif body.bump:
        ov.update(bump=body.bump, bump_t=3.0, bump_angle=90.0)
    ver = next(v for v in STATE["versions"] if v["version"] == pol["policy"]["robot_version"])
    inc = claims.run_mission(m, ver["ctrl"], body.seed, ov)  # re-derive the incident from the logged seed
    adj = claims.adjudicate(m, pol["policy"], inc, ver["ctrl"])
    claim = {"id": "CLM-" + uuid.uuid4().hex[:8].upper(), "policy_id": pol["id"], "mission": pol["mission"],
             "incident": {k: inc[k] for k in ("outcome", "t", "x", "day", "describe", "seed")}, **adj,
             "created": time.strftime("%H:%M:%S")}
    claim["what_if"] = body.what_if
    if adj["decision"] == "APPROVED" and not body.what_if:
        try:
            claim["payout"] = {"amount": adj["payout"], **paypal.payout(claim["id"], pol["operator_email"], adj["payout"],
                                                                         adj["note"]["text"])}
        except Exception as e:
            claim["payout"] = {"amount": adj["payout"], "error": str(e)[:300]}
        pol["status"] = "claimed"
    if not body.what_if:
        STATE["claims"].append(claim)
    return claim


class MarksIn(BaseModel):
    marks: list[dict]


@app.post("/api/marks")
def api_marks(body: MarksIn):
    """The auto-demo posts its shot timestamps here; tools/film.py aligns the voiceover to them."""
    import json
    (ROOT / "runs").mkdir(exist_ok=True)
    (ROOT / "runs" / "marks.json").write_text(json.dumps(body.marks, indent=1))
    return {"ok": True, "n": len(body.marks)}


@app.post("/api/paypal/webhook")
async def webhook(req: Request):
    event = await req.json()
    ok = paypal.verify_webhook(dict(req.headers), event)
    STATE["webhooks"].insert(0, {"time": time.strftime("%H:%M:%S"), "event": event.get("event_type"),
                                 "resource": (event.get("resource") or {}).get("id"), "verified": ok})
    return {"ok": True}


@app.get("/api/ledger")
def ledger():
    pols = [{"id": p["id"], "mission": p["mission"], "robot": p["policy"]["robot_version"], "p_fail": p["policy"]["p_fail"],
             "premium": p["policy"]["premium"], "cover": p["policy"]["cover"], "status": p["status"],
             "paypal_order": p["order"]["id"], "created": p["created"]} for p in STATE["policies"]]
    cls = [{"id": c["id"], "policy": c["policy_id"], "mission": c["mission"], "outcome": c["incident"]["outcome"],
            "decision": c["decision"], "reason": c["reason"], "payout": c.get("payout", {}).get("amount", 0),
            "paypal_batch": c.get("payout", {}).get("batch_id", ""), "created": c["created"]} for c in STATE["claims"]]
    atk = [{"id": a["id"], "mission": a["mission"], "robot": a["robot"], "name": a["name"], "hypothesis": a["hypothesis"],
            "minimal": a["describe"], "found": a["found"], "confirmed": a["confirmed_rate"], "modes": ", ".join(a["modes"]),
            "deviation": a["deviation"], "engine": a.get("engine", "")} for a in STATE["attacks"]]
    vers = [{"version": v["version"], "created": v["created"], **{k: round(x, 3) for k, x in v["ctrl"].items()},
             "gauntlet": (v["gate"] or {}).get("checks", [{}, {}, {"after": None}])[2].get("after")} for v in STATE["versions"]]
    return {"policies": pols, "claims": cls, "attacks": atk, "versions": vers, "webhooks": STATE["webhooks"]}


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
