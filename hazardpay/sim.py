"""Rollouts: drive the robot through a site and report what physically happened.

A failure comes from the simulator, never from a model's opinion:
  tipped         the body's up-axis leans past 55 degrees
  off_sidewalk   the robot leaves the 3 m sidewalk (|y| > 1.5 m)
  stuck          less than 0.15 m of progress in 3 s
  timeout        didn't reach the drop-off in time
"""
import math
from dataclasses import replace

import mujoco
import numpy as np

from .world import WHEEL_R, Site, mjcf

CTRL_DT = 0.02
DEFAULT_CTRL = {"speed_scale": 1.0, "k_heading": 2.0, "tilt_brake": 0.0, "slip_ctrl": 0.0, "stall_boost": 0.0}
CTRL_BOUNDS = {"speed_scale": (0.6, 1.05), "k_heading": (0.5, 5.0), "tilt_brake": (0.0, 6.0),
               "slip_ctrl": (0.0, 1.0), "stall_boost": (0.0, 2.0)}

_cache: dict[str, tuple] = {}


def _model(site: Site):
    xml, scene = mjcf(site)
    if xml not in _cache:
        if len(_cache) > 64:
            _cache.clear()
        m = mujoco.MjModel.from_xml_string(xml)
        _cache[xml] = (m, scene)
    return _cache[xml]


def _yaw_tilt(q):
    w, x, y, z = q
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    upz = 1 - 2 * (x * x + y * y)  # z component of body z-axis
    pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
    return yaw, upz, pitch


def rollout(site: Site, ctrl: dict | None = None, seed: int = 0, record: bool = False) -> dict:
    rng = np.random.default_rng(seed)
    ctrl = {**DEFAULT_CTRL, **(ctrl or {})}
    m, scene = _model(site)
    m = m.__copy__() if hasattr(m, "__copy__") else m
    d = mujoco.MjData(m)
    # per-seed realism: friction +-10%, mass +-5%, start yaw jitter
    fr = m.geom_friction.copy()
    m.geom_friction[:, 0] = fr[:, 0] * rng.uniform(0.9, 1.1, size=fr.shape[0])
    body = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "robot")
    mass0 = m.body_mass[body]
    m.body_mass[body] = mass0 * rng.uniform(0.95, 1.05)
    yaw0 = rng.normal(0, 0.02)
    d.qpos[3:7] = [math.cos(yaw0 / 2), 0, 0, math.sin(yaw0 / 2)]
    mujoco.mj_forward(m, d)

    steps_per_ctrl = int(round(CTRL_DT / m.opt.timestep))
    T = site.goal_x / max(0.3, site.speed * ctrl["speed_scale"]) * 2.2 + 4
    pushes = [(t0 + rng.uniform(-0.1, 0.1), dur, f, a) for (t0, dur, f, a) in site.pushes]
    buf = []
    frames, outcome, cause_t = [], "delivered", None
    hist = []
    t = 0.0
    nwheels = m.nu
    while t < T:
        x, y, z = d.qpos[0:3]
        yaw, upz, pitch = _yaw_tilt(d.qpos[3:7])
        vfwd = d.qvel[0] * math.cos(yaw) + d.qvel[1] * math.sin(yaw)
        wheel_v = float(np.mean(d.qvel[7:7 + nwheels])) * WHEEL_R
        obs = (yaw + site.yaw_bias + rng.normal(0, site.heading_noise), upz, pitch, vfwd, wheel_v)
        buf.append(obs)
        o = buf[max(0, len(buf) - 1 - site.latency_steps)]
        # --- controller ---
        v = site.speed * ctrl["speed_scale"]
        tilt = math.acos(max(-1.0, min(1.0, o[1])))
        if tilt > 0.12:
            v *= max(0.15, 1 - ctrl["tilt_brake"] * (tilt - 0.12))
        slip = o[4] - o[3]
        if slip > 0.25:
            v *= max(0.3, 1 - ctrl["slip_ctrl"] * (slip - 0.25) * 2)
        if o[3] < 0.15 * v and t > 1.0:
            v *= 1 + ctrl["stall_boost"]
        turn = -ctrl["k_heading"] * o[0]
        wl = (v - turn * 0.31) / WHEEL_R
        wr = (v + turn * 0.31) / WHEEL_R
        for i in range(nwheels):
            d.ctrl[i] = wl if i % 2 == 0 else wr
        # --- disturbances ---
        d.xfrc_applied[body, :] = 0
        for (t0, dur, f, a) in pushes:
            if t0 <= t < t0 + dur:
                ang = math.radians(a)
                d.xfrc_applied[body, 0] += f * math.cos(ang) * 0  # pushes are lateral/vertical-free
                d.xfrc_applied[body, 1] += -f * math.sin(ang)
                d.xfrc_applied[body, 0] += f * math.cos(ang)
        for _ in range(steps_per_ctrl):
            mujoco.mj_step(m, d)
        t += CTRL_DT
        if record and int(round(t / CTRL_DT)) % 2 == 0:
            frames.append([round(t, 3), *[round(float(v), 4) for v in d.qpos[0:7]],
                           round(float(np.mean(d.qpos[7:7 + nwheels])), 3)])
        hist.append((t, d.qpos[0]))
        if upz < math.cos(math.radians(55)):
            outcome = "tipped"
        elif abs(d.qpos[1]) > 1.5:
            outcome = "off_sidewalk"
        elif t > 3.0 and d.qpos[0] < site.goal_x and d.qpos[0] - hist[max(0, len(hist) - 150)][1] < 0.15:
            outcome = "stuck"
        elif d.qpos[0] >= site.goal_x:
            outcome = "delivered"
            break
        if outcome != "delivered":
            cause_t = t
            break
    else:
        outcome = "timeout"
        cause_t = t
    m.geom_friction[:] = fr
    m.body_mass[body] = mass0
    res = {"outcome": outcome, "failed": outcome != "delivered", "t": round(t, 2), "x": round(float(d.qpos[0]), 3),
           "t_fail": cause_t}
    if record:
        res["frames"] = frames
        res["scene"] = scene
    return res


def batch(site: Site, ctrl: dict | None = None, seeds=range(16)) -> dict:
    rs = [rollout(site, ctrl, s) for s in seeds]
    fails = [r for r in rs if r["failed"]]
    modes = {}
    for r in fails:
        modes[r["outcome"]] = modes.get(r["outcome"], 0) + 1
    ok = [r for r in rs if not r["failed"]]
    return {"n": len(rs), "fails": len(fails), "rate": len(fails) / max(1, len(rs)), "modes": modes,
            "mean_time": round(float(np.mean([r["t"] for r in ok])), 2) if ok else None}
