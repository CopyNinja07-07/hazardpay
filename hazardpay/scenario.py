"""Hazard programs: the JSON language the attacker writes, compiled to a Site.

A program is a hypothesis plus ops. Every number is fixed or a range [lo, hi]
the optimizer searches. Programs are validated data, never executed.

    {"name": "ice on the driveway apron",
     "hypothesis": "the heading loop can't hold the line when the apron tilts on ice",
     "ops": [{"op": "cross_slope", "start": 2.5, "length": 3, "roll": [4, 12], "mu": [0.08, 0.3]},
             {"op": "payload", "mass": 6}]}
"""
import random

from .world import GOAL_X, Site

# op -> {param: (lo, hi, nominal, unit, doc)}; nominal = the harmless value, used for shrinking
OPS = {
    "ice":         {"start": (0.5, 6.0, 3.0, "m", "where the patch begins"), "length": (0.3, 4.0, 0.0, "m", "patch length"),
                    "mu": (0.05, 0.2, 1.0, "", "black ice 0.05-0.1, packed snow 0.15-0.2")},
    "wet":         {"start": (0.5, 6.0, 3.0, "m", ""), "length": (0.5, 5.0, 0.0, "m", ""),
                    "mu": (0.25, 0.5, 1.0, "", "wet tile 0.25-0.4, wet asphalt 0.5")},
    "leaves":      {"start": (0.5, 6.0, 3.0, "m", ""), "length": (0.5, 4.0, 0.0, "m", ""),
                    "mu": (0.3, 0.5, 1.0, "", "wet leaves 0.3-0.45")},
    "curb":        {"at": (1.0, 6.0, 3.0, "m", ""), "height": (0.02, 0.16, 0.0, "m", "kerbs are 0.05-0.15 m; dropped kerbs 0.02-0.04")},
    "ramp":        {"at": (1.0, 5.0, 2.0, "m", ""), "length": (1.0, 3.0, 2.0, "m", ""),
                    "angle": (2.0, 15.0, 0.0, "deg", "ADA ramps max 4.8 deg; driveways up to 15"),
                    "mu": (0.08, 1.0, 1.0, "", "surface grip on the ramp")},
    "cross_slope": {"start": (1.0, 5.0, 2.5, "m", ""), "length": (2.0, 4.0, 3.0, "m", ""),
                    "roll": (1.0, 16.0, 0.0, "deg", "sidewalk cross-slope 2 deg; driveway aprons 6-12"),
                    "mu": (0.08, 1.0, 1.0, "", "grip on the apron")},
    "payload":     {"mass": (0.0, 12.0, 0.0, "kg", "cargo; rated 10 kg"), "dz": (0.0, 0.25, 0.0, "m", "how high it sits")},
    "shove":       {"t": (0.5, 5.0, 2.0, "s", ""), "dur": (0.1, 0.8, 0.0, "s", ""),
                    "force": (0.0, 200.0, 0.0, "N", "a pedestrian bump 50-120 N, a kick 150-200 N"),
                    "angle": (0.0, 180.0, 90.0, "deg", "90 = from the right, 0 = from behind")},
    "motor":       {"strength": (0.4, 1.0, 1.0, "", "cold batteries / wear: 0.6-0.9")},
    "latency":     {"ms": (0.0, 100.0, 0.0, "ms", "control delay")},
    "imu_noise":   {"deg": (0.0, 6.0, 0.0, "deg", "heading noise std")},
    "heading_bias": {"deg": (-15.0, 15.0, 0.0, "deg", "compass/IMU misalignment")},
}


def validate(program: dict) -> list[str]:
    errs = []
    ops = program.get("ops")
    if not isinstance(ops, list) or not ops:
        return ["program needs a non-empty 'ops' list"]
    for i, o in enumerate(ops):
        spec = OPS.get(o.get("op"))
        if not spec:
            errs.append(f"ops[{i}]: unknown op {o.get('op')!r}; use one of {sorted(OPS)}")
            continue
        for k, v in o.items():
            if k == "op":
                continue
            if k not in spec:
                errs.append(f"ops[{i}].{k}: not a parameter of {o['op']} ({sorted(spec)})")
                continue
            lo, hi = spec[k][0], spec[k][1]
            vals = v if isinstance(v, list) else [v]
            if len(vals) not in (1, 2) or not all(isinstance(x, (int, float)) for x in vals):
                errs.append(f"ops[{i}].{k}: must be a number or [lo, hi]")
                continue
            if any(x < lo - 1e-9 or x > hi + 1e-9 for x in vals):
                errs.append(f"ops[{i}].{k}={v} outside the realistic range {lo}..{hi}")
    return errs


def free_params(program: dict) -> list[tuple[int, str, float, float]]:
    """(op index, param, lo, hi) for every [lo, hi] range in the program."""
    out = []
    for i, o in enumerate(program["ops"]):
        for k, v in o.items():
            if isinstance(v, list) and len(v) == 2:
                out.append((i, k, float(v[0]), float(v[1])))
    return out


def fill(program: dict, x: list[float] | None = None) -> list[dict]:
    """Concrete ops: free params set from x in [0,1]^k (midpoint when x is None)."""
    fp = free_params(program)
    ops = [dict(o) for o in program["ops"]]
    for j, (i, k, lo, hi) in enumerate(fp):
        u = 0.5 if x is None else min(1.0, max(0.0, x[j]))
        ops[i][k] = lo + u * (hi - lo)
    for o in ops:  # unset params: middle of the realistic range (a shove comes from the right)
        for k, spec in OPS[o["op"]].items():
            o.setdefault(k, 90.0 if (o["op"], k) == ("shove", "angle") else (spec[0] + spec[1]) / 2)
    return ops


def compile_ops(ops: list[dict], speed: float = 1.2, goal_x: float = GOAL_X) -> Site:
    s = Site(surfaces=[], blocks=[], ramps=[], cross=[], speed=speed, goal_x=goal_x)
    pushes = []
    for o in ops:
        k = o["op"]
        if k in ("ice", "wet", "leaves"):
            s.surfaces.append((o["start"], o["start"] + o["length"], o["mu"], k))
        elif k == "curb":
            s.blocks.append((o["at"], 30.0, o["height"], "curb"))
        elif k == "ramp":
            s.ramps.append((o["at"], o["length"], o["angle"], "ramp", o["mu"]))
        elif k == "cross_slope":
            s.cross = list(s.cross) + [(o["start"], o["start"] + o["length"], o["roll"], o["mu"], "apron")]
        elif k == "payload":
            s.payload_kg, s.payload_dz = o["mass"], o["dz"]
        elif k == "shove":
            pushes.append((o["t"], o["dur"], o["force"], o["angle"]))
        elif k == "motor":
            s.motor = o["strength"]
        elif k == "latency":
            s.latency_steps = int(round(o["ms"] / 20))
        elif k == "imu_noise":
            s.heading_noise = o["deg"] * 3.14159 / 180
        elif k == "heading_bias":
            s.yaw_bias = o["deg"] * 3.14159 / 180
    s.pushes = tuple(pushes)
    return s


def deviation(ops: list[dict]) -> float:
    """How far from harmless, summed over params, each normalised to its realistic range (0 = nominal)."""
    total = 0.0
    for o in ops:
        spec = OPS[o["op"]]
        for k in ("mu", "height", "angle", "roll", "mass", "force", "strength", "ms", "deg"):
            if k in spec and k in o and not (o["op"] == "shove" and k == "angle"):
                lo, hi, nom = spec[k][:3]
                total += abs(o[k] - nom) / (hi - lo)
    return round(total, 3)


def describe(ops: list[dict]) -> str:
    bits = []
    for o in ops:
        k = o["op"]
        if k in ("ice", "wet", "leaves"):
            bits.append(f"{k} (mu {o['mu']:.2f}) for {o['length']:.1f} m from {o['start']:.1f} m")
        elif k == "curb":
            bits.append(f"a {o['height'] * 100:.0f} cm curb at {o['at']:.1f} m")
        elif k == "ramp":
            bits.append(f"a {o['angle']:.0f} deg ramp (grip {o['mu']:.2f})")
        elif k == "cross_slope":
            bits.append(f"a {o['roll']:.0f} deg sideways tilt (grip {o['mu']:.2f})")
        elif k == "payload":
            bits.append(f"{o['mass']:.1f} kg of cargo")
        elif k == "shove":
            bits.append(f"a {o['force']:.0f} N shove at {o['t']:.1f} s")
        elif k == "motor":
            bits.append(f"motors at {o['strength'] * 100:.0f}%")
        elif k == "latency":
            bits.append(f"{o['ms']:.0f} ms control delay")
        elif k == "imu_noise":
            bits.append(f"{o['deg']:.1f} deg heading noise")
        elif k == "heading_bias":
            bits.append(f"{o['deg']:.1f} deg heading bias")
    return ", ".join(bits)


def random_program(rng: random.Random, n_ops: int = 2) -> dict:
    """A blind baseline attacker: random ops across their full ranges."""
    ops = []
    for name in rng.sample(sorted(OPS), n_ops):
        o = {"op": name}
        for k, (lo, hi, *_r) in OPS[name].items():
            o[k] = [lo, hi]
        ops.append(o)
    return {"name": "random", "hypothesis": "blind random search", "ops": ops}
