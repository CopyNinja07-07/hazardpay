// Hazard Pay: the film. A timed, 3D, self-playing explainer built from real MuJoCo recordings (/api/film).
// Shots follow docs/STORYBOARD_V2.md. Open /static/film.html (add ?t=SECONDS to start mid-film while editing).
(async function () {
  const $ = s => document.querySelector(s);
  const DATA = await (await fetch("/api/film")).json();
  const canvas = $("#gl");
  const R = new THREE.WebGLRenderer({ canvas, antialias: true });
  R.setPixelRatio(Math.min(2, devicePixelRatio)); R.setSize(innerWidth, innerHeight);
  R.shadowMap.enabled = true; R.shadowMap.type = THREE.PCFSoftShadowMap; R.outputEncoding = THREE.sRGBEncoding; R.toneMapping = THREE.NoToneMapping;
  const S = new THREE.Scene(); S.background = new THREE.Color(0x020306); S.fog = new THREE.Fog(0x020306, 16, 60);
  const cam = new THREE.PerspectiveCamera(38, innerWidth / innerHeight, 0.03, 400); cam.up.set(0, 0, 1);
  addEventListener("resize", () => { R.setSize(innerWidth, innerHeight); cam.aspect = innerWidth / innerHeight; cam.updateProjectionMatrix(); });
  let composer = null;
  if (THREE.EffectComposer && THREE.UnrealBloomPass) {
    composer = new THREE.EffectComposer(R); composer.addPass(new THREE.RenderPass(S, cam));
    composer.addPass(new THREE.UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.45, 0.45, 0.9));
  }
  const hemi = new THREE.HemisphereLight(0xcfdcff, 0x0e121a, 0.55); S.add(hemi);
  const key = new THREE.DirectionalLight(0xffe9d2, 1.0); key.position.set(-4, -8, 10); key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048); Object.assign(key.shadow.camera, { left: -12, right: 16, top: 10, bottom: -10, far: 60 }); S.add(key);
  const rim = new THREE.PointLight(0x4fe3d1, 0.0, 30); rim.position.set(3, 4, 3); S.add(rim);
  const redLight = new THREE.PointLight(0xff3040, 0, 40); redLight.position.set(3, -4, 6); S.add(redLight);

  // ---------- helpers ----------
  const mat = (c, o = {}) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.8, metalness: 0.05, ...o });
  const glow = c => new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: 1.2 });
  const ease = k => k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
  const lerp = (a, b, k) => a + (b - a) * k;
  const V3 = (a) => new THREE.Vector3(...a);
  function label(text, fg = "#e9eef7", bg = "rgba(10,14,22,.9)", s = 1) {
    const cv = document.createElement("canvas"); cv.width = 1024; cv.height = 192; const g = cv.getContext("2d");
    g.font = "600 88px Inter, Arial"; const w = Math.min(1000, g.measureText(text).width + 80);
    g.fillStyle = bg; g.beginPath(); g.roundRect((1024 - w) / 2, 24, w, 144, 36); g.fill();
    g.fillStyle = fg; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(text, 512, 98);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(cv), depthTest: false, transparent: true }));
    sp.scale.set(2.4 * s, 0.45 * s, 1); sp.renderOrder = 20; return sp;
  }
  function overlay(id, html, on = true) { const e = $(id); if (html !== null && html !== undefined) e.innerHTML = html; e.style.opacity = on ? 1 : 0; }

  // ---------- Bolt ----------
  class Bolt {
    constructor(opts = {}) {
      const lite = !!opts.lite, tint = opts.tint;
      this.g = new THREE.Group(); this.rig = new THREE.Group(); this.g.add(this.rig);
      this.bodyMat = mat(tint || 0xf1f3f6, { roughness: 0.45, emissive: 0x4fe3d1, emissiveIntensity: 0, transparent: !!tint, opacity: tint ? 0.6 : 1 });
      const body = new THREE.Mesh(new THREE.BoxGeometry(0.72, 0.52, 0.40), this.bodyMat); body.castShadow = !lite; this.rig.add(body);
      const lid = new THREE.Mesh(new THREE.BoxGeometry(0.66, 0.46, 0.03), mat(0x2f7dff, { roughness: 0.35 })); lid.position.z = 0.215; this.rig.add(lid);
      const face = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.38, 0.16), mat(0x0b0f17, { roughness: 0.25 })); face.position.set(0.362, 0, 0.06); this.rig.add(face);
      this.eyes = []; this.xs = [];
      for (const y of [0.085, -0.085]) {
        const e = new THREE.Mesh(new THREE.BoxGeometry(0.014, 0.075, 0.075), glow(0x4fe3d1)); e.position.set(0.37, y, 0.06); this.rig.add(e); this.eyes.push(e);
        if (!lite) { const a = new THREE.Mesh(new THREE.BoxGeometry(0.014, 0.1, 0.018), glow(0xff3050)); a.rotation.x = .78; const b = a.clone(); b.rotation.x = -.78; const xg = new THREE.Group(); xg.add(a, b); xg.position.set(0.372, y, 0.06); xg.visible = false; this.rig.add(xg); this.xs.push(xg); }
      }
      if (!lite) {
        const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.007, 0.007, 0.9), mat(0xff6a1a)); pole.rotation.x = Math.PI / 2; pole.position.set(-0.31, 0.21, 0.65); this.rig.add(pole);
        this.flag = new THREE.Group(); this.flag.position.set(-0.31, 0.21, 1.03); this.rig.add(this.flag);
        const pen = new THREE.Mesh(new THREE.PlaneGeometry(0.2, 0.11), mat(0xff6a1a, { side: THREE.DoubleSide })); pen.position.x = 0.1; pen.rotation.x = Math.PI / 2; this.flag.add(pen);
      }
      this.cargo = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.3, 0.18), mat(0xd9893a)); this.cargo.position.z = 0.32; this.cargo.visible = false; this.rig.add(this.cargo);
      this.wheels = [];
      for (const ax of [0.27, 0, -0.27]) for (const sy of [0.31, -0.31]) {
        const w = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.11, 0.08, lite ? 10 : 24), mat(0x111317)); w.position.set(ax, sy, -0.18); w.castShadow = !lite; this.g.add(w); this.wheels.push(w);
      }
      this.mood = "idle"; this.mt = 0; this.hop = 0; this.shim = 0;
    }
    setCargo(kg) { this.cargo.visible = kg > 0; const s = kg > 10 ? 1.55 : 1; this.cargo.scale.set(s, s, s * 1.2); this.cargo.position.z = 0.3 + (s - 1) * 0.12; }
    setMood(m) {
      if (this.mood === m) return; this.mood = m; this.mt = 0;
      const c = { idle: 0x4fe3d1, worried: 0xffb547, fail: 0xff3050, success: 0x3ddc91, off: 0x14181f }[m] || 0x4fe3d1;
      this.eyes.forEach(e => { e.material.color.setHex(c); e.material.emissive.setHex(c); e.visible = m !== "fail" || !this.xs.length; });
      this.xs.forEach(x => x.visible = m === "fail");
      if (m === "success") this.hop = 0.5;
    }
    pose(f) { const [, x, y, z, qw, qx, qy, qz, wa] = f; this.g.position.set(x, y + (this.yoff || 0), z); this.g.quaternion.set(qx, qy, qz, qw); this.wheels.forEach(w => w.rotation.y = wa); }
    tick(dt, t, moving) {
      this.mt += dt;
      this.rig.scale.z = 1 + 0.012 * Math.sin(t * 3.1);
      const blink = (t % 3.7) < 0.11 ? 0.12 : 1;
      this.eyes.forEach(e => e.scale.z = (this.mood === "worried" ? 0.45 : this.mood === "success" ? 0.35 : 1) * blink);
      if (this.flag) this.flag.rotation.z = moving ? -0.55 + 0.18 * Math.sin(t * 15) : 0.12 * Math.sin(t * 2);
      if (this.hop > 0) { this.hop = Math.max(0, this.hop - dt); this.rig.position.z = 0.07 * Math.sin((0.5 - this.hop) / 0.5 * Math.PI); } else this.rig.position.z = moving ? 0.004 * Math.sin(t * 30) : 0;
      if (this.shim > 0) { this.shim = Math.max(0, this.shim - dt); this.bodyMat.emissiveIntensity = 0.8 * Math.sin(this.shim / 1.6 * Math.PI); }
    }
  }

  // ---------- routes ----------
  function route(items, yoff = 0, o = {}) {
    const G = new THREE.Group(); G.position.y = yoff; const lite = !!o.lite;
    const g = new THREE.Mesh(new THREE.BoxGeometry(o.len || 12, 3, 0.04), mat(0x23272f, { roughness: 0.95 })); g.position.set((o.len || 12) / 2 - 1.5, 0, -0.02); g.receiveShadow = !lite; G.add(g); G.ground = g;
    if (!lite) { const road = new THREE.Mesh(new THREE.PlaneGeometry(40, 8), mat(0x101318)); road.position.set(5, -5.5, -0.03); G.add(road); }
    for (const y of [1.5, -1.5]) { const e = new THREE.Mesh(new THREE.BoxGeometry(o.len || 12, 0.05, 0.03), mat(0xffd24a, { emissive: 0x5a4400 })); e.position.set((o.len || 12) / 2 - 1.5, y, 0.01); G.add(e); }
    const goal = new THREE.Mesh(new THREE.BoxGeometry(0.07, 3, 0.03), glow(0x3ddc91)); goal.position.set(7, 0, 0.02); G.add(goal);
    G.haz = [];
    for (const s of items || []) {
      let m = null, lx = null, txt = "";
      if (s.kind === "patch") {
        const c = { ice: 0xc9ecff, wet: 0x3c5a80, leaves: 0x9a6a2a }[s.name] || 0x667788;
        m = new THREE.Mesh(new THREE.BoxGeometry(Math.min(s.x1, 9) - s.x0, 2.6, 0.006), mat(c, { transparent: true, opacity: 0.8, roughness: s.name === "ice" ? 0.05 : 0.6, metalness: s.name === "ice" ? 0.4 : 0 }));
        m.position.set((s.x0 + Math.min(s.x1, 9)) / 2, 0, 0.004); if (s.x1 - s.x0 < 5) { lx = (s.x0 + s.x1) / 2; txt = s.name === "ice" ? "ice" : s.name; }
      } else if (s.kind === "block") {
        const len = Math.min(s.x1, 10) - s.x0; m = new THREE.Mesh(new THREE.BoxGeometry(len, 3.0, s.h), mat(0x8d929c)); m.position.set(s.x0 + len / 2, 0, s.h / 2); m.castShadow = m.receiveShadow = !lite;
        lx = s.x0; txt = `${Math.round(s.h * 100)} cm curb`;
      } else if (s.kind === "cross") {
        m = new THREE.Group(); const n = Math.round((s.x1 - s.x0) / 0.2);
        for (let k = 0; k < n; k++) { const xm = s.x0 + (k + .5) * (s.x1 - s.x0) / n, ri = Math.max(0, Math.min(1, (xm - s.x0), (s.x1 - xm)));
          const p = new THREE.Mesh(new THREE.BoxGeometry((s.x1 - s.x0) / n + .003, 3.0, 0.04), mat(s.mu < 0.3 ? 0xbfe6fa : 0x6d7380, { roughness: s.mu < 0.3 ? 0.1 : 0.8 })); p.position.set(xm, 0, -0.02); p.rotation.x = s.roll * ri * Math.PI / 180; p.receiveShadow = !lite; m.add(p); }
        lx = (s.x0 + s.x1) / 2; txt = `${Math.round(s.roll)}° sloped driveway${s.mu < 0.3 ? " (icy)" : ""}`;
      } else if (s.kind === "ramp") {
        const a = s.angle * Math.PI / 180; m = new THREE.Mesh(new THREE.BoxGeometry(s.len, 3, 0.1), mat(0x7d828c)); m.position.set(s.x0 + s.len / 2 * Math.cos(a), 0, s.len / 2 * Math.sin(a) - 0.05); m.rotation.y = -a;
        lx = s.x0 + s.len / 2; txt = `${Math.round(s.angle)}° ramp`;
      }
      if (m) { G.add(m); G.haz.push(m); }
      if (lx !== null && !lite && o.labels !== false) { const l = label(txt, "#1a1205", "#ffd7a8", 0.8); l.position.set(lx, 1.2, 0.75); G.add(l); G.haz.push(l); }
    }
    return G;
  }

  class Clip {
    constructor(rec, bolt, speed = 1) { this.rec = rec; this.b = bolt; this.speed = speed; this.i = 0; this.done = false; }
    at(lt) {
      const fr = this.rec.frames, t0 = fr[0][0], tt = lt * this.speed;
      while (this.i < fr.length - 1 && fr[this.i + 1][0] - t0 <= tt) this.i++;
      this.b.pose(fr[this.i]);
      const end = this.i >= fr.length - 1; if (end && !this.done) { this.done = true; this.b.setMood(this.rec.outcome === "delivered" ? "success" : "fail"); if (this.onEnd) this.onEnd(); }
      return fr[this.i];
    }
  }

  // ---------- stage management ----------
  let stage = new THREE.Group(); S.add(stage);
  function newStage() { S.remove(stage); stage = new THREE.Group(); S.add(stage); return stage; }
  let shake = 0;
  function camAt(p, l) { cam.position.copy(p); cam.lookAt(l); }
  function camPath(lt, dur, p0, p1, l0, l1) { const k = ease(Math.min(1, Math.max(0, lt / dur))); camAt(V3(p0).lerp(V3(p1), k), V3(l0).lerp(V3(l1), k)); }
  function cap(html) { overlay("#cap", html, !!html); }
  function chap(t) { overlay("#chap", t, !!t); }

  // ---------- the shots ----------
  const ctx = {};
  const SHOTS = [
    { id: "p0", t: 0, d: 7, enter() { newStage(); $("#fade").style.transition = "none"; overlay("#fade", null, false); }, update(lt) {
        const L = ["8:47 pm. The first snow of the year.", "Maya’s little bakery has one delivery left:", "<i>a birthday cake, for a 7-year-old.</i>"];
        overlay("#title", `<p style="font-size:40px;line-height:1.6">${L.map((l, i) => `<span style="opacity:${lt > 0.4 + i * 2.6 ? 1 : 0};transition:opacity 1s">${l}</span>`).join("<br>")}</p>`);
      }, exit() { overlay("#title", null, false); } },
    { id: "s0", t: 0, d: 7, enter() {
        newStage(); ctx.b = new Bolt(); ctx.b.setMood("off"); ctx.b.setCargo(6); stage.add(ctx.b.g); ctx.b.pose(DATA.intro.frames[0]);
        const g = route(DATA.intro.scene, 0, { labels: false }); stage.add(g); rim.intensity = 1.2; overlay("#fade", null, false);
      }, update(lt) {
        camPath(lt, 7, [1.25, -0.95, 0.32], [2.4, -2.6, 0.9], [0.2, 0, 0.18], [0.6, 0, 0.3]);
        if (lt > 1.4) ctx.b.setMood("idle");
        if (lt > 2.4) overlay("#name", `<h2><em>Meet</em> Bolt.</h2><p>Maya’s <b>delivery robot</b>. Tonight, he carries the cake.</p>`);
      }, exit() { overlay("#name", null, false); rim.intensity = 0; } },
    { id: "build", t: 0, d: 13, enter() {
        newStage(); chap("HOW BOLT IS BUILT"); cap("Bolt is simple: <b>six motorized wheels</b>, a <b>balance sensor</b>, a <b>10 kg cargo bay</b>, and two eyes that show how he’s doing."); rim.intensity = 1.4;
        const floor = new THREE.Mesh(new THREE.CircleGeometry(2.2, 64), mat(0x10151f, { roughness: 0.9 })); floor.position.z = -0.29; stage.add(floor);
        const ring = new THREE.Mesh(new THREE.RingGeometry(2.15, 2.2, 96), glow(0x1d3b4a)); ring.position.z = -0.285; stage.add(ring);
        const b = ctx.bb = new Bolt(); b.setCargo(6); b.setMood("idle"); stage.add(b.g); b.bodyMat.transparent = true;
        const imu = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.1, 0.03), glow(0x9b7bff)); imu.position.set(0, 0, 0.05); b.rig.add(imu);
        const motors = b.wheels.map(w => { const m = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.08, 16), glow(0xff8a3d)); m.position.copy(w.position); m.position.y *= 0.72; b.g.add(m); return m; });
        // explode: every part starts away from its place
        const parts = [];
        const push = (o, off) => { parts.push({ o, home: o.position.clone(), off: V3(off) }); };
        b.wheels.forEach((w, i) => push(w, [0, w.position.y > 0 ? 0.9 : -0.9, -0.15]));
        motors.forEach(m => push(m, [0, m.position.y > 0 ? 0.6 : -0.6, -0.1]));
        b.rig.children.forEach(o => { if (o === b.cargo) push(o, [0, 0, 0.9]); else if (o.position.z > 0.2 && o.position.z < 0.25) push(o, [0, 0, 0.6]); else if (o === b.flag) push(o, [0, 0, 0.8]); else if (o.position.x > 0.35) push(o, [0.6, 0, 0]); });
        push(imu, [0, 0, 0.45]);
        ctx.parts = parts; ctx.imu = imu;
        const L = [["6 motorized wheels", [0.35, -0.62, -0.05], 1.0], ["balance sensor (IMU)", [0, 0.2, 0.55], 4.4], ["cargo bay · up to 10 kg", [0, -0.2, 0.95], 6.6],
                   ["LED eyes: how he feels", [0.75, 0, 0.25], 8.6], ["flag: drivers see him", [-0.45, 0.4, 1.35], 10.4]];
        ctx.blabels = L.map(([t, p, at]) => { const l = label(t, "#e9eef7", "rgba(10,14,22,.92)", 0.36); l.position.set(...p); l.visible = false; stage.add(l); return { l, at }; });
      }, update(lt) {
        const k = ease(Math.min(1, Math.max(0, (lt - 0.3) / 3.2)));
        for (const p of ctx.parts) p.o.position.copy(p.home.clone().add(p.off.clone().multiplyScalar(1 - k)));
        ctx.bb.bodyMat.opacity = lt < 4 ? 1 : (lt < 6.2 ? 0.35 : 1);
        ctx.imu.scale.setScalar(lt > 4 && lt < 6.2 ? 1.6 : 1);
        ctx.blabels.forEach(x => x.l.visible = lt > x.at);
        const a = -0.9 + lt * 0.14; camAt(V3([3.1 * Math.cos(a), 3.1 * Math.sin(a), 1.35]), V3([0, 0, 0.25]));
      }, exit() { rim.intensity = 0; } },
    { id: "s1", t: 7, d: 8, enter() { newStage(); ctx.b = new Bolt(); ctx.b.setCargo(6); stage.add(ctx.b.g); stage.add(route(DATA.intro.scene, 0, { labels: true })); ctx.c = new Clip(DATA.intro, ctx.b); chap("THE JOB"); cap("Bolt’s job: carry your parcel <b>from the sidewalk to your back door</b>. Over a sloped driveway, up a 5 cm curb."); },
      update(lt) { const f = ctx.c.at(lt); camAt(V3([f[1] - 1.6, -3.3, 1.25]), V3([f[1] + 1.2, 0, 0.3])); } },
    { id: "s2", t: 15, d: 15, enter() {
        newStage(); ctx.b = new Bolt(); ctx.b.setCargo(6); stage.add(ctx.b.g); stage.add(route(DATA.fail.scene)); ctx.c = new Clip(DATA.fail, ctx.b);
        ctx.c.onEnd = () => { shake = 0.5; }; chap("THE PROBLEM"); cap("The last stop. The driveway has turned to <i>ice</i>.");
      }, update(lt) {
        const f = ctx.c.at(Math.max(0, lt - 1.5));
        if (f[1] > 1.4 && !ctx.c.done) ctx.b.setMood("worried");
        camPath(lt, 9, [-1.6, -6.4, 3.6], [1.2, -4.6, 2.1], [2, 0, 0], [3.4, -0.8, 0.2]);
        if (ctx.c.done) { cap("Bolt slides into the road. <b>The cake never arrives.</b> A birthday without a cake, and Maya loses $400."); overlay("#price", `<div class="a" style="color:#ff5c77">−$400</div><div class="s">No insurer would cover it, <i>because nobody could measure the risk.</i></div>`); }
      }, exit() { overlay("#price", null, false); } },
    { id: "s3", t: 30, d: 9, enter() { cap(""); chap("THE REAL PROBLEM"); },
      update(lt) {
        camPath(lt, 9, [3.5, -0.01, 16], [3.5, -0.01, 12], [3.5, 0, 0], [3.5, 0, 0]);
        const n = this.d - 3.6;
        if (lt < n) overlay("#title", `<p style="font-size:44px;line-height:1.55;color:#eef2f8">Robots fail in the real world.<br><span style="opacity:${lt > 2.2 ? 1 : 0}">Nobody can say <u>how often</u>.</span><br><span style="opacity:${lt > 4.4 ? 1 : 0}">So nobody insures a single robot job,<br><i style="color:#ff8a3d">and small businesses carry the whole loss.</i></span></p>`);
        else overlay("#title", `<h1>Hazard <em>Pay</em></h1><p><u>Crash-test the robot in a computer first</u>, charge a price from what we measured, and <b>pay out automatically</b> when it really fails.</p>`);
      }, exit() { overlay("#title", null, false); chap(""); } },
    { id: "s3b", t: 39, d: 9, enter() {
        newStage(); ctx.g = route(DATA.intro.scene); stage.add(ctx.g); ctx.b = new Bolt(); ctx.b.setCargo(6); stage.add(ctx.b.g); ctx.b.pose(DATA.intro.frames[0]);
        ctx.g.haz.forEach(h => h.scale.set(0.001, 0.001, 0.001)); chap("STEP 0 · REBUILD THE ROUTE");
        cap("First we rebuild the real route <b>in a physics simulator</b>: same slope, same curb, same weather. Describe it, or upload a photo, and Gemini builds it.");
      }, update(lt) {
        ctx.g.haz.forEach((h, i) => { const k = Math.min(1, Math.max(0, (lt - 1 - i * 0.7) / 0.6)); const s = Math.max(0.001, ease(k)); h.scale.set(s, s, s); });
        const a = lt / 9 * 1.2; camAt(V3([3.5 + 7 * Math.cos(-1.9 + a), 7 * Math.sin(-1.9 + a), 4.2]), V3([3.5, 0, 0]));
      } },
    { id: "s4", t: 48, d: 20, enter() {
        newStage(); chap("STEP 1 · CRASH-TEST IT 120 TIMES"); ctx.lanes = []; S.fog.far = 320; S.fog.near = 60;
        const fails = DATA.days.filter(d => d.outcome !== "delivered"), oks = DATA.days.filter(d => d.outcome === "delivered");
        const pick = []; for (let i = 0; i < 120; i++) pick.push(i % 6 === 0 ? fails[i % fails.length] : oks[i % oks.length]);  // 20 of 120 fail, as measured
        for (let i = 0; i < 120; i++) {
          const col = i % 10, row = Math.floor(i / 10), x = col * 11, y = row * 3.3;
          const g = route(pick[i].scene, 0, { lite: true, labels: false, len: 9.5 }); g.position.set(x, y, 0); stage.add(g);
          g.children.forEach(ch => { if (ch !== g.ground && ch.material && ch.material.color && !ch.material.emissive?.getHex?.()) ch.material.opacity = 0.6; });
          const b = new Bolt({ lite: true }); b.setCargo(6); b.g.scale.set(1.5, 1.5, 1.5); b.g.position.x = x; stage.add(b.g); const c = new Clip(pick[i], b); c.x = x; c.y = y; c.delay = (i * 37 % 10) / 10 * 1.2;
          c.g = g; ctx.lanes.push(c);
        }
        ctx.done = 0; ctx.failed = 0;
        overlay("#score", `<div class="row">test days <b id="sd">0</b></div><div class="row">failed <b id="sf">0</b></div><div class="big red" id="sp">0.0%</div><div class="row" style="margin-top:6px">price to insure $400</div><div class="big price" id="spr">$—</div>`);
        cap("Bolt drives this route <b>120 times</b>. Each run is a different day: <i>dry, rain, ice, someone bumps into him</i>. Every motion here is real physics.");
      }, update(lt) {
        for (const c of ctx.lanes) {
          const t = Math.max(0, lt - 2.2 - c.delay); const f = c.at(t * 2.0); c.b.g.position.x += c.x; c.b.g.position.y += c.y;
          if (c.done && !c.counted) { c.counted = true; ctx.done++; const bad = c.rec.outcome !== "delivered"; if (bad) ctx.failed++;
            c.g.ground.material.color.setHex(bad ? 0xb3263d : 0x1f6b48); c.g.ground.material.emissive = new THREE.Color(bad ? 0x5a0d18 : 0x0b3020); }
        }
        const d = Math.min(120, ctx.done), fl = ctx.failed;
        $("#sd").textContent = d; $("#sf").textContent = fl; $("#sp").textContent = (d ? fl / d * 100 : 0).toFixed(1) + "%";
        if (d >= 120) { $("#spr").textContent = "$83.65"; cap("<b>20 of 120 days failed: 16.7%.</b> That measured risk sets the price: <b>$83.65</b> to insure a $400 delivery."); }
        if (lt < 4) camPath(lt, 4, [-2, -3.2, 1.4], [-2, -3.2, 1.4], [1.5, 0, 0.3], [1.5, 0, 0.3]);
        else camPath(lt - 4, 9, [-2, -3.2, 1.4], [-14, -16, 34], [1.5, 0, 0.3], [44, 17, 0]);
      }, exit() { overlay("#score", null, false); S.fog.far = 60; S.fog.near = 16; } },
    { id: "s5", t: 68, d: 22, enter() {
        newStage(); chap("STEP 2 · AN AI TRIES TO BREAK HIM"); redLight.intensity = 2.2; hemi.intensity = 0.5;
        stage.add(route(DATA.attack.scene)); ctx.b = new Bolt(); ctx.b.setCargo(6); stage.add(ctx.b.g); ctx.b.pose(DATA.attack.frames[0]); ctx.c = new Clip(DATA.attack, ctx.b, 1.0);
        ctx.ice = new THREE.Mesh(new THREE.BoxGeometry(3, 2.6, 0.03), mat(0xbfe6fa, { transparent: true, opacity: .55 })); ctx.ice.position.set(3.5, 0, 5); stage.add(ctx.ice);
        ctx.arrow = new THREE.Mesh(new THREE.ConeGeometry(0.18, 0.5, 16), glow(0xff5c77)); ctx.arrow.rotation.x = Math.PI; ctx.arrow.visible = false; stage.add(ctx.arrow);
        ctx.ai = ["“The heading control can’t stop a sideways slide on a slick driveway.”", "→ test it: wet driveway, 7° slope + a 100 N bump at 2.8 s", "→ search 30 versions · shrink to the smallest · re-check on 32 new runs"]; ctx.aiN = 0;
        cap("Then <b>Gemini</b>, Google’s AI, plays an engineer whose job is to <u>find how Bolt fails</u>. It suggests a weakness, and we test it in physics.");
      }, update(lt) {
        const typed = Math.floor(Math.max(0, lt - 0.5) * 60); let s = "", left = typed; for (const line of ctx.ai) { s += line.slice(0, Math.max(0, left)) + "<br>"; left -= line.length; }
        overlay("#ai", `<div class="h">GEMINI · ADVERSARY</div>${s}`);
        ctx.ice.position.z = Math.max(0.01, 5 - Math.max(0, lt - 2.5) * 3);
        if (lt > 5) { const f = ctx.c.at(lt - 5); const near = Math.abs(ctx.c.rec.frames[ctx.c.i][0] - 2.8) < 0.5; ctx.arrow.visible = near; ctx.arrow.position.set(f[1], f[2] + 0.9, 0.45); if (f[1] > 1.6 && !ctx.c.done) ctx.b.setMood("worried"); }
        if (ctx.c.done) cap("<b>Found one:</b> a wet slope plus a small bump slides him into the road, <b>3 times out of 4</b>.");
        camPath(lt, 16, [-0.5, -4.8, 2.6], [2.2, -3.2, 1.5], [2, 0, 0.2], [4.2, -1, 0.2]);
        cam.rotateZ(0.06);
      }, exit() { overlay("#ai", null, false); redLight.intensity = 0; hemi.intensity = 0.55; } },
    { id: "s6", t: 90, d: 22, enter() {
        newStage(); chap("STEP 3 · PRACTISE, THEN A STRICT CHECK");
        stage.add(route(DATA.old.scene, 0)); stage.add(route(DATA.new.scene, 3.4, { labels: false }));
        ctx.o = new Bolt({ tint: 0xff8a3d }); ctx.o.yoff = 0; ctx.o.setCargo(6); stage.add(ctx.o.g);
        ctx.n = new Bolt(); ctx.n.yoff = 3.4; ctx.n.setCargo(6); ctx.n.shim = 1.6; stage.add(ctx.n.g);
        const l1 = label("old Bolt (v1)", "#1a0c04", "#ff8a3d", 1); l1.position.set(-1.2, 0, 1.2); stage.add(l1);
        const l2 = label("new Bolt (v2)", "#06221d", "#4fe3d1", 1); l2.position.set(-1.2, 3.4, 1.2); stage.add(l2);
        ctx.co = new Clip(DATA.old, ctx.o); ctx.cn = new Clip(DATA.new, ctx.n);
        overlay("#gates", ["fails less on what broke it", "still drives normally", "passes 16 locked tests"].map(t => `<div class="gate"><i></i>${t}</div>`).join(""));
        cap("Bolt <b>practises</b> on those failures. The new version only ships if it passes <u>three strict checks</u>.");
      }, update(lt) {
        ctx.co.at(Math.max(0, lt - 1)); ctx.cn.at(Math.max(0, lt - 1));
        [...document.querySelectorAll(".gate")].forEach((g, i) => g.classList.toggle("on", lt > 7.5 + i * 1.1));
        if (lt > 10.8) { overlay("#price", `<div class="a"><s style="color:#7f8ba0;font-weight:400">$83.65</s> → $66.95</div><div class="s">same job, safer robot, <b>cheaper to insure</b></div>`); cap("Same icy slope: <b>old Bolt slides off, new Bolt holds the line.</b> A safer robot is cheaper to insure."); }
        camPath(lt, 11, [-1.2, -4.5, 3.8], [3.6, -4.2, 3.1], [2.5, 1.7, 0], [4.5, 1.7, 0]);
      }, exit() { overlay("#gates", null, false); overlay("#price", null, false); } },
    { id: "s7", t: 112, d: 24, enter() {
        newStage(); chap("STEP 4 · PAYPAL MOVES THE MONEY");
        const N = [["The route", 0x4fe3d1], ["Physics test", 0x4fe3d1], ["The price", 0x4fe3d1], ["PayPal order", 0xffc439], ["Cover is on", 0x4fe3d1], ["Delivery day", 0x4fe3d1], ["Replay", 0x4fe3d1], ["PayPal payout", 0xffc439]];
        ctx.nodes = N.map(([t, c], i) => { const g = new THREE.Group(); const box = new THREE.Mesh(new THREE.BoxGeometry(1.6, 1.0, 0.5), mat(0x101826, { emissive: c, emissiveIntensity: 0.08 }));
          const edge = new THREE.LineSegments(new THREE.EdgesGeometry(box.geometry), new THREE.LineBasicMaterial({ color: c })); g.add(box, edge); const l = label(t, "#e9eef7", "rgba(10,14,22,.9)", 0.9); l.position.z = 0.9; g.add(l);
          g.position.set(i * 2.6, 0, 0.5); stage.add(g); g.box = box; g.c = c; return g; });
        const pipe = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 2.6 * 7), mat(0x2a3548)); pipe.rotation.z = Math.PI / 2; pipe.position.set(2.6 * 3.5, 0, 0.5); stage.add(pipe);
        ctx.coin = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.06, 40), mat(0xffc439, { metalness: 0.8, roughness: 0.25, emissive: 0x6a4c00 })); ctx.coin.rotation.x = Math.PI / 2; stage.add(ctx.coin);
        S.fog.far = 70; cap("Every dollar goes through <b>PayPal</b>: the price is a <u>PayPal order</u> the customer approves, and a claim is a <u>PayPal payout</u> to the robot’s owner.");
      }, update(lt) {
        const u = Math.min(7, Math.max(0, (lt - 0.8) / 1.15)); const i = Math.floor(u), k = u - i;
        ctx.coin.position.set(lerp(i * 2.6, (i + 1) * 2.6, ease(k)), 0, 0.5 + 0.9 * Math.sin(k * Math.PI)); ctx.coin.rotation.z += 0.08;
        ctx.nodes.forEach((n, j) => n.box.material.emissiveIntensity = j <= u ? 0.55 : 0.08);
        if (u >= 3 && u < 4) cap("<b>PayPal order:</b> the customer pays the price, and the policy’s signature is stamped on the order so every payment traces back to the measured risk.");
        if (u >= 7 && lt < 9.6) cap("<b>PayPal payout:</b> if Bolt really fails and it’s covered, the owner is paid in seconds. <i>Tested live on the PayPal sandbox.</i>");
        if (lt >= 9.6) {
          stage.visible = false;
          overlay("#ai", `<div class="h" style="color:#ffc439">UNDER THE HOOD · PAYPAL</div>
            <span style="color:#ffc439">POST /v2/checkout/orders</span> intent=CAPTURE<br>PayPal-Request-Id: policy hash <i style="color:#7f8ba0">(idempotent)</i><br>reference_id = policy HMAC signature<br>
            <span style="color:#ffc439">POST /v2/checkout/orders/{id}/capture</span><br><span style="color:#ffc439">POST /v1/payments/payouts</span> sender_item_id = claim id<br>webhooks verified · verify-webhook-signature`);
          $("#ai").style.borderColor = "#5a4520"; $("#ai").style.background = "rgba(24,18,4,.85)"; $("#ai").style.color = "#ffe6a8";
          overlay("#price", `<div class="s" style="font-size:26px;color:#ffc439;letter-spacing:2px">WHY PAYPAL WINS</div><div class="a" style="font-size:64px">Every robot job =<br>2 PayPal transactions</div><div class="s">a premium in, a payout out. <i>Illustration:</i> 1M robot jobs a month × $1.50 average premium = <b>$1.5M a month</b> of new volume through PayPal, plus every claim paid with PayPal Payouts.</div>`);
          $("#price").style.left = "68%"; $("#price").style.width = "860px"; $("#ai").style.top = "260px"; $("#ai").style.left = "90px";
          cap("");
        }
      }, exit() { overlay("#ai", null, false); overlay("#price", null, false); $("#price").style.left = ""; $("#price").style.width = ""; $("#ai").style.cssText = ""; } },
    { id: "s8", t: 130, d: 25, enter() {
        newStage(); chap("CLAIM DAY"); stage.add(route(DATA.claim.scene)); ctx.b = new Bolt(); ctx.b.setCargo(6); stage.add(ctx.b.g); ctx.c = new Clip(DATA.claim, ctx.b);
        ctx.c.onEnd = () => { shake = 0.4; }; ctx.cf = [];
        cap("Delivery day, and it’s icy. Bolt gets <b>stuck</b>. Instead of weeks of paperwork…");
      }, update(lt) {
        if (lt < 7) { const f = ctx.c.at(lt * 1.4); camAt(V3([f[1] - 1.8, -3.6, 1.7]), V3([f[1] + 1, 0, 0.3])); return; }
        if (!ctx.cf.length) {
          newStage(); DATA.counterfactuals.forEach((r, i) => { const y = i * 3.4; stage.add(route(r.scene, y, { labels: false })); const b = new Bolt(); b.yoff = y; b.setCargo(i === 3 ? 0 : 6); stage.add(b.g); ctx.cf.push(new Clip(r, b)); });
          overlay("#cflabels", DATA.counterfactuals.map((r, i) => `<div class="cfl" id="cf${i}" style="left:120px;top:${210 + i * 150}px">${r.label}</div>`).join(""));
          cap("…we <b>replay the exact same run</b>, taking away <u>one thing at a time</u>. Whatever makes the failure disappear was the cause.");
        }
        ctx.cf.forEach((c, i) => { c.at((lt - 7.3) * 1.3); if (c.done) { const e = $("#cf" + i); e.className = "cfl " + (c.rec.outcome === "delivered" ? "ok" : "bad"); e.textContent = c.rec.label + (c.rec.outcome === "delivered" ? " → would have made it" : " → still stuck"); } });
        camPath(lt - 7, 6, [-3, 5.1, 16], [1, 5.1, 13.5], [4, 5.1, 0], [4.5, 5.1, 0]);
        if (lt > 13.5) { overlay("#stamp", "APPROVED"); $("#stamp").style.color = $("#stamp").style.borderColor = "#3ddc91"; $("#stamp").style.transform = "translate(-50%,-50%) rotate(-8deg) scale(1)";
          cap("Ice caused it, and ice is covered. <b>$400 PayPal payout to Maya, in seconds.</b> Tomorrow, Bolt delivers again."); }
      }, exit() { overlay("#cflabels", "", false); overlay("#stamp", null, false); $("#stamp").style.transform = ""; } },
    { id: "s9", t: 155, d: 9, enter() {
        newStage(); chap("WHAT ISN’T COVERED"); stage.add(route(DATA.overload.scene)); ctx.b = new Bolt(); ctx.b.setCargo(14); stage.add(ctx.b.g); ctx.c = new Clip(DATA.overload, ctx.b, 1.8);
        cap("Load him with <b>14 kg</b>, over his 10 kg limit, and the replay shows <u>that’s</u> what stopped him.");
      }, update(lt) {
        const f = ctx.c.at(lt); camAt(V3([f[1] + 2.2, -2.6, 1.0]), V3([f[1], 0, 0.35]));
        if (lt > 4.2) { overlay("#stamp", "DENIED"); $("#stamp").style.color = $("#stamp").style.borderColor = "#ff5c77"; $("#stamp").style.transform = "translate(-50%,-50%) rotate(-8deg) scale(1)"; }
      }, exit() { overlay("#stamp", null, false); $("#stamp").style.transform = ""; } },
    { id: "s10", t: 164, d: 10, enter() {
        newStage(); chap(""); stage.add(route(DATA.final.scene)); ctx.b = new Bolt(); ctx.b.setCargo(6); ctx.b.shim = 1.6; stage.add(ctx.b.g); ctx.c = new Clip(DATA.final, ctx.b); rim.intensity = 1.2;
        cap("");
      }, update(lt) {
        const f = ctx.c.at(lt + 3); camPath(lt, 8, [9.5, -2.6, 0.5], [9.8, -3.4, 1.2], [6.5, 0, 0.3], [6.8, 0, 0.3]);
        if (lt > 2.5) overlay("#title", `<h1>Hazard <em>Pay</em></h1><p><i>Robots, insured by the AI that tries to break them.</i></p><p style="font:600 24px 'JetBrains Mono';color:#7f8ba0">github.com/CopyNinja07-07/hazardpay</p>`);
        if (lt > 7.4) overlay("#fade", null, true);
      } },
  ];
  const MIN = { p0: 9, s0: 4.5, build: 12, s1: 7, s2: 12, s3: 12, s3b: 7, s4: 15, s5: 13, s6: 13.5, s7: 13, s8: 17, s9: 6, s10: 7.5 };
  let VO = {}; try { VO = await (await fetch("/static/film/vo3.json")).json(); } catch (e) {}
  const DUR = {}; for (const k in MIN) DUR[k] = Math.max(MIN[k], (VO[k] || 0) + 0.9);
  const INTRO = new URLSearchParams(location.search).has("intro");
  if (INTRO) {  // music-only cinematic intro: story + Bolt + the problem + the idea, no narration
    const keep = { p0: 8.5, s0: 4.5, build: 12, s2: 10, s3: 12.5, s4: 14, s6: 12 };
    for (let i = SHOTS.length - 1; i >= 0; i--) if (!(SHOTS[i].id in keep)) SHOTS.splice(i, 1);
    Object.assign(DUR, keep);
  }
  { let t = 0; for (const sh of SHOTS) { sh.t = t; sh.d = DUR[sh.id] || sh.d; t += sh.d; } }
  const END = SHOTS.reduce((a, s) => a + s.d, 0);

  // ---------- clock ----------
  const startAt = +(new URLSearchParams(location.search).get("t") || 0);
  let T0 = performance.now() - startAt * 1000, cur = null, last = performance.now();
  if (startAt > 0) { $("#fade").style.transition = "none"; overlay("#fade", null, false); }
  const FREEZE = new URLSearchParams(location.search).has("freeze");
  const marks = [{ id: "wall", t: Date.now() / 1000 - startAt }];
  const RENDER = new URLSearchParams(location.search).has("render");
  if (RENDER) { const st = document.createElement("style"); st.textContent = "*{transition:none!important}"; document.head.appendChild(st); }
  window.__film = { END, shots: SHOTS.map(s => ({ id: s.id, t: s.t, d: s.d })) };
  function frame(now, forcedT) {
    if (!RENDER) requestAnimationFrame(frame);
    const T = forcedT !== undefined ? forcedT : FREEZE ? Math.min((now - T0) / 1000, startAt + 1.2) : (now - T0) / 1000;
    const dt = forcedT !== undefined ? 1 / 30 : Math.min(0.05, (now - last) / 1000); last = now;
    const shot = SHOTS.filter(s => T >= s.t).pop();
    if (shot && shot !== cur) { if (cur && cur.exit) cur.exit(); cur = shot; shot.enter(); marks.push({ id: shot.id, t: +T.toFixed(2) }); }
    if (cur) cur.update(T - cur.t);
    stage.traverse(o => { if (o.userData.bolt) o.userData.bolt.tick(dt, T, true); });
    [ctx.b, ctx.o, ctx.n, ctx.bb].forEach(b => b && b.tick(dt, T, cur && cur.id !== "build"));
    (ctx.lanes || []).forEach(c => c.b.tick(dt, T, true)); (ctx.cf || []).forEach(c => c.b.tick(dt, T, true));
    if (shake > 0) { shake -= dt; cam.position.x += Math.sin(T * 97) * shake * .12; cam.position.z += Math.cos(T * 83) * shake * .12; }
    if (composer) composer.render(); else R.render(S, cam);
    if (T > END && !window.__filmDone) { window.__filmDone = true; document.body.dataset.done = "1"; fetch("/api/marks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ marks: marks.concat([{ id: "end", t: END }]) }) }); }
  }
  if (RENDER) { window.__frame = T => frame(0, T); window.__ready = true; } else requestAnimationFrame(frame);
})();
