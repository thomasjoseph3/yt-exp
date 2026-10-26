// Thoma the tech imp: a small comic mascot drawn in SVG and animated per frame.
// buildMascot(parent, width) -> { el, update(t, mouth 0-3, mood, speaking) }
// moods: talk | point | think | wow | laugh | wave

const MASCOT = {
  body: "#8b5cf6", dark: "#6d28d9", belly: "#c4b5fd", horn: "#fbbf24", hornDark: "#d97706",
  ink: "#1b1033", glass: "#111827", mouth: "#3b0a2a", tongue: "#fb7185", glow: "#22d3ee",
};

function buildMascot(parent, width) {
  const c = MASCOT;
  const wrap = document.createElement("div");
  wrap.style.cssText = `position:absolute;width:${width}px;height:${width * 1.3}px;`;
  wrap.innerHTML = `
<svg viewBox="0 0 200 260" width="100%" height="100%" style="overflow:visible">
  <ellipse cx="100" cy="252" rx="52" ry="7" fill="rgba(0,0,0,0.35)" class="m-shadow"/>
  <g class="m-all">
    <g class="m-tail">
      <path d="M128 196 C 168 206, 182 168, 166 140 S 176 104, 190 100" fill="none" stroke="${c.ink}" stroke-width="13" stroke-linecap="round"/>
      <path d="M128 196 C 168 206, 182 168, 166 140 S 176 104, 190 100" fill="none" stroke="${c.dark}" stroke-width="7" stroke-linecap="round"/>
      <path d="M190 100 l-6 -20 l20 6 z M190 100 l-16 -2 l12 -12 z" fill="${c.dark}" stroke="${c.ink}" stroke-width="3" stroke-linejoin="round"
            transform="rotate(10 190 100)"/>
    </g>
    <g class="m-legs">
      <path d="M84 214 q-2 22 -14 30 h20 q6 -10 6 -28" fill="${c.dark}" stroke="${c.ink}" stroke-width="4" stroke-linejoin="round"/>
      <path d="M116 214 q2 22 14 30 h-20 q-6 -10 -6 -28" fill="${c.dark}" stroke="${c.ink}" stroke-width="4" stroke-linejoin="round"/>
    </g>
    <ellipse cx="100" cy="186" rx="44" ry="40" fill="${c.body}" stroke="${c.ink}" stroke-width="4.5"/>
    <ellipse cx="100" cy="194" rx="26" ry="24" fill="${c.belly}" opacity="0.9"/>
    <g class="m-armR">
      <path d="M138 172 q20 6 26 26" fill="none" stroke="${c.ink}" stroke-width="15" stroke-linecap="round"/>
      <path d="M138 172 q20 6 26 26" fill="none" stroke="${c.body}" stroke-width="9" stroke-linecap="round"/>
      <rect x="160" y="168" width="6" height="40" rx="3" fill="${c.glow}" transform="rotate(20 163 198)" class="m-stylus"/>
      <circle cx="165" cy="199" r="8" fill="${c.body}" stroke="${c.ink}" stroke-width="3.5"/>
    </g>
    <g class="m-armL">
      <path d="M62 172 q-20 6 -26 26" fill="none" stroke="${c.ink}" stroke-width="15" stroke-linecap="round"/>
      <path d="M62 172 q-20 6 -26 26" fill="none" stroke="${c.body}" stroke-width="9" stroke-linecap="round"/>
      <circle cx="35" cy="199" r="8" fill="${c.body}" stroke="${c.ink}" stroke-width="3.5"/>
      <path class="m-finger" d="M30 196 l-12 -4" stroke="${c.ink}" stroke-width="7" stroke-linecap="round" opacity="0"/>
    </g>
    <g class="m-head">
      <path d="M58 70 q-14 -28 4 -46 q2 22 18 34 z" fill="${c.horn}" stroke="${c.ink}" stroke-width="4" stroke-linejoin="round"/>
      <path d="M142 70 q14 -28 -4 -46 q-2 22 -18 34 z" fill="${c.horn}" stroke="${c.ink}" stroke-width="4" stroke-linejoin="round"/>
      <path d="M40 104 l-22 -16 l10 30 z" fill="${c.body}" stroke="${c.ink}" stroke-width="4" stroke-linejoin="round"/>
      <path d="M160 104 l22 -16 l-10 30 z" fill="${c.body}" stroke="${c.ink}" stroke-width="4" stroke-linejoin="round"/>
      <ellipse cx="100" cy="104" rx="62" ry="56" fill="${c.body}" stroke="${c.ink}" stroke-width="4.5"/>
      <path d="M70 62 q30 -16 60 0" fill="none" stroke="${c.dark}" stroke-width="5" stroke-linecap="round" opacity="0.6"/>
      <ellipse cx="66" cy="126" rx="10" ry="6" fill="#f472b6" opacity="0.45"/>
      <ellipse cx="134" cy="126" rx="10" ry="6" fill="#f472b6" opacity="0.45"/>
      <g class="m-brows">
        <path class="m-browL" d="M60 74 q14 -8 28 0" fill="none" stroke="${c.ink}" stroke-width="5" stroke-linecap="round"/>
        <path class="m-browR" d="M112 74 q14 -8 28 0" fill="none" stroke="${c.ink}" stroke-width="5" stroke-linecap="round"/>
      </g>
      <g class="m-eyes">
        <circle cx="76" cy="98" r="15" fill="#fff"/><circle cx="124" cy="98" r="15" fill="#fff"/>
        <g class="m-pupils"><circle cx="79" cy="100" r="7" fill="${c.ink}"/><circle cx="127" cy="100" r="7" fill="${c.ink}"/>
          <circle cx="81" cy="97" r="2.4" fill="#fff"/><circle cx="129" cy="97" r="2.4" fill="#fff"/></g>
        <g class="m-lids" opacity="0"><path d="M60 98 h32 M108 98 h32" stroke="${c.ink}" stroke-width="5" stroke-linecap="round"/></g>
      </g>
      <g fill="none" stroke="${c.glass}" stroke-width="5">
        <circle cx="76" cy="98" r="21"/><circle cx="124" cy="98" r="21"/><path d="M97 96 q3 -4 6 0"/>
      </g>
      <g class="m-mouth">
        <g class="m0"><path d="M86 134 q14 12 28 0" fill="none" stroke="${c.ink}" stroke-width="4.5" stroke-linecap="round"/>
          <path d="M106 138.6 l2.2 5 l2.6 -6.2 z" fill="#fff" stroke="${c.ink}" stroke-width="1.6" stroke-linejoin="round"/></g>
        <g class="m1" opacity="0"><path d="M88 132 q12 14 24 0 z" fill="${c.mouth}" stroke="${c.ink}" stroke-width="4" stroke-linejoin="round"/>
          <path d="M92.5 133.5 l2.2 4.6 l2.2 -4.6 z M103.1 133.5 l2.2 4.6 l2.2 -4.6 z" fill="#fff"/></g>
        <g class="m2" opacity="0"><path d="M84 130 q16 26 32 0 z" fill="${c.mouth}" stroke="${c.ink}" stroke-width="4" stroke-linejoin="round"/>
          <ellipse cx="100" cy="143" rx="8" ry="4" fill="${c.tongue}"/>
          <path d="M89.5 131.8 l2.6 5.4 l2.6 -5.4 z M105.3 131.8 l2.6 5.4 l2.6 -5.4 z" fill="#fff"/></g>
        <g class="m3" opacity="0"><ellipse cx="100" cy="138" rx="15" ry="16" fill="${c.mouth}" stroke="${c.ink}" stroke-width="4"/>
          <ellipse cx="100" cy="147" rx="9" ry="5" fill="${c.tongue}"/>
          <path d="M93.4 124.2 l2.3 5 l2.3 -5 z M102.0 124.2 l2.3 5 l2.3 -5 z" fill="#fff"/></g>
      </g>
    </g>
    <g class="m-fx" font-family="Inter" font-weight="900">
      <text class="fx-q" x="150" y="40" font-size="46" fill="${c.horn}" opacity="0">?</text>
      <text class="fx-ex" x="152" y="40" font-size="50" fill="${c.horn}" opacity="0">!</text>
      <g class="fx-spark" opacity="0" fill="${c.glow}">
        <path d="M164 30 l4 10 l10 4 l-10 4 l-4 10 l-4 -10 l-10 -4 l10 -4 z"/>
        <path d="M30 40 l3 7 l7 3 l-7 3 l-3 7 l-3 -7 l-7 -3 l7 -3 z"/>
      </g>
    </g>
  </g>
</svg>`;
  parent.appendChild(wrap);
  const q = (s) => wrap.querySelector(s);
  const parts = {
    all: q(".m-all"), tail: q(".m-tail"), head: q(".m-head"), armR: q(".m-armR"), armL: q(".m-armL"),
    finger: q(".m-finger"), pupils: q(".m-pupils"), lids: q(".m-lids"), eyes: [...wrap.querySelectorAll(".m-eyes > circle")],
    browL: q(".m-browL"), browR: q(".m-browR"), mouths: [0, 1, 2, 3].map(i => q(".m" + i)),
    q: q(".fx-q"), ex: q(".fx-ex"), spark: q(".fx-spark"), shadow: q(".m-shadow"), stylus: q(".m-stylus"),
  };
  const set = (el, tr) => el.setAttribute("transform", tr);

  function update(t, mouth, mood, speaking, blink, moodAge) {
    const hop = mood === "wow" ? Math.max(0, Math.sin(Math.min(moodAge, 0.5) * Math.PI / 0.5)) * 22 : 0;
    const bounce = mood === "laugh" ? Math.abs(Math.sin(t * 14)) * 6 : 0;
    const float = Math.sin(t * 2.2) * 4 + (speaking ? Math.sin(t * 9) * 1.2 : 0);
    set(parts.all, `translate(0 ${float - hop - bounce})`);
    parts.shadow.setAttribute("rx", 52 - (float + hop) * 0.6);
    set(parts.tail, `rotate(${Math.sin(t * 2.8) * 12 + (mood === "wow" ? -15 : 0)} 128 196)`);
    const tilt = mood === "think" ? -8 : mood === "point" ? -5 : Math.sin(t * 1.3) * 3;
    set(parts.head, `rotate(${tilt} 100 150)`);
    // arms
    let l = Math.sin(t * 3) * 4, r = Math.sin(t * 3 + 1) * 4;
    if (mood === "point") l = 75;
    if (mood === "wave") r = -95 + Math.sin(t * 12) * 18;
    if (mood === "think") r = -70;
    if (mood === "wow") { l = 40; r = -40; }
    if (mood === "laugh") { l = 15 + Math.sin(t * 14) * 8; r = -15 - Math.sin(t * 14) * 8; }
    if (mood === "talk" && speaking) { r = -18 + Math.sin(t * 4.5) * 14; }
    set(parts.armL, `rotate(${l} 62 172)`);
    set(parts.armR, `rotate(${r} 138 172)`);
    parts.finger.setAttribute("opacity", mood === "point" ? 1 : 0);
    parts.stylus.setAttribute("opacity", mood === "wave" ? 0 : 1);
    // eyes
    const look = mood === "point" ? -5 : mood === "think" ? 4 : 0;
    set(parts.pupils, `translate(${look} ${mood === "think" ? -4 : 0})`);
    const shut = blink || mood === "laugh";
    parts.lids.setAttribute("opacity", shut ? 1 : 0);
    parts.pupils.setAttribute("opacity", shut ? 0 : 1);
    parts.eyes.forEach(e => e.setAttribute("opacity", shut ? 0 : 1));
    const browUp = mood === "wow" ? -8 : mood === "think" ? -4 : speaking ? Math.sin(t * 5) * 1.5 : 0;
    set(parts.browL, `translate(0 ${browUp})`);
    set(parts.browR, `translate(0 ${mood === "think" ? 3 : browUp})`);
    // mouth
    const m = mood === "wow" && !speaking ? 3 : mood === "laugh" ? 2 : mouth;
    parts.mouths.forEach((el, i) => el.setAttribute("opacity", i === m ? 1 : 0));
    // effects
    parts.q.setAttribute("opacity", mood === "think" ? 0.6 + Math.sin(t * 4) * 0.4 : 0);
    parts.ex.setAttribute("opacity", mood === "wow" ? 1 : 0);
    parts.spark.setAttribute("opacity", mood === "laugh" || mood === "wave" ? 0.5 + Math.sin(t * 8) * 0.5 : 0);
  }
  return { el: wrap, update };
}
