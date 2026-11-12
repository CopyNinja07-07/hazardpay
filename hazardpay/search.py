"""The adversary's engine: search a hazard program for the most plausible failure.

  1. search   an evolution strategy over the program's free ranges, maximising
              fail rate minus a plausibility penalty (smaller hazards score higher)
  2. shrink   delta-debugging: drop every op the failure doesn't need, then pull each
              remaining value back toward harmless while it still fails
  3. confirm  fresh seeds the search never saw; only a confirmed failure counts
"""
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from . import scenario as SC
from .sim import rollout

_POOL = None
LAMBDA = 0.12  # plausibility weight


def pool():
    global _POOL
    if _POOL is None:
        _POOL = ProcessPoolExecutor(max_workers=max(2, (os.cpu_count() or 4) - 1))
    return _POOL


def _one(args):
    site, ctrl, seed = args
    r = rollout(site, ctrl, seed)
    return r["failed"], r["outcome"]


def fail_rate(ops, ctrl=None, seeds=range(8), speed=1.2):
    site = SC.compile_ops(ops, speed=speed)
    res = list(pool().map(_one, [(site, ctrl, s) for s in seeds]))
    modes = {}
    for f, o in res:
        if f:
            modes[o] = modes.get(o, 0) + 1
    return sum(f for f, _ in res) / len(res), modes


def fail_rates(ops_list, ctrl=None, seeds=range(8), speed=1.2):
    jobs, idx = [], []
    for j, ops in enumerate(ops_list):
        site = SC.compile_ops(ops, speed=speed)
        for s in seeds:
            jobs.append((site, ctrl, s))
            idx.append(j)
    out = [0] * len(ops_list)
    for j, (f, _) in zip(idx, pool().map(_one, jobs, chunksize=4)):
        out[j] += f
    return [o / len(list(seeds)) for o in out]


def search(program, ctrl=None, pop=12, gens=6, seeds=range(6), rng_seed=0, speed=1.2):
    fp = SC.free_params(program)
    if not fp:
        ops = SC.fill(program)
        r, _ = fail_rate(ops, ctrl, seeds, speed)
        return ops, r, [{"gen": 0, "best": r}]
    rng = np.random.default_rng(rng_seed)
    k = len(fp)
    mean, sigma = np.full(k, 0.5), 0.3
    best, best_score, curve = None, -1e9, []
    for g in range(gens):
        X = np.clip(mean + sigma * rng.standard_normal((pop, k)), 0, 1)
        cand = [SC.fill(program, x) for x in X]
        rates = fail_rates(cand, ctrl, seeds, speed)
        scores = np.array([r - LAMBDA * SC.deviation(c) for r, c in zip(rates, cand)])
        order = np.argsort(-scores)
        elite = X[order[: max(2, pop // 4)]]
        mean = 0.7 * elite.mean(axis=0) + 0.3 * mean
        sigma = max(0.05, sigma * (0.85 if rates[order[0]] > 0.5 else 1.05))
        if scores[order[0]] > best_score:
            best_score, best = scores[order[0]], (cand[order[0]], rates[order[0]])
        curve.append({"gen": g + 1, "best": round(float(rates[order[0]]), 3), "score": round(float(scores[order[0]]), 3)})
    return best[0], best[1], curve


def shrink(ops, ctrl=None, seeds=range(12), keep=0.75, speed=1.2):
    """Smallest version that still fails at least `keep` of the time."""
    ops = [dict(o) for o in ops]
    # 1. drop ops it doesn't need
    i = 0
    while i < len(ops) and len(ops) > 1:
        trial = ops[:i] + ops[i + 1:]
        if fail_rate(trial, ctrl, seeds, speed)[0] >= keep:
            ops = trial
        else:
            i += 1
    # 2. pull intensities toward harmless
    for o in ops:
        spec = SC.OPS[o["op"]]
        for k in ("mu", "height", "angle", "roll", "mass", "force", "deg", "ms", "strength"):
            if k not in o or k not in spec or (o["op"] == "shove" and k == "angle"):
                continue
            nom, cur = spec[k][2], o[k]
            lo_frac, hi_frac = 0.0, 1.0  # fraction of the way from cur back to nominal
            for _ in range(4):
                mid = (lo_frac + hi_frac) / 2
                o[k] = cur + mid * (nom - cur)
                if fail_rate(ops, ctrl, seeds, speed)[0] >= keep:
                    lo_frac = mid
                else:
                    hi_frac = mid
            o[k] = round(cur + lo_frac * (nom - cur), 3)
    return ops


def attack(program, ctrl=None, speed=1.2, confirm_seeds=range(100, 132), quick=False):
    """search -> shrink -> confirm. Returns a failure record (confirmed or not)."""
    errs = SC.validate(program)
    if errs:
        return {"ok": False, "errors": errs}
    ops, r, curve = search(program, ctrl, pop=8 if quick else 12, gens=4 if quick else 6, speed=speed)
    shrunk = shrink(ops, ctrl, speed=speed) if r >= 0.5 else ops
    rate, modes = fail_rate(shrunk, ctrl, confirm_seeds, speed)
    fid = hashlib.sha1(json.dumps(shrunk, sort_keys=True).encode()).hexdigest()[:8]
    return {"ok": True, "id": fid, "name": program.get("name", ""), "hypothesis": program.get("hypothesis", ""),
            "ops": shrunk, "found": round(r, 3), "confirmed_rate": round(rate, 3), "modes": modes,
            "confirmed": rate >= 0.5, "deviation": SC.deviation(shrunk), "describe": SC.describe(shrunk),
            "curve": curve}
