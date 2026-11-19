// Browser smoke test: open every page in headless Chromium and fail on
//   - uncaught JS exceptions            (e.g. a typo that kills a page's script)
//   - console.error output
//   - failed / 4xx requests to this site (missing images, audio, pages)
// plus a few page-specific checks for the two pages that get auto-updated.
//
// Run locally:  npm ci && npx playwright install chromium && npm test
// Optional env: PAGES=Jinbei.html,Chopper.html (limit pages), CHROME_PATH (existing Chrome),
//               LOCAL_LIBS (offline CDN stubs)
const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
  '.gif': 'image/gif', '.svg': 'image/svg+xml', '.mp3': 'audio/mpeg', '.mp4': 'video/mp4',
};

function serve() {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '') || 'index.html';
    const file = path.join(ROOT, rel);
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404); return res.end('not found');
    }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((ok) => server.listen(0, '127.0.0.1', () => ok(server)));
}

// Optional offline stubs so the test also runs where CDNs are unreachable.
function cdnStub(url) {
  const base = process.env.LOCAL_LIBS;
  if (!base) return null;
  const map = [
    [/gsap\/3\.12\.5\/gsap\.min\.js/, 'gsap/dist/gsap.min.js'],
    [/gsap\/3\.12\.5\/ScrollTrigger\.min\.js/, 'gsap/dist/ScrollTrigger.min.js'],
    [/three\.js\/r128\/three\.min\.js/, 'three/build/three.min.js'],
    [/three@0\.128\.0\/examples\/js\/controls\/OrbitControls\.js/, 'three/examples/js/controls/OrbitControls.js'],
    [/@emailjs\/browser@4\/dist\/email\.min\.js/, '@emailjs/browser/dist/email.min.js'],
  ];
  for (const [rx, rel] of map) if (rx.test(url)) return path.join(base, rel);
  return null;
}

(async () => {
  const server = await serve();
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || undefined,
    args: ['--autoplay-policy=no-user-gesture-required'],
  });
  const only = (process.env.PAGES || '').split(',').map((s) => s.trim()).filter(Boolean);
  const pages = fs.readdirSync(ROOT).filter((f) => f.endsWith('.html') && (!only.length || only.includes(f))).sort();
  const failures = [];
  let passed = 0;

  for (const name of pages) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    const problems = [];

    // third-party hosts: fonts are cosmetic, everything else must load
    await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (route) => {
      const url = route.request().url();
      const stub = cdnStub(url);
      if (stub) return route.fulfill({ path: stub, contentType: 'text/javascript' });
      if (/fonts\.(googleapis|gstatic)\.com/.test(url) && process.env.LOCAL_LIBS) return route.abort();
      return route.continue();
    });

    page.on('pageerror', (e) => problems.push(`JS error: ${e.message}`));
    page.on('console', (m) => {
      if (m.type() !== 'error') return;
      const t = m.text();
      if (/Failed to load resource/.test(t)) return; // reported precisely by 'response' below
      problems.push(`console.error: ${t}`);
    });
    page.on('response', (r) => {
      if (r.url().startsWith(origin) && r.status() >= 400)
        problems.push(`${r.status()} ${r.url().replace(origin, '')}`);
    });
    page.on('requestfailed', (r) => {
      if (r.url().startsWith(origin)) problems.push(`request failed: ${r.url().replace(origin, '')}`);
    });

    try {
      await page.goto(`${origin}/${name}`, { waitUntil: 'load', timeout: 30000 });
      await page.waitForTimeout(2000); // let intros / loaders / lazy audio run

      if (name === 'Chopper.html') {
        const total = await page.locator('#entryGrid .card').count();
        if (total < 1) problems.push('Chopper: no entry cards rendered');
        await page.click('.filter-btn[data-filter="kungfu"]');
        await page.waitForTimeout(1200);
        const visible = await page.locator('#entryGrid .card:visible').count();
        const wrong = await page.locator('#entryGrid .card:visible:not([data-cat="kungfu"])').count();
        if (visible < 1 || wrong > 0) problems.push(`Chopper: Kung Fu filter broken (${visible} visible, ${wrong} wrong)`);
      }
      if (name === 'Jinbei.html') {
        const score = (await page.locator('#duo-nl-score').first().textContent().catch(() => '')) || '';
        if (!/^\d{1,3}$/.test(score.trim())) problems.push(`Jinbei: #duo-nl-score missing or not a number ("${score.trim()}")`);
      }
    } catch (e) {
      problems.push(`navigation failed: ${e.message.split('\n')[0]}`);
    }

    const unique = [...new Set(problems)];
    if (unique.length) failures.push([name, unique]); else passed++;
    console.log(`${unique.length ? 'FAIL' : ' ok '}  ${name}${unique.length ? '  (' + unique.length + ')' : ''}`);
    await ctx.close();
  }

  await browser.close();
  server.close();

  if (failures.length) {
    console.log('\n' + failures.map(([n, ps]) => `${n}\n${ps.map((p) => '   - ' + p).join('\n')}`).join('\n'));
    console.log(`\n${passed}/${pages.length} pages clean.`);
    process.exit(1);
  }
  console.log(`\nAll ${pages.length} pages clean.`);
})();
