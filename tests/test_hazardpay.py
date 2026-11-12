"""Offline tests (no keys): physics, adversary, underwriting, gate, claims, PayPal fake, API."""
import os

os.environ["DEMO_MODE"] = "1"

from hazardpay import scenario as SC  # noqa: E402
from hazardpay.claims import adjudicate, run_mission  # noqa: E402
from hazardpay.search import attack, fail_rate  # noqa: E402
from hazardpay.sim import rollout  # noqa: E402
from hazardpay.train import GAUNTLET, GAUNTLET_HASH  # noqa: E402
from hazardpay.underwrite import MISSIONS, quote, verify_policy  # noqa: E402


def test_flat_sidewalk_delivers():
    r = rollout(SC.compile_ops([]), seed=0)
    assert r["outcome"] == "delivered" and r["t"] < 7


def test_physics_failures_are_real():
    assert fail_rate([{"op": "ramp", "at": 2, "length": 2.5, "angle": 12, "mu": 0.1}], seeds=range(4))[0] == 1.0
    assert fail_rate([{"op": "ramp", "at": 2, "length": 2.5, "angle": 12, "mu": 0.9}], seeds=range(4))[0] == 0.0


def test_validation_rejects_unrealistic_programs():
    errs = SC.validate({"ops": [{"op": "curb", "height": 0.5}, {"op": "teleport"}]})
    assert any("outside the realistic range" in e for e in errs) and any("unknown op" in e for e in errs)


def test_attack_shrinks_and_confirms():
    r = attack({"name": "t", "hypothesis": "h", "ops": [
        {"op": "ramp", "at": 2, "length": 2.5, "angle": 10, "mu": [0.08, 0.6]}, {"op": "payload", "mass": [0, 8]}]}, quick=True)
    assert r["ok"] and r["confirmed"]
    assert [o["op"] for o in r["ops"]] == ["ramp"]  # the cargo wasn't needed


def test_quote_is_signed_and_tamper_evident():
    q = quote(MISSIONS[0], n=30)
    assert 0 <= q["risk"]["p"] <= 1 and q["policy"]["premium"] >= 0.5
    assert verify_policy(q["policy"])
    assert not verify_policy({**q["policy"], "cover": 99999})


def test_claim_counterfactual():
    m = MISSIONS[0]
    q = quote(m, n=20)
    inc = run_mission(m, seed=7, overrides={"weather": "ice"})
    assert inc["failed"]
    a = adjudicate(m, q["policy"], inc)
    assert a["decision"] == "APPROVED" and any(t["saved"] for t in a["tests"])


def test_gauntlet_is_locked():
    assert len(GAUNTLET) == 16 and GAUNTLET_HASH == "e37b7660e8720913"


def test_api_flow():
    from fastapi.testclient import TestClient
    import time
    from server import app
    c = TestClient(app)
    j = c.post("/api/quote", json={"name": MISSIONS[2]["name"]}).json()["job"]
    for _ in range(120):
        s = c.get(f"/api/job/{j}").json()
        if s["status"] != "running":
            break
        time.sleep(0.5)
    assert s["status"] == "done"
    pol = c.post("/api/buy", json={"name": MISSIONS[2]["name"]}).json()
    assert pol["order"]["id"].startswith("FAKE-")
    assert c.post("/api/capture", json={"order_id": pol["order"]["id"]}).json()["status"] == "active"
