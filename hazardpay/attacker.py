"""The adversary's mind: Gemini forms hypotheses about why this robot will fail this mission.

Each round it sees the hazard language with realistic ranges, the mission's
route, and every program tried so far with its confirmed result. It answers
with new programs (ranges allowed); invalid ones go back once with the
validation errors. Without a key, a library of hand-written hypotheses runs
instead, and the UI says so.
"""
import json

from . import llm
from . import scenario as SC

SYSTEM = """You are the adversary for a robot insurer. Your job is to find the most PLAUSIBLE physical conditions under
which a six-wheel sidewalk delivery robot fails a specific mission, so the insurer can price the risk and the operator
can fix it.

Robot: 22 kg body 0.72 x 0.52 x 0.40 m, six 0.11 m wheels on rigid axles, velocity-controlled motors with a torque
limit, heading hold from an IMU, cruise 1.2 m/s, cargo bay on top (rated 10 kg). Route: straight along +x for 7 m.
Failure = tipped (>55 deg), off_sidewalk (|y| > 1.5 m, slides into the road), stuck (<0.15 m progress in 3 s), timeout.

How to attack well:
- Form a specific HYPOTHESIS about a weakness (e.g. "heading hold can't fight a sideways slide on a tilted icy apron"),
  then write the SMALLEST program that tests it. Use ranges [lo, hi] for values you are unsure of; an optimizer
  searches them and shrinks the failure to its minimal form.
- Prefer realistic conditions: wet leaves and a 6 cm curb teach more than black ice plus a 200 N kick.
- Combine hazards in space and time: a bump while on the apron, a curb right after a slick patch, cold motors and cargo.
- Do not repeat programs that failed to break the robot.

Hazard ops and realistic ranges:
{ops}

Answer with JSON only: {{"programs": [{{"name": "...", "hypothesis": "...", "ops": [...]}}, ...]}}"""

LIBRARY = [
    {"name": "icy apron slide", "hypothesis": "heading hold can't stop a sideways slide when a driveway apron tilts on ice",
     "ops": [{"op": "cross_slope", "start": 2.5, "length": 3.0, "roll": [3, 12], "mu": [0.08, 0.4]}]},
    {"name": "bump on the apron", "hypothesis": "a pedestrian bump on a tilted section pushes it over the edge",
     "ops": [{"op": "cross_slope", "start": 2.0, "length": 3.0, "roll": [4, 10], "mu": [0.2, 0.9]},
             {"op": "shove", "t": [2.0, 3.5], "dur": 0.4, "force": [30, 140]}]},
    {"name": "slick before the curb", "hypothesis": "wheels lose grip just before the curb, so it can't climb it",
     "ops": [{"op": "wet", "start": 1.5, "length": 2.0, "mu": [0.25, 0.5]}, {"op": "curb", "at": 3.6, "height": [0.03, 0.1]}]},
    {"name": "cold motors and cargo", "hypothesis": "winter battery sag plus cargo leaves too little torque for a curb",
     "ops": [{"op": "motor", "strength": [0.5, 0.95]}, {"op": "payload", "mass": [2, 10], "dz": 0.1},
             {"op": "curb", "at": 3.0, "height": [0.03, 0.08]}]},
    {"name": "leafy ramp", "hypothesis": "wet leaves on an accessible ramp make the wheels spin out",
     "ops": [{"op": "ramp", "at": 2.0, "length": 2.5, "angle": [3, 10], "mu": [0.1, 0.6]}]},
    {"name": "drifting compass", "hypothesis": "an IMU bias walks it off a slick sidewalk",
     "ops": [{"op": "heading_bias", "deg": [0, 12]}, {"op": "wet", "start": 1.0, "length": 5.0, "mu": [0.25, 0.45]}]},
]


def _ops_doc() -> str:
    lines = []
    for name, spec in SC.OPS.items():
        ps = ", ".join(f"{k} [{v[3]}] {v[0]}..{v[1]}" + (f" ({v[4]})" if v[4] else "") for k, v in spec.items())
        lines.append(f"- {name}: {ps}")
    return "\n".join(lines)


def propose(mission: dict, history: list[dict], n: int = 3, offset: int = 0, library: bool = False) -> tuple[list[dict], str]:
    if llm.live() and not library:
        try:
            prompt = (f"Mission: {mission.get('description', '')}\nDeclared route hazards: {json.dumps(mission['site'])}\n"
                      f"Weather odds: {json.dumps(mission.get('weather', {}))}; cargo {mission.get('cargo_kg', 0)} kg.\n"
                      f"Tried so far (confirmed fail rate on fresh seeds): {json.dumps(history[-10:])}\n"
                      f"Write {n} new programs.")
            out = llm.json_call(prompt, 0.9, system=SYSTEM.format(ops=_ops_doc()))
            progs = out.get("programs", [])[:n]
            good, bad = [], []
            for p in progs:
                (bad if SC.validate(p) else good).append(p)
            if bad:  # one repair round
                fix = llm.json_call("Fix these programs. Errors: " + json.dumps(
                    [{"program": p, "errors": SC.validate(p)} for p in bad]) + ' Answer {"programs": [...]}', 0.2,
                    system=SYSTEM.format(ops=_ops_doc()))
                good += [p for p in fix.get("programs", []) if not SC.validate(p)]
            if good:
                return good[:n], llm.LAST["model"]
        except Exception:
            pass
    k = len(LIBRARY)
    return [LIBRARY[(offset + i) % k] for i in range(n)], ("hypothesis library (Gemini busy)" if llm.live() and not library else "hypothesis library")


SITE_PROMPT = """Turn this delivery site into the robot's route hazards. Route is straight along +x for 7 m from the robot.
Only include hazards you can see or that are described. Return ONLY JSON:
{{"name": "short site name", "description": "one line", "site": [<ops with FIXED numbers>],
"weather": {{"dry": p, "wet": p, "ice": p}}, "cargo_kg": number, "bump_prob": 0-1 (pedestrian traffic)}}
Allowed site ops: curb, ramp, cross_slope, ice, wet, leaves (ranges below).
{ops}
Site: {text}"""


def site_from(text: str, image_b64: str | None = None) -> tuple[dict | None, str]:
    """Photo or description -> a mission. Gemini Vision when available, else None (UI uses presets)."""
    if not llm.live():
        return None, "no Gemini key"
    out = llm.json_call(SITE_PROMPT.format(ops=_ops_doc(), text=text or "(see photo)"), 0.2, image_b64=image_b64,
                        model=llm.VISION_MODEL if image_b64 else None)
    site = [o for o in out.get("site", []) if not SC.validate({"ops": [o]}) and o.get("op") in
            ("curb", "ramp", "cross_slope", "ice", "wet", "leaves")]
    m = {"name": out.get("name", "Custom site"), "description": out.get("description", text),
         "site": [SC.fill({"ops": [o]})[0] for o in site], "weather": out.get("weather") or {"dry": 0.7, "wet": 0.3},
         "cargo_kg": float(out.get("cargo_kg") or 4), "bump_prob": float(out.get("bump_prob") or 0.15), "cover": 300, "speed": 1.2}
    return m, llm.LAST["model"]
