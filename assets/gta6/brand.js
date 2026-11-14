// Kanal banneri (2560x1440) va profil rasmi (800x800) ni chizadi: node brand.js
const { chromium } = require('playwright');
const path = require('path');
const font = 'data:font/ttf;base64,' + require('fs').readFileSync(path.resolve(__dirname, '../../cartoon/fonts/Anton-Regular.ttf')).toString('base64');

const palm = (x, y, s, flip) => `
<g transform="translate(${x},${y}) scale(${flip ? -s : s},${s})" fill="#12031f">
  <path d="M-6 0 C-2 -120 10 -230 34 -330 L46 -328 C26 -228 16 -120 14 0 Z"/>
  <g transform="translate(40,-330)">
    ${[-205,-178,-150,-122,-58,-30,-2,25].map((a,i)=>`<path transform="rotate(${a}) scale(1,${a<-90?-1:1})" d="M0 0 C50 -70 150 -80 ${215+i%2*25} 30 C150 -30 70 -25 0 14 Z"/>`).join('')}
    <circle r="16"/>
  </g>
</g>`;

const skyline = (w, base, seed, k = 1) => {
  let x = 0, out = '', r = seed;
  const rnd = () => (r = (r * 9301 + 49297) % 233280) / 233280;
  while (x < w) { const bw = 40 + rnd() * 90, bh = (40 + rnd() * 200) * k;
    out += `<rect x="${x}" y="${base - bh}" width="${bw}" height="${bh}"/>`;
    for (let wy = base - bh + 14; wy < base - 10; wy += 22) for (let wx = x + 8; wx < x + bw - 10; wx += 18)
      if (rnd() > 0.62) out += `<rect x="${wx}" y="${wy}" width="8" height="10" fill="#ffd36e" opacity=".85"/>`;
    x += bw + 6; }
  return out;
};

const scene = (w, h, horizon, sunR) => `
<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="position:absolute;inset:0">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#14052e"/><stop offset=".38" stop-color="#5a1175"/>
      <stop offset=".68" stop-color="#e0368f"/><stop offset="1" stop-color="#ff9a4a"/></linearGradient>
    <linearGradient id="sun" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#fff07a"/><stop offset=".55" stop-color="#ff8a3c"/><stop offset="1" stop-color="#ff2e88"/></linearGradient>
    <linearGradient id="sea" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#7a1c8c"/><stop offset="1" stop-color="#0d0220"/></linearGradient>
    <radialGradient id="glow"><stop offset="0" stop-color="#ffb35c" stop-opacity=".75"/><stop offset="1" stop-color="#ff2e88" stop-opacity="0"/></radialGradient>
    <clipPath id="sunclip"><rect x="0" y="0" width="${w}" height="${horizon}"/></clipPath>
  </defs>
  <rect width="${w}" height="${h}" fill="url(#sky)"/>
  <circle cx="${w/2}" cy="${horizon}" r="${sunR*2.1}" fill="url(#glow)"/>
  <g clip-path="url(#sunclip)">
    <circle cx="${w/2}" cy="${horizon - sunR*0.25}" r="${sunR}" fill="url(#sun)"/>
    ${[0,1,2,3,4,5].map(i=>`<rect x="0" y="${horizon - sunR*0.62 + i*sunR*0.11}" width="${w}" height="${sunR*0.022*(i+1)}" fill="#c22a86"/>`).join('')}
  </g>
  <g fill="#1d0636">${skyline(w, horizon, 7, w / 2560 + 0.25)}</g>
  <rect x="0" y="${horizon}" width="${w}" height="${h-horizon}" fill="url(#sea)"/>
  <g stroke="#ff4fd8" stroke-opacity=".55" stroke-width="2">
    ${Array.from({length:10},(_, i)=>`<line x1="0" x2="${w}" y1="${horizon + Math.pow(i+1,2.1)*(h-horizon)/130}" y2="${horizon + Math.pow(i+1,2.1)*(h-horizon)/130}"/>`).join('')}
    ${Array.from({length:41},(_, i)=>`<line x1="${w/2 + (i-20)*w/60}" y1="${horizon}" x2="${w/2 + (i-20)*w/7}" y2="${h}"/>`).join('')}
  </g>
</svg>`;

const css = `@font-face{font-family:A;src:url('${font}')} *{margin:0;box-sizing:border-box} body{font-family:A;overflow:hidden;position:relative}
.t{position:absolute;left:0;right:0;text-align:center;line-height:1}
.neon{color:#fff;text-shadow:0 0 12px #ff4fd8,0 0 40px #ff2e88,0 0 90px #b3128f,0 8px 0 #2a0845}
.gold{background:linear-gradient(#fff3a0,#ffb23c 55%,#ff5fa8);-webkit-background-clip:text;color:transparent;filter:drop-shadow(0 6px 0 #2a0845) drop-shadow(0 0 30px rgba(255,80,180,.7))}
.pill{display:inline-block;background:rgba(18,3,31,.78);border:3px solid #ff4fd8;border-radius:999px;color:#fff;box-shadow:0 0 30px rgba(255,79,216,.6)}`;

const banner = `<html><style>${css} body{width:2560px;height:1440px}</style><body>
${scene(2560, 1440, 1010, 360)}
<div style="position:absolute;left:380px;right:380px;top:470px;height:500px;background:radial-gradient(ellipse at center,rgba(20,5,46,.72),rgba(20,5,46,0) 70%)"></div>
<svg width="2560" height="1440" style="position:absolute;inset:0">${palm(170,1440,2.7)}${palm(430,1440,1.6,true)}${palm(2390,1440,2.7,true)}${palm(2130,1440,1.6)}</svg>
<div class="t neon" style="top:512px;font-size:84px;letter-spacing:26px">ALI</div>
<div class="t gold" style="top:606px;font-size:230px;letter-spacing:8px">GTA 6 GAMEPLAY</div>
<div class="t" style="top:856px"><span class="pill" style="font-size:46px;letter-spacing:5px;padding:12px 44px">HAR KUNI YANGI SHORTS &nbsp;•&nbsp; O'ZBEK TILIDA &nbsp;•&nbsp; OBUNA BO'LING</span></div>
</body></html>`;

const avatar = `<html><style>${css} body{width:800px;height:800px}</style><body>
${scene(800, 800, 560, 290)}
<div style="position:absolute;inset:0;background:radial-gradient(circle at 50% 46%,rgba(20,5,46,.55),rgba(20,5,46,0) 60%)"></div>
<div class="t neon" style="top:185px;font-size:120px;letter-spacing:22px;padding-left:22px">ALI</div>
<div class="t gold" style="top:300px;font-size:235px;letter-spacing:6px">GTA 6</div>
</body></html>`;

(async () => {
  const b = await chromium.launch();
  for (const [name, html, w, h] of [['banner', banner, 2560, 1440], ['avatar', avatar, 800, 800]]) {
    const p = await b.newPage({ viewport: { width: w, height: h } });
    await p.setContent(html); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(300);
    await p.screenshot({ path: path.join(__dirname, name + '.png') });
  }
  await b.close();
})();
