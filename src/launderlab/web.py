"""The shared design language for every published LaunderLab page.

One product, five pages. This module owns the shell, the tokens, the components
and the chart primitives so that the landing page, Story Mode, the results
dashboard and both benchmark pages cannot drift into looking like four separate
documents that happen to live in the same folder.

WHY THIS IS PYTHON AND NOT A STATIC SITE. Every figure on every page is rendered
from the project's scoring modules at build time. That is the single property
that makes the numbers trustworthy: nobody types them, so a published figure
cannot disagree with the one the scorers grade. A hand-authored site with the
results pasted in would look identical on day one and be silently wrong the
first time a threshold moved -- which is the exact failure mode §7 of HANDOFF.md
records four separate instances of. So the presentation layer is generated too.

CONSTRAINTS THAT SHAPED IT
* **Self-contained.** No CDN, no web font, no external request of any kind. A
  portfolio artifact that needs the network is one that fails in the room, and a
  test asserts it.
* **No build step.** Semantic HTML, modern CSS, vanilla JS. It has to keep
  working on GitHub Pages with nothing in front of it.
* **Dark, and committed to it.** The reference points (Linear, Vercel, Datadog,
  a Bloomberg terminal) are dark-first, and a single theme is one fewer axis on
  which five pages can disagree.
* **Motion is subtle and refusable.** Everything animated respects
  `prefers-reduced-motion`, and every animated element is fully legible in its
  final state if the animation never runs -- so a reader who disables motion,
  or a browser that fails the observer, loses nothing but the movement.
"""

from __future__ import annotations

import html
import json

GITHUB_URL = "https://github.com/Dhanu2626/launderlab"

# (filename, nav label). One list, so every page's nav is the same nav.
NAV = (
    ("index.html", "Overview"),
    ("story.html", "Story Mode"),
    ("results.html", "Results"),
    ("redteam.html", "Red Team"),
    ("multibank.html", "Cross-Bank"),
)

TOKENS = """
:root {
  color-scheme: dark;
  --bg:#08090a; --bg-soft:#0c0e10; --surface:#111417; --surface-2:#161a1e;
  --surface-3:#1c2126; --line:#222930; --line-strong:#2f3841;
  --ink:#e9ecef; --ink-dim:#9aa3ab; --ink-faint:#6b747c;
  --accent:#4c8dff; --accent-soft:#1b3a63;
  --accent-glow:rgba(76,141,255,.14);
  --teal:#2dd4bf; --violet:#a78bfa; --amber:#f0b429; --rose:#f87171;
  --green:#4ade80;
  --c1:#4c8dff; --c2:#2dd4bf; --c3:#f0b429; --c4:#a78bfa; --c5:#f87171;
  --radius:14px; --radius-sm:9px; --radius-lg:20px;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 28px -12px rgba(0,0,0,.7);
  --shadow-lg:0 2px 4px rgba(0,0,0,.4), 0 24px 60px -20px rgba(0,0,0,.85);
  --mono:ui-monospace,"SF Mono","JetBrains Mono","Cascadia Mono",Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",Roboto,"Helvetica Neue",sans-serif;
  --ease:cubic-bezier(.16,1,.3,1);
  --maxw:1120px;
}
"""

BASE_CSS = """
*,*::before,*::after { box-sizing:border-box; }
html { -webkit-text-size-adjust:100%; scroll-behavior:smooth; }
body {
  margin:0; background:var(--bg); color:var(--ink);
  font:400 16px/1.65 var(--sans);
  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
  overflow-x:hidden;
}
body::before {
  content:''; position:fixed; inset:0; pointer-events:none; z-index:0;
  background:
    radial-gradient(900px 500px at 12% -8%, rgba(76,141,255,.10), transparent 60%),
    radial-gradient(760px 420px at 92% 4%, rgba(167,139,250,.07), transparent 62%);
}
main,header,footer { position:relative; z-index:1; }
h1,h2,h3,h4 { margin:0; font-weight:640; letter-spacing:-.021em; line-height:1.18; }
h1 { font-size:clamp(2.1rem,5.2vw,3.5rem); letter-spacing:-.033em; }
h2 { font-size:clamp(1.45rem,2.9vw,2rem); letter-spacing:-.026em; }
h3 { font-size:1.075rem; letter-spacing:-.014em; }
p { margin:0 0 1em; color:var(--ink-dim); }
p:last-child { margin-bottom:0; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; text-underline-offset:3px; }
strong,b { color:var(--ink); font-weight:620; }
code,.mono { font-family:var(--mono); font-size:.875em; }
code {
  background:var(--surface-2); border:1px solid var(--line);
  padding:.13em .42em; border-radius:5px; color:var(--ink);
}
.num { font-family:var(--mono); font-variant-numeric:tabular-nums; }
.wrap { width:100%; max-width:var(--maxw); margin:0 auto; padding:0 24px; }
.narrow { max-width:760px; }
:focus-visible { outline:2px solid var(--accent); outline-offset:3px; border-radius:4px; }
.skip {
  position:absolute; left:-9999px; top:0; background:var(--accent); color:#04070d;
  padding:10px 18px; border-radius:0 0 8px 0; font-weight:600; z-index:100;
}
.skip:focus { left:0; }
.sr { position:absolute; width:1px; height:1px; padding:0; margin:-1px;
      overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }
"""

NAV_CSS = """
.nav {
  position:sticky; top:0; z-index:50;
  background:rgba(8,9,10,.76); backdrop-filter:blur(14px) saturate(150%);
  -webkit-backdrop-filter:blur(14px) saturate(150%);
  border-bottom:1px solid var(--line);
}
.nav-in { display:flex; align-items:center; gap:8px; height:58px;
          max-width:var(--maxw); margin:0 auto; padding:0 24px; }
.brand { display:flex; align-items:center; gap:9px; font-weight:660;
         letter-spacing:-.02em; color:var(--ink); margin-right:6px; font-size:.97rem; }
.brand:hover { text-decoration:none; }
.brand .dot { width:9px; height:9px; border-radius:3px;
  background:linear-gradient(140deg,var(--accent),var(--teal)); flex:0 0 auto; }
.nav-links { display:flex; gap:2px; margin-left:auto; align-items:center;
             overflow-x:auto; scrollbar-width:none; }
.nav-links::-webkit-scrollbar { display:none; }
.nav-links a {
  color:var(--ink-dim); font-size:.855rem; font-weight:500; padding:7px 11px;
  border-radius:8px; white-space:nowrap; transition:color .16s, background .16s;
}
.nav-links a:hover { color:var(--ink); background:var(--surface-2); text-decoration:none; }
.nav-links a[aria-current="page"] { color:var(--ink); background:var(--surface-3); }
.nav-links a.ext { color:var(--ink-faint); }
@media (max-width:720px){ .nav-in { padding:0 14px; } .brand span.full { display:none; } }
"""

LAYOUT_CSS = """
.hero { padding:76px 0 44px; }
.eyebrow {
  display:inline-flex; align-items:center; gap:8px; font-family:var(--mono);
  font-size:.72rem; letter-spacing:.13em; text-transform:uppercase;
  color:var(--accent); background:var(--accent-glow);
  border:1px solid rgba(76,141,255,.24); padding:5px 11px; border-radius:99px;
  margin-bottom:20px;
}
.eyebrow.teal { color:var(--teal); background:rgba(45,212,191,.1);
                border-color:rgba(45,212,191,.24); }
.eyebrow.violet { color:var(--violet); background:rgba(167,139,250,.1);
                  border-color:rgba(167,139,250,.24); }
.eyebrow.amber { color:var(--amber); background:rgba(240,180,41,.1);
                 border-color:rgba(240,180,41,.24); }
.hero h1 { max-width:16ch; }
.hero .grad {
  background:linear-gradient(96deg,var(--ink) 18%,var(--accent) 62%,var(--teal) 96%);
  -webkit-background-clip:text; background-clip:text; color:transparent;
}
.lede { font-size:clamp(1.03rem,1.7vw,1.2rem); color:var(--ink-dim);
        max-width:66ch; margin-top:20px; line-height:1.62; }
.lede strong { color:var(--ink); }
.hero-meta { display:flex; flex-wrap:wrap; gap:9px; margin-top:26px; }
.chip {
  display:inline-flex; align-items:center; gap:7px; font-size:.79rem;
  color:var(--ink-dim); background:var(--surface); border:1px solid var(--line);
  padding:6px 12px; border-radius:99px; font-family:var(--mono);
}
.chip b { color:var(--ink); font-weight:600; }
section { padding:52px 0; }
section + section { border-top:1px solid var(--line); }
.sec-head { margin-bottom:28px; max-width:74ch; }
.sec-head h2 { margin-bottom:12px; }
.sec-head p { font-size:1rem; }
.grid { display:grid; gap:16px; }
.g2 { grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); }
.g3 { grid-template-columns:repeat(auto-fit,minmax(232px,1fr)); }
.g4 { grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); }
.split { display:grid; gap:22px; grid-template-columns:1.35fr .95fr; align-items:start; }
@media (max-width:860px){ .split { grid-template-columns:1fr; } }
footer.ft { border-top:1px solid var(--line); padding:38px 0 56px; margin-top:26px;
            color:var(--ink-faint); font-size:.86rem; }
.ft-in { display:flex; flex-wrap:wrap; gap:18px; justify-content:space-between; }
.ft a { color:var(--ink-dim); }
"""

COMPONENT_CSS = """
.card {
  background:linear-gradient(180deg,var(--surface) 0%,var(--bg-soft) 100%);
  border:1px solid var(--line); border-radius:var(--radius); padding:20px 22px;
  transition:border-color .22s var(--ease), transform .22s var(--ease),
             box-shadow .22s var(--ease);
}
.card.pad-lg { padding:26px 28px; }
.card.hover:hover { border-color:var(--line-strong); transform:translateY(-3px);
                    box-shadow:var(--shadow-lg); }
a.card { display:block; color:inherit; }
a.card:hover { text-decoration:none; }
.card h3 { margin-bottom:7px; }
.card p { font-size:.92rem; }
.kpi { background:var(--surface); border:1px solid var(--line);
       border-radius:var(--radius); padding:18px 20px; position:relative;
       overflow:hidden; }
.kpi::after { content:''; position:absolute; left:0; top:0; bottom:0; width:2px;
              background:linear-gradient(180deg,var(--accent),transparent); opacity:.55; }
.kpi .v { font-family:var(--mono); font-variant-numeric:tabular-nums;
          font-size:clamp(1.5rem,3.1vw,1.95rem); font-weight:600;
          letter-spacing:-.03em; color:var(--ink); line-height:1.1; }
.kpi .v.sm { font-size:1.16rem; letter-spacing:-.01em; }
.kpi .k { font-size:.79rem; font-weight:600; color:var(--ink); margin-top:8px;
          letter-spacing:-.005em; }
.kpi .d { font-size:.77rem; color:var(--ink-faint); margin-top:5px; line-height:1.5; }
.kpi.teal::after   { background:linear-gradient(180deg,var(--teal),transparent); }
.kpi.violet::after { background:linear-gradient(180deg,var(--violet),transparent); }
.kpi.amber::after  { background:linear-gradient(180deg,var(--amber),transparent); }
.kpi.rose::after   { background:linear-gradient(180deg,var(--rose),transparent); }
.note {
  border-left:2px solid var(--line-strong); padding:2px 0 2px 16px;
  color:var(--ink-dim); font-size:.9rem; margin:16px 0 0;
}
.box {
  border:1px solid var(--line); border-radius:var(--radius-sm);
  padding:15px 17px; margin:16px 0 0; background:var(--surface);
  font-size:.91rem; color:var(--ink-dim);
}
.box .bt {
  display:flex; align-items:center; gap:8px; font-size:.71rem; font-weight:700;
  letter-spacing:.11em; text-transform:uppercase; margin-bottom:8px;
  font-family:var(--mono);
}
.box.finding    { border-color:rgba(76,141,255,.3);  background:rgba(76,141,255,.045); }
.box.finding .bt{ color:var(--accent); }
.box.why        { border-color:rgba(45,212,191,.3);  background:rgba(45,212,191,.04); }
.box.why .bt    { color:var(--teal); }
.box.limit      { border-color:rgba(240,180,41,.3);  background:rgba(240,180,41,.04); }
.box.limit .bt  { color:var(--amber); }
.box.warn       { border-color:rgba(248,113,113,.32); background:rgba(248,113,113,.045); }
.box.warn .bt   { color:var(--rose); }
.box.method     { border-color:rgba(167,139,250,.3); background:rgba(167,139,250,.04); }
.box.method .bt { color:var(--violet); }
.box b, .box strong { color:var(--ink); }
details.exp {
  border:1px solid var(--line); border-radius:var(--radius-sm); margin:16px 0 0;
  background:var(--surface); overflow:hidden;
}
details.exp > summary {
  cursor:pointer; padding:13px 17px; font-size:.87rem; font-weight:600;
  color:var(--ink); list-style:none; display:flex; align-items:center; gap:10px;
  transition:background .16s;
}
details.exp > summary::-webkit-details-marker { display:none; }
details.exp > summary::before {
  content:'+'; font-family:var(--mono); color:var(--accent); font-weight:700;
  font-size:1rem; width:14px; flex:0 0 auto; transition:transform .2s var(--ease);
}
details.exp[open] > summary::before { content:'\\2212'; }
details.exp > summary:hover { background:var(--surface-2); }
details.exp .exp-body {
  padding:2px 17px 16px; font-size:.89rem; color:var(--ink-dim);
  border-top:1px solid var(--line);
}
details.exp .exp-body > :first-child { margin-top:13px; }
.tbl { width:100%; border-collapse:collapse; font-size:.87rem; }
.tbl th {
  text-align:left; font-weight:600; color:var(--ink-faint); font-size:.72rem;
  letter-spacing:.08em; text-transform:uppercase; padding:0 14px 9px 0;
  border-bottom:1px solid var(--line); white-space:nowrap;
}
.tbl td { padding:9px 14px 9px 0; border-bottom:1px solid var(--line);
          color:var(--ink-dim); vertical-align:top; }
.tbl tr:last-child td { border-bottom:0; }
.tbl td.n { font-family:var(--mono); font-variant-numeric:tabular-nums; color:var(--ink); }
.tbl tr.hi td { background:rgba(76,141,255,.05); }
.scroll-x { overflow-x:auto; margin:0 -22px; padding:0 22px; }
.pill { display:inline-block; font-family:var(--mono); font-size:.71rem;
        padding:2.5px 8px; border-radius:99px; border:1px solid var(--line);
        color:var(--ink-dim); background:var(--surface-2); white-space:nowrap; }
.pill.on   { background:rgba(74,222,128,.13); color:var(--green);
             border-color:rgba(74,222,128,.3); }
.pill.off  { background:rgba(248,113,113,.12); color:var(--rose);
             border-color:rgba(248,113,113,.3); }
.pill.wait { background:rgba(240,180,41,.12); color:var(--amber);
             border-color:rgba(240,180,41,.28); }
.tl { position:relative; padding-left:26px; }
.tl::before { content:''; position:absolute; left:6px; top:5px; bottom:5px;
              width:1px; background:var(--line); }
.tl-i { position:relative; padding-bottom:20px; }
.tl-i:last-child { padding-bottom:0; }
.tl-i::before {
  content:''; position:absolute; left:-24px; top:6px; width:9px; height:9px;
  border-radius:99px; background:var(--surface-3); border:2px solid var(--line-strong);
}
.tl-i.done::before { background:var(--accent); border-color:var(--accent); }
.tl-i .tl-h { font-size:.9rem; font-weight:620; color:var(--ink); }
.tl-i .tl-d { font-size:.84rem; color:var(--ink-dim); margin-top:3px; }
.tl-i .tl-t { font-family:var(--mono); font-size:.71rem; color:var(--ink-faint); }
.btn {
  display:inline-flex; align-items:center; gap:9px; padding:11px 19px;
  border-radius:10px; font-size:.9rem; font-weight:600; border:1px solid transparent;
  transition:transform .18s var(--ease), background .18s, border-color .18s;
}
.btn:hover { text-decoration:none; transform:translateY(-1.5px); }
.btn.pri { background:var(--accent); color:#04070d; }
.btn.pri:hover { background:#6ba1ff; }
.btn.sec { background:var(--surface-2); color:var(--ink); border-color:var(--line-strong); }
.btn.sec:hover { background:var(--surface-3); }
.btn-row { display:flex; flex-wrap:wrap; gap:11px; margin-top:30px; }
.next {
  display:flex; align-items:center; justify-content:space-between; gap:18px;
  padding:22px 24px; border:1px solid var(--line); border-radius:var(--radius);
  background:linear-gradient(100deg,var(--surface),var(--bg-soft));
  transition:border-color .22s, transform .22s var(--ease);
}
.next:hover { border-color:var(--accent); transform:translateY(-2px); text-decoration:none; }
.next .nx-k { font-family:var(--mono); font-size:.71rem; letter-spacing:.11em;
              text-transform:uppercase; color:var(--ink-faint); }
.next .nx-t { font-size:1.06rem; font-weight:620; color:var(--ink); margin-top:5px; }
.next .nx-d { font-size:.87rem; color:var(--ink-dim); margin-top:4px; }
.next .arw { color:var(--accent); font-size:1.3rem; flex:0 0 auto; }
"""

CHART_CSS = """
.chart-wrap { position:relative; }
.chart-wrap svg { display:block; width:100%; height:auto; overflow:visible; }
.c-lbl  { font-family:var(--sans); font-size:12.5px; fill:var(--ink-dim); }
.c-lbl.k{ fill:var(--ink); font-weight:560; }
.c-val  { font-family:var(--mono); font-size:12px; fill:var(--ink);
          font-variant-numeric:tabular-nums; }
.c-ax   { stroke:var(--line); stroke-width:1; }
.c-grid { stroke:var(--line); stroke-width:1; stroke-dasharray:2 5; opacity:.65; }
.c-bar  { rx:4; transform-origin:left center; transition:opacity .18s; }
.c-row  { cursor:default; }
.c-row:hover .c-bar { opacity:.82; }
.c-row.dim { opacity:.28; }
.c-hit  { fill:transparent; }
.reveal .c-bar { animation:barIn .85s var(--ease) both; }
.reveal .c-line { animation:lineIn 1.15s var(--ease) both; }
.reveal .c-dot { animation:dotIn .4s var(--ease) both; }
@keyframes barIn { from { transform:scaleX(0); } to { transform:scaleX(1); } }
@keyframes lineIn { from { stroke-dashoffset:var(--len); } to { stroke-dashoffset:0; } }
@keyframes dotIn { from { opacity:0; transform:scale(.3); } to { opacity:1; transform:scale(1); } }
.c-line { fill:none; stroke-width:2.25; stroke-linecap:round; stroke-linejoin:round;
          stroke-dasharray:var(--len); }
.legend { display:flex; flex-wrap:wrap; gap:7px; margin-top:16px; }
.legend button {
  display:inline-flex; align-items:center; gap:7px; font:inherit; font-size:.79rem;
  color:var(--ink-dim); background:var(--surface-2); border:1px solid var(--line);
  padding:5px 11px; border-radius:99px; cursor:pointer;
  transition:background .16s, color .16s, opacity .16s;
}
.legend button:hover { color:var(--ink); background:var(--surface-3); }
.legend button[aria-pressed="false"] { opacity:.4; }
.legend i { width:9px; height:9px; border-radius:3px; flex:0 0 auto; }
.tip {
  position:fixed; pointer-events:none; opacity:0; z-index:80;
  background:var(--surface-3); border:1px solid var(--line-strong);
  border-radius:9px; padding:9px 12px; font-size:.8rem; color:var(--ink);
  box-shadow:var(--shadow-lg); transition:opacity .13s; max-width:280px;
  line-height:1.5;
}
.tip.show { opacity:1; }
.tip .tt { font-weight:640; margin-bottom:3px; }
.tip .td { color:var(--ink-dim); font-size:.76rem; }
"""

MOTION_CSS = """
/* Scoped to .js, which a one-line inline script in <head> adds. With JavaScript
   disabled or broken the rule never applies and every section is simply visible.
   Hiding content unconditionally and relying on script to reveal it would make a
   scroll animation load-bearing for whether the page has any content at all. */
.js [data-rv] { opacity:0; transform:translateY(14px);
                transition:opacity .62s var(--ease), transform .62s var(--ease); }
.js [data-rv].in { opacity:1; transform:none; }
@media (prefers-reduced-motion:reduce) {
  html { scroll-behavior:auto; }
  *,*::before,*::after { animation-duration:.001ms !important;
    animation-iteration-count:1 !important; transition-duration:.001ms !important; }
  .js [data-rv] { opacity:1; transform:none; }
  .reveal .c-bar,.reveal .c-line,.reveal .c-dot { animation:none; }
  .c-line { stroke-dasharray:none; }
}
"""

BASE_JS = """
(function(){
  var RM = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* Scroll reveal. Falls back to fully visible if IntersectionObserver is
     missing -- content must never depend on an animation having run. */
  var rv = document.querySelectorAll('[data-rv]');
  if (!('IntersectionObserver' in window) || RM) {
    rv.forEach(function(el){ el.classList.add('in'); });
  } else {
    var io = new IntersectionObserver(function(es){
      es.forEach(function(e){
        if (!e.isIntersecting) return;
        var el = e.target, d = +(el.getAttribute('data-rv') || 0);
        setTimeout(function(){ el.classList.add('in'); }, d * 60);
        io.unobserve(el);
      });
    }, { rootMargin:'0px 0px -8% 0px', threshold:.08 });
    rv.forEach(function(el){ io.observe(el); });
  }

  /* Count-up. The element's text is already correct in the DOM; this only
     replays toward it, and restores the exact original string at the end so no
     rounding here can ever alter a published figure. */
  function countUp(el){
    var target = el.getAttribute('data-count'), final = el.textContent;
    var n = parseFloat(target);
    if (isNaN(n) || RM) return;
    var dec = (target.split('.')[1] || '').length, t0 = null, dur = 950;
    function step(ts){
      if (!t0) t0 = ts;
      var p = Math.min((ts - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3);
      el.textContent = final.replace(target, (n * e).toFixed(dec));
      if (p < 1) requestAnimationFrame(step); else el.textContent = final;
    }
    requestAnimationFrame(step);
  }
  var cu = document.querySelectorAll('[data-count]');
  if ('IntersectionObserver' in window && !RM) {
    var io2 = new IntersectionObserver(function(es){
      es.forEach(function(e){ if (e.isIntersecting) { countUp(e.target); io2.unobserve(e.target); } });
    }, { threshold:.5 });
    cu.forEach(function(el){ io2.observe(el); });
  }

  /* Chart draw-in */
  var charts = document.querySelectorAll('.chart-wrap');
  if ('IntersectionObserver' in window && !RM) {
    var io3 = new IntersectionObserver(function(es){
      es.forEach(function(e){
        if (!e.isIntersecting) return;
        e.target.classList.add('reveal'); io3.unobserve(e.target);
      });
    }, { threshold:.15 });
    charts.forEach(function(c){ io3.observe(c); });
  } else { charts.forEach(function(c){ c.classList.add('reveal'); }); }

  /* One tooltip element, shared by every chart on the page */
  var tip = document.createElement('div');
  tip.className = 'tip'; tip.setAttribute('role','status');
  document.body.appendChild(tip);
  function move(ev){
    var r = tip.getBoundingClientRect();
    var x = ev.clientX + 14, y = ev.clientY - r.height - 12;
    if (x + r.width > window.innerWidth - 10) x = ev.clientX - r.width - 14;
    if (y < 8) y = ev.clientY + 18;
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }
  document.querySelectorAll('[data-tip]').forEach(function(el){
    function show(ev){
      tip.innerHTML = '<div class="tt">' + el.getAttribute('data-tip') + '</div>' +
        (el.getAttribute('data-tip-d') ? '<div class="td">' + el.getAttribute('data-tip-d') + '</div>' : '');
      tip.classList.add('show'); move(ev);
    }
    el.addEventListener('mouseenter', show);
    el.addEventListener('mousemove', move);
    el.addEventListener('mouseleave', function(){ tip.classList.remove('show'); });
    el.addEventListener('focus', function(){
      var b = el.getBoundingClientRect();
      show({ clientX:b.left + b.width / 2, clientY:b.top + b.height / 2 });
    });
    el.addEventListener('blur', function(){ tip.classList.remove('show'); });
  });

  /* Interactive legends: toggle a series without removing it from the DOM, so
     the underlying data stays readable to assistive tech and to view-source. */
  document.querySelectorAll('.legend button[data-series]').forEach(function(btn){
    btn.addEventListener('click', function(){
      var on = btn.getAttribute('aria-pressed') !== 'false';
      btn.setAttribute('aria-pressed', on ? 'false' : 'true');
      var sel = btn.closest('[data-chart]');
      if (!sel) return;
      sel.querySelectorAll('[data-s="' + btn.getAttribute('data-series') + '"]')
         .forEach(function(n){ n.style.display = on ? 'none' : ''; });
    });
  });
})();
"""


def css(*extra: str) -> str:
    return "".join((TOKENS, BASE_CSS, NAV_CSS, LAYOUT_CSS, COMPONENT_CSS,
                    CHART_CSS, MOTION_CSS) + extra)


def esc(text: str) -> str:
    return html.escape(str(text))


# ------------------------------------------------------------------ structure

def nav(active: str) -> str:
    links = "".join(
        f'<a href="{href}"{" aria-current=\"page\"" if href == active else ""}>{esc(label)}</a>'
        for href, label in NAV)
    return (
        '<header class="nav"><div class="nav-in">'
        f'<a class="brand" href="index.html"><span class="dot"></span>'
        f'LaunderLab</a>'
        f'<nav class="nav-links" aria-label="Sections">{links}'
        f'<a class="ext" href="{GITHUB_URL}" rel="noopener">GitHub &#8599;</a>'
        '</nav></div></header>')


def footer() -> str:
    return (
        '<footer class="ft"><div class="wrap"><div class="ft-in">'
        '<div>An open adversarial range for AML detection testing.<br>'
        'All data synthetic. All typologies from public FATF / FinCEN / RBI advisories.</div>'
        f'<div>Built by Dhanush Jangadi &middot; <a href="{GITHUB_URL}" rel="noopener">'
        'Source on GitHub</a><br>'
        'Every figure is rendered from the project&rsquo;s scoring modules, never typed by hand.'
        '</div></div></div></footer>')


def shell(*, title: str, description: str, active: str, body: str,
          extra_css: str = "", extra_js: str = "") -> str:
    """One full HTML document. Self-contained: no external request of any kind."""
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<title>{esc(title)}</title>\n'
        f'<meta name="description" content="{esc(description)}">\n'
        '<meta name="theme-color" content="#08090a">\n'
        f'<meta property="og:title" content="{esc(title)}">\n'
        f'<meta property="og:description" content="{esc(description)}">\n'
        '<meta property="og:type" content="website">\n'
        '<meta name="twitter:card" content="summary_large_image">\n'
        f'<style>{css(extra_css)}</style>\n'
        # Marks that scripting is live, so the reveal styles may apply. Inline
        # and in <head> so it runs before first paint and nothing flashes.
        '<script>document.documentElement.className+=" js";</script>\n'
        '</head>\n<body>\n'
        '<a class="skip" href="#main">Skip to content</a>\n'
        f'{nav(active)}\n<main id="main">\n{body}\n</main>\n{footer()}\n'
        f'<script>{BASE_JS}{extra_js}</script>\n'
        '</body>\n</html>\n')


def hero(*, eyebrow: str, title: str, lede: str, meta: list[tuple[str, str]] | None = None,
         buttons: str = "", tone: str = "") -> str:
    chips = "".join(f'<span class="chip"><b>{esc(v)}</b> {esc(k)}</span>'
                    for v, k in (meta or []))
    return (
        f'<div class="hero"><div class="wrap">'
        f'<span class="eyebrow {tone}" data-rv="0">{esc(eyebrow)}</span>'
        f'<h1 data-rv="1"><span class="grad">{esc(title)}</span></h1>'
        f'<p class="lede" data-rv="2">{lede}</p>'
        + (f'<div class="hero-meta" data-rv="3">{chips}</div>' if chips else "")
        + (f'<div class="btn-row" data-rv="3">{buttons}</div>' if buttons else "")
        + '</div></div>')


def section(*, sid: str, eyebrow: str, title: str, lede: str = "", body: str = "",
            tone: str = "") -> str:
    head = (f'<div class="sec-head" data-rv="0">'
            f'<span class="eyebrow {tone}">{esc(eyebrow)}</span>'
            f'<h2>{esc(title)}</h2>'
            + (f"<p>{lede}</p>" if lede else "") + "</div>")
    return f'<section id="{sid}"><div class="wrap">{head}{body}</div></section>'


def kpi(value: str, label: str, detail: str = "", tone: str = "",
        count: str | None = None, small: bool = False) -> str:
    """One headline number. `count` opts the value into the count-up animation.

    The animation only ever replays toward the value already in the DOM and
    restores the exact original string when it finishes, so it cannot round a
    published figure into a different one.
    """
    attr = f' data-count="{esc(count)}"' if count else ""
    cls = "v sm" if small else "v"
    return (f'<div class="kpi {tone}">'
            f'<div class="{cls}"{attr}>{esc(value)}</div>'
            f'<div class="k">{esc(label)}</div>'
            + (f'<div class="d">{detail}</div>' if detail else "") + "</div>")


def kpis(items: list[tuple], columns: str = "g4") -> str:
    return (f'<div class="grid {columns}" data-rv="1">'
            + "".join(kpi(*i) if isinstance(i, tuple) else i for i in items) + "</div>")


def box(kind: str, title: str, body: str) -> str:
    """A callout. `kind` is one of finding / why / limit / warn / method."""
    return (f'<div class="box {kind}"><div class="bt">{esc(title)}</div>{body}</div>')


def expandable(summary: str, body: str) -> str:
    """Native <details>: keyboard accessible and works with JS disabled."""
    return (f'<details class="exp"><summary>{esc(summary)}</summary>'
            f'<div class="exp-body">{body}</div></details>')


def card(title: str, body: str, *, href: str = "", hover: bool = True,
         extra: str = "") -> str:
    cls = "card hover" if hover else "card"
    inner = f"<h3>{esc(title)}</h3><p>{body}</p>{extra}"
    if href:
        return f'<a class="{cls}" href="{href}">{inner}</a>'
    return f'<div class="{cls}">{inner}</div>'


def next_link(href: str, kind: str, title: str, detail: str) -> str:
    return (f'<a class="next" href="{href}" data-rv="0"><div>'
            f'<div class="nx-k">{esc(kind)}</div>'
            f'<div class="nx-t">{esc(title)}</div>'
            f'<div class="nx-d">{esc(detail)}</div></div>'
            f'<div class="arw" aria-hidden="true">&#8594;</div></a>')


def chart_card(svg: str, *, caption: str = "", legend: str = "") -> str:
    return (f'<div class="card pad-lg" data-rv="1" data-chart>'
            f'<div class="chart-wrap">{svg}</div>{legend}'
            + (f'<p class="note">{caption}</p>' if caption else "") + "</div>")


# --------------------------------------------------------------------- charts

_SERIES = ("c1", "c2", "c3", "c4", "c5")


def bars(rows: list[tuple[str, float]], *, maximum: float | None = None,
         fmt: str = "{:.0%}", accent: set[str] | None = None,
         tips: dict[str, str] | None = None, width: int = 780) -> str:
    """Horizontal bars, animated on reveal, each row hoverable for a tooltip.

    `rows` is [(label, value)]. Values are formatted with `fmt` and never
    recomputed here -- this draws what it is handed.
    """
    if not rows:
        return '<p class="note">No data.</p>'
    accent, tips = accent or set(), tips or {}
    top = maximum if maximum is not None else max((v for _, v in rows), default=0)
    top = top or 1.0
    row_h, pad_l, pad_r = 34, 232, 74
    plot = width - pad_l - pad_r
    height = len(rows) * row_h + 10

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="Bar chart, {len(rows)} values">',
           '<defs>']
    for i, key in enumerate(("c1", "c2")):
        out.append(f'<linearGradient id="bg{i}" x1="0" x2="1" y1="0" y2="0">'
                   f'<stop offset="0%" stop-color="var(--{key})" stop-opacity=".95"/>'
                   f'<stop offset="100%" stop-color="var(--{key})" stop-opacity=".55"/>'
                   f'</linearGradient>')
    out.append("</defs>")

    for i, (label, value) in enumerate(rows):
        y = i * row_h + 6
        w = max(2.0, (value / top) * plot) if value > 0 else 0.0
        fill = "url(#bg1)" if label in accent else "url(#bg0)"
        tip = tips.get(label, "")
        out.append(f'<g class="c-row" data-tip="{esc(label)}" '
                   f'data-tip-d="{esc(tip)}" tabindex="0">')
        out.append(f'<rect class="c-hit" x="0" y="{y - 3}" width="{width}" '
                   f'height="{row_h - 2}"></rect>')
        out.append(f'<text class="c-lbl k" x="{pad_l - 14}" y="{y + 17}" '
                   f'text-anchor="end">{esc(label)}</text>')
        if w:
            out.append(f'<rect class="c-bar" x="{pad_l}" y="{y + 4}" width="{w:.1f}" '
                       f'height="{row_h - 16}" fill="{fill}" '
                       f'style="animation-delay:{i * 70}ms"></rect>')
        out.append(f'<text class="c-val" x="{pad_l + w + 9:.1f}" y="{y + 17}">'
                   f'{fmt.format(value)}</text>')
        out.append("</g>")
    out.append(f'<line class="c-ax" x1="{pad_l}" y1="2" x2="{pad_l}" y2="{height - 8}"/>')
    out.append("</svg>")
    return "".join(out)


def lines(series: dict[str, list[float]], *, y_max: float = 1.0,
          y_fmt: str = "{:.0%}", x_label: str = "gen", width: int = 780,
          height: int = 340) -> tuple[str, str]:
    """Multi-series line chart. Returns (svg, legend html)."""
    if not series:
        return '<p class="note">No data.</p>', ""
    n = max(len(v) for v in series.values())
    pad = 54
    pw, ph = width - pad * 2, height - pad * 2
    step = pw / max(n - 1, 1)

    def xy(i, v):
        return pad + i * step, pad + ph * (1 - min(v / y_max, 1.0))

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="Line chart, {len(series)} series over {n} points">']
    for frac in (0, .25, .5, .75, 1):
        _, y = xy(0, frac * y_max)
        out.append(f'<line class="c-grid" x1="{pad}" y1="{y:.1f}" '
                   f'x2="{width - pad}" y2="{y:.1f}"/>')
        out.append(f'<text class="c-val" x="{pad - 12}" y="{y + 4:.1f}" '
                   f'text-anchor="end">{y_fmt.format(frac * y_max)}</text>')
    for i in range(n):
        x, _ = xy(i, 0)
        out.append(f'<text class="c-lbl" x="{x:.1f}" y="{height - pad + 24}" '
                   f'text-anchor="middle">{x_label}{i}</text>')

    for idx, (name, values) in enumerate(series.items()):
        col = f"var(--{_SERIES[idx % len(_SERIES)]})"
        pts = [xy(i, v) for i, v in enumerate(values)]
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        length = int(sum(((pts[i + 1][0] - pts[i][0]) ** 2
                          + (pts[i + 1][1] - pts[i][1]) ** 2) ** .5
                         for i in range(len(pts) - 1)) + 10)
        out.append(f'<g data-s="{esc(name)}">')
        out.append(f'<polyline class="c-line" points="{d}" stroke="{col}" '
                   f'style="--len:{length};animation-delay:{idx * 110}ms"/>')
        for i, (x, y) in enumerate(pts):
            out.append(f'<circle class="c-dot" cx="{x:.1f}" cy="{y:.1f}" r="4" '
                       f'fill="{col}" style="animation-delay:{700 + i * 45}ms" '
                       f'data-tip="{esc(name)} &middot; {x_label}{i}" '
                       f'data-tip-d="{y_fmt.format(values[i])}" tabindex="0"/>')
        out.append("</g>")
    out.append("</svg>")

    legend = '<div class="legend">' + "".join(
        f'<button type="button" aria-pressed="true" data-series="{esc(name)}">'
        f'<i style="background:var(--{_SERIES[i % len(_SERIES)]})"></i>{esc(name)}</button>'
        for i, name in enumerate(series)) + "</div>"
    return "".join(out), legend


def donut(fraction: float, *, label: str, size: int = 132) -> str:
    """A single share, drawn as a ring. Used where one number IS the finding."""
    r, cx = size / 2 - 12, size / 2
    circ = 2 * 3.141592653589793 * r
    return (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" role="img" '
        f'aria-label="{esc(label)}: {fraction:.0%}">'
        f'<circle cx="{cx}" cy="{cx}" r="{r:.1f}" fill="none" stroke="var(--line)" '
        f'stroke-width="10"/>'
        f'<circle cx="{cx}" cy="{cx}" r="{r:.1f}" fill="none" stroke="var(--c1)" '
        f'stroke-width="10" stroke-linecap="round" '
        f'stroke-dasharray="{circ * fraction:.1f} {circ:.1f}" '
        f'transform="rotate(-90 {cx} {cx})"/>'
        f'<text x="{cx}" y="{cx + 2}" text-anchor="middle" class="c-val" '
        f'style="font-size:21px" >{fraction:.0%}</text>'
        f'<text x="{cx}" y="{cx + 20}" text-anchor="middle" class="c-lbl" '
        f'style="font-size:10.5px">{esc(label)}</text></svg>')


def json_payload(name: str, data) -> str:
    return f"const {name} = {json.dumps(data, separators=(',', ':'))};"
