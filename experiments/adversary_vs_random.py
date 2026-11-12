"""Does a hypothesis-driven adversary find more plausible failures than blind random programs?

Same budget per arm (same number of programs, same search settings). A "strict" failure is one
confirmed on 32 fresh seeds (rate >= 0.5) with plausibility cost <= 1.5. Results go to
experiments/results.json whichever way they come out.

    python -m experiments.adversary_vs_random [--programs 12]
"""
import json
import random
import sys
import time

from hazardpay import attacker
from hazardpay import scenario as SC
from hazardpay.search import attack
from hazardpay.underwrite import MISSIONS


def run_arm(name, programs):
    rows = []
    for p in programs:
        r = attack(p, quick=True)
        if r.get("ok"):
            rows.append({"name": p.get("name"), "confirmed": r["confirmed"], "rate": r["confirmed_rate"],
                         "deviation": r["deviation"], "minimal": r["describe"]})
    strict = [x for x in rows if x["confirmed"] and x["deviation"] <= 1.5]
    return {"arm": name, "programs": len(rows), "confirmed": sum(x["confirmed"] for x in rows), "strict": len(strict),
            "mean_cost_of_confirmed": round(sum(x["deviation"] for x in rows if x["confirmed"]) /
                                            max(1, sum(x["confirmed"] for x in rows)), 3), "rows": rows}


if __name__ == "__main__":
    n = int(sys.argv[sys.argv.index("--programs") + 1]) if "--programs" in sys.argv else 12
    t = time.time()
    progs, engine = [], None
    while len(progs) < n:
        ps, engine = attacker.propose(MISSIONS[0], [], n=min(3, n - len(progs)), offset=len(progs))
        progs += ps
    rng = random.Random(0)
    rand = [SC.random_program(rng, 2) for _ in range(n)]
    res = {"engine": engine, "budget_programs": n, "arms": [run_arm(f"adversary ({engine})", progs), run_arm("random programs", rand)],
           "seconds": round(time.time() - t)}
    json.dump(res, open("experiments/results.json", "w"), indent=1)
    for a in res["arms"]:
        print(f"{a['arm']:<45} confirmed {a['confirmed']}/{a['programs']}  strict {a['strict']}  mean cost {a['mean_cost_of_confirmed']}")
