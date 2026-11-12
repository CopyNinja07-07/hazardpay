// Auto-demo ("sit back and watch"): open /?tour=1. Follows docs/STORYBOARD.md shot by shot.
// It drives the real app (real simulator, real Gemini, real PayPal sandbox), shows title cards and
// subtitles, and records a timestamp for each shot in window.__marks so the film tool can place
// the voiceover and the score on top of the screen recording.
(function () {
  if (!/[?&]tour=1/.test(location.search)) return;
  const q = new URLSearchParams(location.search);
  const OPERATOR = q.get("operator") || "";
  window.__fast = true;
  window.__serverPay = q.get("pay") !== "popup";  // default: premium paid server-side with the sandbox test card  // shorter attack + retrain so the film stays under 3 minutes
  const css = document.createElement("style");
  css.textContent = `
  #tCard{position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:18px;background:#070a10;opacity:0;pointer-events:none;transition:opacity .7s}
  #tCard.on{opacity:1}#tCard h1{font:700 64px "Space Grotesk";letter-spacing:-1px;margin:0;max-width:1300px;text-align:center;line-height:1.1}
  #tCard p{font:400 26px Inter;color:#9aa6ba;margin:0;max-width:1100px;text-align:center}
  #tCard .w{opacity:0;transition:opacity .35s;display:inline-block;margin-right:.28em}#tCard .w.on{opacity:1}
  #tSub{position:fixed;left:50%;bottom:34px;transform:translateX(-50%);z-index:60;max-width:1100px;padding:12px 20px;border-radius:12px;background:rgba(7,10,16,.86);border:1px solid #1e2839;font:500 22px/1.4 Inter;color:#e9eef7;text-align:center;opacity:0;transition:opacity .3s}
  #tSub.on{opacity:1}
  #tChap{position:fixed;left:24px;top:76px;z-index:60;font:600 13px "JetBrains Mono";letter-spacing:1px;text-transform:uppercase;color:#ff8a3d;background:rgba(7,10,16,.86);padding:6px 10px;border-radius:8px;border:1px solid #3a2414;opacity:0;transition:opacity .3s}
  #tChap.on{opacity:1}
  .coin{position:fixed;z-index:70;width:46px;height:46px;border-radius:50%;background:#ffc439;color:#14213d;font:800 20px Inter;display:grid;place-items:center;box-shadow:0 6px 20px rgba(255,196,57,.4);transition:transform 1.2s cubic-bezier(.6,-0.2,.3,1.3),opacity .3s}
  .stamp{position:fixed;z-index:70;left:50%;top:42%;transform:translate(-50%,-50%) rotate(-8deg) scale(2.2);opacity:0;font:800 84px "Space Grotesk";padding:6px 28px;border:8px solid;border-radius:14px;transition:all .35s cubic-bezier(.2,1.6,.4,1)}
  .stamp.on{opacity:1;transform:translate(-50%,-50%) rotate(-8deg) scale(1)}
  .hl{outline:3px solid #ff8a3d;outline-offset:3px;border-radius:12px;transition:outline-color .3s}
  #tTag{position:fixed;z-index:75;left:50%;top:84px;transform:translateX(-50%) translateY(-8px);opacity:0;padding:8px 18px;border-radius:999px;background:#ff8a3d;color:#1a0c04;font:700 18px Inter;transition:all .35s}
  #tTag.on{opacity:1;transform:translateX(-50%) translateY(0)}
  #tUrl{position:fixed;z-index:75;right:24px;top:76px;padding:6px 12px;border-radius:8px;background:rgba(7,10,16,.86);border:1px solid #1e2839;font:600 15px "JetBrains Mono";color:#e9eef7;opacity:0;transition:opacity .4s}#tUrl.on{opacity:1}
  #tCur{position:fixed;z-index:80;left:0;top:0;width:26px;height:26px;pointer-events:none;transition:transform .9s cubic-bezier(.45,.05,.25,1);transform:translate(960px,600px)}
  #tCur .r{position:absolute;left:-14px;top:-14px;width:28px;height:28px;border-radius:50%;border:3px solid #ff8a3d;opacity:0;transform:scale(.4)}
  #tCur .r.go{animation:rip .5s ease-out}@keyframes rip{0%{opacity:1;transform:scale(.4)}100%{opacity:0;transform:scale(1.8)}}`;
  document.head.appendChild(css);
  document.body.insertAdjacentHTML("beforeend", `<div id="tCard"></div><div id="tSub"></div><div id="tChap"></div><div id="tTag"></div><div id="tUrl">github.com/CopyNinja07-07/hazardpay</div><div id="tCur"><svg width="26" height="26" viewBox="0 0 26 26"><path d="M3 2 L3 21 L8.5 16 L12 24 L15.5 22.5 L12 15 L19 15 Z" fill="#fff" stroke="#111" stroke-width="1.5"/></svg><div class="r"></div></div>`);
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const T0 = performance.now();
  window.__marks = [{ id: "wall", t: Date.now() / 1000 }];  // wall clock at tour start, to sync with the screen recording
  let VO = {};
  const mark = (id) => window.__marks.push({ id, t: +((performance.now() - T0) / 1000).toFixed(2) });
  const voLen = id => (VO[id] || 0) * 1000;

  async function card(id, title, sub, ms = 3200, wordByWord = false) {
    const c = $("#tCard");
    c.innerHTML = `<h1>${wordByWord ? title.split(" ").map(w => `<span class="w">${esc(w)}</span>`).join("") : esc(title)}</h1>${sub ? `<p>${esc(sub)}</p>` : ""}`;
    c.classList.add("on");
    if (wordByWord) for (const w of c.querySelectorAll(".w")) { w.classList.add("on"); await wait(170); }
    await wait(Math.max(ms, voLen(id)));
    c.classList.remove("on"); await wait(700);
  }
  async function tag(text, ms = 2600) { const t = $("#tTag"); t.textContent = text; t.classList.add("on"); setTimeout(() => t.classList.remove("on"), ms); }
  function url(on) { $("#tUrl").classList.toggle("on", on); }
  function sub(text) { const s = $("#tSub"); if (!text) { s.classList.remove("on"); return; } s.textContent = text; s.classList.add("on"); }
  function chap(text) { const c = $("#tChap"); c.textContent = text; c.classList.add("on"); }
  function tab(v) { document.querySelector(`[data-v=${v}]`).click(); window.scrollTo({ top: 0, behavior: "smooth" }); }
  function hl(sel, on = true) { const e = $(sel); if (e) e.classList.toggle("hl", on); }
  async function until(fn, ms = 240000) { const t = performance.now(); while (!fn()) { if (performance.now() - t > ms) throw new Error("timed out"); await wait(300); } }
  async function moveTo(sel) {
    const e = $(sel); if (!e) return; e.scrollIntoView({ behavior: "smooth", block: "center" }); await wait(450);
    const b = e.getBoundingClientRect(); $("#tCur").style.transform = `translate(${b.left + Math.min(b.width * 0.5, 60)}px, ${b.top + b.height * 0.55}px)`; await wait(950);
  }
  async function press() { const r = $("#tCur .r"); r.classList.remove("go"); void r.offsetWidth; r.classList.add("go"); await wait(180); }
  async function clickWait(btnSel) { await moveTo(btnSel); hl(btnSel); await press(); $(btnSel).click(); await wait(400); hl(btnSel, false); await until(() => !$(btnSel) || !$(btnSel).disabled); }
  async function typeInto(sel, text) { await moveTo(sel); await press(); const e = $(sel); e.focus(); e.value = ""; for (const ch of text) { e.value += ch; await wait(38 + Math.random() * 40); } await wait(300); }
  async function choose(sel, value) { await moveTo(sel); await press(); $(sel).value = value; $(sel).dispatchEvent(new Event("change")); hl(sel); await wait(500); hl(sel, false); }
  function coin(from, to, label = "$") {
    const a = $(from).getBoundingClientRect(), b = $(to).getBoundingClientRect();
    const c = document.createElement("div"); c.className = "coin"; c.textContent = label;
    c.style.left = (a.left + a.width / 2 - 23) + "px"; c.style.top = (a.top + a.height / 2 - 23) + "px"; document.body.appendChild(c);
    requestAnimationFrame(() => c.style.transform = `translate(${b.left + b.width / 2 - a.left - a.width / 2}px, ${b.top + b.height / 2 - a.top - a.height / 2}px)`);
    setTimeout(() => { c.style.opacity = 0; setTimeout(() => c.remove(), 400); }, 1300);
  }
  async function stamp(text, color) { const s = document.createElement("div"); s.className = "stamp"; s.textContent = text; s.style.color = color; s.style.borderColor = color; document.body.appendChild(s); await wait(50); s.classList.add("on"); await wait(1800); s.style.opacity = 0; await wait(400); s.remove(); }
  async function hold(id, ms) { await wait(Math.max(ms, voLen(id))); }
  function view3d() { $("#view3d").scrollIntoView({ behavior: "smooth", block: "center" }); }
  async function playClip(r, badge) { tab("under"); view3d(); await wait(500); play(r, badge); try { await until(() => !V.playing, (r.t || 10) * 1000 + 4000); } catch (e) {} await wait(900); }

  let LINES = {};


  async function run() {
    try { VO = await api("/static/film/vo.json"); } catch (e) { VO = {}; }
    LINES = await api("/static/film/lines.json");
    await until(() => typeof V !== "undefined" && V && S);
    document.querySelector("header").style.zIndex = 40;
    // 1
    mark("s1"); sub(LINES.s1); url(true); setTimeout(() => url(false), 6000);
    const dry = await api("/api/preview?name=" + encodeURIComponent(mission().name));
    await card("s1", "Robots are going outside.", "", 2200);
    await Replay.camTo(V, [-1.5, -4.2, 1.8], [2, 0, 0.3], 1.2);
    tag("MuJoCo physics simulation");
    await playClip(dry);
    // 2
    mark("s2"); sub(LINES.s2);
    const icy = await api("/api/clip", { ops: [{ op: "cross_slope", start: 2.0, length: 3.0, roll: 8, mu: 0.12 }], seed: 3 });
    await playClip(icy);
    await card("s2", "And they fail.", "Nobody can price that risk, so robot jobs go uninsured.", 3000);
    // 3
    mark("s3"); sub(""); await card("s3", "Hazard Pay breaks the robot before the job, prices what it measured, and pays out when it really fails.", "Physics simulation · Gemini · PayPal", 3500, true);
    // 3b: describe a route, Gemini builds it
    mark("s3b"); chap("Any route"); sub(LINES.s3b); tab("under");
    await typeInto("#siteText", "Back door with a steep icy driveway and a 6 cm curb");
    tag("Gemini reads the route");
    if (S.ai.startsWith("DEMO")) { await wait(1200); } else { try { await clickWait("#bSite"); await wait(600); try { await until(() => !V.playing, 15000); } catch (e) {} } catch (e) {} }
    await hold("s3b", 1500);
    $("#mission").value = "Maple St back door"; $("#mission").dispatchEvent(new Event("change")); await wait(1200);
    // 4
    mark("s4"); chap("1 · Price the job"); sub(LINES.s4); tab("under");
    await card("e4", "Step 1 · Price the job", "Bolt drives this route 120 times. Each run is a different day: dry, rain or ice, sometimes a pedestrian bumps it. Here are some of those days at 5× speed.", 3600);
    tag("120 simulated days · fast-forward", 5000);
    await moveTo("#bDays"); await press(); try { await montage(7); } catch (e) {}
    await clickWait("#bQuote"); hl("#quote"); await hold("s4", 6000); hl("#quote", false);
    const p1 = QUOTE.policy.premium;
    // 5
    mark("s5"); chap("2 · Try to break it"); sub(LINES.s5); tab("adv");
    await card("e5", "Step 2 · Try to break it", "Gemini suggests how Bolt could fail. We test every idea in physics, keep only what really breaks it, and shrink it to the simplest version.", 3400);
    tag("Gemini writes attack ideas", 4000);
    await clickWait("#bAdv");
    await hold("s5", 3000);
    if (FAILS[0] && FAILS[0].clip) await playClip(FAILS[0].clip, "Broken: " + FAILS[0].describe);
    // 6
    mark("s6"); chap("3 · Make it safer"); sub(LINES.s6);
    await card("e6", "Step 3 · Make it safer", "Bolt practises on what broke it. It only goes live if it fails less, still drives normally, and passes 16 locked tests.", 3400);
    tab("train");
    await clickWait("#bTrain"); await wait(2500);
    if (FAILS[0]) {
      const cmp = await api("/api/compare", { ops: FAILS[0].ops, seed: 101 });
      tab("under"); view3d(); await wait(500); tag(`Same problem: ${cmp.old_version} vs ${cmp.new_version}`, 5000);
      Replay.play(V, cmp.new.frames, cmp.new.scene, { cargo: true, outcome: cmp.new.outcome, ghost: cmp.old.frames, ghostOffset: 0, ghostLabel: cmp.old_version });
      Replay.version(V, cmp.new_version);
      try { await until(() => !V.playing, 20000); } catch (e) {} await wait(1200);
    }
    tab("under"); view3d(); await clickWait("#bQuote");
    const p2 = QUOTE.policy.premium;
    await card("s6", `$${p1.toFixed(2)}  →  $${p2.toFixed(2)}`, "A safer robot is cheaper to insure.", 3000);
    // 7
    mark("s7"); chap("4 · Insure it"); sub(LINES.s7);
    await card("e7", "Step 4 · PayPal moves the money", "The price becomes a PayPal order. The policy's signature is stamped on the order, so every payment traces back to the exact risk we measured. If Bolt fails, a PayPal payout pays the operator.", 4200);
    tab("claim");
    if (OPERATOR) await typeInto("#opEmail", OPERATOR);
    tag("PayPal Orders API");
    await clickWait("#bBuy");
    const oid = POLICY.order.id;
    if (POLICY.status !== "active" && POLICY.order.mode === "SANDBOX") {
      sub("Approve the payment in the PayPal window (sandbox personal account).");
      window.open(POLICY.order.approve_url, "paypal", "width=520,height=760,left=120,top=80");
      let ok = false; const t = performance.now();
      while (!ok && performance.now() - t < 300000) { const o = await api("/api/order/" + oid); ok = o.status === "APPROVED"; if (!ok) await wait(2000); }
    }
    sub(LINES.s7);
    if (POLICY.status !== "active") { await until(() => $("#bCap")); await clickWait("#bCap"); }
    else { tag("Paid with a PayPal sandbox test card · captured"); Flow.light("cover"); await wait(1500); }
    coin("#bBuy", "#polBox", "$"); await hold("s7", 2500);
    // 8
    mark("s8"); chap("Claim day"); sub(LINES.s8);
    await card("e8", "Claim day", "No forms. We replay the exact run, removing one condition at a time. Whatever makes the failure disappear was the cause.", 3200);
    $("#rSeed").value = "7"; $("#rBump").value = "0"; $("#rCargo").value = ""; $("#rSpeed").value = "";
    await choose("#rWeather", "ice");
    await moveTo("#bRun"); await press(); $("#bRun").click(); await wait(300); await until(() => !$("#bRun").disabled); try { await until(() => !V.playing, 16000); } catch (e) {} await wait(1200);
    tab("claim"); await clickWait("#bClaim"); $("#claimCard").scrollIntoView({ behavior: "smooth", block: "center" }); await wait(1600);
    await stamp("APPROVED", "#3ddc91"); tag("PayPal Payouts API"); coin("#claimOut", "#opEmail", "$");
    await hold("s8", 4000);
    // 9
    mark("s9"); sub(LINES.s9);
    const ov = { weather: "dry", bump: 0, cargo_kg: 14 };
    const r9 = await api("/api/run", { policy_id: POLICY.id, seed: 1, what_if: true, ...ov });
    await playClip(r9);
    const c9 = await api("/api/claim", { policy_id: POLICY.id, seed: 1, what_if: true, ...ov });
    tab("claim"); await stamp(c9.decision, c9.decision === "DENIED" ? "#ff5c77" : "#3ddc91"); await hold("s9", 1500);
    // 10
    mark("s10"); chap("Records"); sub(""); tab("ledger"); tag("Every policy, attack and claim · AG Grid"); await wait(2500); url(true);
    await card("s10", "Robots, insured by the AI that tries to break them.", "Hazard Pay · github.com/CopyNinja07-07/hazardpay", 4000);
    mark("end"); sub(""); $("#tChap").classList.remove("on");
    try { await api("/api/marks", { marks: window.__marks }); } catch (e) {}
    window.__tourDone = true;
  }
  window.addEventListener("load", () => setTimeout(() => run().catch(e => { sub("Tour stopped: " + e.message); window.__tourError = e.message; }), 1200));
})();
