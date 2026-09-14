// PL-4 evidence: every built-in preset at 1920x1080, in the 4th quarter and
// on FINAL, rendered by the real spectator page over a stub bridge (the
// layout-editor verification recipe). Reads JSON {presets, fourth, final, out}
// on stdin; writes PNGs and prints a JSON report of the clock widgets' state.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

async function main(data) {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const report = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    await page.route(/^https?:/, route => route.abort());
    await page.addInitScript(({ model, layout }) => {
      window.pywebview = { api: {
        get_snapshot: () => Promise.resolve(model),
        get_layout: () => Promise.resolve(layout),
        get_motion: () => Promise.resolve(false),
        get_cutscene: () => Promise.resolve(null),
      } };
    }, { model: data.fourth, layout: data.presets[0].layout });
    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/spectator/index.html')).href);
    await page.waitForFunction(() => document.querySelector('#canvas').dataset.revision !== undefined);
    fs.mkdirSync(data.out, { recursive: true });
    const clockState = () => page.evaluate(() => {
      const out = {};
      for (const id of ['game_clock_label', 'game_clock_value', 'play_clock_label', 'play_clock_value']) {
        const el = document.querySelector('[data-widget="' + id + '"]');
        out[id] = el ? { hidden: el.hidden, hasValue: el.dataset.hasValue, layoutVisible: el.dataset.layoutVisible } : null;
      }
      out.quarter = document.querySelector('[data-widget="quarter"] .widget-text').textContent;
      return out;
    });
    for (const preset of data.presets) {
      await page.evaluate(layout => window.applyLayout(layout), preset.layout);
      await page.evaluate(model => window.applyView(model), data.fourth);
      await page.evaluate(() => document.fonts.ready.then(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))));
      await page.waitForTimeout(150);
      await page.screenshot({ path: path.join(data.out, `pl4-${preset.id}-4th.png`) });
      const before = await clockState();
      await page.evaluate(model => window.applyView(model), data.final);
      await page.waitForTimeout(150);
      await page.screenshot({ path: path.join(data.out, `pl4-${preset.id}-final.png`) });
      const after = await clockState();
      await page.evaluate(model => window.applyView(model), data.fourth);
      await page.waitForTimeout(100);
      const restored = await clockState();
      report.push({ preset: preset.id, before, after, restored });
    }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(report));
}
let input = '';
process.stdin.on('data', c => input += c);
process.stdin.on('end', () => main(JSON.parse(input)).catch(e => { console.error(e); process.exitCode = 1; }));
