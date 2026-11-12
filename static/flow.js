// The "how it all connects" pipeline: an animated flow diagram. Flow.mount(el), Flow.light(id).
window.Flow = (function () {
  const N = [
    { id: "route", x: 70, y: 112, t: ["The route", "curb, slope, weather"] },
    { id: "sim", x: 245, y: 112, t: ["Physics twin", "MuJoCo"] },
    { id: "days", x: 420, y: 112, t: ["120 test days", "how often it fails"] },
    { id: "price", x: 595, y: 112, t: ["The price", "risk × cover"] },
    { id: "order", x: 770, y: 112, t: ["PayPal order", "customer pays"] },
    { id: "cover", x: 945, y: 112, t: ["Cover is on", "signed policy"] },
    { id: "job", x: 1120, y: 112, t: ["Delivery day", "the real run"] },
    { id: "replay", x: 1295, y: 112, t: ["Replay", "what caused it?"] },
    { id: "payout", x: 1470, y: 112, t: ["PayPal payout", "to the operator"] },
    { id: "attack", x: 332, y: 30, t: ["Gemini attacks", "finds weak spots"] },
    { id: "train", x: 507, y: 30, t: ["Practise + check", "safer → cheaper"] },
  ];
  const E = [["route", "sim"], ["sim", "days"], ["days", "price"], ["price", "order"], ["order", "cover"], ["cover", "job"], ["job", "replay"], ["replay", "payout"],
             ["sim", "attack"], ["attack", "train"], ["train", "price"]];
  const pay = new Set(["order", "payout"]);
  let svg = null;
  const pos = id => N.find(n => n.id === id);
  function mount(el, compact) {
    const h = 160;
    let s = `<svg viewBox="-12 0 1580 ${h}" width="100%" style="display:block" aria-label="How Hazard Pay connects the robot simulation to PayPal">
    <defs><filter id="fg"><feGaussianBlur stdDeviation="3"/></filter></defs>`;
    for (const [a, b] of E) {
      const A = pos(a), B = pos(b);
      const d = A.y === B.y ? `M${A.x + 75},${A.y} L${B.x - 75},${B.y}` : `M${A.x + (B.x > A.x ? 40 : 0)},${A.y + (B.y > A.y ? 20 : -20)} C${(A.x + B.x) / 2},${(A.y + B.y) / 2} ${(A.x + B.x) / 2},${(A.y + B.y) / 2} ${B.x - (B.x > A.x ? 40 : 0)},${B.y + (B.y > A.y ? -22 : 22)}`;
      s += `<path id="e-${a}-${b}" d="${d}" fill="none" stroke="#2a3548" stroke-width="2.5" stroke-dasharray="${A.y === B.y ? "0" : "5 5"}"/>`;
    }
    for (const n of N) {
      const c = pay.has(n.id) ? "#ffc439" : n.id === "attack" ? "#ff8a3d" : "#4fe3d1";
      s += `<g id="n-${n.id}" class="fn" data-c="${c}" opacity=".55">
        <rect x="${n.x - 75}" y="${n.y - 24}" width="150" height="48" rx="10" fill="#0f1522" stroke="${c}" stroke-width="1.5"/>
        <text x="${n.x}" y="${n.y - 3}" text-anchor="middle" fill="#e9eef7" font-family="Inter" font-size="15" font-weight="600">${n.t[0]}</text>
        <text x="${n.x}" y="${n.y + 13}" text-anchor="middle" fill="#8e9bb1" font-family="Inter" font-size="12">${n.t[1]}</text></g>`;
    }
    s += `<g id="pulses"></g></svg>`;
    el.innerHTML = s;
    svg = el.querySelector("svg");
  }
  function light(id, on = true) {
    if (!svg) return;
    const g = svg.querySelector("#n-" + id); if (!g) return;
    g.setAttribute("opacity", on ? "1" : ".55");
    g.querySelector("rect").setAttribute("fill", on ? "#17233a" : "#0f1522");
    if (on) {
      g.querySelector("rect").animate([{ strokeWidth: 1.5 }, { strokeWidth: 5 }, { strokeWidth: 2.5 }], { duration: 700 });
      for (const [a, b] of E) if (b === id) pulse(`e-${a}-${b}`, g.dataset.c);
    }
  }
  function pulse(pathId, color) {
    const p = svg.querySelector("#" + pathId); if (!p) return;
    p.setAttribute("stroke", color); p.setAttribute("stroke-opacity", ".8");
    const L = p.getTotalLength();
    for (let k = 0; k < 3; k++) {
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("r", "5"); c.setAttribute("fill", color); svg.querySelector("#pulses").appendChild(c);
      const t0 = performance.now() + k * 180;
      (function step(now) {
        const u = Math.min(1, Math.max(0, (now - t0) / 700)); const pt = p.getPointAtLength(u * L);
        c.setAttribute("cx", pt.x); c.setAttribute("cy", pt.y);
        if (u < 1) requestAnimationFrame(step); else c.remove();
      })(performance.now());
    }
  }
  function reset() { if (svg) N.forEach(n => light(n.id, false)); }
  return { mount, light, reset, nodes: N };
})();
