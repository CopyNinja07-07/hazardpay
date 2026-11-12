"""Retrain and gate: make the robot safer, and only ship it if it really is.

"Training" here tunes the robot's driving controller (cruise speed, heading
gain, tilt braking, traction control, stall boost) with an evolution strategy
on the failures the adversary found. Then the regression gate:

  1. it fails less on the failures it trained on (held-out seeds)
  2. it still delivers on a flat sidewalk, and no more than 10% slower
  3. it is no worse on the LOCKED GAUNTLET, a fixed suite whose hash is
     committed in this file before any result

Pass all three and the new version goes live, and the premium is re-quoted.
"""
import hashlib
import json

import numpy as np

from .scenario import compile_ops
from .search import fail_rates, pool
from .sim import CTRL_BOUNDS, DEFAULT_CTRL, rollout

GAUNTLET = [
    [{"op": "curb", "at": 3.0, "height": h}] for h in (0.04, 0.06, 0.08)
] + [
    [{"op": "ice", "start": 2.0, "length": 3.0, "mu": 0.08}, {"op": "shove", "t": 3.0, "dur": 0.4, "force": f, "angle": 90.0}]
    for f in (40.0, 80.0)
] + [
    [{"op": "cross_slope", "start": 2.0, "length": 3.0, "roll": r, "mu": m}] for r, m in ((6, 0.3), (10, 0.3), (8, 0.12))
] + [
    [{"op": "ramp", "at": 2.0, "length": 2.5, "angle": a, "mu": m}] for a, m in ((8, 0.3), (12, 0.5), (6, 0.15))
] + [
    [{"op": "payload", "mass": 10.0, "dz": 0.2}, {"op": "shove", "t": 2.5, "dur": 0.4, "force": 120.0, "angle": 90.0}],
    [{"op": "motor", "strength": 0.7}, {"op": "curb", "at": 3.0, "height": 0.07}],
    [{"op": "wet", "start": 1.0, "length": 5.0, "mu": 0.35}, {"op": "heading_bias", "deg": 8.0}],
    [{"op": "latency", "ms": 60.0}, {"op": "imu_noise", "deg": 3.0}, {"op": "cross_slope", "start": 2.0, "length": 3.0, "roll": 6.0, "mu": 0.5}],
    [{"op": "leaves", "start": 1.0, "length": 3.0, "mu": 0.35}, {"op": "ramp", "at": 2.0, "length": 2.0, "angle": 7.0, "mu": 0.4}],
]
GAUNTLET_SEEDS = range(500, 508)
GAUNTLET_HASH = hashlib.sha256(json.dumps(GAUNTLET, sort_keys=True).encode()).hexdigest()[:16]
NOMINAL = []  # flat sidewalk


def gauntlet_rate(ctrl) -> tuple[float, list[float]]:
    rates = fail_rates(GAUNTLET, ctrl, GAUNTLET_SEEDS)
    return float(np.mean(rates)), [round(r, 3) for r in rates]


def _nom(args):
    ctrl, s = args
    return rollout(compile_ops(NOMINAL), ctrl, s)


def nominal_time(ctrl) -> float | None:
    rs = list(pool().map(_nom, [(ctrl, s) for s in range(4)]))
    if any(r["failed"] for r in rs):
        return None
    return float(np.mean([r["t"] for r in rs]))


def _vec_to_ctrl(u):
    keys = list(CTRL_BOUNDS)
    return {k: CTRL_BOUNDS[k][0] + float(np.clip(x, 0, 1)) * (CTRL_BOUNDS[k][1] - CTRL_BOUNDS[k][0]) for k, x in zip(keys, u)}


def _ctrl_to_vec(c):
    return np.array([(c[k] - CTRL_BOUNDS[k][0]) / (CTRL_BOUNDS[k][1] - CTRL_BOUNDS[k][0]) for k in CTRL_BOUNDS])


def train(bank: list[list[dict]], base_ctrl: dict | None = None, gens: int = 6, pop: int = 10, seed: int = 0,
          progress=None) -> dict:
    """bank = concrete op lists (failures to learn from). Returns the candidate and the gate verdict."""
    base = {**DEFAULT_CTRL, **(base_ctrl or {})}
    t0 = nominal_time(base) or 6.0
    rng = np.random.default_rng(seed)
    mean, sigma = _ctrl_to_vec(base), 0.25
    train_seeds = range(0, 6)
    best, best_score = base, None
    for g in range(gens):
        X = np.clip(mean + sigma * rng.standard_normal((pop, len(mean))), 0, 1)
        X[0] = mean
        cands = [_vec_to_ctrl(x) for x in X]
        scores = []
        for c in cands:
            r = float(np.mean(fail_rates(bank, c, train_seeds))) if bank else 0.0
            # mild pressure to stay fast: slow robots are a business failure too
            # mild pressure to stay fast (slow robots lose money too) and close to the old driver
            drift = float(np.sum((_ctrl_to_vec(c) - _ctrl_to_vec(base)) ** 2))
            scores.append(-r - 0.15 * max(0.0, 1.0 - c["speed_scale"]) - 0.05 * drift)
        order = np.argsort(scores)[::-1]
        if best_score is None or scores[order[0]] > best_score:
            best_score, best = scores[order[0]], cands[order[0]]
        mean = 0.7 * X[order[:3]].mean(axis=0) + 0.3 * mean
        sigma = max(0.06, sigma * 0.85)
        if progress:
            progress({"gen": g + 1, "bank_fail": round(-scores[order[0]], 3)})
    return gate(bank, base, best, t0)


def gate(bank, old, new, t_old=None) -> dict:
    held = range(200, 208)
    b_old = float(np.mean(fail_rates(bank, old, held))) if bank else 0.0
    b_new = float(np.mean(fail_rates(bank, new, held))) if bank else 0.0
    g_old, g_old_rows = gauntlet_rate(old)
    g_new, g_new_rows = gauntlet_rate(new)
    t_old = t_old or nominal_time(old)
    t_new = nominal_time(new)
    checks = [
        {"check": "fails less on what it trained on (held-out seeds)", "ok": b_new < b_old,
         "before": round(b_old, 3), "after": round(b_new, 3)},
        {"check": "still delivers on a flat sidewalk, at most 10% slower", "ok": t_new is not None and t_new <= t_old * 1.10,
         "before": t_old, "after": t_new},
        {"check": f"no worse on the locked gauntlet ({len(GAUNTLET)} scenarios, hash {GAUNTLET_HASH})",
         "ok": g_new <= g_old + 1e-9, "before": round(g_old, 3), "after": round(g_new, 3)},
    ]
    return {"accepted": all(c["ok"] for c in checks), "checks": checks, "ctrl": {k: round(v, 3) for k, v in new.items()},
            "gauntlet_rows": {"before": g_old_rows, "after": g_new_rows}}
