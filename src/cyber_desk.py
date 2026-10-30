"""Personal watchlist research room with imported snapshots and public quotes."""

from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from .calculations import stock_snapshot_history
from .cyber_desk_model import build_cyber_desk_model
from .cyber_quote import load_focused_quote
from .watchlist_store import load_watchlist, save_watchlist


_WATCHLIST_PATH = Path(__file__).resolve().parent.parent / "data" / "watchlist.json"


_CSS = """<style>
.cyber-desk{--cd-bg:#081420;--cd-panel:#122436;--cd-line:#54717d;--cd-text:#e9f8f8;--cd-mint:#8cf0c5;--cd-pink:#e166ae;color:var(--cd-text);font-family:'Microsoft YaHei',sans-serif}
.cyber-desk *{box-sizing:border-box}.cyber-desk .cd-banner{padding:9px 15px;border:1px solid #846a42;background:#3c3020;color:#ffdfaa;font-size:12px;font-weight:700;text-align:center}
.cyber-desk .cd-head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:21px 3px 16px}.cyber-desk h1{margin:0;color:#e9fbfb;font-size:29px;letter-spacing:.13em}.cyber-desk .cd-kicker{color:#6bdfdc;letter-spacing:.24em;font-size:10px}.cyber-desk .cd-meta{color:#a7c2c9;text-align:right;font-size:12px}
.cyber-desk .cd-room{position:relative;min-height:485px;overflow:hidden;border:1px solid #6c8793;background:radial-gradient(ellipse at 50% 5%,#44536e,#212e43 42%,#0b1728 90%);box-shadow:inset 0 0 80px #020713,0 15px 35px #0008}.cyber-desk .cd-room:before{content:'';position:absolute;inset:26% -20% -10%;background:repeating-linear-gradient(0deg,transparent 0 34px,#8495a321 35px 36px),repeating-linear-gradient(90deg,transparent 0 78px,#8495a321 79px 80px);transform:perspective(440px) rotateX(50deg);transform-origin:bottom}.cyber-desk .cd-room:after{content:'';position:absolute;inset:0;border:6px solid #c6529b70;box-shadow:inset 0 0 18px #ee65b068;pointer-events:none}.cyber-desk .cd-room-title{position:relative;z-index:3;display:flex;justify-content:space-between;gap:10px;padding:20px 23px;color:#ddf9f5;font-size:12px;font-weight:700;letter-spacing:.12em}.cyber-desk .cd-room-title small{color:#a9c8d0;font-weight:400;letter-spacing:0}
.cyber-desk .cd-desks{position:relative;z-index:2;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px 22px;max-width:910px;margin:5px auto 75px;padding:0 18px}.cyber-desk .cd-desk{min-height:152px;position:relative;padding-top:5px;filter:drop-shadow(0 12px 8px #0009);animation:cd-enter .7s both}.cyber-desk .cd-desk:nth-child(2){animation-delay:.09s}.cyber-desk .cd-desk:nth-child(3){animation-delay:.18s}.cyber-desk .cd-desk:nth-child(4){animation-delay:.27s}.cyber-desk .cd-desk:nth-child(5){animation-delay:.36s}.cyber-desk .cd-desk:nth-child(6){animation-delay:.45s}.cyber-desk .cd-monitor{position:relative;width:78%;min-height:91px;margin:auto;padding:9px 9px 15px;border:4px solid #90a4af;border-radius:7px;background:linear-gradient(145deg,#1b2b3d,#0b1422);box-shadow:inset 0 0 25px #154d5a,0 0 12px #40dec342}.cyber-desk .cd-monitor:after{content:'';position:absolute;bottom:-17px;left:46%;height:14px;width:8%;background:#8095a0}.cyber-desk .cd-monitor header{display:flex;justify-content:space-between;gap:4px;padding:0;border:0}.cyber-desk .cd-monitor b{color:#eafafa;font-size:12px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.cyber-desk .cd-monitor em{color:#a4efc7;font:normal 700 11px Consolas,monospace;white-space:nowrap}.cyber-desk .cd-monitor em.down{color:#f5a7ae}.cyber-desk .cd-screen-note{display:block;margin-top:16px;color:#83aeb8;font-size:10px}.cyber-desk .cd-spark{display:flex;align-items:end;gap:3px;width:100%;height:38px;margin-top:7px;padding:3px 2px 0;border-bottom:1px solid #6ba8af55}.cyber-desk .cd-spark i{display:block;flex:1;min-width:2px;height:var(--bar-height);background:linear-gradient(0deg,#327d87,#88f0ca);box-shadow:0 0 6px #71e7cd77;transform-origin:bottom;animation:cd-bar .75s ease both}.cyber-desk .cd-spark i:nth-child(2n){animation-delay:.12s}.cyber-desk .cd-spark i:nth-child(3n){animation-delay:.24s}.cyber-desk .cd-desk:nth-child(2n) .cd-spark i{background:linear-gradient(0deg,#4176a1,#a2caff)}.cyber-desk .cd-desk:nth-child(3n) .cd-spark i{background:linear-gradient(0deg,#854a81,#f3afd6)}.cyber-desk .cd-keyboard{width:96%;height:35px;margin:15px auto 0;border:2px solid #899da9;border-radius:4px;background:linear-gradient(#647b8c,#2e4355);transform:perspective(100px) rotateX(48deg);box-shadow:0 4px #172b3a}.cyber-desk .cd-keyboard:before{content:'';display:block;margin:8px 16px;height:12px;border-top:2px dashed #b6c4ce88;border-bottom:2px dashed #b6c4ce88}.cyber-desk .cd-bot{position:absolute;z-index:3;width:20px;height:23px;border-radius:11px 11px 5px 5px;background:#ffafd1;box-shadow:0 0 12px #ffafd1;animation:cd-patrol 7s ease-in-out infinite}.cyber-desk .cd-bot:before{content:'··';position:absolute;top:-1px;left:4px;color:#264053;font-size:20px;line-height:16px}.cyber-desk .cd-bot:after{content:'';position:absolute;left:3px;bottom:-3px;width:5px;height:5px;background:inherit;box-shadow:10px 0 currentColor}.cyber-desk .cd-bot.a{left:18%;top:49%}.cyber-desk .cd-bot.b{left:51%;top:43%;background:#8bcaff;box-shadow:0 0 12px #8bcaff;animation-delay:-2s}.cyber-desk .cd-bot.c{left:78%;top:57%;background:#a9ffb2;box-shadow:0 0 12px #a9ffb2;animation-delay:-4s}.cyber-desk .cd-floor{position:absolute;z-index:3;bottom:0;left:0;right:0;min-height:54px;display:flex;align-items:center;gap:12px;padding:10px 20px;border-top:3px solid #d455a5;background:#0b1a29ee;box-shadow:0 -6px 18px #ed65b060}.cyber-desk .cd-floor span{color:#a9c5ce;font-size:11px;white-space:nowrap}.cyber-desk .cd-floor strong{color:#a5f1c8;font:700 15px Consolas,monospace}.cyber-desk .cd-floor-line{flex:1;height:25px;background:linear-gradient(170deg,transparent 25%,#86eabf 26% 28%,transparent 29% 48%,#86eabf 49% 51%,transparent 52%);opacity:.6;animation:cd-scan 7s ease-in-out infinite}
.cyber-desk .cd-desk.cd-focused .cd-monitor{border-color:#adf7d8;box-shadow:inset 0 0 28px #2a8e89,0 0 18px #7af1d3;animation:cd-focus 3s ease-in-out infinite}.cyber-desk .cd-desk.cd-focused .cd-keyboard{border-color:#adf7d8}.cyber-desk .cd-desk.cd-related .cd-monitor{border-color:#8e9fd0}.cyber-desk .cd-focus-tag{position:absolute;z-index:2;top:-8px;left:11%;padding:2px 7px;border:1px solid #a8f5d3;background:#16443f;color:#d6ffeb;font-size:9px;letter-spacing:.08em}
.cyber-desk .cd-monitor[data-focus-code],.cyber-desk button.cd-keyboard{cursor:pointer}.cyber-desk .cd-monitor[data-focus-code]:hover{border-color:#b8e9e1}.cyber-desk .cd-monitor:focus-visible,.cyber-desk button.cd-keyboard:focus-visible{outline:3px solid #f2d391;outline-offset:3px}.cyber-desk button.cd-keyboard{display:block;color:#e4f9f4;font:700 11px 'Microsoft YaHei',sans-serif;letter-spacing:.14em}.cyber-desk button.cd-keyboard:before{display:none}.cyber-desk button.cd-keyboard:hover{background:linear-gradient(#7d9aa9,#355b68)}
.cyber-desk .cd-room-wires{position:absolute;inset:0;width:100%;height:100%;z-index:1;pointer-events:none}.cyber-desk .cd-room-wires.mobile{display:none}.cyber-desk .cd-room-wires .track{fill:none;stroke:#76e5e9;stroke-width:2;opacity:.65;filter:drop-shadow(0 0 4px #66efe8)}.cyber-desk .cd-room-wires .pulse{fill:none;stroke:#dcfff9;stroke-width:3.5;stroke-dasharray:24 216;stroke-linecap:round;filter:drop-shadow(0 0 8px #9ffff1);animation:cd-room-route 4s linear infinite}@keyframes cd-room-route{to{stroke-dashoffset:-240}}.cyber-desk.cd-motion-off .cd-room-wires .pulse{animation:none;opacity:0}.cyber-desk .cd-room .cd-floor{z-index:3}
@keyframes cd-enter{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}@keyframes cd-bar{from{transform:scaleY(.08)}to{transform:scaleY(1)}}@keyframes cd-scan{0%,100%{opacity:.35}50%{opacity:.9}}@keyframes cd-focus{0%,100%{box-shadow:inset 0 0 24px #2a8e89,0 0 10px #7af1d3}50%{box-shadow:inset 0 0 30px #2a8e89,0 0 22px #7af1d3}}@keyframes cd-patrol{0%,100%{transform:translate(0,0)}35%{transform:translate(18px,-12px)}70%{transform:translate(-12px,7px)}}
.cyber-desk.cd-motion-off *,.cyber-desk.cd-motion-off *:before,.cyber-desk.cd-motion-off *:after{animation:none!important;transition:none!important}
@media(max-width:720px){.cyber-desk .cd-head{align-items:flex-start;flex-direction:column}.cyber-desk .cd-meta{text-align:left}.cyber-desk .cd-room{min-height:470px}.cyber-desk .cd-desks{gap:4px;padding:0 3px}.cyber-desk .cd-monitor{width:95%;padding:5px;min-height:81px}.cyber-desk .cd-monitor b{font-size:9px}.cyber-desk .cd-monitor em{font-size:8px}.cyber-desk .cd-keyboard{width:110%}.cyber-desk .cd-floor{padding:8px}.cyber-desk .cd-floor span{font-size:9px}}@media(prefers-reduced-motion:reduce){.cyber-desk *,.cyber-desk *:before,.cyber-desk *:after{animation:none!important}}
@media(max-width:560px){.cyber-desk .cd-desks{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 5px;margin-bottom:75px}.cyber-desk .cd-desk{min-height:142px}.cyber-desk .cd-monitor{width:88%}.cyber-desk .cd-keyboard{width:95%}.cyber-desk .cd-room-title{padding:14px 10px;flex-direction:column}.cyber-desk .cd-room{min-height:640px}.cyber-desk .cd-floor{gap:5px}.cyber-desk .cd-floor strong{font-size:11px}}
@media(max-width:560px){.cyber-desk .cd-room-wires.desktop{display:none}.cyber-desk .cd-room-wires.mobile{display:block}}
</style>"""

_ROOM_JS = """
export default function ({ data, parentElement, setTriggerValue }) {
  const root = parentElement.querySelector('#room-root');
  if (!root) return;
  root.innerHTML = data.room;
  root.onclick = (event) => {
    const open = event.target.closest('[data-open-code]');
    if (open && root.contains(open)) {
      setTriggerValue('open_stock', open.dataset.openCode);
      return;
    }
    const monitor = event.target.closest('[data-focus-code]');
    if (monitor && root.contains(monitor)) {
      setTriggerValue('focus_stock', monitor.dataset.focusCode);
    }
  };
  root.onkeydown = (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const monitor = event.target.closest('[data-focus-code]');
    if (monitor && root.contains(monitor)) {
      event.preventDefault();
      setTriggerValue('focus_stock', monitor.dataset.focusCode);
    }
  };
  return () => { root.onclick = null; root.onkeydown = null; };
}
"""

_ROOM_COMPONENT = st.components.v2.component(
    "cyber_watchlist_room",
    html='<div id="room-root"></div>',
    css=_CSS.removeprefix("<style>").removesuffix("</style>"),
    js=_ROOM_JS,
)

_FLOW_JS = """
export default function ({ data, parentElement }) {
  const doc = parentElement.ownerDocument;
  const svgNS = 'http://www.w3.org/2000/svg';
  const overlay = doc.createElementNS(svgNS, 'svg');
  overlay.setAttribute('aria-hidden', 'true');
  overlay.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:5;overflow:visible';
  doc.body.appendChild(overlay);
  let lastGeometry = '';
  const render = () => {
    const animate = data.motion && !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const roots = [doc];
    for (const element of doc.querySelectorAll('*')) {
      if (element.shadowRoot) roots.push(element.shadowRoot);
    }
    const pick = (selector) => roots.flatMap(root => [...root.querySelectorAll(selector)])
      .map(element => element.getBoundingClientRect())
      .filter(rect => rect.width > 80 && rect.height > 20);
    const room = pick('.cyber-desk .cd-room')[0];
    const motionControl = pick('.st-key-cyber_desk_motion')[0];
    const focusControl = pick('.st-key-cyber_focus_stock')[0];
    const banner = pick('.cyber-desk .cd-banner')[0];
    const quote = pick('.cd-quote-network')[0];
    const minute = pick('.st-key-cyber-minute-panel')[0];
    const notice = !quote && room && minute ? pick('[data-testid="stAlert"]')
      .filter(rect => rect.top >= room.bottom && rect.bottom <= minute.top + 8)
      .sort((a, b) => a.top - b.top)[0] : null;
    const panels = [room, quote || notice, minute].filter(Boolean);
    if (panels.length < 2) {
      overlay.replaceChildren();
      lastGeometry = '';
      return;
    }
    const footer = pick('[data-testid="stExpander"]')
      .filter(rect => rect.top >= panels[panels.length - 1].bottom - 10)
      .sort((a, b) => a.top - b.top)[0];
    if (footer) panels.push(footer);
    const bridges = panels.slice(1).map((panel, index) => [panels[index], panel]);
    const geometry = bridges.map(([a, b]) => [a.left,a.right,a.top,a.bottom,b.left,b.right,b.top,b.bottom].map(Math.round).join(',')).join('|')
      + [motionControl, focusControl, banner].filter(Boolean).map(rect => [rect.left,rect.right,rect.top,rect.bottom].map(Math.round).join(',')).join('|')
      + `|${animate}|${window.innerWidth}`;
    if (geometry === lastGeometry) return;
    lastGeometry = geometry;
    overlay.setAttribute('viewBox', `0 0 ${window.innerWidth} ${window.innerHeight}`);
    const edgeRoutes = [
      {side:-1, from:.62, to:.08, reach:13, wave:-7, phase:.36, major:true},
      {side:-1, from:.79, to:.23, reach:27, wave:9, phase:.57},
      {side:-1, from:.84, to:.31, reach:39, wave:-11, phase:.48},
      {side:-1, from:.91, to:.17, reach:19, wave:-5, phase:.46},
      {side:-1, from:.98, to:.04, reach:35, wave:11, phase:.68},
      {side:1, from:.69, to:.17, reach:17, wave:-9, phase:.39, major:true},
      {side:1, from:.82, to:.33, reach:34, wave:12, phase:.52},
      {side:1, from:.86, to:.25, reach:43, wave:-12, phase:.61},
      {side:1, from:.94, to:.11, reach:24, wave:-7, phase:.64},
      {side:1, from:.99, to:.05, reach:39, wave:8, phase:.44},
    ];
    const middleRoutes = [
      {from:.22, to:.29, sway:-.10, major:true},
      {from:.34, to:.43, sway:.14},
      {from:.46, to:.39, sway:-.08},
      {from:.51, to:.58, sway:.07},
      {from:.59, to:.66, sway:.12, major:true},
      {from:.73, to:.61, sway:-.13},
      {from:.78, to:.73, sway:.11},
      {from:.84, to:.80, sway:.09},
    ];
    const paths = bridges.flatMap(([a, b], bridgeIndex) => {
      const edgePaths = edgeRoutes.map((route, strand) => {
        const left = route.side < 0;
        const startX = left ? a.left + 1 : a.right - 1;
        const endX = left ? b.left + 1 : b.right - 1;
        const startY = a.top + a.height * route.from;
        const endY = b.top + b.height * route.to;
        const gap = Math.max(1, endY - startY);
        const outside = left
          ? Math.max(6, Math.min(a.left, b.left) - route.reach)
          : Math.min(window.innerWidth - 6, Math.max(a.right, b.right) + route.reach);
        const midX = Math.max(5, Math.min(window.innerWidth - 5, outside + route.wave));
        const midY = startY + gap * route.phase;
        return {
          d: `M ${startX} ${startY} C ${outside} ${startY + gap * .12}, ${midX + route.wave} ${midY - gap * .14}, ${midX} ${midY} C ${midX - route.wave} ${midY + gap * .14}, ${outside} ${endY - gap * .1}, ${endX} ${endY}`,
          startX, startY, endX, endY, major:!!route.major, pulse:strand % 2 === 0,
          delay: -(bridgeIndex * .8 + strand * .43),
          color: strand % 5 === 3 ? '#b5a8e7' : '#72d9de',
        };
      });
      const middlePaths = middleRoutes.slice(0, b.top - a.bottom < 28 ? 5 : 8).map((route, strand) => {
        const startX = a.left + a.width * route.from;
        const endX = b.left + b.width * route.to;
        const startY = a.bottom, endY = b.top;
        const gap = Math.max(1, endY - startY);
        const drift = Math.min(a.width, b.width) * route.sway * Math.min(1, gap / 70);
        return {
          d: `M ${startX} ${startY} C ${startX + drift} ${startY + gap * .26}, ${endX - drift * .7} ${endY - gap * .31}, ${endX} ${endY}`,
          startX, startY, endX, endY, major:!!route.major, pulse:strand % 2 === 1,
          delay: -(bridgeIndex * .9 + strand * .61 + 1.1),
          color: strand === 2 ? '#c5a8d9' : '#72d9de',
        };
      });
      return [...edgePaths, ...middlePaths];
    });
    const topConnections = [
      [motionControl, banner, .44, .09, -15, true],
      [motionControl, banner, .68, .17, 14, false],
      [focusControl, banner, .22, .57, -18, false],
      [focusControl, banner, .53, .74, 21, true],
      [focusControl, banner, .83, .87, -13, false],
      [banner, room, .30, .36, -23, true],
      [banner, room, .40, .48, 17, false],
      [banner, room, .51, .53, -14, false],
      [banner, room, .61, .68, 24, true],
      [banner, room, .74, .72, -19, false],
      [banner, room, .83, .80, 15, false],
    ];
    paths.push(...topConnections.flatMap(([a, b, from, to, sway, major], index) => {
      if (!a || !b) return [];
      const startX = a.left + a.width * from, startY = a.bottom;
      const endX = b.left + b.width * to, endY = b.top;
      const gap = Math.max(1, endY - startY);
      return [{
        d: `M ${startX} ${startY} C ${startX + sway} ${startY + gap * .28}, ${endX - sway * .7} ${endY - gap * .32}, ${endX} ${endY}`,
        startX, startY, endX, endY, major, pulse:index % 2 === 0,
        delay: -(index * .47 + .6), color:index % 4 === 2 ? '#b5a8e7' : '#72d9de',
      }];
    }));
    overlay.innerHTML = `<style>
      .cyber-flow-halo{fill:none;stroke:#57ebdf;stroke-width:7;opacity:.12;filter:blur(5px)}
      .cyber-flow-track{fill:none;stroke:#6dcbd5;stroke-width:1.4;opacity:.57;filter:drop-shadow(0 0 3px #58eae3)}
      .cyber-flow-pulse{fill:none;stroke:#c8fff5;stroke-width:2.8;stroke-linecap:round;stroke-dasharray:19 205;filter:drop-shadow(0 0 6px #85ffee);animation:cyber-page-travel 3.7s linear infinite}
      .cyber-flow-node{fill:#bafff0;opacity:.75;filter:drop-shadow(0 0 5px #68f5e7)}
      @keyframes cyber-page-travel{to{stroke-dashoffset:-224}}
    </style>` + paths.map(path => `${path.major ? `<path class="cyber-flow-halo" d="${path.d}"/>` : ''}<path class="cyber-flow-track" style="stroke:${path.color};opacity:${path.major ? .68 : .42}" d="${path.d}"/>${path.major ? `<circle class="cyber-flow-node" cx="${path.startX}" cy="${path.startY}" r="2.1"/><circle class="cyber-flow-node" cx="${path.endX}" cy="${path.endY}" r="2.1"/>` : ''}${animate && (path.major || path.pulse) ? `<path class="cyber-flow-pulse" style="animation-delay:${path.delay}s;opacity:${path.major ? .8 : .32}" d="${path.d}"/>` : ''}`).join('');
  };
  const onScroll = () => requestAnimationFrame(render);
  window.addEventListener('scroll', onScroll, {passive:true});
  window.addEventListener('resize', onScroll);
  const timer = window.setInterval(render, 2000);
  render();
  return () => {
    window.clearInterval(timer);
    window.removeEventListener('scroll', onScroll);
    window.removeEventListener('resize', onScroll);
    overlay.remove();
  };
}
"""

_FLOW_COMPONENT = st.components.v2.component(
    "cyber_page_flow", html='<span aria-hidden="true" style="display:none"></span>', js=_FLOW_JS,
)

_PANEL_CSS = """<style>
.block-container{padding-left:3.25rem!important;padding-right:3.75rem!important}
@media(max-width:700px){.block-container{padding-left:2.8rem!important;padding-right:2.8rem!important}}
.st-key-cyber-minute-panel{background:radial-gradient(circle at 90% 5%,#21465b55,transparent 45%),linear-gradient(145deg,#0b1e2d,#08121f)!important;border:1px solid #457884!important;box-shadow:inset 0 0 25px #1a697225,0 12px 30px #0005!important}
.st-key-cyber-minute-panel h3{color:#dffaf5;letter-spacing:.05em}
.cd-quote-network{position:relative;margin:10px 0 0;isolation:isolate}.cd-quote-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));column-gap:22px;row-gap:32px;position:relative;z-index:2}.cd-quote-card{position:relative;min-height:88px;padding:15px 16px;border:1px solid #3e7b87;border-radius:8px;background:linear-gradient(140deg,#112b3bf5,#0a1728f5);box-shadow:inset 0 0 20px #52c6ce13,0 0 0 1px #1a63751c}.cd-quote-card:after{content:'';position:absolute;bottom:-5px;left:calc(50% - 4px);width:8px;height:8px;border-radius:50%;background:#7ff4ee;box-shadow:0 0 12px #7ff4ee;opacity:.72}.cd-quote-card small{display:block;color:#9fc7ce;font-size:12px}.cd-quote-card strong{display:block;margin-top:7px;color:#a8fff0;font:700 24px Consolas,monospace;text-shadow:0 0 12px #51e6db66}.cd-quote-card.up strong{color:#ff9cac}.cd-quote-card.down strong{color:#83e7c3}.cd-quote-wires{position:absolute;top:0;left:0;width:100%;height:calc(100% - 42px);z-index:1;overflow:visible;pointer-events:none}.cd-quote-wires.mobile{display:none}.cd-quote-wires .track{fill:none;stroke:#63c2d4;stroke-width:1.5;opacity:.38}.cd-quote-wires .pulse{fill:none;stroke:#a8fff7;stroke-width:3;stroke-linecap:round;stroke-dasharray:16 180;filter:drop-shadow(0 0 5px #8dfaf4);opacity:0}.cd-quote-network.motion-on .pulse{opacity:.95;animation:cd-wire-travel 3s linear infinite}.cd-quote-network.motion-on .pulse:nth-of-type(3n){animation-delay:-1s}.cd-quote-network.motion-on .pulse:nth-of-type(4n){animation-delay:-2s}@keyframes cd-wire-travel{to{stroke-dashoffset:-196}}.cd-quote-network .conduit{height:42px;display:flex;justify-content:center;align-items:stretch;gap:24px}.cd-quote-network .conduit i{width:2px;background:linear-gradient(#8cfff1,#78b8e0 55%,transparent);box-shadow:0 0 9px #78e8e8;opacity:.65}.cd-quote-network.motion-on .conduit i{animation:cd-conduit 2.4s ease-in-out infinite}.cd-quote-network.motion-on .conduit i:nth-child(2){animation-delay:-.8s}.cd-quote-network.motion-on .conduit i:nth-child(3){animation-delay:-1.6s}@keyframes cd-conduit{50%{opacity:1;box-shadow:0 0 17px #adfff9}}.cd-quote-grid.live .cd-quote-card{animation:cd-quote-arrive .7s ease-out both}@keyframes cd-quote-arrive{from{box-shadow:inset 0 0 22px #77ffff77;transform:translateY(4px)}to{box-shadow:inset 0 0 20px #52c6ce13;transform:translateY(0)}}@media(max-width:650px){.cd-quote-grid{grid-template-columns:repeat(2,minmax(0,1fr));column-gap:18px;row-gap:28px}.cd-quote-card strong{font-size:19px}.cd-quote-wires.desktop{display:none}.cd-quote-wires.mobile{display:block}}@media(prefers-reduced-motion:reduce){.cd-quote-network .pulse,.cd-quote-network .conduit i,.cd-quote-grid .cd-quote-card{animation:none!important}.cd-quote-network .pulse{opacity:0!important}}
.cd-quote-grid{row-gap:26px}
.cd-quote-card{--card-accent:#72e9e8;min-height:151px;padding:0;border:1px solid #5593a0;border-radius:0;clip-path:polygon(0 0,calc(100% - 18px) 0,100% 18px,100% 100%,18px 100%,0 calc(100% - 18px));background:radial-gradient(circle at 92% 8%,#4ab9c827,transparent 32%),linear-gradient(140deg,#153447,#0a192a 64%,#111a31);box-shadow:inset 0 0 26px #47c8d328;transition:transform .25s ease,border-color .25s ease,filter .25s ease;isolation:isolate}
.cd-quote-card.up{--card-accent:#ff91ad}.cd-quote-card.down{--card-accent:#81efc5}
.cd-quote-card:before{content:'';position:absolute;inset:0;z-index:0;background:linear-gradient(105deg,transparent 35%,#b9fff417 49%,transparent 63%),repeating-linear-gradient(0deg,transparent 0 6px,#8de9ed0b 7px 8px);transform:translateX(-115%);pointer-events:none}
.cd-quote-network.motion-on .cd-quote-card:before{animation:cd-card-sweep 7s linear infinite}
.cd-quote-card:nth-child(2n):before{animation-delay:-2.2s!important}.cd-quote-card:nth-child(3n):before{animation-delay:-4.1s!important}
.cd-quote-card:after{top:0;right:19px;bottom:auto;left:auto;width:46px;height:2px;border-radius:0;background:var(--card-accent);box-shadow:0 0 12px var(--card-accent);opacity:.86}
.cd-quote-card:hover{transform:translateY(-3px);border-color:var(--card-accent);filter:drop-shadow(0 0 12px #59d5dc5c)}
.cd-card-shell{position:relative;z-index:1;display:flex;flex-direction:column;min-height:149px;padding:14px 18px 12px}
.cd-card-top{display:flex;align-items:center;gap:7px;min-height:18px}.cd-card-top small{font-size:11px;letter-spacing:.09em;color:#a8ccd5}
.cd-card-badge{margin-left:auto;padding:2px 6px;border:1px solid #5cbbb0;background:#123b3d;color:#a7fff0;font:9px Consolas,monospace;white-space:nowrap;letter-spacing:.03em}
.cd-card-badge.snapshot,.cd-card-badge.stale{border-color:#9b7750;background:#3a2c25;color:#ffcf92}
.cd-quote-card strong{display:block;margin-top:13px;color:var(--card-accent);font:700 30px Consolas,monospace;line-height:1.15;letter-spacing:.025em;text-shadow:0 0 18px color-mix(in srgb,var(--card-accent),transparent 52%)}
.cd-card-tail{display:flex;align-items:end;gap:10px;min-height:33px;margin-top:auto;padding-right:54px;color:#8cb9c4}
.cd-mini-line,.cd-mini-bars{flex:1;min-width:60px;max-width:180px;height:28px;overflow:visible}.cd-mini-line polyline{fill:none;stroke:var(--card-accent);stroke-width:2;vector-effect:non-scaling-stroke;filter:drop-shadow(0 0 4px var(--card-accent))}.cd-mini-bars rect{fill:#65cbd3;opacity:.82}
.cd-tail-note{font:10px 'Microsoft YaHei',sans-serif;color:#8fb5c1;white-space:nowrap}.cd-card-index{position:absolute;right:17px;bottom:13px;color:#56818f;font:10px Consolas,monospace;letter-spacing:.04em}
.cd-data-arrow{font:700 29px Consolas,monospace;line-height:24px;color:var(--card-accent);text-shadow:0 0 11px var(--card-accent)}
.cd-amount .cd-card-tail:before{content:'';width:88px;height:9px;background:repeating-linear-gradient(90deg,#75d7d8 0 4px,transparent 4px 9px);mask-image:linear-gradient(90deg,#000,transparent);opacity:.8}
.cd-turnover .cd-card-tail:before{content:'';width:21px;height:21px;border:2px dashed #7ee8db;border-radius:50%;box-shadow:0 0 9px #72d9d866;opacity:.78}
.cd-ratio-scale{position:relative;display:flex;justify-content:space-between;align-items:end;width:min(180px,100%);height:28px;padding-top:11px;border-top:1px solid #62acb8;color:#8fb5c1;font:9px Consolas,monospace}.cd-ratio-scale i{position:absolute;top:-5px;width:2px;height:9px;background:#b9fff5;box-shadow:0 0 8px #b9fff5}
@keyframes cd-card-sweep{to{transform:translateX(115%)}}
@media(max-width:900px){.cd-card-shell{padding:12px}.cd-quote-card strong{font-size:24px}.cd-card-badge{font-size:8px}.cd-tail-note{font-size:9px}}
@media(max-width:650px){.cd-quote-card{min-height:138px}.cd-card-shell{min-height:136px}.cd-quote-card strong{font-size:21px}.cd-card-tail{padding-right:36px}.cd-mini-line,.cd-mini-bars{min-width:44px}.cd-card-index{right:10px;bottom:10px}}
@media(prefers-reduced-motion:reduce){.cd-quote-network .cd-quote-card:before{animation:none!important;transform:none!important}.cd-quote-card{transition:none!important}}
</style>"""

_QUOTE_JS = """
export default function ({ data, parentElement }) {
  const root = parentElement.querySelector('#quote-root');
  if (root) root.innerHTML = data.markup;
}
"""

_QUOTE_COMPONENT = st.components.v2.component(
    "cyber_quote_network", html='<div id="quote-root"></div>',
    css=_PANEL_CSS.removeprefix("<style>").removesuffix("</style>"), js=_QUOTE_JS,
)


def _quote_wires() -> str:
    """Decorative signal routes between the six quote cards; no market meaning."""
    desktop = (
        "M185 44 C194 44 198 44 207 44",
        "M392 44 C401 44 405 44 414 44",
        "M185 164 C194 164 198 164 207 164",
        "M392 164 C401 164 405 164 414 164",
        "M92 88 C92 105 92 107 92 120",
        "M300 88 C300 105 300 107 300 120",
        "M508 88 C508 105 508 107 508 120",
        "M92 88 C125 111 255 102 300 120",
        "M508 88 C475 111 345 102 300 120",
    )
    mobile = (
        "M191 44 C198 44 202 44 209 44",
        "M191 160 C198 160 202 160 209 160",
        "M191 276 C198 276 202 276 209 276",
        "M95 88 C95 101 95 103 95 116",
        "M305 88 C305 101 305 103 305 116",
        "M95 204 C95 217 95 219 95 232",
        "M305 204 C305 217 305 219 305 232",
        "M95 88 C125 108 270 96 305 116",
        "M305 204 C270 224 125 212 95 232",
    )
    def svg(paths: tuple[str, ...], kind: str, width: int, height: int) -> str:
        tracks = "".join(f'<path class="track" d="{path}"/><path class="pulse" d="{path}"/>' for path in paths)
        return f'<svg class="cd-quote-wires {kind}" viewBox="0 0 {width} {height}" preserveAspectRatio="none" aria-hidden="true">{tracks}</svg>'
    return svg(desktop, "desktop", 600, 208) + svg(mobile, "mobile", 400, 320)


def _room_wires() -> str:
    desktop = (
        "M265 132 C300 115 315 115 345 132", "M555 132 C590 115 605 115 635 132",
        "M265 298 C300 281 315 281 345 298", "M555 298 C590 281 605 281 635 298",
        "M160 168 C130 220 190 235 160 260", "M450 168 C415 220 485 235 450 260",
        "M740 168 C710 220 770 235 740 260",
        "M160 168 C235 212 375 217 450 260", "M740 168 C665 212 525 217 450 260",
        "M450 334 C450 378 450 405 450 430",
    )
    mobile = (
        "M168 135 C190 117 210 117 232 135", "M168 283 C190 265 210 265 232 283",
        "M168 431 C190 413 210 413 232 431", "M100 170 C68 210 132 225 100 250",
        "M300 170 C268 210 332 225 300 250", "M100 318 C68 358 132 373 100 398",
        "M300 318 C268 358 332 373 300 398", "M200 468 C200 520 200 540 200 580",
    )
    def svg(paths: tuple[str, ...], kind: str, width: int, height: int) -> str:
        tracks = "".join(f'<path class="track" d="{path}"/><path class="pulse" d="{path}"/>' for path in paths)
        return f'<svg class="cd-room-wires {kind}" viewBox="0 0 {width} {height}" preserveAspectRatio="none" aria-hidden="true">{tracks}</svg>'
    return svg(desktop, "desktop", 900, 485) + svg(mobile, "mobile", 400, 640)


def _sparkline(history: pd.DataFrame, code: str, through_date: str | None) -> str:
    frame = stock_snapshot_history(history, code, through_date=through_date)
    if len(frame) < 2:
        return '<span class="cd-screen-note">暂无历史轨迹</span>'
    values = pd.to_numeric(frame["价格"], errors="coerce").dropna().tail(12).tolist()
    if len(values) < 2:
        return '<span class="cd-screen-note">暂无历史轨迹</span>'
    low, high = min(values), max(values)
    spread = high - low or 1
    bars = "".join(f'<i style="--bar-height:{round(9 + (value - low) * 24 / spread)}px"></i>' for value in values)
    return f'<div class="cd-spark" role="img" aria-label="导入历史快照价格轨迹">{bars}</div>'


def _cached_minute_microcharts(code: str, trade_date: str | None) -> tuple[str, str, str | None]:
    """Draw tiny charts only from saved minutes for the quote's own trade date."""
    if not trade_date:
        return "", "", None
    try:
        day = pd.Timestamp(trade_date).strftime("%Y%m%d")
        path = Path(__file__).resolve().parent.parent / "data" / "stock_minute" / f"{code}_{day}.csv"
        frame = pd.read_csv(path).tail(60)
        closes = pd.to_numeric(frame["收盘"], errors="coerce")
        volumes = pd.to_numeric(frame["成交量"], errors="coerce")
    except (OSError, ValueError, KeyError, pd.errors.ParserError):
        return "", "", None
    if len(frame) < 8 or closes.isna().any():
        return "", "", None
    prices = closes.tolist()
    low, high = min(prices), max(prices)
    spread = high - low or 1.0
    points = " ".join(
        f"{index * 160 / (len(prices) - 1):.1f},{25 - (price - low) * 21 / spread:.1f}"
        for index, price in enumerate(prices)
    )
    price_svg = (
        '<svg class="cd-mini-line" viewBox="0 0 160 29" preserveAspectRatio="none" '
        'role="img" aria-label="同日真实分钟价格轨迹">'
        f'<polyline points="{points}"/></svg>'
    )
    volume_svg = ""
    if volumes.notna().all() and volumes.ge(0).all():
        values = volumes.tolist()
        count = min(18, len(values))
        buckets = [sum(values[index * len(values) // count:(index + 1) * len(values) // count])
                   for index in range(count)]
        peak = max(buckets) or 1.0
        width = 160 / count
        bars = "".join(
            f'<rect x="{index * width + 1:.1f}" y="{27 - value * 22 / peak:.1f}" '
            f'width="{max(1.5, width - 2):.1f}" height="{max(1, value * 22 / peak):.1f}"/>'
            for index, value in enumerate(buckets)
        )
        volume_svg = (
            '<svg class="cd-mini-bars" viewBox="0 0 160 29" preserveAspectRatio="none" '
            f'role="img" aria-label="同日真实分钟成交量分布">{bars}</svg>'
        )
    return price_svg, volume_svg, f"{day[4:6]}.{day[6:8]} 分钟"


def _open_stock(code: str) -> None:
    st.session_state["stock_detail_query"] = code
    st.session_state.pop("stock_detail_selection", None)
    st.session_state["active_nav"] = "个股详情"


def _focus_from_room() -> None:
    code = st.session_state["cyber_room"].focus_stock
    if code in st.session_state.get("cyber_visible_codes", []):
        st.session_state["cyber_focus_stock"] = code


def _open_from_room() -> None:
    code = st.session_state["cyber_room"].open_stock
    if code in st.session_state.get("cyber_visible_codes", []):
        _open_stock(code)


@st.fragment(run_every="1min")
def _render_focused_quote(stock: dict, motion: bool, snapshot_date: str | None) -> None:
    code = stock["code"]
    st.subheader(f"{stock['name']} · 行情仪表", icon=":material/monitoring:")
    live_quote, error = load_focused_quote(code)
    snapshot = live_quote is None
    if snapshot:
        quote = {
            "price": stock.get("price"), "change_pct": stock.get("change_pct"),
            "volume_hands": stock.get("volume"), "amount_yuan": stock.get("amount_yuan"),
            "turnover_pct": stock.get("turnover_pct"), "volume_ratio": stock.get("volume_ratio"),
        }
        if snapshot_date and stock.get("price") is not None:
            st.warning(f"实时行情暂不可用；下方显示 {snapshot_date} 的导入快照，非实时数据。")
            volume_source = stock.get("volume_source")
            source_caption = f"导入行情快照 · 原成交量字段：{volume_source or '未注明'} · 成交量单位以原文件为准"
        else:
            st.warning("实时行情暂不可用，且这只股票没有可用的导入报价；核心信息暂显示为空值。")
            source_caption = "暂无可用报价快照；空值不会补成模拟行情。"
        stale = True
    else:
        quote = live_quote
        fetched = pd.Timestamp(quote["fetched_at"])
        age = (pd.Timestamp.now(tz="Asia/Shanghai") - fetched).total_seconds()
        stale = bool(error) or age > 180
        state = "更新失败，显示上次成功值" if error else "缓存行情" if stale else "公开行情"
        source_caption = f"AKShare / 东方财富个股盘口 · 接口读取于 {fetched:%Y-%m-%d %H:%M:%S} · {state} · 盘中每分钟尝试更新；源行情可能延迟"
    def show(value: object, suffix: str = "", digits: int = 2) -> str:
        return "—" if value is None else f"{value:,.{digits}f}{suffix}"
    change = quote["change_pct"]
    fields = [
        ("快照价" if snapshot else "最新价", show(quote["price"], " 元"), "up" if change is not None and change > 0 else "down" if change is not None and change < 0 else ""),
        ("涨跌幅", show(change, "%"), "up" if change is not None and change > 0 else "down" if change is not None and change < 0 else ""),
        ("成交量 · 导入源" if snapshot else "成交量 · 总手", show(quote["volume_hands"], "" if snapshot else " 手", 0), ""),
        ("成交额", show(quote["amount_yuan"] / 100000000 if quote["amount_yuan"] is not None else None, " 亿元"), ""),
        ("换手率", show(quote["turnover_pct"], "%"), ""),
        ("量比", show(quote["volume_ratio"]), ""),
    ]
    visual_date = snapshot_date if snapshot else fetched.strftime("%Y-%m-%d")
    price_svg, volume_svg, minute_label = _cached_minute_microcharts(code, visual_date)
    minute_note = escape(minute_label or "同日分钟数据暂无")
    ratio = quote.get("volume_ratio")
    ratio_position = max(0, min(float(ratio), 2)) * 50 if ratio is not None else None
    ratio_tail = (
        f'<div class="cd-ratio-scale" role="img" aria-label="量比相对 1.00 基准">'
        f'<i style="left:{ratio_position:.1f}%"></i><span>0</span><span>1.00</span><span>2.00+</span></div>'
        if ratio_position is not None else '<span class="cd-tail-note">暂无可用量比</span>'
    )
    tails = [
        f'{price_svg}<span class="cd-tail-note">{minute_note}</span>' if price_svg else f'<span class="cd-tail-note">{minute_note}</span>',
        f'<span class="cd-data-arrow" aria-hidden="true">{"↗" if change is not None and change > 0 else "↘" if change is not None and change < 0 else "→"}</span><span class="cd-tail-note">相对昨收</span>',
        f'{volume_svg}<span class="cd-tail-note">{minute_note}</span>' if volume_svg else f'<span class="cd-tail-note">{minute_note}</span>',
        '<span class="cd-tail-note">成交金额 · 人民币</span>',
        '<span class="cd-tail-note">成交量相对流通股本</span>',
        ratio_tail,
    ]
    badge = f"快照 {snapshot_date}" if snapshot else f"{'缓存' if stale else '公开行情'} {fetched:%H:%M}"
    badge_kind = "snapshot" if snapshot else "stale" if stale else "live"
    card_names = ("price", "change", "volume", "amount", "turnover", "ratio")
    cards = "".join(
        f'<div class="cd-quote-card cd-{card_names[index]} {kind}" role="group" aria-label="{escape(label)}">'
        f'<div class="cd-card-shell"><div class="cd-card-top"><small>{escape(label)}</small>'
        f'<span class="cd-card-badge {badge_kind}">{escape(badge)}</span></div>'
        f'<strong>{escape(value)}</strong><div class="cd-card-tail">{tails[index]}</div>'
        f'<span class="cd-card-index">0{index + 1} / 06</span></div></div>'
        for index, (label, value, kind) in enumerate(fields)
    )
    signature = tuple(quote.get(field) for field in ("price", "change_pct", "volume_hands", "amount_yuan", "turnover_pct", "volume_ratio"))
    previous = st.session_state.get(f"cyber_quote_signature_{code}")
    st.session_state[f"cyber_quote_signature_{code}"] = signature
    live_class = "live" if motion and not stale and previous != signature else ""
    network_class = "motion-on" if motion else ""
    markup = (
        f'<div class="cd-quote-network {network_class}">'
        f'{_quote_wires()}<div class="cd-quote-grid {live_class}">{cards}</div>'
        '<div class="conduit" aria-hidden="true"><i></i><i></i><i></i></div></div>'
    )
    _QUOTE_COMPONENT(data={"markup": markup}, key=f"cyber_quote_network_{code}", width="stretch")
    st.caption(source_caption)
    if error:
        with st.expander("行情接口异常详情", expanded=False):
            st.caption(error)


@st.fragment(run_every="1min")
def _render_focused_minute_chart(stock: dict) -> None:
    """Show real intraday closes for one focused watchlist stock."""
    from .stock_intraday import load_stock_minutes, minute_series
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    code = stock["code"]
    with st.container(border=True, key="cyber-minute-panel"):
        st.subheader(f"{stock['name']} · 分钟走势", icon=":material/show_chart:")
        controls = st.columns([2, 1], vertical_alignment="bottom")
        with controls[0]:
            period = st.segmented_control(
                "分钟周期", ["1分钟", "5分钟"], default="1分钟",
                key=f"cyber_minute_period_{code}",
            ) or "1分钟"
        with controls[1]:
            refresh = st.button("刷新分钟线", key=f"cyber_minute_refresh_{code}", icon=":material/refresh:")
        with st.spinner("正在读取个股分钟行情…"):
            bars, metadata, error = load_stock_minutes(code, force_refresh=refresh)
        if bars.empty:
            st.warning("这只股票暂时没有可用分钟行情；公开数据源不可用时不会补画模拟走势。")
            if error:
                st.caption(f"数据源提示：{error}")
            return
        visible = minute_series(bars, 1 if period == "1分钟" else 5)
        trade_day = visible["时间"].dt.strftime("%Y-%m-%d").iloc[-1]
        if error:
            st.warning(f"更新失败，当前显示本地缓存。数据源提示：{error}")
        st.caption(
            f"{metadata.get('source', '本地缓存')} · {trade_day} · "
            f"截至 {visible['时间'].iloc[-1]:%H:%M} · 不复权 · 盘中每分钟尝试刷新"
        )
        if trade_day != pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d"):
            st.info("数据源尚未返回今天的分钟行情；当前显示最近可用交易日，并已标出日期。")
        has_volume = visible["成交量"].notna().any()
        # Use consecutive trading-minute positions so the noon market closure takes no space.
        positions = list(range(len(visible)))
        tick_step = max(1, len(visible) // 8)
        tick_positions = list(range(0, len(visible), tick_step))
        if tick_positions[-1] != len(visible) - 1:
            tick_positions.append(len(visible) - 1)
        tick_labels = [visible["时间"].iloc[index].strftime("%H:%M") for index in tick_positions]
        figure = make_subplots(
            rows=2 if has_volume else 1, cols=1, shared_xaxes=True,
            row_heights=[0.76, 0.24] if has_volume else None,
            vertical_spacing=0.04,
        )
        figure.add_trace(go.Scatter(
            x=positions, y=visible["收盘"], mode="lines", name="价格",
            line=dict(color="#77efff", width=2.5),
            customdata=visible["时间"].dt.strftime("%H:%M"),
            hovertemplate="%{customdata}<br>价格 %{y:.2f} 元<extra></extra>",
        ), row=1, col=1)
        if has_volume:
            previous = visible["收盘"].shift(1).fillna(visible["收盘"])
            colors = ["#ed7cae" if close >= prior else "#65dcb9"
                      for close, prior in zip(visible["收盘"], previous)]
            figure.add_trace(go.Bar(
                x=positions, y=visible["成交量"], name="成交量",
                marker_color=colors,
            ), row=2, col=1)
            figure.update_yaxes(title_text="成交量（源单位）", row=2, col=1)
            figure.update_xaxes(tickmode="array", tickvals=tick_positions,
                                ticktext=tick_labels, row=2, col=1)
        else:
            figure.update_xaxes(tickmode="array", tickvals=tick_positions,
                                ticktext=tick_labels, row=1, col=1)
        figure.update_layout(
            height=440, margin=dict(t=12, l=12, r=12, b=8), showlegend=False,
            yaxis_title="价格（元）", hovermode="x unified",
            paper_bgcolor="#081725", plot_bgcolor="#081725",
            font=dict(color="#bad7df", family="Microsoft YaHei, sans-serif", size=11),
            hoverlabel=dict(bgcolor="#123643", font_color="#e3fffa", bordercolor="#67d5d0"),
        )
        figure.update_xaxes(showgrid=False, zeroline=False, linecolor="#41717a", tickfont_color="#91b5bf")
        figure.update_yaxes(gridcolor="rgba(114, 203, 213, 0.16)", zeroline=False,
                            linecolor="#41717a", tickfont_color="#91b5bf")
        st.plotly_chart(figure, width="stretch", key=f"cyber_minute_chart_{code}_{period}")


def render_cyber_desk(data: dict) -> None:
    st.html(_PANEL_CSS)
    watchlist_codes = load_watchlist(_WATCHLIST_PATH)
    model = build_cyber_desk_model({**data, "watchlist_codes": watchlist_codes})
    stocks = model["stocks"]
    mode_text = "导入快照" if model["mode"] == "snapshot" else "关注名单" if stocks else "暂无关注名单"
    date_text = f"快照交易日：{model['snapshot_date']}" if model["snapshot_date"] else "当前无可用行情快照"
    motion_column, focus_column = st.columns([1, 2], vertical_alignment="bottom")
    motion = motion_column.toggle("环境动效", value=True, key="cyber_desk_motion", help="关闭巡游和席位入场动画；系统减少动态效果设置也会自动生效。")
    stock_by_code = {stock["code"]: stock for stock in stocks}
    if stocks:
        if st.session_state.get("cyber_focus_stock") not in stock_by_code:
            st.session_state["cyber_focus_stock"] = stocks[0]["code"]
        focus_code = focus_column.selectbox(
            "聚焦关注股票 · 同步下方走势",
            list(stock_by_code),
            format_func=lambda code: f"{stock_by_code[code]['name']} · {code}",
            key="cyber_focus_stock",
        )
        focused = stock_by_code[focus_code]
        display_stocks = stocks[:6]
        if focus_code not in {stock["code"] for stock in display_stocks}:
            display_stocks = [*display_stocks[:5], focused]
    else:
        focus_code = None
        focused = None
        display_stocks = []
    cards = []
    history = data.get("market_history")
    for stock in display_stocks:
        change = stock["change_pct"]
        change_text = f"{change:+.2f}%" if change is not None else "无报价"
        change_class = "down" if change is not None and change < 0 else ""
        spark = _sparkline(history, stock["code"], model["snapshot_date"]) if model["mode"] == "snapshot" else '<span class="cd-screen-note">暂无历史轨迹</span>'
        state_class = "cd-focused" if stock["code"] == focus_code else "cd-related" if focused and stock["sector"] != "未分类" and stock["sector"] == focused["sector"] else ""
        focus_tag = '<span class="cd-focus-tag">当前聚焦</span>' if stock["code"] == focus_code else ""
        code = escape(stock["code"])
        name = escape(stock["name"])
        cards.append(f'<div class="cd-desk {state_class}">{focus_tag}<div class="cd-monitor" role="button" tabindex="0" aria-label="聚焦{name}" data-focus-code="{code}"><header><b>{name}</b><em class="{change_class}">{change_text}</em></header>{spark}</div><button type="button" class="cd-keyboard" aria-label="打开{name}详情" data-open-code="{code}">详情 ↗</button></div>')
    if not cards:
        cards = ['<div class="cd-desk"><div class="cd-monitor"><b>等待添加关注股票</b><span class="cd-screen-note">从下方搜索并加入</span></div><div class="cd-keyboard"></div></div>']
    room_class = "cyber-desk" if motion else "cyber-desk cd-motion-off"
    room = f'''<div class="{room_class}"><div class="cd-banner">研究观察 · 席位为{escape(mode_text)} · 不执行交易</div><div class="cd-head"><div><div class="cd-kicker">PERSONAL WATCHLIST / RESEARCH ROOM</div><h1>赛博交易舱</h1></div><div class="cd-meta">数据来源：{escape(model['source'])}<br>{escape(date_text)}</div></div><div class="cd-room">{_room_wires()}<div class="cd-room-title"><span>我的关注股票 · 研究席位</span><small>点击屏幕聚焦 · 点击键盘查看详情</small></div><div class="cd-desks">{''.join(cards)}</div><div class="cd-bot a" aria-hidden="true"></div><div class="cd-bot b" aria-hidden="true"></div><div class="cd-bot c" aria-hidden="true"></div><div class="cd-floor"><span>数据状态 / {escape(mode_text)}</span><div class="cd-floor-line" aria-hidden="true"></div><strong>{len(stocks)} WATCHING</strong></div></div></div>'''
    st.session_state["cyber_visible_codes"] = [stock["code"] for stock in display_stocks]
    _ROOM_COMPONENT(
        data={"room": room},
        key="cyber_room",
        on_focus_stock_change=_focus_from_room,
        on_open_stock_change=_open_from_room,
        width="stretch",
    )
    _FLOW_COMPONENT(data={"motion": motion}, key="cyber_page_flow", width="stretch")
    if stocks:
        _render_focused_quote(focused, motion, model["snapshot_date"])
        _render_focused_minute_chart(focused)
    pool = data.get("research_pool")
    with st.expander(f"编辑关注名单 · {len(stocks)} 只", expanded=not stocks):
        if isinstance(pool, pd.DataFrame) and {"代码", "名称"}.issubset(pool.columns):
            choices = []
            choice_to_code = {}
            for row in pool[["代码", "名称"]].drop_duplicates("代码").to_dict("records"):
                code = str(row["代码"]).strip().removesuffix(".0").zfill(6)
                if code in watchlist_codes:
                    continue
                label = f"{row['名称']} · {code}"
                choices.append(label)
                choice_to_code[label] = code
            selected_add = st.selectbox("搜索导入股票并添加关注", choices, index=None, placeholder="输入名称或代码搜索", key="cyber_add_stock") if choices else None
            if st.button("添加到关注", disabled=not selected_add, key="cyber_add_button") and selected_add:
                save_watchlist(_WATCHLIST_PATH, [*watchlist_codes, choice_to_code[selected_add]])
                st.rerun()
        else:
            st.info("尚无可搜索的导入股票数据。先到「数据导入」上传股票文件。")
        if not stocks:
            st.info("尚未添加关注股票。请从上方搜索导入股票并添加。")
        for stock in stocks:
            left, right = st.columns([4, 1], vertical_alignment="center")
            left.write(f"{stock['name']} · {stock['code']}")
            if right.button("移除", key=f"cyber_remove_{stock['code']}"):
                save_watchlist(_WATCHLIST_PATH, [code for code in watchlist_codes if code != stock["code"]])
                st.rerun()
