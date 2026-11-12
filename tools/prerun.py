"""Play every demo flow once on a real machine and store the physics, so the hosted demo answers at once.

    uvicorn server:app --port 8799 &   # a normal local server (its process pool does the physics)
    python -m tools.prerun             # plays the flows against it, then it writes prerun/physics.json.gz

Each flow starts from a fresh robot v1: preview, day montage, quote, two adversary rounds, retrain + gate,
re-quote, the locked gauntlet, the old-vs-new replay, and a few claim days. Maple St runs last, so its
retraining is the one the hosted demo replays; then every mission is re-quoted with that v2.
"""
import os
import time

import httpx

from hazardpay import attacker
from hazardpay.underwrite import MISSIONS

C = httpx.Client(base_url=os.getenv("PRERUN_URL", "http://127.0.0.1:8799"), timeout=900)


def reset(v2=None):
    C.post("/api/reset", json={"v2": v2})


def ctrl_now():
    return C.get("/api/ledger").json()["versions"][-1]


def wait(r):
    jid = r.json()["job"]
    while True:
        j = C.get(f"/api/job/{jid}").json()
        if j["status"] != "running":
            if j["status"] == "error":
                print("   job error:", j.get("error"))
            return j.get("result")
        time.sleep(0.2)


def views(name):
    C.get("/api/preview", params={"name": name})
    for n in (14, 24):
        C.get("/api/days", params={"name": name, "n": n})


def flow(m, n_adv=3, gens=6):
    reset()
    name = m["name"]
    t0 = time.time()
    views(name)
    q = wait(C.post("/api/quote", json={"name": name}))
    a1 = wait(C.post("/api/adversary", json={"name": name, "n": n_adv}))
    a2 = wait(C.post("/api/adversary", json={"name": name, "n": n_adv}))
    hits = [a for a in (a1 or {}).get("attacks", []) + (a2 or {}).get("attacks", []) if a.get("confirmed")]
    rt = C.post("/api/retrain", params={"gens": gens})
    res = wait(rt) if rt.status_code == 200 else None
    q2 = wait(C.post("/api/quote", json={"name": name}))
    C.get("/api/gauntlet")
    for h in hits[:3]:
        C.post("/api/compare", json={"ops": h["ops"], "seed": 101})
    print(f"  {name} (n={n_adv}, gens={gens}): {q['risk']['p']:.3f} -> {q2['risk']['p']:.3f}, "
          f"{len(hits)} confirmed, gate {'PASS' if res and res.get('accepted') else 'no'}, {time.time() - t0:.0f}s", flush=True)
    v = ctrl_now()
    return {k: v[k] for k in ("speed_scale", "k_heading", "tilt_brake", "slip_ctrl", "stall_boost")} if v["version"] != "v1" else None


def main():
    t0 = time.time()
    maple = MISSIONS[0]
    for m in MISSIONS[1:]:
        flow(m, 2, 4)   # the auto-demo's fast settings
        flow(m, 3, 6)   # the app's defaults
    v2s = [c for c in (flow(maple, 2, 4), flow(maple, 3, 6)) if c]  # last: the retrainings the hosted demo replays
    print("every mission with the pre-run v2s, and the attack library on every robot…", flush=True)
    for ctrl in [None, *v2s]:
        for m in MISSIONS:
            reset(ctrl)
            views(m["name"])
            wait(C.post("/api/quote", json={"name": m["name"]}))
            C.get("/api/gauntlet")
        reset(ctrl)
        for i in range(0, len(attacker.LIBRARY), 3):  # walk the library (what a hosted adversary falls back to)
            wait(C.post("/api/adversary", json={"name": maple["name"], "n": 3, "library": True}))
    print("film + tour clips…", flush=True)
    C.get("/api/film")
    C.post("/api/clip", json={"ops": [{"op": "cross_slope", "start": 2.0, "length": 3.0, "roll": 8, "mu": 0.12}], "seed": 3})
    r = C.post("/api/prerun/save").json()
    print(f"saved {r['saved']} results {r['stats']}, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
