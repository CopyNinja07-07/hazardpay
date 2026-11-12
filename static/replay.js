// 3D replay of a MuJoCo rollout, with "Bolt" the delivery robot as a small animated character.
// Physics sets the body pose; a nested rig adds character motion (breathing, hop, shake) on top.
window.Replay = (function () {
  const C = { cyan: 0x4fe3d1, amber: 0xffb547, red: 0xff4d6a, green: 0x3ddc91 };

  function make(el) {
    const W = el.clientWidth, H = el.clientHeight;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    renderer.setSize(W, H);
    renderer.shadowMap.enabled = true;
    el.prepend(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0c1119);
    scene.fog = new THREE.Fog(0x0c1119, 14, 32);
    const cam = new THREE.PerspectiveCamera(42, W / H, 0.05, 100);
    cam.up.set(0, 0, 1); cam.position.set(-2.6, -5.6, 3.0);
    const ctl = new THREE.OrbitControls(cam, renderer.domElement);
    ctl.target.set(3.5, 0, 0.2); ctl.update();
    scene.add(new THREE.HemisphereLight(0xdfe9ff, 0x1a1f2a, 0.95));
    const sun = new THREE.DirectionalLight(0xffffff, 0.85); sun.position.set(3, -6, 9); sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024); Object.assign(sun.shadow.camera, { left: -8, right: 12, top: 8, bottom: -8 });
    scene.add(sun);
    const world = new THREE.Group(); scene.add(world);
    const robot = buildRobot(); scene.add(robot.group);
    const ghost = buildRobot(0xff8a3d); ghost.group.visible = false; scene.add(ghost.group);
    const st = { renderer, scene, cam, ctl, world, robot, ghost, gframes: [], gi: 0, frames: [], i: 0, playing: false, follow: true, el,
                 mood: "idle", moodT: 0, shake: 0, hop: 0, shimmer: 0, time: 0, hazards: [], speed: 1 };
    let last = performance.now();
    function loop(now) {
      requestAnimationFrame(loop);
      now = now || performance.now();
      const dt = Math.min(0.1, (now - last) / 1000); last = now; st.time += dt;
      if (st.playing && st.frames.length) {
        st.clock = (st.clock || 0) + dt * st.speed;
        const t0 = st.frames[0][0];
        while (st.i < st.frames.length - 1 && st.frames[st.i + 1][0] - t0 <= st.clock) st.i++;
        const f = st.frames[st.i];
        pose(st, f);
        if (st.gframes.length) { while (st.gi < st.gframes.length - 1 && st.gframes[st.gi + 1][0] - t0 <= st.clock) st.gi++; poseG(st, st.gframes[st.gi]); }
        // worried when a hazard is just ahead
        if (st.mood === "idle" || st.mood === "driving" || st.mood === "worried") {
          const ahead = st.hazards.some(h => f[1] > h - 0.9 && f[1] < h + 0.6);
          setMood(st, ahead ? "worried" : "driving");
        }
        if (st.onFrame) st.onFrame(f);
        if (st.i >= st.frames.length - 1 && (!st.gframes.length || st.gi >= st.gframes.length - 1)) {
          st.playing = false;
          setMood(st, st.outcome === "delivered" ? "success" : "fail");
          st.onEnd && st.onEnd();
        }
      }
      animate(st, dt);
      ctl.update();
      if (st.shake > 0) { st.shake = Math.max(0, st.shake - dt); const a = st.shake * 0.12; cam.position.x += (Math.random() - .5) * a; cam.position.z += (Math.random() - .5) * a; }
      renderer.render(scene, cam);
    }
    loop();
    new ResizeObserver(() => { const w = el.clientWidth, h = el.clientHeight; renderer.setSize(w, h); cam.aspect = w / h; cam.updateProjectionMatrix(); }).observe(el);
    return st;
  }

  function mat(c, o = {}) { return new THREE.MeshStandardMaterial({ color: c, roughness: 0.85, metalness: 0.05, ...o }); }
  function glow(c) { return new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: 0.9 }); }
  function label(text, color = "#e9eef7", bg = "rgba(12,17,25,.82)", scale = 1) {
    const cv = document.createElement("canvas"); cv.width = 512; cv.height = 128;
    const g = cv.getContext("2d");
    g.font = "600 52px Inter, Arial"; const w = Math.min(500, g.measureText(text).width + 48);
    g.fillStyle = bg; g.beginPath(); g.roundRect((512 - w) / 2, 18, w, 92, 22); g.fill();
    g.fillStyle = color; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(text, 256, 66);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(cv), depthTest: false, transparent: true }));
    sp.scale.set(2.4 * scale, 0.6 * scale, 1); sp.renderOrder = 10;
    return sp;
  }

  function buildRobot(tint) {
    const g = new THREE.Group();     // physics pose
    const rig = new THREE.Group();   // character motion
    g.add(rig);
    const bodyMat = mat(tint || 0xeef0f4, { roughness: 0.5, emissive: 0x4fe3d1, emissiveIntensity: 0, transparent: !!tint, opacity: tint ? 0.55 : 1 });
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.72, 0.52, 0.40), bodyMat);
    body.castShadow = true; rig.add(body);
    const lid = new THREE.Mesh(new THREE.BoxGeometry(0.64, 0.44, 0.02), mat(0x2f7dff, { roughness: 0.4 }));
    lid.position.z = 0.21; rig.add(lid);
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.9), mat(0xff6a1a));
    pole.rotation.x = Math.PI / 2; pole.position.set(-0.31, 0.21, 0.65); rig.add(pole);
    const flagPivot = new THREE.Group(); flagPivot.position.set(-0.31, 0.21, 1.03); rig.add(flagPivot);
    const pennant = new THREE.Mesh(new THREE.PlaneGeometry(0.18, 0.1), mat(0xff6a1a, { side: THREE.DoubleSide }));
    pennant.position.set(0.09, 0, 0); pennant.rotation.x = Math.PI / 2; flagPivot.add(pennant);
    // face: two eyes on the front panel
    const face = new THREE.Group(); face.position.set(0.362, 0, 0.07); rig.add(face);
    const panel = new THREE.Mesh(new THREE.BoxGeometry(0.01, 0.36, 0.14), mat(0x111722, { roughness: 0.3 })); face.add(panel);
    const eyes = [], xs = [];
    for (const y of [0.08, -0.08]) {
      const e = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.07, 0.07), glow(C.cyan)); e.position.set(0.006, y, 0); face.add(e); eyes.push(e);
      const x1 = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.09, 0.016), glow(C.red)); x1.rotation.x = Math.PI / 4;
      const x2 = x1.clone(); x2.rotation.x = -Math.PI / 4;
      const xg = new THREE.Group(); xg.add(x1, x2); xg.position.set(0.008, y, 0); xg.visible = false; face.add(xg); xs.push(xg);
    }
    const wheels = [];
    for (const ax of [0.27, 0, -0.27]) for (const sy of [0.31, -0.31]) {
      const w = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.11, 0.08, 20), mat(0x121316));
      w.position.set(ax, sy, -0.18); w.castShadow = true; g.add(w); wheels.push(w);
      const hub = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.085, 0.02), mat(0x4a4f5a)); w.add(hub);
    }
    const cargo = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.28, 0.16), mat(0xf29a3a));
    cargo.position.z = 0.3; cargo.visible = false; rig.add(cargo);
    const bang = label("!", "#1a1205", "#ffb547", 0.6); bang.position.set(0, 0, 0.95); bang.visible = false; rig.add(bang);
    const badge = label("v1", "#06221d", "#4fe3d1", 0.55); badge.position.set(0.1, 0, 0.62); rig.add(badge);
    return { group: g, rig, body, bodyMat, flagPivot, eyes, xs, wheels, cargo, bang, badge };
  }

  function setMood(st, m) {
    if (st.mood === m) return;
    st.mood = m; st.moodT = 0;
    const r = st.robot;
    const col = { idle: C.cyan, driving: C.cyan, worried: C.amber, fail: C.red, success: C.green }[m] || C.cyan;
    r.eyes.forEach(e => { e.material.color.setHex(col); e.material.emissive.setHex(col); e.visible = m !== "fail"; });
    r.xs.forEach(x => x.visible = m === "fail");
    r.bang.visible = m === "worried";
    if (m === "fail") st.shake = 0.35;
    if (m === "success") st.hop = 0.5;
  }

  function animate(st, dt) {
    const r = st.robot, t = st.time;
    st.moodT += dt;
    // breathing + flag
    const breathe = 1 + 0.012 * Math.sin(t * Math.PI);
    r.rig.scale.set(1, 1, breathe);
    const moving = st.playing;
    r.flagPivot.rotation.z = moving ? -0.5 + 0.15 * Math.sin(t * 14) : 0.1 * Math.sin(t * 2.2);
    // eyes: blink every ~3.5 s, narrow when worried, squint up when happy
    const blink = (t % 3.5) < 0.12 ? 0.15 : 1;
    r.eyes.forEach(e => {
      const sy = st.mood === "worried" ? 0.45 : st.mood === "success" ? 0.35 : 1;
      e.scale.set(1, 1, sy * blink);
      e.position.z = st.mood === "success" ? 0.02 : 0;
    });
    if (st.mood === "fail" && st.moodT < 0.8) r.xs.forEach(x => x.visible = Math.floor(st.moodT * 8) % 2 === 0);
    if (st.mood === "fail" && st.moodT >= 0.8) r.xs.forEach(x => x.visible = true);
    r.bang.position.z = 0.95 + 0.04 * Math.sin(t * 9);
    // hop
    if (st.hop > 0) { st.hop = Math.max(0, st.hop - dt); r.rig.position.z = 0.06 * Math.sin((0.5 - st.hop) / 0.5 * Math.PI); } else r.rig.position.z = moving ? 0.004 * Math.sin(t * 30) : 0;
    // retrain shimmer
    if (st.shimmer > 0) { st.shimmer = Math.max(0, st.shimmer - dt); r.bodyMat.emissiveIntensity = 0.6 * Math.sin(st.shimmer / 1.6 * Math.PI); } else r.bodyMat.emissiveIntensity = 0;
  }

  function setScene(st, items, opts = {}) {
    st.world.clear(); st.hazards = [];
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(40, 3), mat(0x3c414c)); ground.position.set(9, 0, 0); ground.receiveShadow = true; st.world.add(ground);
    const road = new THREE.Mesh(new THREE.PlaneGeometry(40, 8), mat(0x15181e)); road.position.set(9, -5.5, -0.005); st.world.add(road);
    const road2 = road.clone(); road2.position.y = 5.5; st.world.add(road2);
    for (const y of [1.5, -1.5]) { const e = new THREE.Mesh(new THREE.BoxGeometry(40, 0.04, 0.02), mat(0xffd24a)); e.position.set(9, y, 0.01); st.world.add(e); }
    const roadLbl = label("road", "#8e9bb1", "rgba(12,17,25,.6)", 0.7); roadLbl.position.set(2, -2.6, 0.1); st.world.add(roadLbl);
    const gx = opts.goal || 7;
    const goal = new THREE.Mesh(new THREE.BoxGeometry(0.06, 3, 0.02), glow(C.green)); goal.position.set(gx, 0, 0.02); st.world.add(goal);
    const gl = label("drop-off", "#06221d", "#3ddc91", 0.8); gl.position.set(gx, 1.1, 0.7); st.world.add(gl);
    const col = { ice: 0xbfe9ff, wet: 0x3c5a80, leaves: 0x9a6a2a };
    const name = { ice: "ice", wet: "wet", leaves: "wet leaves" };
    for (const s of items || []) {
      let lx = null, ltxt = "";
      if (s.kind === "patch") {
        const m = new THREE.Mesh(new THREE.BoxGeometry(s.x1 - s.x0, 2.4, 0.004), mat(col[s.name] || 0x667, { transparent: true, opacity: s.name === "ice" ? 0.85 : 0.75, roughness: s.name === "ice" ? 0.1 : 0.6, metalness: s.name === "ice" ? 0.3 : 0 }));
        m.position.set((s.x0 + s.x1) / 2, 0, 0.003); st.world.add(m);
        if (s.x1 - s.x0 < 5.5) { lx = (s.x0 + s.x1) / 2; ltxt = name[s.name] || s.name; }
      } else if (s.kind === "block") {
        const len = Math.min(s.x1, 25) - s.x0;
        const m = new THREE.Mesh(new THREE.BoxGeometry(len, 3.2, s.h), mat(0x8b8f99)); m.position.set(s.x0 + len / 2, 0, s.h / 2); m.castShadow = m.receiveShadow = true; st.world.add(m);
        lx = s.x0; ltxt = `${Math.round(s.h * 100)} cm curb`;
      } else if (s.kind === "ramp") {
        const a = s.angle * Math.PI / 180;
        const m = new THREE.Mesh(new THREE.BoxGeometry(s.len, 3.2, 0.1), mat(s.mu < 0.5 ? 0x5a7a9a : 0x7d828c)); m.position.set(s.x0 + s.len / 2 * Math.cos(a), 0, s.len / 2 * Math.sin(a) - 0.05); m.rotation.y = -a; m.receiveShadow = true; st.world.add(m);
        const top = new THREE.Mesh(new THREE.BoxGeometry(3, 3.2, s.top), mat(0x7d828c)); top.position.set(s.x0 + s.len * Math.cos(a) + 1.5, 0, s.top / 2); st.world.add(top);
        lx = s.x0 + s.len / 2; ltxt = `${Math.round(s.angle)}° ramp`;
      } else if (s.kind === "cross") {
        const n = Math.max(1, Math.round((s.x1 - s.x0) / 0.2));
        for (let k = 0; k < n; k++) {
          const xm = s.x0 + (k + 0.5) * (s.x1 - s.x0) / n;
          const ri = Math.max(0, Math.min(1, (xm - s.x0) / 1, (s.x1 - xm) / 1));
          const m = new THREE.Mesh(new THREE.BoxGeometry((s.x1 - s.x0) / n + 0.002, 3.2, 0.04), mat(s.mu < 0.3 ? 0xa9d8f2 : 0x6f7480)); m.position.set(xm, 0, -0.02); m.rotation.x = s.roll * ri * Math.PI / 180; m.receiveShadow = true; st.world.add(m);
        }
        lx = (s.x0 + s.x1) / 2; ltxt = `${Math.round(s.roll)}° sloped driveway`;
      }
      if (lx !== null) { const l = label(ltxt, "#1a1205", "#ffd7a8", 0.75); l.position.set(lx, 1.15, 0.55); st.world.add(l); st.hazards.push(lx); }
    }
    st.robot.cargo.visible = !!opts.cargo;
  }

  function pose(st, f) {
    const [t, x, y, z, qw, qx, qy, qz, wa] = f;
    st.robot.group.position.set(x, y, z);
    st.robot.group.quaternion.set(qx, qy, qz, qw);
    for (const w of st.robot.wheels) w.rotation.y = wa;
    if (st.follow) st.ctl.target.lerp(new THREE.Vector3(x + 0.6, y, 0.2), 0.08);
  }

  function poseG(st, f) {
    const [t, x, y, z, qw, qx, qy, qz, wa] = f;
    st.ghost.group.position.set(x, y + st.goff, z);
    st.ghost.group.quaternion.set(qx, qy, qz, qw);
    for (const w of st.ghost.wheels) w.rotation.y = wa;
  }
  function play(st, frames, scene, opts = {}) {
    st.gframes = opts.ghost || []; st.gi = 0; st.goff = opts.ghostOffset || 0;
    st.ghost.group.visible = !!st.gframes.length;
    if (st.gframes.length) { st.ghost.rig.remove(st.ghost.badge); st.ghost.badge = label(opts.ghostLabel || "v1", "#1a0c04", "#ff8a3d", 0.55); st.ghost.badge.position.set(0.1, 0, 0.62); st.ghost.rig.add(st.ghost.badge); poseG(st, st.gframes[0]); }
    setScene(st, scene, opts);
    st.frames = frames || []; st.i = 0; st.clock = 0; st.playing = true; st.outcome = opts.outcome || "delivered";
    st.onEnd = opts.onEnd || null; st.onFrame = opts.onFrame || null; st.speed = opts.speed || 1;
    setMood(st, "driving");
    if (st.frames.length) pose(st, st.frames[0]);
  }
  function version(st, v) { st.robot.rig.remove(st.robot.badge); st.robot.badge = label(v, "#06221d", "#4fe3d1", 0.55); st.robot.badge.position.set(0.1, 0, 0.62); st.robot.rig.add(st.robot.badge); st.shimmer = 1.6; }
  function camTo(st, pos, target, secs = 2) {
    const p0 = st.cam.position.clone(), t0 = st.ctl.target.clone(), P = new THREE.Vector3(...pos), T = new THREE.Vector3(...target);
    const start = performance.now();
    st.follow = false;
    return new Promise(res => {
      const iv = setInterval(() => {
        const k = Math.min(1, (performance.now() - start) / (secs * 1000)); const e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        st.cam.position.lerpVectors(p0, P, e); st.ctl.target.lerpVectors(t0, T, e);
        if (k >= 1) { clearInterval(iv); st.follow = true; res(); }
      }, 16);
    });
  }
  return { make, play, setScene, setMood, version, camTo };
})();
