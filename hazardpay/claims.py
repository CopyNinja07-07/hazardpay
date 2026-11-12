"""Claims: when a mission fails, decide in seconds whether the policy pays.

Parametric and counterfactual. The incident is replayed in the physics twin
with the exact same seed, once per condition, with that one condition taken
away. If removing a COVERED condition (ice, a bump, the declared curb) turns
the failure into a delivery, that condition caused it and the claim pays. If
only removing an EXCLUDED one (cargo over the rated 10 kg, a speed override, an
unserviced motor) saves it, the claim is denied. Gemini writes the adjuster's
note, but the decision comes from physics.
"""
import random

from . import llm
from . import scenario as SC
from .sim import rollout
from .underwrite import RATED_CARGO, _with_weather, sample_day, verify_policy


def _ops_for(mission: dict, day: dict) -> list[dict]:
    ops = _with_weather([dict(o) for o in mission["site"]], day["weather"])
    if day.get("cargo_kg"):
        ops.append({"op": "payload", "mass": day["cargo_kg"], "dz": mission.get("cargo_dz", 0.1)})
    if day.get("bump"):
        ops.append({"op": "shove", "t": day["bump_t"], "dur": 0.4, "force": float(day["bump"]), "angle": day["bump_angle"]})
    if day.get("motor", 1.0) < 1.0:
        ops.append({"op": "motor", "strength": day["motor"]})
    return ops


def run_mission(mission: dict, ctrl=None, seed: int = 42, overrides: dict | None = None) -> dict:
    """The 'real' run: one day drawn from the mission's conditions, recorded for replay."""
    rng = random.Random(seed)
    _, d0 = sample_day(mission, rng)
    rng = random.Random(seed)
    day = {"weather": d0["weather"], "cargo_kg": mission.get("cargo_kg", 0), "motor": mission.get("motor", 1.0),
           "speed": mission.get("speed", 1.2)}
    if d0["bump"]:
        day.update(bump=d0["bump"], bump_t=round(rng.uniform(1.5, 4.0), 2), bump_angle=90.0)
    day.update(overrides or {})
    ops = _ops_for(mission, day)
    r = rollout(SC.compile_ops(ops, speed=day["speed"]), ctrl, seed, record=True)
    return {"seed": seed, "day": day, "ops": ops, "describe": SC.describe(ops), **r}


def adjudicate(mission: dict, policy: dict, incident: dict, ctrl=None) -> dict:
    if not verify_policy(policy):
        return {"decision": "DENIED", "reason": "policy signature invalid", "tests": []}
    if not incident["failed"]:
        return {"decision": "NO CLAIM", "reason": "the robot delivered", "tests": []}
    day, seed = incident["day"], incident["seed"]
    quoted_speed = mission.get("speed", 1.2)
    exclusions = []
    if day.get("cargo_kg", 0) > RATED_CARGO:
        exclusions.append("cargo_kg")
    if day.get("speed", quoted_speed) > quoted_speed + 1e-6:
        exclusions.append("speed")
    if day.get("motor", 1.0) < 0.6:
        exclusions.append("motor")

    # counterfactuals: take away one condition at a time, same seed
    tests = []

    def test(label, kind, d=None, site=None):
        m = dict(mission, site=site if site is not None else mission["site"])
        ops = _ops_for(m, d or day)
        r = rollout(SC.compile_ops(ops, speed=(d or day)["speed"]), ctrl, seed)
        tests.append({"remove": label, "kind": kind, "outcome": r["outcome"], "saved": not r["failed"]})

    if day["weather"] != "dry":
        test(f"{day['weather']} weather -> dry", "covered", {**day, "weather": "dry"})
    if day.get("bump"):
        test(f"the {day['bump']} N bump", "covered", {**day, "bump": None})
    for i, o in enumerate(mission["site"]):
        test(SC.describe([SC.fill({"ops": [o]})[0]]), "covered",
             site=[x for j, x in enumerate(mission["site"]) if j != i])
    if day.get("cargo_kg"):
        test(f"{day['cargo_kg']} kg cargo", "excluded" if "cargo_kg" in exclusions else "covered", {**day, "cargo_kg": 0})
    if "speed" in exclusions:
        test(f"speed override {day['speed']} m/s -> quoted {quoted_speed}", "excluded", {**day, "speed": quoted_speed})
    if "motor" in exclusions:
        test(f"motor at {day['motor'] * 100:.0f}% -> serviced", "excluded", {**day, "motor": 1.0})

    covered_causes = [t["remove"] for t in tests if t["saved"] and t["kind"] == "covered"]
    excluded_causes = [t["remove"] for t in tests if t["saved"] and t["kind"] == "excluded"]
    if excluded_causes:
        decision, reason = "DENIED", "the failure goes away only when an excluded condition is removed: " + "; ".join(excluded_causes)
    elif covered_causes:
        decision, reason = "APPROVED", "caused by covered conditions: " + "; ".join(covered_causes)
    elif not exclusions:
        decision, reason = "APPROVED", "no single condition explains it; the combination is all covered conditions"
    else:
        decision, reason = "DENIED", "combined failure involving excluded conditions"
    payout = float(policy["cover"]) if decision == "APPROVED" else 0.0
    note = adjuster_note(incident, tests, decision, reason)
    return {"decision": decision, "reason": reason, "payout": payout, "tests": tests, "note": note,
            "exclusions_present": exclusions}


NOTE_PROMPT = """You are an insurance claims adjuster for delivery robots. Write a 3-sentence plain-English note for the
robot operator. Facts (from a physics replay; do not invent others):
incident: {outcome} at t={t}s, x={x} m. conditions: {desc}.
counterfactual replays (same seed, one condition removed): {tests}
decision (already made by the rules, do not change it): {decision} because {reason}."""


def adjuster_note(incident, tests, decision, reason) -> dict:
    facts = dict(outcome=incident["outcome"], t=incident["t"], x=incident["x"], desc=incident["describe"],
                 tests="; ".join(f"without {t['remove']}: {t['outcome']}" for t in tests), decision=decision, reason=reason)
    if llm.live():
        try:
            return {"text": llm.text(NOTE_PROMPT.format(**facts)), "engine": llm.LAST["model"]}
        except Exception as e:
            pass
    saved = [t["remove"] for t in tests if t["saved"]]
    text = (f"The robot {incident['outcome'].replace('_', ' ')} {incident['t']} s into the run, {incident['x']} m along the route. "
            f"We replayed the exact run with one condition removed at a time; "
            + (f"it delivers without {', '.join(saved)}. " if saved else "no single change saved it. ")
            + f"Decision: {decision.lower()} ({reason}).")
    return {"text": text, "engine": "template"}
