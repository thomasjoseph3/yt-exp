// Thoma Explains: scene templates + a paused GSAP timeline that Python seeks frame by frame.
//
// Python calls  await load(DATA)  once, then  seek(t)  before every screenshot.
// Each visual type below is a builder. To add a new look, add a builder and list its
// reveal order in thoma/visuals.py (elements()) so narration timing lines up.

const COLORS = ["--cyan", "--violet", "--amber", "--pink", "--green", "--blue"];
const col = (i) => `var(${COLORS[i % COLORS.length]})`;
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const hex = (i) => css(COLORS[i % COLORS.length]);

let D, tl, tickers = [], mascot, capEl, lastCap = "", cuts = [];

function h(tag, cls, parent, styles = {}, html = "") {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  Object.assign(e.style, styles);
  if (html) e.innerHTML = html;
  if (parent) parent.appendChild(e);
  return e;
}

function icon(name, size, color, parent, styles = {}) {
  const box = h("div", "icon", parent, Object.assign({
    width: size + "px", height: size + "px", color,
    background: `color-mix(in srgb, ${color} 16%, transparent)`,
    border: `2px solid color-mix(in srgb, ${color} 45%, transparent)`,
    boxShadow: `0 0 34px color-mix(in srgb, ${color} 30%, transparent)`,
  }, styles));
  box.innerHTML = D.icons[name] || D.icons["sparkles"] || "";
  return box;
}

// *word* in text -> highlighted span
function marked(text) {
  return String(text || "").split(/(\*[^*]+\*)/).map(part =>
    part.startsWith("*") && part.endsWith("*") ? `<span class="hl">${esc(part.slice(1, -1))}</span>` : esc(part)).join("");
}
function words(text) {
  const out = [];
  String(text || "").split(/(\*[^*]+\*)/).forEach(part => {
    const hl = part.startsWith("*") && part.endsWith("*");
    (hl ? part.slice(1, -1) : part).split(/\s+/).filter(Boolean).forEach(w => {
      if (/^[^\w]+$/.test(w) && out.length) out[out.length - 1].w += w;  // keep "?" with its word
      else out.push({ w, hl });
    });
  });
  return out;
}
function esc(s) { return String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

// Shrink font until the element fits its box.
function fit(el, maxW, maxH, start, min = 18) {
  let size = start;
  el.style.fontSize = size + "px";
  el.style.maxWidth = maxW + "px";
  if (el.style.left === "0px" || el.className.includes("heading") || el.className.includes("big")) {
    el.style.marginLeft = "auto"; el.style.marginRight = "auto";
  }
  while (size > min && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > maxH + 1)) {
    size -= 2;
    el.style.fontSize = size + "px";
  }
  return size;
}

function popIn(el, at, extra = {}) {
  tl.fromTo(el, { opacity: 0, scale: 0.6, y: 30 }, Object.assign({ opacity: 1, scale: 1, y: 0, duration: 0.5, ease: "back.out(1.7)" }, extra), at);
}
function slideIn(el, at, from = { x: -60 }) {
  tl.fromTo(el, Object.assign({ opacity: 0 }, from), { opacity: 1, x: 0, y: 0, duration: 0.45, ease: "power3.out" }, at);
}
function wordsIn(container, list, at, size) {
  container.innerHTML = "";
  const spans = list.map(({ w, hl }) => h("span", "w" + (hl ? " hl" : ""), container, {}, esc(w)));
  tl.fromTo(spans, { opacity: 0, y: size * 0.5 }, { opacity: 1, y: 0, duration: 0.4, ease: "power3.out", stagger: 0.06 }, at);
  return spans;
}
function heading(scene, text, box, at, size = 54) {
  if (!text) return 0;
  const el = h("div", "heading", scene, { top: "0px" }, marked(text));
  const s = fit(el, box.w * 0.95, size * 1.4, size);
  slideIn(el, at, { y: -30 });
  return s * 1.6;
}

// ---------- builders: (scene, v, box, reveals, start, end) ----------
const B = {};

B.title = (scene, v, box, R) => {
  const ic = icon(v.icon || "sparkles", 170, col(0), scene, { position: "absolute", left: box.w / 2 - 85 + "px", top: box.h * 0.12 + "px" });
  popIn(ic, R[0]);
  const t = h("div", "big", scene, { top: box.h * 0.38 + "px" });
  t.innerHTML = marked(v.text);
  const size = fit(t, box.w * 0.92, box.h * 0.36, 104, 40);
  wordsIn(t, words(v.text), R[1], size);
  if (v.sub) {
    const s = h("div", "sub", scene, { position: "absolute", left: "5%", right: "5%", top: box.h * 0.8 + "px" }, esc(v.sub));
    fit(s, box.w * 0.9, 120, 42);
    slideIn(s, R[2] ?? R[1] + 0.5, { y: 30 });
  }
};

B.bigtext = (scene, v, box, R) => {
  const t = h("div", "big", scene, {});
  t.innerHTML = marked(v.text);
  const size = fit(t, box.w * 0.92, box.h * 0.55, 120, 40);
  t.style.top = (box.h * (v.sub ? 0.42 : 0.5) - t.scrollHeight / 2) + "px";
  const spans = wordsIn(t, words(v.text), R[0], size);
  const hl = spans.filter(s => s.classList.contains("hl"));
  if (hl.length) {
    tl.add(() => {}, R[0]);
    const first = hl[0], last = hl[hl.length - 1];
    const u = h("div", "underline", t, {});
    const place = () => {
      u.style.left = first.offsetLeft + "px";
      u.style.top = first.offsetTop + first.offsetHeight * 0.92 + "px";
      u.style.width = (last.offsetLeft + last.offsetWidth - first.offsetLeft) + "px";
    };
    place();
    tl.fromTo(u, { scaleX: 0 }, { scaleX: 1, duration: 0.45, ease: "power2.out" }, R[0] + 0.5);
  }
  if (v.sub) {
    const s = h("div", "sub", scene, { position: "absolute", left: "5%", right: "5%", top: box.h * 0.74 + "px" }, esc(v.sub));
    fit(s, box.w * 0.9, 130, 44);
    slideIn(s, R[1] ?? R[0] + 0.8, { y: 30 });
  }
};

B.stat = (scene, v, box, R) => {
  const m = String(v.value).match(/^([^0-9]*)([0-9][0-9,.]*)(.*)$/);
  const el = h("div", "big", scene, { top: box.h * 0.2 + "px", fontSize: "220px",
    background: "linear-gradient(90deg, var(--cyan), var(--violet))", webkitBackgroundClip: "text", color: "transparent" }, esc(v.value));
  fit(el, box.w * 0.9, box.h * 0.42, 230, 60);
  popIn(el, R[0]);
  if (m) {
    const target = parseFloat(m[2].replace(/,/g, "")), dec = (m[2].split(".")[1] || "").length, obj = { n: 0 };
    tl.to(obj, { n: target, duration: 1.2, ease: "power2.out", onUpdate: () => {
      el.textContent = m[1] + obj.n.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + m[3];
    } }, R[0]);
  }
  const l = h("div", "label", scene, { position: "absolute", left: "5%", right: "5%", top: box.h * 0.66 + "px" }, marked(v.label));
  fit(l, box.w * 0.9, box.h * 0.25, 56);
  slideIn(l, R[1] ?? R[0] + 0.6, { y: 30 });
};

function layoutNodes(v, box, top, portrait) {
  const n = v.nodes.length;
  let layout = v.layout || "row";
  if (portrait && layout === "row" && n >= 3) layout = "stack";
  if (!portrait && layout === "stack" && n <= 4) layout = "row";
  const area = { x: 0, y: top, w: box.w, h: box.h - top };
  const rects = [];
  if (layout === "row") {
    const gap = Math.max(70, area.w * 0.07);
    const w = Math.min(portrait ? 290 : 340, (area.w - gap * (n - 1)) / n), hh = Math.min(w * 0.85, area.h * 0.8);
    const x0 = (area.w - (w * n + gap * (n - 1))) / 2;
    for (let i = 0; i < n; i++) rects.push({ x: x0 + i * (w + gap), y: area.y + (area.h - hh) / 2, w, h: hh });
  } else if (layout === "stack") {
    const gap = Math.max(46, area.h * 0.06);
    const hh = Math.min(170, (area.h - gap * (n - 1)) / n), w = Math.min(area.w * 0.78, 640);
    const y0 = area.y + (area.h - (hh * n + gap * (n - 1))) / 2;
    for (let i = 0; i < n; i++) rects.push({ x: (area.w - w) / 2, y: y0 + i * (hh + gap), w, h: hh });
  } else if (layout === "grid") {
    const cols = n <= 4 ? 2 : 3, rows = Math.ceil(n / cols), gap = 60;
    const w = Math.min(portrait ? 400 : 330, (area.w - gap * (cols - 1)) / cols), hh = Math.min(w * 0.75, (area.h - gap * (rows - 1)) / rows);
    const x0 = (area.w - (w * cols + gap * (cols - 1))) / 2, y0 = area.y + (area.h - (hh * rows + gap * (rows - 1))) / 2;
    for (let i = 0; i < n; i++) rects.push({ x: x0 + (i % cols) * (w + gap), y: y0 + Math.floor(i / cols) * (hh + gap), w, h: hh });
  } else { // hub or cycle
    const cx = area.w / 2, cy = area.y + area.h / 2;
    const rx = area.w * (portrait ? 0.29 : 0.38), ry = area.h * (portrait ? 0.32 : 0.34);
    const w = Math.min(portrait ? 340 : 300, area.w * (portrait ? 0.38 : 0.27)), hh = w * (portrait ? 0.7 : 0.75);
    const ring = layout === "hub" ? n - 1 : n;
    if (layout === "hub") rects.push({ x: cx - w * 0.6, y: cy - hh * 0.6, w: w * 1.2, h: hh * 1.2 });
    for (let i = 0; i < ring; i++) {
      const a = -Math.PI / 2 + (2 * Math.PI * i) / ring;
      rects.push({ x: cx + rx * Math.cos(a) - w / 2, y: cy + ry * Math.sin(a) - hh / 2, w, h: hh });
    }
  }
  let edges = v.edges;
  if (!edges || !edges.length) {
    edges = [];
    if (layout === "hub") for (let i = 1; i < n; i++) edges.push({ from: 0, to: i });
    else if (layout === "cycle") for (let i = 0; i < n; i++) edges.push({ from: i, to: (i + 1) % n });
    else if (layout !== "grid") for (let i = 0; i + 1 < n; i++) edges.push({ from: i, to: i + 1 });
  }
  return { rects, edges, layout };
}

function edgePoint(r, toward) {
  const cx = r.x + r.w / 2, cy = r.y + r.h / 2, dx = toward.x - cx, dy = toward.y - cy;
  const s = Math.min(Math.abs((r.w / 2 + 14) / (dx || 1e-6)), Math.abs((r.h / 2 + 14) / (dy || 1e-6)));
  return { x: cx + dx * s, y: cy + dy * s };
}

B.diagram = (scene, v, box, R, start, end, portrait) => {
  v.nodes = (v.nodes || []).slice(0, 6).map(n => typeof n === "string" ? { label: n } : n);
  const top = heading(scene, v.heading, box, start + 0.1);
  const ids = Object.fromEntries(v.nodes.map((n, i) => [n.id ?? i, i]));
  const { rects, edges } = layoutNodes(v, box, top, portrait);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "edges");
  scene.appendChild(svg);
  const nodeEls = v.nodes.map((n, i) => {
    const r = rects[i], wide = r.w / r.h > 1.8;
    const card = h("div", "card", scene, { left: r.x + "px", top: r.y + "px", width: r.w + "px", height: r.h + "px",
      display: "flex", flexDirection: wide ? "row" : "column", alignItems: "center", justifyContent: wide ? "flex-start" : "center",
      gap: wide ? "26px" : "14px", padding: wide ? "0 30px" : "18px" });
    const isz = Math.min(r.h * (wide ? 0.62 : 0.42), 110);
    icon(n.icon || "box", isz, col(i), card, { flexShrink: 0 });
    const txt = h("div", "", card, { display: "flex", flexDirection: "column", gap: "6px", alignItems: wide ? "flex-start" : "center", minWidth: 0 });
    const lab = h("div", "label", txt, { textAlign: wide ? "left" : "center" }, esc(n.label));
    const availW = wide ? r.w - isz - 90 : r.w - 30;
    fit(lab, availW, r.h * (n.sub ? 0.28 : 0.4), wide ? 44 : 38, 18);
    if (n.sub) {
      const s = h("div", "sub", txt, { textAlign: wide ? "left" : "center" }, esc(n.sub));
      fit(s, availW, r.h * 0.22, 26, 14);
    }
    popIn(card, R[i] ?? start + 0.3 + i * 0.4);
    return card;
  });
  edges.forEach((e, k) => {
    const a = ids[e.from] ?? e.from, b = ids[e.to] ?? e.to;
    if (rects[a] == null || rects[b] == null) return;
    const ca = { x: rects[a].x + rects[a].w / 2, y: rects[a].y + rects[a].h / 2 };
    const cb = { x: rects[b].x + rects[b].w / 2, y: rects[b].y + rects[b].h / 2 };
    const p = edgePoint(rects[a], cb), q = edgePoint(rects[b], ca);
    const color = hex(a);
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", `M${p.x},${p.y} L${q.x},${q.y}`);
    path.setAttribute("class", "edge");
    path.setAttribute("stroke", color);
    path.setAttribute("opacity", "0.8");
    svg.appendChild(path);
    const len = Math.hypot(q.x - p.x, q.y - p.y);
    const ang = Math.atan2(q.y - p.y, q.x - p.x);
    const head = document.createElementNS(svg.namespaceURI, "path");
    const hx = q.x, hy = q.y, s = 18;
    head.setAttribute("d", `M${hx},${hy} L${hx - s * Math.cos(ang - 0.45)},${hy - s * Math.sin(ang - 0.45)} L${hx - s * Math.cos(ang + 0.45)},${hy - s * Math.sin(ang + 0.45)} Z`);
    head.setAttribute("fill", color);
    svg.appendChild(head);
    const at = Math.max(R[a] ?? start, R[b] ?? start) + 0.25;
    path.style.strokeDasharray = len;
    tl.fromTo(path, { strokeDashoffset: len }, { strokeDashoffset: 0, duration: 0.5, ease: "power2.inOut" }, at);
    tl.fromTo(head, { opacity: 0 }, { opacity: 1, duration: 0.15 }, at + 0.4);
    const dots = [0, 0.5].map(() => {
      const c = document.createElementNS(svg.namespaceURI, "circle");
      c.setAttribute("r", 8); c.setAttribute("fill", color); c.setAttribute("class", "packet");
      c.style.color = color; c.style.opacity = 0;
      svg.appendChild(c);
      return c;
    });
    tickers.push((t) => {
      const on = t > at + 0.55 && t < end + 0.2;
      dots.forEach((c, j) => {
        c.style.opacity = on ? 1 : 0;
        if (!on) return;
        const d = (((t - at) * 240) / len + j * 0.5) % 1;
        c.setAttribute("cx", p.x + (q.x - p.x) * d);
        c.setAttribute("cy", p.y + (q.y - p.y) * d);
      });
    });
    if (e.label) {
      const lab = h("div", "edge-label", scene, { left: (p.x + q.x) / 2 + "px", top: (p.y + q.y) / 2 - 30 + "px", fontSize: "22px" }, esc(e.label));
      tl.fromTo(lab, { opacity: 0 }, { opacity: 1, duration: 0.3 }, at + 0.4);
    }
  });
  const hi = v.highlight != null ? ids[v.highlight] ?? v.highlight : null;
  if (hi != null && rects[hi]) {
    const r = rects[hi];
    const ring = h("div", "ring", scene, { left: r.x - 12 + "px", top: r.y - 12 + "px", width: r.w + 24 + "px", height: r.h + 24 + "px" });
    const at = Math.max(Math.max(...R.filter(x => x != null)) + 0.9, start + (end - start) * 0.6);
    tl.fromTo(ring, { opacity: 0, scale: 1.15 }, { opacity: 1, scale: 1, duration: 0.4, ease: "power2.out" }, at);
    tl.to(nodeEls[hi], { scale: 1.06, duration: 0.4, yoyo: true, repeat: 1 }, at);
  }
};

B.steps = (scene, v, box, R, start, end, portrait) => {
  const items = (v.items || []).slice(0, 5).map(x => typeof x === "string" ? { text: x } : x);
  const top = heading(scene, v.heading, box, start + 0.1);
  const n = items.length, gap = 26;
  const hh = Math.min(portrait ? 165 : 130, (box.h - top - gap * (n - 1)) / n);
  const w = Math.min(box.w * 0.9, 1100), x = (box.w - w) / 2;
  const y0 = top + (box.h - top - (hh * n + gap * (n - 1))) / 2;
  items.forEach((it, i) => {
    const card = h("div", "card", scene, { left: x + "px", top: y0 + i * (hh + gap) + "px", width: w + "px", height: hh + "px",
      display: "flex", alignItems: "center", gap: "28px", padding: "0 30px" });
    const sz = hh * 0.62;
    if (v.numbered === false || it.icon) icon(it.icon || "check", sz, col(i), card, { flexShrink: 0 });
    else h("div", "icon", card, { width: sz + "px", height: sz + "px", flexShrink: 0, background: col(i), color: "#0a0f1f",
      fontWeight: 900, fontSize: sz * 0.5 + "px" }, String(i + 1));
    const t = h("div", "label", card, { textAlign: "left" }, marked(it.text));
    fit(t, w - sz - 100, hh * 0.85, portrait ? 46 : 44, 20);
    slideIn(card, R[i] ?? start + 0.3 + i * 0.5);
  });
};

B.compare = (scene, v, box, R, start, end, portrait) => {
  const top = heading(scene, v.heading, box, start + 0.1);
  const gap = portrait ? 90 : 120;
  const cw = portrait ? box.w * 0.9 : (box.w - gap) / 2 * 0.95;
  const ch = portrait ? (box.h - top - gap) / 2 : box.h - top - 20;
  ["left", "right"].forEach((side, k) => {
    const sd = v[side] || {};
    const x = portrait ? (box.w - cw) / 2 : (k ? box.w / 2 + gap / 2 : box.w / 2 - gap / 2 - cw);
    const y = portrait ? top + k * (ch + gap) : top + 10;
    const card = h("div", "card", scene, { left: x + "px", top: y + "px", width: cw + "px", height: ch + "px",
      padding: "26px 30px", display: "flex", flexDirection: "column", gap: "16px", borderColor: k ? "rgba(244,114,182,0.5)" : "rgba(34,211,238,0.5)" });
    const head = h("div", "", card, { display: "flex", alignItems: "center", gap: "18px" });
    icon(sd.icon || (k ? "x" : "check"), portrait ? 76 : 84, k ? "var(--pink)" : "var(--cyan)", head, { flexShrink: 0 });
    const lab = h("div", "label", head, { textAlign: "left" }, esc(sd.label || ""));
    fit(lab, cw - 160, 110, 46, 22);
    const items = (sd.items || []).slice(0, 4);
    const rowH = (ch - (portrait ? 110 : 130)) / Math.max(items.length, 1);
    items.forEach((it, j) => {
      const row = h("div", "sub", card, { textAlign: "left", color: "var(--text)", display: "flex", gap: "12px", alignItems: "center" },
        `<span style="color:${k ? "var(--pink)" : "var(--cyan)"}">●</span><span>${esc(it)}</span>`);
      fit(row, cw - 70, Math.min(rowH, 110), portrait ? 38 : 36, 18);
      tl.fromTo(row, { opacity: 0, x: -20 }, { opacity: 1, x: 0, duration: 0.35 }, (R[k] ?? start + 0.4) + 0.35 + j * 0.25);
    });
    popIn(card, R[k] ?? start + 0.4 + k * 1.2, { duration: 0.45 });
  });
  const vs = h("div", "vs", scene, { width: "96px", height: "96px", fontSize: "38px",
    left: box.w / 2 + "px", top: (portrait ? top + ch + gap / 2 : top + 10 + ch / 2) + "px" }, "VS");
  popIn(vs, (R[1] ?? start + 1) - 0.2);
};

B.code = (scene, v, box, R, start, end) => {
  const lines = (v.lines || []).slice(0, 12);
  const top = heading(scene, v.heading, box, start + 0.1, 48);
  const hasOut = v.output && v.output.length;
  const ew = Math.min(box.w * 0.94, 1150);
  const maxLen = Math.max(...lines.map(l => l.length), 10);
  const fs = Math.min(48, (ew - 70) / (maxLen * 0.61), ((box.h - top) * (hasOut ? 0.68 : 0.95) - 110) / (lines.length * 1.5));
  const eh = Math.min((box.h - top) * (hasOut ? 0.68 : 0.95), lines.length * fs * 1.5 + 120);
  const ed = h("div", "editor", scene, { left: (box.w - ew) / 2 + "px", top: top + "px", width: ew + "px", height: eh + "px" });
  h("div", "bar", ed, {}, `<i style="background:#ff5f57"></i><i style="background:#febc2e"></i><i style="background:#28c840"></i><span>${esc(v.file || ({ python: "main.py", javascript: "index.js", bash: "terminal", sql: "query.sql" }[v.lang] || "code"))}</span>`);
  const code = h("div", "code", ed);
  code.style.fontSize = fs + "px";
  code.style.lineHeight = "1.5";
  popIn(ed, start + 0.15, { duration: 0.4, ease: "power3.out" });
  lines.forEach((ln, i) => {
    const el = h("div", "line", code);
    let html = esc(ln) || " ";
    try { if (window.hljs && v.lang) html = hljs.highlight(ln, { language: v.lang, ignoreIllegals: true }).value || " "; } catch (e) {}
    el.innerHTML = html;
    const at = R[i] ?? start + 0.5 + i * 0.4;
    const dur = Math.min(0.9, 0.03 * Math.max(ln.length, 1));
    tl.fromTo(el, { width: "0ch" }, { width: (ln.length + 1) + "ch", duration: dur, ease: `steps(${Math.max(ln.length, 1)})` }, at);
  });
  if (hasOut) {
    const t = h("div", "term", scene, { left: (box.w - ew) / 2 + "px", top: top + eh + 24 + "px", width: ew + "px",
      fontSize: Math.min(fs, 32) + "px", lineHeight: 1.45 }, esc("$ run\n" + v.output.slice(0, 4).join("\n")));
    slideIn(t, R[lines.length] ?? end - 1.5, { y: 30 });
  }
};

B.analogy = (scene, v, box, R, start, end, portrait) => {
  const L = v.left || {}, Rt = v.right || {};
  const cw = portrait ? box.w * 0.8 : box.w * 0.36, ch = portrait ? box.h * 0.36 : box.h * 0.62;
  const pos = portrait
    ? [{ x: (box.w - cw) / 2, y: 0 }, { x: (box.w - cw) / 2, y: box.h * 0.46 }]
    : [{ x: box.w * 0.06, y: (box.h - ch) / 2 - 30 }, { x: box.w * 0.58, y: (box.h - ch) / 2 - 30 }];
  [L, Rt].forEach((sd, k) => {
    const card = h("div", "card", scene, { left: pos[k].x + "px", top: pos[k].y + "px", width: cw + "px", height: ch + "px",
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "22px", padding: "20px" });
    h("div", "pill", card, { fontSize: "26px" }, k ? "IN TECH" : "IN REAL LIFE");
    icon(sd.icon || (k ? "cpu" : "coffee"), Math.min(ch * 0.4, 150), col(k ? 1 : 2), card);
    const lab = h("div", "label", card, {}, esc(sd.label || ""));
    fit(lab, cw - 50, ch * 0.24, 46, 20);
    popIn(card, R[k] ?? start + 0.3 + k);
  });
  const mid = portrait ? { x: box.w / 2, y: (ch + box.h * 0.46) / 2 } : { x: box.w / 2 + 2, y: box.h / 2 - 30 };
  const vs = h("div", "vs", scene, { left: mid.x + "px", top: mid.y + "px", width: "150px", height: "64px", fontSize: "27px" }, "IS LIKE");
  popIn(vs, (R[1] ?? start + 1.3) - 0.25);
  if (v.note) {
    const n = h("div", "sub", scene, { position: "absolute", left: "6%", right: "6%", top: (portrait ? box.h * 0.86 : box.h * 0.86) + "px" }, marked(v.note));
    fit(n, box.w * 0.88, 120, 44);
    slideIn(n, R[2] ?? end - 1.5, { y: 20 });
  }
};

B.takeaway = (scene, v, box, R, start, end, portrait) => {
  const pill = h("div", "pill", scene, { position: "absolute", left: "50%", top: box.h * 0.12 + "px", fontSize: "30px", transform: "translateX(-50%)" }, "KEY TAKEAWAY");
  tl.fromTo(pill, { opacity: 0 }, { opacity: 1, duration: 0.3 }, start + 0.1);
  const cw = box.w * 0.88, ch = box.h * 0.5;
  const card = h("div", "card", scene, { left: (box.w - cw) / 2 + "px", top: box.h * 0.25 + "px", width: cw + "px", height: ch + "px",
    display: "flex", alignItems: "center", justifyContent: "center", padding: "40px", borderColor: "rgba(251,191,36,0.55)",
    boxShadow: "0 0 60px rgba(251,191,36,0.18), 0 20px 60px rgba(0,0,0,0.45)" });
  const t = h("div", "label", card, { fontWeight: 850 }, marked(v.text));
  fit(t, cw - 90, ch - 70, portrait ? 88 : 80, 26);
  popIn(card, R[0] ?? start + 0.3);
  const sub = h("div", "sub", scene, { position: "absolute", left: 0, right: 0, top: box.h * 0.82 + "px", fontSize: "34px",
    display: "flex", justifyContent: "center", alignItems: "center", gap: "14px" }, `${D.icons["bell"] || ""}<span>Follow for a new explainer every day</span>`);
  const svg = sub.querySelector("svg");
  if (svg) { svg.style.width = "38px"; svg.style.height = "38px"; svg.style.color = "var(--amber)"; }
  slideIn(sub, end - 2.2, { y: 20 });
};

// ---------- concept visuals (how AI works, drawn the ByteMonk way) ----------
const SVGNS = "http://www.w3.org/2000/svg";
function sv(tag, attrs, parent) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function svgLayer(scene) {
  const s = sv("svg", { class: "edges" }, scene);
  return s;
}
// Stable pseudo-random number in [0, 1) from a string, so layouts never change between frames.
function hash(s, k = 0) {
  let x = 2166136261 ^ k;
  for (const c of String(s)) x = Math.imul(x ^ c.charCodeAt(0), 16777619);
  return ((x >>> 0) % 10000) / 10000;
}

// "Unbelievable results" -> ["Un", "believ", "able", " results"]: illustrative sub-word pieces.
function autoTokens(text) {
  const out = [];
  String(text || "").split(/\s+/).filter(Boolean).forEach((w, i) => {
    const pre = i ? " " : "";
    if (w.length > 7) { const cut = Math.ceil(w.length * 0.55); out.push(pre + w.slice(0, cut), w.slice(cut)); }
    else out.push(pre + w);
  });
  return out;
}

B.tokens = (scene, v, box, R, start, end, portrait) => {
  const top = heading(scene, v.heading, box, start + 0.1);
  const toks = (v.tokens && v.tokens.length ? v.tokens : autoTokens(v.text)).slice(0, 16);
  const sent = h("div", "big", scene, { top: top + (box.h - top) * 0.06 + "px" }, esc(v.text));
  fit(sent, box.w * 0.92, (box.h - top) * 0.26, portrait ? 74 : 80, 30);
  tl.fromTo(sent, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.45, ease: "power3.out" }, R[0]);
  const split = R[1] ?? R[0] + 1.2;
  tl.to(sent, { opacity: 0.3, scale: 0.92, duration: 0.4 }, split);
  // a scanning bar sweeps the sentence, then the pieces drop out of it as chips
  const scan = h("div", "scan", scene, { top: sent.offsetTop - 10 + "px", height: sent.offsetHeight + 20 + "px" });
  tl.fromTo(scan, { left: "0%", opacity: 0 }, { left: "96%", opacity: 1, duration: 0.6, ease: "power1.inOut" }, split - 0.5);
  tl.to(scan, { opacity: 0, duration: 0.15 }, split + 0.1);
  const wrap = h("div", "chips", scene, { top: top + (box.h - top) * 0.38 + "px", gap: portrait ? "18px 14px" : "22px 16px" });
  const fs = toks.length > 10 ? 40 : toks.length > 5 ? 52 : 62;
  toks.forEach((t, i) => {
    const chip = h("div", "chip", wrap, { borderColor: col(i), fontSize: fs + "px",
      background: `color-mix(in srgb, ${col(i)} 18%, #0d1430)` });
    h("div", "", chip, {}, esc(t.trim() || "␣").replace(/^ /, ""));
    if (v.ids !== false) h("div", "tid", chip, { color: col(i) }, String(100 + Math.floor(hash(t) * 49000)));
    tl.fromTo(chip, { opacity: 0, y: -90, scale: 0.5, rotation: (hash(t, 1) - 0.5) * 30 },
      { opacity: 1, y: 0, scale: 1, rotation: 0, duration: 0.5, ease: "back.out(1.8)" }, split + 0.1 + i * 0.09);
  });
  const count = h("div", "pill", scene, { position: "absolute", left: "50%", top: box.h * 0.88 + "px", fontSize: portrait ? "34px" : "30px",
    transform: "translateX(-50%)", whiteSpace: "nowrap" }, `${toks.length} tokens${v.ids !== false ? " · each one is a number" : ""}`);
  tl.fromTo(count, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, split + 0.4 + toks.length * 0.09);
};

B.predict = (scene, v, box, R, start, end, portrait) => {
  const opts = (v.options || []).slice(0, 5);
  const pick = Math.min(Math.max(v.pick ?? 0, 0), Math.max(opts.length - 1, 0));
  const top = heading(scene, v.heading, box, start + 0.1, 50);
  const pc = h("div", "card prompt", scene, { left: "3%", width: "94%", top: top + "px", padding: portrait ? "30px 34px" : "26px 40px" });
  h("div", "pill", pc, { fontSize: "24px", marginBottom: "14px" }, "PROMPT");
  const line = h("div", "label", pc, { textAlign: "left", fontWeight: 750 });
  line.innerHTML = `${esc(v.prompt || "")} <span class="slot"><span class="cursor">▍</span><span class="fill">${esc(opts[pick] ? opts[pick].word : "")}</span></span>`;
  fit(line, box.w * 0.94 - 90, portrait ? 210 : 150, portrait ? 58 : 54, 26);
  popIn(pc, R[0], { duration: 0.45 });
  const cursor = line.querySelector(".cursor"), fill = line.querySelector(".fill");
  const at = R[opts.length + 1] ?? end - 1.4;
  tickers.push((t) => { cursor.style.opacity = t < at && Math.floor(t * 2.4) % 2 === 0 ? 1 : 0; cursor.style.display = t < at ? "" : "none"; });
  tl.fromTo(fill, { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.45, ease: "back.out(2)" }, at + 0.25);
  const lbl = h("div", "sub", scene, { position: "absolute", left: 0, right: 0, top: top + pc.offsetHeight + 34 + "px", fontSize: portrait ? "34px" : "30px" },
    esc(v.label || "What word comes next? The model scores every option"));
  tl.fromTo(lbl, { opacity: 0 }, { opacity: 1, duration: 0.3 }, (R[1] ?? R[0] + 0.6) - 0.3);
  const yy = top + pc.offsetHeight + 110, rowH = Math.min(portrait ? 190 : 120, (box.h - yy - 10) / Math.max(opts.length, 1));
  const y0 = yy + (box.h - yy - rowH * opts.length) * 0.35;
  const maxP = Math.max(...opts.map(o => +o.p || 0), 1);
  opts.forEach((o, i) => {
    const row = h("div", "", scene, { position: "absolute", left: "3%", width: "94%", top: y0 + i * rowH + "px", height: rowH * 0.78 + "px",
      display: "flex", alignItems: "center", gap: "22px" });
    const w = h("div", "label", row, { width: portrait ? "250px" : "260px", textAlign: "right", flexShrink: 0, fontSize: Math.min(rowH * 0.42, 52) + "px" }, esc(o.word));
    const track = h("div", "bar-track", row, {});
    const bar = h("div", "bar", track, { background: i === pick ? "linear-gradient(90deg, var(--amber), #fde68a)" : `linear-gradient(90deg, ${col(i + 1)}, color-mix(in srgb, ${col(i + 1)} 55%, white))` });
    const pct = h("div", "label", row, { width: "150px", flexShrink: 0, textAlign: "left", fontSize: Math.min(rowH * 0.4, 48) + "px", color: i === pick ? "var(--amber)" : "var(--muted)" }, "0%");
    const t0 = R[i + 1] ?? start + 0.8 + i * 0.4;
    tl.fromTo(row, { opacity: 0, x: -40 }, { opacity: 1, x: 0, duration: 0.3 }, t0);
    tl.fromTo(bar, { width: "0%" }, { width: Math.max(2, (+o.p || 0) / maxP * 100) + "%", duration: 0.8, ease: "power2.out" }, t0 + 0.1);
    const obj = { n: 0 };
    tl.to(obj, { n: +o.p || 0, duration: 0.8, ease: "power2.out", onUpdate: () => { pct.textContent = Math.round(obj.n) + "%"; } }, t0 + 0.1);
    if (i === pick) {
      tl.to(row, { scale: 1.05, duration: 0.3, transformOrigin: "left center" }, at);
      tl.to(bar, { boxShadow: "0 0 40px rgba(251,191,36,0.8)", duration: 0.3 }, at);
      tl.to(w, { color: "var(--amber)", duration: 0.2 }, at);
    } else tl.to(row, { opacity: 0.4, duration: 0.3 }, at);
  });
};

B.vectors = (scene, v, box, R, start, end, portrait) => {
  const groups = (v.groups || []).slice(0, 4).map(g => typeof g === "string" ? { label: g, items: [] } : g);
  const top = heading(scene, v.heading, box, start + 0.1, 50);
  const readH = v.query ? (portrait ? 120 : 90) : 0;
  const area = { x: 0, y: top, w: box.w, h: box.h - top - readH - 10 };
  const plane = h("div", "card plane", scene, { left: area.x + "px", top: area.y + "px", width: area.w + "px", height: area.h + "px" });
  tl.fromTo(plane, { opacity: 0 }, { opacity: 1, duration: 0.4 }, start + 0.1);
  const svg = svgLayer(scene);
  const centers = [[[0.5, 0.5]], [[0.28, 0.5], [0.72, 0.5]], [[0.27, 0.3], [0.73, 0.3], [0.5, 0.74]],
    [[0.27, 0.28], [0.73, 0.28], [0.27, 0.74], [0.73, 0.74]]][Math.max(groups.length, 1) - 1];
  const spots = [];
  groups.forEach((g, gi) => {
    const [cx, cy] = centers[gi];
    const X = area.x + area.w * cx, Y = area.y + area.h * cy, rad = Math.min(area.w / (groups.length > 1 ? 2 : 1), area.h) * (groups.length > 2 ? 0.2 : 0.28);
    const c = col(gi), t0 = R[gi] ?? start + 0.5 + gi * 0.8;
    const halo = h("div", "halo", scene, { left: X - rad * 1.25 + "px", top: Y - rad * 1.25 + "px", width: rad * 2.5 + "px", height: rad * 2.5 + "px",
      background: `radial-gradient(circle, color-mix(in srgb, ${c} 22%, transparent) 0%, transparent 70%)` });
    tl.fromTo(halo, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.6 }, t0);
    const tag = h("div", "pill", scene, { position: "absolute", left: X + "px", top: Y - rad * 1.05 - 20 + "px", transform: "translate(-50%, -50%)",
      fontSize: portrait ? "30px" : "26px", color: c, borderColor: c, background: "#0d1430" }, esc(g.label));
    tl.fromTo(tag, { opacity: 0, y: -14 }, { opacity: 1, y: 0, duration: 0.35 }, t0);
    const items = (g.items || []).slice(0, 5);
    items.forEach((it, k) => {
      const a = (k / items.length) * Math.PI * 2 + gi + hash(it, gi) * 0.5, r = rad * (items.length > 1 ? 0.5 + 0.25 * hash(it, 7) : 0);
      const px = X + Math.cos(a) * r, py = Y + Math.sin(a) * r * 0.8 + rad * 0.1;
      const dot = h("div", "vdot", scene, { left: px + "px", top: py + "px", background: c, boxShadow: `0 0 18px ${c}` });
      const lab = h("div", "vlabel", scene, { left: px + "px", top: py + 16 + "px", fontSize: portrait ? "36px" : "30px" }, esc(it));
      spots.push({ x: px, y: py, g: gi });
      tl.fromTo([dot, lab], { opacity: 0, scale: 0 }, { opacity: 1, scale: 1, duration: 0.4, ease: "back.out(2)" }, t0 + 0.2 + k * 0.12);
      tickers.push((t) => { if (t > t0 + 0.8) dot.style.transform = `translate(-50%, -50%) translate(${Math.sin(t * 1.3 + k + gi) * 4}px, ${Math.cos(t * 1.1 + k) * 4}px)`; });
    });
  });
  if (!v.query) return;
  const near = Math.min(Math.max(v.near ?? 0, 0), groups.length - 1);
  const tq = R[groups.length] ?? end - 2;
  const [ncx, ncy] = centers[near] || [0.5, 0.5];
  // the query lands just outside its cluster, on the side facing the middle of the map
  const NX = area.x + area.w * ncx, NY = area.y + area.h * ncy;
  const away = groups.length > 1 ? Math.atan2(area.y + area.h / 2 - NY, area.x + area.w / 2 - NX) : Math.PI / 2;
  const nrad = Math.min(area.w / (groups.length > 1 ? 2 : 1), area.h) * (groups.length > 2 ? 0.2 : 0.28);
  const qx = NX + Math.cos(away) * nrad * 1.15, qy = NY + Math.sin(away) * nrad * 1.0 + (groups.length === 2 ? nrad * 0.75 : 0);
  const q = h("div", "vdot query", scene, { left: qx + "px", top: qy + "px" });
  const ql = h("div", "vlabel", scene, { left: qx + "px", top: qy + 22 + "px", fontSize: portrait ? "32px" : "28px", color: "var(--amber)", fontWeight: 850 }, esc(v.query));
  tl.fromTo([q, ql], { opacity: 0, scale: 3 }, { opacity: 1, scale: 1, duration: 0.5, ease: "power3.out" }, tq);
  const pulse = h("div", "qpulse", scene, { left: qx + "px", top: qy + "px" });
  tickers.push((t) => { const p = ((t - tq) % 1.2) / 1.2; pulse.style.opacity = t > tq + 0.4 ? 1 - p : 0; pulse.style.transform = `translate(-50%, -50%) scale(${1 + p * 3})`; });
  spots.filter(s => s.g === near).sort((a, b) => Math.hypot(a.x - qx, a.y - qy) - Math.hypot(b.x - qx, b.y - qy)).slice(0, 3).forEach((s, k) => {
    const len = Math.hypot(s.x - qx, s.y - qy);
    const ln = sv("path", { d: `M${qx},${qy} L${s.x},${s.y}`, class: "edge", stroke: css("--amber"), "stroke-dasharray": `${len}`, opacity: 0.9 }, svg);
    ln.style.strokeWidth = 4;
    tl.fromTo(ln, { strokeDashoffset: len }, { strokeDashoffset: 0, duration: 0.45, ease: "power2.out" }, tq + 0.5 + k * 0.15);
  });
  const read = h("div", "vector-read", scene, { top: box.h - readH + "px", height: readH - 10 + "px", fontSize: portrait ? "34px" : "30px" });
  const nums = [0, 1, 2, 3].map(k => ((hash(v.query, k + 3) * 2 - 1)).toFixed(2));
  read.innerHTML = `<span style="color:var(--amber)">"${esc(v.query)}"</span> <span class="arrow">→</span> <span class="mono">[${nums.join(", ")}, …]</span>`;
  tl.fromTo(read, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.4 }, tq + 0.3);
};

B.network = (scene, v, box, R, start, end, portrait) => {
  const layers = (v.layers && v.layers.length >= 2 ? v.layers : [3, 5, 5, 2]).slice(0, 6).map(n => Math.min(Math.max(+n || 1, 1), 7));
  const top = heading(scene, v.heading, box, start + 0.1, 50);
  const lab = portrait ? 90 : 70;
  const area = { x: box.w * 0.08, y: top + lab, w: box.w * 0.84, h: box.h - top - lab * 2 - 20 };
  const svg = svgLayer(scene);
  const L = layers.length, gx = area.w / (L - 1);
  const pos = layers.map((n, li) => Array.from({ length: n }, (_, k) => ({ x: area.x + li * gx, y: area.y + area.h * (k + 0.5) / n })));
  const r = Math.min(portrait ? 34 : 30, area.h / Math.max(...layers) * 0.3);
  const lines = [];
  for (let li = 0; li + 1 < L; li++) pos[li].forEach(a => pos[li + 1].forEach(b => {
    const ln = sv("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: css("--violet"), "stroke-width": 2 }, svg);
    lines.push({ el: ln, li, w: hash(`${a.x},${a.y},${b.y}`) });
  }));
  const tIn = R[0] ?? start + 0.3, tMid = R[1] ?? tIn + 1, tOut = R[2] ?? tMid + 1;
  tl.fromTo(lines.map(l => l.el), { opacity: 0 }, { opacity: 0.18, duration: 0.6, stagger: 0.004 }, tMid);
  const nodes = [];
  pos.forEach((col_, li) => col_.forEach((p) => {
    const c = li === 0 ? "var(--cyan)" : li === L - 1 ? "var(--amber)" : "var(--violet)";
    const n = h("div", "neuron", scene, { left: p.x - r + "px", top: p.y - r + "px", width: r * 2 + "px", height: r * 2 + "px", borderColor: c, color: c });
    nodes.push({ el: n, li });
    tl.fromTo(n, { opacity: 0, scale: 0 }, { opacity: 1, scale: 1, duration: 0.35, ease: "back.out(2)" }, (li === 0 ? tIn : li === L - 1 ? tOut : tMid) + 0.04 * nodes.length % 0.4);
  }));
  const pills = [[v.input || "Input", 0, "var(--cyan)", tIn], [v.middle || "Hidden layers", (L - 1) / 2, "var(--violet)", tMid], [v.output || "Output", L - 1, "var(--amber)", tOut]];
  pills.forEach(([text, li, c, t], k) => {
    const p = h("div", "pill", scene, { position: "absolute", left: area.x + li * gx + "px", top: (k === 1 ? box.h - lab - 10 : top + 4) + "px",
      transform: "translateX(-50%)", fontSize: portrait ? "30px" : "28px", color: c, borderColor: c, background: "#0d1430", whiteSpace: "nowrap" }, esc(text));
    tl.fromTo(p, { opacity: 0, y: k === 1 ? 14 : -14 }, { opacity: 1, y: 0, duration: 0.35 }, t);
  });
  // a wave of activation sweeps input -> output, again and again
  tickers.push((t) => {
    if (t < tMid + 0.5) return;
    const wave = ((t - tMid - 0.5) % 1.8) / 1.8 * (L + 0.6) - 0.3;
    lines.forEach(l => { const d = Math.abs(wave - (l.li + 0.5)); l.el.setAttribute("opacity", d < 0.5 && l.w > 0.35 ? 0.18 + 0.7 * (1 - d * 2) : 0.18); });
    nodes.forEach(n => { const d = Math.abs(wave - n.li); n.el.style.boxShadow = d < 0.5 ? `0 0 ${50 * (1 - d * 2)}px currentColor, inset 0 0 ${30 * (1 - d * 2)}px currentColor` : "none"; });
  });
};

B.chat = (scene, v, box, R, start, end, portrait) => {
  const msgs = (v.messages || []).slice(0, 4).map(m => typeof m === "string" ? { from: "user", text: m } : m);
  const top = heading(scene, v.heading, box, start + 0.1, 50);
  const ww = portrait ? box.w * 0.94 : Math.min(box.w * 0.7, 1100);
  const win = h("div", "card chatwin", scene, { left: (box.w - ww) / 2 + "px", top: top + "px", width: ww + "px", maxHeight: box.h - top - 10 + "px" });
  const bar = h("div", "chatbar", win, {});
  icon("bot", 64, "var(--violet)", bar, { flexShrink: 0, borderRadius: "50%" });
  h("div", "", bar, {}, `<b>${esc(v.bot || "AI chatbot")}</b><br><span class="online">● online</span>`);
  popIn(win, start + 0.15, { duration: 0.45, ease: "power3.out" });
  const body = h("div", "chatbody", win, {});
  let fs = portrait ? 54 : 44;
  const els = msgs.map((m, i) => {
    const bot = m.from !== "user";
    const b = h("div", "bubble " + (bot ? "bot" : "user"), body, {});
    const text = h("div", "", b, {});
    wordsIn(text, words(m.text), (R[i] ?? start + 0.6 + i * 1.2) + (bot ? 0.55 : 0), 20).forEach(s => { s.style.display = "inline-block"; s.style.marginRight = "0.25em"; });
    return { b, bot, m };
  });
  const avail = box.h - top - 10 - 130;
  const apply = () => els.forEach(({ b }) => { b.style.fontSize = fs + "px"; });
  apply();
  while (fs > 22 && body.scrollHeight > avail) { fs -= 2; apply(); }
  win.style.top = top + Math.max(0, (box.h - top - win.offsetHeight) * 0.3) + "px";
  els.forEach(({ b, bot, m }, i) => {
    const t0 = R[i] ?? start + 0.6 + i * 1.2;
    tl.fromTo(b, { opacity: 0, y: 30, scale: 0.9 }, { opacity: 1, y: 0, scale: 1, duration: 0.35, ease: "back.out(1.6)",
      transformOrigin: bot ? "left bottom" : "right bottom" }, t0);
    if (bot) {  // "typing…" dots first
      const dots = h("div", "typing", b, {}, "<i></i><i></i><i></i>");
      tickers.push((t) => {
        const on = t >= t0 && t < t0 + 0.55;
        dots.style.display = on ? "flex" : "none";
        if (on) [...dots.children].forEach((d, k) => { d.style.opacity = 0.3 + 0.7 * Math.max(0, Math.sin((t * 8) - k)); });
      });
    }
    if (m.flag === "wrong" || m.flag === "right") {
      const bad = m.flag === "wrong";
      const st = h("div", "stamp " + (bad ? "bad" : "good"), b, { fontSize: Math.max(fs * 0.7, 22) + "px" },
        esc(m.note || (bad ? "MADE UP!" : "✓ FROM SOURCES")));
      tl.fromTo(st, { opacity: 0, scale: 2.2, rotation: bad ? -18 : 0 }, { opacity: 1, scale: 1, rotation: bad ? -8 : 0, duration: 0.35, ease: "power4.in" },
        t0 + 0.55 + Math.min(words(m.text).length * 0.06, 1.4) + 0.3);
    }
  });
};

// ---------- Shorts cover: the first 0.4 s is a bold title card, so the frame feeds and Reels show is never empty ----------
function buildCover(frame, W, H) {
  const c = h("div", "", frame, { position: "absolute", inset: 0, zIndex: 9, background: "radial-gradient(ellipse at 30% 25%, #1b2858 0%, var(--bg) 70%)" });
  c.id = "cover";
  const words = h("div", "", c, { position: "absolute", left: "60px", right: "60px", top: H * 0.12 + "px", height: H * 0.42 + "px",
    display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", fontWeight: 900, lineHeight: 1.02,
    letterSpacing: "-0.03em", textTransform: "uppercase", color: "#fff", paintOrder: "stroke fill", webkitTextStroke: "16px #05070f" });
  let html = marked(D.cover.text);
  if (!/\*/.test(D.cover.text)) { const p = html.trim().split(" "); p[p.length - 1] = `<span class="hl">${p[p.length - 1]}</span>`; html = p.join(" "); }
  const inner = h("div", "", words, {}, html);
  inner.querySelectorAll(".hl").forEach(e => { e.style.color = "var(--amber)"; });
  let size = 190;
  inner.style.fontSize = size + "px";
  while (size > 60 && (inner.scrollHeight > H * 0.42 || inner.scrollWidth > W - 120)) { size -= 6; inner.style.fontSize = size + "px"; }
  const th = h("div", "", c, { position: "absolute", left: W / 2 - 230 + "px", top: H * 0.58 + "px" });
  buildMascot(th, 460).update(0.3, 3, "wow", false, false, 0);
  tl.set(c, { opacity: 1 }, 0);
  tl.to(c, { opacity: 0, scale: 1.25, duration: 0.25, ease: "power2.in" }, 0.4);
}

// ---------- stage ----------
window.load = async (data) => {
  D = data;
  if (D.theme) document.documentElement.dataset.theme = D.theme;
  await document.fonts.ready;
  const { W, H } = D;
  document.body.style.width = W + "px";
  document.body.style.height = H + "px";
  const frame = h("div", "", document.body, { width: W + "px", height: H + "px" });
  frame.id = "frame";
  const grid = h("div", "", frame); grid.id = "grid";
  const blobs = ["--cyan", "--violet", "--pink"].map((c, i) => h("div", "blob", frame, {
    width: W * 0.5 + "px", height: W * 0.5 + "px", background: `var(${c})` }));
  tickers.push((t) => blobs.forEach((b, i) => {
    b.style.left = (W * (0.15 + 0.35 * i) + Math.sin(t * 0.21 + i * 2) * W * 0.12 - W * 0.25) + "px";
    b.style.top = (H * (0.2 + 0.3 * i) + Math.cos(t * 0.17 + i) * H * 0.1 - W * 0.25) + "px";
  }));
  tickers.push((t) => { grid.style.transform = `translate(${(t * 6) % 44}px, ${(t * 4) % 44}px)`; });

  const L = D.layout;
  const brand = h("div", "", frame, { left: L.brand.x + "px", top: L.brand.y + "px", fontSize: L.brand.size + "px" },
    `<span class="dot"></span><span class="name">Thoma Explains</span>` + (D.kind === "long" ? `<span class="chapter">${esc(D.title)}</span>` : ""));
  brand.id = "brand";
  if (D.kind === "short") {
    const bar = h("div", "", frame); bar.id = "progress";
    tickers.push((t) => { bar.style.width = (W * Math.min(t / D.duration, 1)) + "px"; });
  }

  const stage = h("div", "", frame, { left: L.stage.x + "px", top: L.stage.y + "px", width: L.stage.w + "px", height: L.stage.h + "px" });
  stage.id = "stage";
  const flash = h("div", "", frame, { position: "absolute", inset: 0, background: "#e0f2fe", opacity: 0, zIndex: 4, pointerEvents: "none", mixBlendMode: "screen" });
  const flashes = [];
  tickers.push((t) => {
    const d = Math.min(...flashes.map(f => (t >= f ? t - f : 9)), 9);
    flash.style.opacity = d < 0.35 ? 0.55 * (1 - d / 0.35) : 0;
  });
  const CUTS = [
    [{ y: 50, scale: 0.97 }, { y: -40, scale: 1.02 }],                                  // slide up
    [{ scale: 1.3, filter: "blur(14px)" }, { scale: 0.85, filter: "blur(10px)" }],     // zoom punch
    [{ x: W * 0.6, rotation: 3, filter: "blur(10px)" }, { x: -W * 0.6, rotation: -3, filter: "blur(10px)" }],  // whip pan
    [{ scale: 0.6, rotation: -6 }, { scale: 1.4 }],                                       // pop
  ];
  const box = { w: L.stage.w, h: L.stage.h };
  tl = gsap.timeline({ paused: true });
  const portrait = H > W;
  D.blocks.forEach((blk, i) => {
    const scene = h("div", "scene", stage);
    const zoom = h("div", "", scene, { position: "absolute", inset: 0 });
    const build = B[blk.visual.type] || B.bigtext;
    try {
      build(zoom, blk.visual, box, blk.reveals, blk.start, blk.end, portrait);
    } catch (e) {
      console.error("builder failed", blk.visual.type, e && e.stack);
    }
    // cuts rotate between a few editing styles so the eye keeps getting something new
    const [inFrom, outTo] = i === 0 ? CUTS[0] : CUTS[i % CUTS.length];
    tl.fromTo(scene, Object.assign({ opacity: 0 }, inFrom), { opacity: 1, x: 0, y: 0, scale: 1, rotation: 0, filter: "blur(0px)", duration: 0.42, ease: "power3.out" }, blk.start);
    tl.fromTo(zoom, { scale: 1 }, { scale: 1.035, duration: Math.max(blk.end - blk.start, 0.5), ease: "none" }, blk.start);
    if (i < D.blocks.length - 1) tl.to(scene, Object.assign({ opacity: 0, duration: 0.28, ease: "power2.in" }, outTo), blk.end - 0.28);
    if (i > 0 && i % CUTS.length === 2) {  // a quick light flash on some cuts
      flashes.push(blk.start);
    }
  });
  // punch-in + tiny shake when Thoma is surprised: a classic retention beat
  (D.thoma.moods || []).filter(([, m]) => m === "wow").forEach(([t]) => {
    tl.to(stage, { scale: 1.07, duration: 0.18, ease: "power2.out" }, t);
    tl.to(stage, { scale: 1, duration: 0.5, ease: "power2.inOut" }, t + 0.5);
    tl.fromTo(frame, { x: 0 }, { x: 0, duration: 0.3, ease: "none", keyframes: { x: [0, -8, 7, -5, 3, 0] } }, t);
  });

  const th = h("div", "", frame, { left: L.thoma.x + "px", top: L.thoma.y + "px" });
  th.id = "thoma";
  mascot = buildMascot(th, L.thoma.w);
  // he flies in on his spear from off-screen right
  tl.fromTo(th, { x: 700, y: -160, rotation: -14 }, { x: 0, y: 0, rotation: 0, duration: 0.9, ease: "power3.out" }, 0.05);
  cuts = D.blocks.slice(1).map(b => b.start);

  if (D.cover) buildCover(frame, W, H);

  if (D.captions && D.captions.length) {
    capEl = h("div", "", frame, { top: L.captions_y + "px", fontSize: L.caption_size + "px" });
    capEl.id = "captions";
  }
  tl.add(() => {}, D.duration);
  return true;
};

window.seek = (t) => {
  tl.seek(t, false);
  tickers.forEach(f => f(t));
  const M = D.thoma, fi = Math.min(Math.floor(t * D.fps), M.mouth.length - 1);
  let mood = "talk", since = 0;
  for (const [mt, mm] of M.moods) { if (mt <= t) { mood = mm; since = mt; } else break; }
  const blink = M.blinks.some(b => t >= b && t < b + 0.13);
  let cut = 9;
  for (const c of cuts) if (c <= t) cut = t - c; else break;
  mascot.update(t, M.mouth[fi], mood, M.mouth[fi] > 0, blink, t - since, cut);
  if (capEl) {
    const g = D.captions.find(c => t >= c.start && t < c.end);
    let key = "";
    if (g) {
      const on = g.words.findIndex(w => t >= w.s && t < w.e);
      key = g.start + ":" + on;
      if (key !== lastCap) capEl.innerHTML = g.words.map((w, i) => `<span class="w${i === on ? " on" : ""}">${esc(w.w)}</span>`).join(" ");
    } else if (lastCap) capEl.innerHTML = "";
    lastCap = key;
  }
};
