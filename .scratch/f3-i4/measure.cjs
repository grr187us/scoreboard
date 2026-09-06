/* One-off sizing check for the F3 crowd row and the I4 history affordance.
 * Development tool, not part of the suite.
 * Run: ./.venv/Scripts/python.exe .scratch/f3-i4/seed.py | node .scratch/f3-i4/measure.cjs
 */
const { chromium } = require('playwright');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const VIEWPORTS = [
  { width: 1093, height: 614 },
  { width: 1180, height: 720 },
  { width: 1366, height: 768 },
];

async function main(seed) {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const out = [];
  try {
    for (const viewport of VIEWPORTS) {
      const page = await browser.newPage({ viewport });
      const errors = [];
      page.on('pageerror', (error) => errors.push(String(error)));
      await page.route(/^https?:/, (route) => route.abort());
      await page.addInitScript((view) => {
        window.__view = view;
        window.pywebview = { api: {
          get_snapshot: () => Promise.resolve(window.__view),
          command: () => Promise.resolve({ accepted: true, view: window.__view }),
          teams: () => Promise.resolve({ teams: [], available: true, message: '' }),
        } };
      }, seed);
      await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/operator/index.html')).href);
      await page.waitForFunction(() => document.querySelector('#chip-revision').textContent !== 'Rev 0'
        || document.querySelector('#last-action').textContent !== 'nothing yet');
      const measured = await page.evaluate(() => {
        const doc = document.documentElement;
        const rect = (sel) => {
          const el = document.querySelector(sel);
          if (!el) return null;
          const box = el.getBoundingClientRect();
          return { h: Math.round(box.height * 10) / 10, w: Math.round(box.width * 10) / 10,
                   bottom: Math.round(box.bottom * 10) / 10, right: Math.round(box.right * 10) / 10 };
        };
        const heights = (sel) => Array.from(document.querySelectorAll(sel))
          .map((b) => ({ id: b.id || b.textContent.trim().slice(0, 10),
                         h: Math.round(b.getBoundingClientRect().height * 10) / 10 }));
        const clockBottoms = Array.from(document.querySelectorAll('.clocks button'))
          .map((b) => b.getBoundingClientRect().bottom);
        const crowd = document.querySelector('.crowd-bar');
        return {
          scrollHeight: doc.scrollHeight, clientHeight: doc.clientHeight,
          scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth,
          crowdBar: rect('.crowd-bar'), quarterBar: rect('.quarter-bar'), tools: rect('.tools'),
          board: rect('.board'),
          crowdOverflow: { scrollWidth: crowd.scrollWidth, clientWidth: crowd.clientWidth },
          quarterOverflow: (() => { const q = document.querySelector('.quarter-bar');
            return { scrollWidth: q.scrollWidth, clientWidth: q.clientWidth }; })(),
          reopen: rect('#reopen-display'), openDisplay: rect('#open-display'),
          lastAction: rect('#last-action-button'), undoDepthHidden: document.getElementById('undo-depth').hidden,
          crowdButtons: heights('.crowd-bar button'),
          lowestClockButtonBottom: Math.round(Math.max(...clockBottoms) * 10) / 10,
          historyRows: (() => { document.getElementById('history-drawer').hidden = false;
            const n = document.querySelectorAll('#history-list li').length;
            document.getElementById('history-drawer').hidden = true; return n; })(),
        };
      });
      out.push({ viewport, errors, ...measured });
      await page.close();
    }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(out, null, 1));
}

let input = '';
process.stdin.on('data', (chunk) => { input += chunk; });
process.stdin.on('end', () => {
  main(JSON.parse(input)).catch((error) => { console.error(error); process.exit(1); });
});
