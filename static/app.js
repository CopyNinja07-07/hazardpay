const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const api = (u, b) => fetch(u, b === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) })
  .then(async r => { const j = await r.json(); if (!r.ok) throw new Error(j.detail || r.statusText); return j; });
function note(m) { let n = document.querySelector("#note"); if (!n) { n = document.createElement("div"); n.id = "note"; n.style.cssText = "position:fixed;right:20px;bottom:20px;z-index:90;max-width:420px;background:#2b220f;color:#ffc24a;border:1px solid #5a4520;border-radius:12px;padding:12px 14px;font:14px Inter"; document.body.appendChild(n); } n.textContent = m; n.style.display = "block"; clearTimeout(n._t); n._t = setTimeout(() => n.style.display = "none", 6000); }
const money = v => "$" + (+v).toFixed(2), pct = v => (v * 100).toFixed(1) + "%";
let S = null, V = null, QUOTE = null, POLICY = null, LASTRUN = null;

document.querySelectorAll("nav button").forEach(b => b.onclick = () => {
  document.querySelectorAll("nav button").forEach(x => x.classList.toggle("on", x === b));
  ["under", "adv", "train", "claim", "ledger", "how"].forEach(v => $("#v-" + v).classList.toggle("hidden", v !== b.dataset.v));
  const host = { under: "#v-under .card", adv: "#v-adv .card", claim: "#v-claim .card" }[b.dataset.v];
  if (b.dataset.v === "ledger") loadLedger();
});

async function poll(jid, onEvent) {
  let seen = 0;
  for (;;) {
    const j = await api("/api/job/" + jid);
    for (; seen < j.events.length; seen++) onEvent(j.events[seen]);
    if (j.status !== "running") { if (j.status === "error") throw new Error(j.error); return j.result; }
    await new Promise(r => setTimeout(r, 700));
  }
}
function busy(btn, on, label) { btn.disabled = on; if (label) btn.dataset.l = btn.dataset.l || btn.textContent; btn.textContent = on ? label : (btn.dataset.l || btn.textContent); }

// ---------- boot ----------
async function boot() {
  S = await api("/api/status");
  $("#cAI").innerHTML = "AI <b>" + esc(S.ai) + "</b>"; if (!S.ai.startsWith("DEMO")) $("#cAI").classList.add("live");
  $("#cPP").innerHTML = "PayPal <b>" + esc(S.paypal) + "</b>"; if (S.paypal === "SANDBOX") $("#cPP").classList.add("live");
  $("#cRobot").innerHTML = "robot <b>" + esc(S.robot) + "</b>";
  $("#ghash").textContent = "gauntlet: " + S.gauntlet_size + " scenarios · hash " + S.gauntlet_hash;
  $("#mission").innerHTML = S.missions.map(m => `<option>${esc(m.name)}</option>`).join("");
  $("#mission").onchange = () => { showMission(); preview(); };
  showMission();
  V = Replay.make($("#view3d"));
  Flow.mount($("#flowHow")); Flow.nodes.forEach(n => Flow.light(n.id));  // the How tab shows it all lit
  Flow.mount($("#flow"));                                                // the live one lights up as you go
  preview();
}
function mission() { return S.missions.find(m => m.name === $("#mission").value); }
function showMission() {
  const m = mission();
  $("#mdesc").innerHTML = `${esc(m.description || "")}<br>weather odds: ${Object.entries(m.weather).map(([k, v]) => k + " " + Math.round(v * 100) + "%").join(" · ")} · cargo ${m.cargo_kg} kg · cover ${money(m.cover)} · pedestrian bump odds ${Math.round((m.bump_prob || 0) * 100)}%`;
  $("#advMission").textContent = "mission: " + m.name;
}
function play(res, badge) {
  const b = $("#badge"); b.style.display = "none";
  Replay.play(V, res.frames, res.scene, {
    cargo: true, outcome: res.outcome,
    onFrame: f => $("#hud").textContent = `t ${f[0].toFixed(1)} s · x ${f[1].toFixed(2)} m · y ${f[2].toFixed(2)} m`,
    onEnd: () => { const ok = res.outcome === "delivered"; b.textContent = badge || (ok ? "Delivered" : ({ stuck: "Stuck", off_sidewalk: "Slid into the road", tipped: "Tipped over", timeout: "Too slow" }[res.outcome] || res.outcome)); b.style.display = "block"; b.style.background = ok ? "#0f2b1f" : "#2b0f17"; b.style.color = ok ? "#3ddc91" : "#ff5c77"; }
  });
}
async function preview() { const r = await api("/api/preview?name=" + encodeURIComponent(mission().name)); play(r); Flow.light("route"); Flow.light("sim"); }
async function montage(n = 14) {
  const days = await api(`/api/days?name=${encodeURIComponent(mission().name)}&n=${n}`);
  const wx = { dry: "dry", wet: "rain", ice: "ice" };
  dotsStart();
  const cells = [...document.querySelectorAll("#dots i")];
  let fails = 0;
  for (const d of days) {
    const bad = d.outcome !== "delivered"; if (bad) fails++;
    await new Promise(res => {
      setTimeout(res, (d.t / 5 + 1.5) * 1000);  // never hang if the tab is in the background
      Replay.play(V, d.frames, d.scene, { cargo: true, outcome: d.outcome, speed: 5, onEnd: res,
        onFrame: f => $("#hud").textContent = `DAY ${d.day} of 120 · ${wx[d.weather]}${d.bump ? " · bumped " + d.bump + " N" : ""} · ${(f[0]).toFixed(1)} s · ⏩ 5×` });
    });
    const cell = cells[d.day - 1]; if (cell) cell.className = bad ? "bad" : "ok";
    $("#badge").style.display = "block"; $("#badge").textContent = bad ? "Day " + d.day + ": failed" : "Day " + d.day + ": delivered";
    $("#badge").style.background = bad ? "#2b0f17" : "#0f2b1f"; $("#badge").style.color = bad ? "#ff5c77" : "#3ddc91";
    await new Promise(r => setTimeout(r, 250));
  }
  for (let k = days.length; k < 120; k++) { $("#hud").textContent = `DAY ${k + 1} of 120 · ⏩ 50×`; await new Promise(r => setTimeout(r, 22)); }
  Flow.light("days");
  return { shown: days.length, fails };
}
$("#bDays").onclick = async () => { const b = $("#bDays"); busy(b, true, "Fast-forwarding…"); try { await montage(); } finally { busy(b, false); } };
$("#bPreview").onclick = preview;

// ---------- site from text / photo ----------
let PHOTO = null;
$("#sitePhoto").onchange = e => { const f = e.target.files[0]; if (!f) return; const rd = new FileReader(); rd.onload = () => { PHOTO = rd.result; $("#siteText").placeholder = "photo attached: " + f.name; }; rd.readAsDataURL(f); };
$("#bSite").onclick = async () => {
  const b = $("#bSite"); busy(b, true, "Reading…");
  try { const r = await api("/api/site", { text: $("#siteText").value, image: PHOTO }); S.missions.push(r.mission); $("#mission").insertAdjacentHTML("beforeend", `<option>${esc(r.mission.name)}</option>`); $("#mission").value = r.mission.name; showMission(); preview(); }
  catch (e) { $("#mdesc").innerHTML = `<span class="pill warn">${esc(e.message)}</span>`; } finally { busy(b, false); }
};

// ---------- quote ----------
$("#bQuote").onclick = async () => {
  const b = $("#bQuote"); busy(b, true, "Simulating 120 days…");
  $("#quote").innerHTML = `<div class="fine">Running the robot through sampled days…</div>`;
  try {
    const { job } = await api("/api/quote", { name: mission().name });
    dotsStart();
    QUOTE = await poll(job, () => {});
    await dotsFill(QUOTE.risk.fails, QUOTE.risk.n);
    renderQuote(QUOTE); Flow.light("days"); Flow.light("price");
  } catch (e) { $("#quote").innerHTML = `<span class="pill bad">${esc(e.message)}</span>`; } finally { busy(b, false); }
};
function dotsStart() { $("#dots").innerHTML = Array.from({ length: 120 }, () => "<i></i>").join(""); }
async function dotsFill(fails, n) {
  const cells = [...document.querySelectorAll("#dots i")].slice(0, n);
  const bad = new Set(); const rng = (i) => (Math.sin(i * 9301 + 49297) * 233280) % 1;
  const order = cells.map((_, i) => i).sort((a, b) => Math.abs(rng(a)) - Math.abs(rng(b)));
  order.slice(0, fails).forEach(i => bad.add(i));
  for (let i = 0; i < cells.length; i++) { cells[i].className = bad.has(i) ? "bad" : "ok"; if (i % 4 === 0) await new Promise(r => setTimeout(r, 12)); }
}
function renderQuote(q) {
  const r = q.risk, p = q.policy;
  $("#quote").innerHTML = `
  <div class="grid3"><div class="stat"><div class="big" style="color:var(--red)">${pct(r.p)}</div><div class="lbl">of days Bolt fails this delivery<br>95% CI ${pct(r.lo)}–${pct(r.hi)} · ${r.fails}/${r.n} days</div></div>
  <div class="stat"><div class="big" style="color:var(--orange)">${money(p.premium)}</div><div class="lbl">price to insure it<br>${esc(q.pricing.formula)}</div></div>
  <div class="stat"><div class="big">${money(p.cover)}</div><div class="lbl">paid out if it fails<br>robot ${esc(p.robot_version)}</div></div></div>
  <h3 style="margin:14px 0 4px">Where the risk comes from</h3>
  ${q.shares.map(s => `<div class="share"><div class="t"><span>${esc(s.hazard)}</span><b>${Math.round(s.share * 100)}%</b></div><div class="bar"><div style="width:${Math.round(s.share * 100)}%"></div></div><div class="fine">risk if this weren’t there: ${pct(s.p_without)}</div></div>`).join("") || '<div class="fine">no route hazards</div>'}
  <div class="fine">by weather: ${Object.entries(r.by_weather).map(([k, v]) => `${k} ${pct(v)}`).join(" · ")} · failure modes: ${Object.entries(r.modes).map(([k, v]) => `${k.replace("_", " ")} ${v}`).join(", ") || "none"}</div>
  <div class="policy" style="margin-top:12px">policy ${esc(p.mission_hash)} · signed ${esc(p.signature.slice(0, 16))}…\ncovered: ${esc(p.covered.join("; "))}\nexcluded: ${esc(p.excluded.join("; "))}</div>
  <div class="row" style="margin-top:12px"><button class="btn pp" onclick="document.querySelector('[data-v=claim]').click()">Insure it with PayPal</button></div>`;
}

// ---------- adversary ----------
const FAILS = [];
$("#bAdv").onclick = async () => {
  const b = $("#bAdv"); busy(b, true, "Adversary thinking…");
  const log = $("#advLog");
  try {
    const { job } = await api("/api/adversary", { name: mission().name, n: window.__fast ? 2 : 3 });
    await poll(job, e => {
      const a = e.attack;
      const isIdea = /^Testing:/.test(e.msg);
      log.insertAdjacentHTML("afterbegin", `<div class="ev ${a ? (a.confirmed ? "hit" : "ok") : ""} ${isIdea ? "idea" : ""}"><div class="t">${esc(e.t)}</div><span class="msg">${isIdea ? "" : esc(e.msg)}</span>${a ? `<div class="fine mono">search ${a.curve.map(c => Math.round(c.best * 100) + "%").join(" → ")} · plausibility cost ${a.deviation}</div>` : ""}</div>`);
      if (isIdea) typeText(log.querySelector(".ev .msg"), "Idea: " + e.msg.replace(/^Testing:\s*/, ""));
      if (a && a.confirmed) { FAILS.unshift(a); renderFails(); Flow.light("attack"); }
    });
  } catch (e) { log.insertAdjacentHTML("afterbegin", `<div class="ev hit">${esc(e.message)}</div>`); } finally { busy(b, false); }
};
async function typeText(el, text) { if (!el) return; el.textContent = ""; for (const ch of text) { el.textContent += ch; await new Promise(r => setTimeout(r, 16)); } }
function renderFails() {
  $("#fails").innerHTML = FAILS.map((f, i) => `<div class="fcard" data-i="${i}"><h3>${esc(f.name)}</h3><p>${esc(f.describe)}</p><p style="margin-top:6px"><span class="pill bad">${Math.round(f.confirmed_rate * 100)}% fail</span> <span class="fine">${esc(Object.keys(f.modes).join(", "))} · robot ${esc(f.robot)}</span></p></div>`).join("") || '<div class="fine">None yet.</div>';
  document.querySelectorAll(".fcard").forEach(c => c.onclick = () => { const f = FAILS[+c.dataset.i]; if (f.clip) { document.querySelector("[data-v=under]").click(); play(f.clip, "✕ " + f.describe); } });
}
renderFails();

// ---------- retrain ----------
$("#bTrain").onclick = async () => {
  const b = $("#bTrain"); busy(b, true, "Training…");
  const log = $("#trainLog");
  try {
    const { job } = await api("/api/retrain" + (window.__fast ? "?gens=4" : ""), {});
    const r = await poll(job, e => log.insertAdjacentHTML("afterbegin", `<div class="ev ${/^FAIL|rejected/.test(e.msg) ? "hit" : /PASS|passed/.test(e.msg) ? "ok" : ""}"><div class="t">${esc(e.t)}</div>${esc(e.msg)}</div>`));
    $("#gate").innerHTML = `<div style="margin-bottom:8px">${r.accepted ? '<span class="pill ok">ACCEPTED</span>' : '<span class="pill bad">REJECTED</span>'} live robot: <b>${esc(r.live)}</b></div>` +
      r.checks.map(c => `<div class="ev ${c.ok ? "ok" : "hit"}">${c.ok ? "✓" : "✕"} ${esc(c.check)}<div class="fine mono">${esc(c.before)} → ${esc(c.after)}</div></div>`).join("");
    const s = await api("/api/status"); S.robot = s.robot; $("#cRobot").innerHTML = "robot <b>" + esc(s.robot) + "</b>";
    if (r.accepted) { Replay.version(V, s.robot); Flow.light("train"); }
    loadVersions();
  } catch (e) { log.insertAdjacentHTML("afterbegin", `<div class="ev hit">${esc(e.message)}</div>`); } finally { busy(b, false); }
};
async function loadVersions() { const L = await api("/api/ledger"); $("#versions").innerHTML = L.versions.map(v => `<div class="ev"><b>${esc(v.version)}</b> <span class="fine">${esc(v.created)} · speed ×${v.speed_scale} · heading ${v.k_heading} · tilt brake ${v.tilt_brake} · traction ${v.slip_ctrl} · stall boost ${v.stall_boost}</span></div>`).join(""); }
loadVersions();

// ---------- policy & claims ----------
$("#bBuy").onclick = async () => {
  if (!QUOTE || QUOTE.policy.mission !== mission().name) { note("Underwrite this mission first (tab 1)."); return; }
  const b = $("#bBuy"); busy(b, true, "Creating PayPal order…");
  try { POLICY = await api("/api/buy", { name: mission().name, operator_email: $("#opEmail").value, server_side: !!window.__serverPay }); renderPolicy(); Flow.light("order"); }
  catch (e) { note(e.message); } finally { busy(b, false); }
};
function renderPolicy() {
  const p = POLICY, o = p.order;
  $("#polBox").innerHTML = `<div class="ev"><b>${esc(p.id)}</b> · ${esc(p.mission)} · premium <b>${money(p.policy.premium)}</b> for ${money(p.policy.cover)} cover<br>
   PayPal order <span class="mono">${esc(o.id)}</span> · ${esc(o.mode)} · status <b>${esc(p.status)}</b></div>
   ${p.status === "awaiting approval" ? `<div class="row" style="margin-top:8px"><a class="btn pp" href="${esc(o.approve_url)}" target="_blank" rel="noopener">Approve in PayPal</a><button class="btn ghost" id="bCap">I’ve approved it</button></div>` : ""}
   ${p.capture ? `<div class="fine" style="margin-top:6px">captured: ${esc(p.capture.capture_id || "")} (${esc(p.capture.status)})</div>` : ""}`;
  const c = $("#bCap"); if (c) c.onclick = async () => { busy(c, true, "Capturing…"); try { POLICY = await api("/api/capture", { order_id: o.id }); renderPolicy(); Flow.light("cover"); } catch (e) { note(e.message); busy(c, false); } };
  $("#bRun").disabled = p.status !== "active";
}
function overrides() {
  const o = {}; if ($("#rWeather").value) o.weather = $("#rWeather").value; if ($("#rBump").value !== "") o.bump = +$("#rBump").value;
  if ($("#rCargo").value) o.cargo_kg = +$("#rCargo").value; if ($("#rSpeed").value) o.speed = +$("#rSpeed").value; return o;
}
$("#bRun").onclick = async () => {
  const b = $("#bRun"); busy(b, true, "Driving…");
  try {
    const seed = $("#rSeed").value ? +$("#rSeed").value : Math.floor(Math.random() * 9000);
    LASTRUN = { seed, ...overrides() };
    const r = await api("/api/run", { policy_id: POLICY.id, ...LASTRUN });
    document.querySelector("[data-v=under]").click(); play(r); Flow.light("job");
    setTimeout(() => document.querySelector("[data-v=claim]").click(), Math.min(9000, r.frames.length * 34 + 1200));
    $("#runOut").innerHTML = `<div class="ev ${r.failed ? "hit" : "ok"}">${r.failed ? "✕" : "✓"} <b>${esc(r.outcome.replace("_", " "))}</b> at ${r.t}s · seed ${r.seed}<div class="fine">${esc(r.describe || "clear day")}</div></div>`;
    $("#bClaim").disabled = !r.failed;
  } catch (e) { note(e.message); } finally { busy(b, false); }
};
$("#bClaim").onclick = async () => {
  const b = $("#bClaim"); busy(b, true, "Replaying counterfactuals…");
  try {
    const c = await api("/api/claim", { policy_id: POLICY.id, ...LASTRUN });
    $("#claimCard").classList.remove("hidden");
    const ok = c.decision === "APPROVED"; Flow.light("replay"); if (ok) Flow.light("payout");
    $("#claimOut").innerHTML = `<div class="row"><span class="pill ${ok ? "ok" : "bad"}" style="font-size:15px">${esc(c.decision)}</span><b>${esc(c.reason)}</b></div>
     <table class="cf" style="margin-top:10px"><tr><th>Same run, without this</th><th>Covered?</th><th>Result</th></tr>
     ${c.tests.map(t => `<tr><td>${esc(t.remove)}</td><td>${t.kind === "covered" ? '<span class="pill ok">covered</span>' : '<span class="pill warn">excluded</span>'}</td><td>${t.saved ? '<span class="pill ok">would have delivered</span>' : '<span class="pill bad">' + esc(t.outcome.replace("_", " ")) + "</span>"}</td></tr>`).join("")}</table>
     <div class="ev" style="margin-top:10px"><b>Note to the operator</b> <span class="fine">(${esc(c.note.engine)})</span><br>${esc(c.note.text)}</div>
     ${c.payout && c.payout.amount ? `<div class="ev ok" style="margin-top:8px">PayPal payout <b>${money(c.payout.amount)}</b> to ${esc(POLICY.operator_email)} · batch <span class="mono">${esc(c.payout.batch_id || c.payout.error)}</span> · ${esc(c.payout.status || "")} ${esc(c.payout.mode || "")}</div>` : ""}`;
    POLICY.status = c.decision === "APPROVED" ? "claimed" : POLICY.status; renderPolicy();
  } catch (e) { note(e.message); } finally { busy(b, false); }
};
if (location.search.includes("paid=1")) {
  // PayPal sends the buyer back here after approval. If the demo opened this as a popup, close it so the demo stays in front.
  if (window.opener) { try { window.opener.focus(); } catch (e) {} window.close(); }
  document.querySelector("[data-v=claim]").click();
}

// ---------- ledger (AG Grid) ----------
const THEME = window.agGrid ? agGrid.themeQuartz.withParams({ backgroundColor: "#0d121c", foregroundColor: "#e9eef7", headerBackgroundColor: "#131a27", borderColor: "#1e2839", accentColor: "#ff8a3d", oddRowBackgroundColor: "#0f1520", fontFamily: "Inter", fontSize: 13, browserColorScheme: "dark" }) : null;
const G = {};
function grid(id, cols, rows) { if (!window.agGrid) return; if (G[id]) { G[id].setGridOption("rowData", rows); return; }
  G[id] = agGrid.createGrid($(id), { theme: THEME, columnDefs: cols, rowData: rows, defaultColDef: { sortable: true, filter: true, resizable: true, flex: 1, minWidth: 100 }, animateRows: true }); }
const usd = p => p.value == null ? "" : "$" + (+p.value).toFixed(2), pc = p => p.value == null ? "" : (p.value * 100).toFixed(1) + "%";
async function loadLedger() {
  const L = await api("/api/ledger");
  grid("#gPol", [{ field: "id" }, { field: "mission", minWidth: 180 }, { field: "robot" }, { field: "p_fail", headerName: "P(fail)", valueFormatter: pc }, { field: "premium", valueFormatter: usd }, { field: "cover", valueFormatter: usd }, { field: "status" }, { field: "paypal_order", headerName: "PayPal order" }, { field: "created" }], L.policies);
  grid("#gCl", [{ field: "id" }, { field: "policy" }, { field: "outcome" }, { field: "decision" }, { field: "reason", minWidth: 320 }, { field: "payout", valueFormatter: usd }, { field: "paypal_batch", headerName: "PayPal payout batch" }, { field: "created" }], L.claims);
  grid("#gAtk", [{ field: "id", maxWidth: 110 }, { field: "robot", maxWidth: 90 }, { field: "name" }, { field: "hypothesis", minWidth: 260 }, { field: "minimal", headerName: "minimal failure", minWidth: 280 }, { field: "found", valueFormatter: pc }, { field: "confirmed", headerName: "confirmed (fresh seeds)", valueFormatter: pc }, { field: "modes" }, { field: "deviation", headerName: "plausibility cost" }, { field: "engine" }], L.attacks);
  grid("#gVer", [{ field: "version" }, { field: "created" }, { field: "speed_scale" }, { field: "k_heading" }, { field: "tilt_brake" }, { field: "slip_ctrl", headerName: "traction" }, { field: "stall_boost" }, { field: "gauntlet", headerName: "gauntlet fail", valueFormatter: pc }], L.versions);
}
$("#bCsv").onclick = () => G["#gPol"] && G["#gPol"].exportDataAsCsv({ fileName: "hazardpay-policies.csv" });

boot();
