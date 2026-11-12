"""The physics twin: a six-wheel sidewalk delivery robot on a site built from hazards.

A site is a list of hazard ops (the attack language, see `scenario.py`) compiled
into a MuJoCo model. The robot drives along +x from x=0 to the drop-off point.

Robot: ~22 kg body (0.72 x 0.52 x 0.30 m), six 0.11 m wheels on rigid axles,
velocity-controlled wheel motors with a torque limit, cargo bay on top.
Contact friction in MuJoCo takes the max of the two geoms, so the wheels have
low friction and every surface carries its own (asphalt 1.0, wet 0.35, ice 0.08).
"""
from dataclasses import dataclass

import numpy as np

WHEEL_R = 0.11
BODY = (0.36, 0.26, 0.2)  # half sizes
AXLES_X = (0.27, 0.0, -0.27)
TRACK_Y = 0.31
GOAL_X = 7.0


@dataclass
class Site:
    """Everything a rollout needs: hazards as geometry + robot/disturbance settings."""
    surfaces: list          # (x0, x1, mu, name) friction patches on flat ground
    blocks: list            # (x0, x1, height, name) raised slabs: curbs, steps
    ramps: list             # (x0, length, angle_deg, name[, mu])
    cross: list = ()        # (x0, x1, roll_deg, mu, name) sidewalk tilted sideways (driveway apron)
    payload_kg: float = 0.0
    payload_dx: float = 0.0
    payload_dz: float = 0.0
    pushes: tuple = ()      # (t0, dur, force_N, angle_deg) angle 90 = from the right
    motor: float = 1.0      # fraction of rated wheel torque
    latency_steps: int = 0  # control delay, x 20 ms
    heading_noise: float = 0.0  # rad std on the IMU heading
    yaw_bias: float = 0.0   # rad, a misaligned path / sidewalk slant
    speed: float = 1.2      # mission cruise speed m/s
    goal_x: float = GOAL_X


def _box(name, pos, size, rgba, mu=1.0, euler=None):
    e = f' euler="{euler[0]} {euler[1]} {euler[2]}"' if euler else ""
    return (f'<geom name="{name}" type="box" pos="{pos[0]:.4f} {pos[1]:.4f} {pos[2]:.4f}" '
            f'size="{size[0]:.4f} {size[1]:.4f} {size[2]:.4f}"{e} rgba="{rgba}" friction="{mu:.3f} 0.01 0.001"/>')


def mjcf(site: Site) -> tuple[str, list[dict]]:
    """Return the MJCF xml and a plain list of static geometry for the 3D replay."""
    geoms, scene = [], []
    # ground: asphalt
    # ground is box segments (not a plane) so a cross-slope can dip below z=0 with nothing under it
    cuts = sorted((c[0], c[1]) for c in site.cross)
    edges, cur = [], -4.0
    for a, b in cuts:
        if a > cur:
            edges.append((cur, a))
        cur = max(cur, b)
    edges.append((cur, 30.0))
    for i, (a, b) in enumerate(edges):
        geoms.append(_box(f"ground{i}", ((a + b) / 2, 0, -0.1), ((b - a) / 2, 6, 0.1), "0.18 0.2 0.24 1", 1.0))
    colors = {"ice": "0.75 0.9 1 1", "wet": "0.25 0.35 0.5 1", "leaves": "0.55 0.38 0.15 1", "gravel": "0.5 0.48 0.44 1"}
    for i, (x0, x1, mu, name) in enumerate(site.surfaces):
        cx, hx = (x0 + x1) / 2, (x1 - x0) / 2
        c = colors.get(name, "0.4 0.4 0.5 1")
        geoms.append(_box(f"surf{i}", (cx, 0, 0.001), (hx, 1.2, 0.001), c, mu))
        scene.append({"kind": "patch", "name": name, "x0": x0, "x1": x1, "mu": mu})
    for i, (x0, x1, h, name) in enumerate(site.blocks):
        cx, hx = (x0 + x1) / 2, (x1 - x0) / 2
        geoms.append(_box(f"blk{i}", (cx, 0, h / 2), (hx, 1.6, h / 2), "0.55 0.56 0.6 1", 1.0))
        scene.append({"kind": "block", "name": name, "x0": x0, "x1": x1, "h": h})
    for i, r in enumerate(site.ramps):
        x0, L, ang, name = r[:4]
        rmu = r[4] if len(r) > 4 else 1.0
        a = np.radians(ang)
        cx, cz = x0 + L / 2 * np.cos(a), L / 2 * np.sin(a) - 0.05 * np.cos(a)
        geoms.append(_box(f"ramp{i}", (cx, 0, cz), (L / 2, 1.6, 0.05), "0.5 0.52 0.58 1", rmu, (0, -ang, 0)))
        top = L * np.sin(a)
        geoms.append(_box(f"rampTop{i}", (x0 + L * np.cos(a) + 1.5, 0, top / 2), (1.5, 1.6, top / 2), "0.5 0.52 0.58 1", rmu))
        scene.append({"kind": "ramp", "name": name, "x0": x0, "len": L, "angle": ang, "top": float(top), "mu": rmu})
    for i, (x0, x1, roll, cmu, name) in enumerate(site.cross):
        # twisted in 0.2 m slices: roll ramps in over 1 m and out over 1 m, so there's no lip
        n = max(1, int(round((x1 - x0) / 0.2)))
        for k in range(n):
            xa = x0 + k * (x1 - x0) / n
            xm = xa + (x1 - x0) / n / 2
            ramp_in = min(1.0, (xm - x0) / 1.0, (x1 - xm) / 1.0)
            r_k = roll * max(0.0, ramp_in)
            geoms.append(_box(f"cross{i}_{k}", (xm, 0, -0.02 / np.cos(np.radians(r_k))), ((x1 - x0) / n / 2 + 0.001, 1.6, 0.02),
                              "0.42 0.44 0.5 1", cmu, (r_k, 0, 0)))
        scene.append({"kind": "cross", "name": name, "x0": x0, "x1": x1, "roll": roll, "mu": cmu})
    z0 = 0.0

    bx, by, bz = BODY
    wheels, acts = [], []
    for ai, ax in enumerate(AXLES_X):
        for side, sy in (("L", TRACK_Y), ("R", -TRACK_Y)):
            n = f"w{ai}{side}"
            wheels.append(f'''
      <body name="{n}" pos="{ax} {sy} {-bz + 0.02}">
        <joint name="{n}" type="hinge" axis="0 1 0" damping="0.05"/>
        <geom type="cylinder" size="{WHEEL_R} 0.04" euler="90 0 0" mass="0.6" rgba="0.08 0.08 0.09 1"
              friction="0.05 0.01 0.001" condim="4"/>
      </body>''')
            acts.append(f'<velocity name="{n}" joint="{n}" kv="6" forcerange="{-4.5 * site.motor:.3f} {4.5 * site.motor:.3f}"/>')
    payload = ""
    if site.payload_kg > 0:
        payload = (f'<geom name="cargo" type="box" pos="{site.payload_dx:.3f} 0 {bz + 0.08 + site.payload_dz:.3f}" '
                   f'size="0.16 0.14 0.08" mass="{site.payload_kg:.3f}" rgba="0.95 0.6 0.2 1" contype="0" conaffinity="0"/>')
    z_start = z0 + WHEEL_R + bz - 0.02 + 0.01
    xml = f'''<mujoco model="hazardpay">
  <option timestep="0.004" integrator="implicitfast"/>
  <default><geom solref="0.004 1" solimp="0.9 0.95 0.001"/></default>
  <worldbody>
    {"".join(geoms)}
    <body name="robot" pos="0 0 {z_start:.4f}">
      <freejoint name="root"/>
      <geom name="chassis" type="box" size="{bx} {by} {bz}" mass="18" rgba="0.92 0.93 0.95 1" friction="0.6 0.01 0.001"/>
      <geom name="lid" type="box" pos="0 0 {bz + 0.01}" size="{bx - 0.04} {by - 0.04} 0.01" mass="1" rgba="0.15 0.45 0.95 1"/>
      <geom name="flag" type="capsule" fromto="{-bx + 0.05} {by - 0.05} {bz} {-bx + 0.05} {by - 0.05} {bz + 0.9}" size="0.006" mass="0.05" rgba="1 0.4 0.1 1"/>
      {payload}
      <site name="imu" pos="0 0 0"/>
      {"".join(wheels)}
    </body>
  </worldbody>
  <actuator>{"".join(acts)}</actuator>
</mujoco>'''
    return xml, scene
