// Thoma Explains: scene templates + a paused GSAP timeline that Python seeks frame by frame.
//
// Python calls  await load(DATA)  once, then  seek(t)  before every screenshot.
// Each visual type below is a builder. To add a new look, add a builder and list its
// reveal order in thoma/visuals.py (elements()) so narration timing lines up.

const COLORS = ["--cyan", "--violet", "--amber", "--pink", "--green", "--blue"];
const col = (i) => `var(${COLORS[i % COLORS.length]})`;
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const hex = (i) => css(COLORS[i % COLORS.length]);

let D, tl, tickers = [], thomaImg, lastKey = -1, capEl, lastCap = "";

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
    const w = Math.min(290, (area.w - gap * (n - 1)) / n), hh = Math.min(w * 0.9, area.h * 0.8);
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
    const rx = area.w * (portrait ? 0.33 : 0.36), ry = area.h * 0.36;
    const w = Math.min(portrait ? 270 : 240, area.w * 0.27), hh = w * 0.8;
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

// ---------- stage ----------
window.load = async (data) => {
  D = data;
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
    tl.fromTo(scene, { opacity: 0, y: 50, scale: 0.97 }, { opacity: 1, y: 0, scale: 1, duration: 0.45, ease: "power3.out" }, blk.start);
    tl.fromTo(zoom, { scale: 1 }, { scale: 1.035, duration: Math.max(blk.end - blk.start, 0.5), ease: "none" }, blk.start);
    if (i < D.blocks.length - 1) tl.to(scene, { opacity: 0, y: -40, scale: 1.02, duration: 0.3, ease: "power2.in" }, blk.end - 0.3);
  });

  const th = h("div", "", frame, { left: L.thoma.x + "px", top: L.thoma.y + "px", width: L.thoma.w + "px", height: L.thoma.h + "px" });
  th.id = "thoma";
  h("div", "glow", th);
  thomaImg = h("img", "", th);
  tl.fromTo(th, { y: 300 }, { y: 0, duration: 0.6, ease: "back.out(1.4)" }, 0);
  window._thoma = th;

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
  const fi = Math.min(Math.floor(t * D.fps), D.thoma.frames.length - 1);
  const [k, bob] = D.thoma.frames[fi];
  if (k !== lastKey) { thomaImg.src = D.thoma.sprites[k]; lastKey = k; }
  thomaImg.style.transform = `translateY(${bob}px)`;
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
