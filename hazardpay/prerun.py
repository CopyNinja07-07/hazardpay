"""Pre-run physics: every MuJoCo rollout result the demo needs, computed once and shipped with the repo.

A hosted demo box has a fraction of a CPU, while one quote is ~240 rollouts and one adversary attack is
hundreds more. So every batch of rollouts goes through `CachedPool.map`: a job whose exact inputs were
already simulated returns the stored result; anything new is simulated live and remembered.
Only the physics results are stored. Pricing, signing, the gate, claims and PayPal all run live.

    python -m tools.prerun      # rebuild prerun/physics.json.gz by playing the demo flows
"""
import dataclasses
import gzip
import hashlib
import json
import os
import threading

from . import ROOT

PATH = ROOT / "prerun" / "physics.json.gz"
MISS = object()
_C: dict = {}
_L = threading.Lock()
STATS = {"hits": 0, "misses": 0, "loaded": 0}

if PATH.exists() and os.getenv("HAZARDPAY_NO_PRERUN", "") not in {"1", "true"}:
    try:
        _C = json.loads(gzip.decompress(PATH.read_bytes()))
        STATS["loaded"] = len(_C)
    except Exception:
        _C = {}


def _norm(x):
    if dataclasses.is_dataclass(x):
        return _norm(dataclasses.asdict(x))
    if isinstance(x, dict):
        return {str(k): _norm(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, (list, tuple)):
        return [_norm(v) for v in x]
    if isinstance(x, float):
        return float(f"{x:.6g}")  # same key on any CPU
    if hasattr(x, "tolist"):
        return _norm(x.tolist())
    return x


def key(name: str, args) -> str:
    return name + ":" + hashlib.sha1(json.dumps(_norm(args), sort_keys=True, default=str).encode()).hexdigest()[:24]


def get(k):
    v = _C.get(k, MISS)
    with _L:
        STATS["hits" if v is not MISS else "misses"] += 1
    return v


def put(k, v):
    with _L:
        _C[k] = json.loads(json.dumps(v, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))


def save():
    PATH.parent.mkdir(exist_ok=True)
    PATH.write_bytes(gzip.compress(json.dumps(_C, separators=(",", ":")).encode(), 9))
    return len(_C)


def memo(name, args, fn):
    """Cache a whole computed result (used for the recorded 3D clips)."""
    k = key(name, args)
    v = get(k)
    if v is MISS:
        v = fn()
        put(k, v)
    return v


class CachedPool:
    def __init__(self, make_real):
        self._make = make_real
        self._real = None

    def map(self, fn, iterable, chunksize=1):
        jobs = list(iterable)
        keys = [key(fn.__name__, j) for j in jobs]
        out = [get(k) for k in keys]
        miss = [i for i, o in enumerate(out) if o is MISS]
        if miss:
            if self._real is None:
                self._real = self._make()
            res = list(self._real.map(fn, [jobs[i] for i in miss], chunksize=chunksize)) if self._real else \
                [fn(jobs[i]) for i in miss]
            for i, r in zip(miss, res):
                out[i] = r
                put(keys[i], r)
        return iter(out)


def rollout(site, ctrl=None, seed=0, record=False):
    """sim.rollout, pre-run: the same inputs give the stored result (a shallow copy, safe to annotate)."""
    from .sim import rollout as _rollout
    return dict(memo("rollout", [site, ctrl, seed, record], lambda: _rollout(site, ctrl, seed, record=record)))
