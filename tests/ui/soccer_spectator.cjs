const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

// Mirrors spectator.cjs's measureWidgets(): glyph ink (not the CSS line box)
// must stay inside the safe area and inside its own box, and no two visible
// widgets' glyph rectangles may overlap.
async function measureWidgets(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('#canvas').getBoundingClientRect();
    const inset = 0.04;
    const safe = {
      left: canvas.left + inset * canvas.width, right: canvas.right - inset * canvas.width,
      top: canvas.top + inset * canvas.height, bottom: canvas.bottom - inset * canvas.height,
    };
    const errors = [];
    const rects = [];
    const ctx = document.createElement('canvas').getContext('2d');
    for (const element of document.querySelectorAll('#game-board [data-widget]')) {
      if (!element.getClientRects().length) continue;
      const textEl = element.querySelector('.widget-text');
      if (!textEl || !textEl.textContent.trim()) continue;
      const range = document.createRange(); range.selectNodeContents(textEl);
      const line = range.getBoundingClientRect();
      const style = getComputedStyle(textEl);
      ctx.font = [style.fontStyle, style.fontWeight, style.fontSize, style.fontFamily].join(' ');
      ctx.letterSpacing = style.letterSpacing;
      const m = ctx.measureText(style.textTransform === 'uppercase' ? textEl.textContent.toUpperCase() : textEl.textContent);
      const baseline = line.top + m.fontBoundingBoxAscent;
      const text = { left: line.left, right: line.right,
                     top: baseline - m.actualBoundingBoxAscent, bottom: baseline + m.actualBoundingBoxDescent };
      const box = element.getBoundingClientRect();
      const name = element.getAttribute('data-widget');
      if (text.left < safe.left - .5 || text.right > safe.right + .5 ||
          text.top < safe.top - .5 || text.bottom > safe.bottom + .5) errors.push('outside safe area: ' + name);
      if (text.left < box.left - 1 || text.right > box.right + 1 ||
          text.top < box.top - 1 || text.bottom > box.bottom + 1) errors.push('text outside box: ' + name);
      rects.push({ name, ...text });
    }
    for (let i = 0; i < rects.length; i++) for (let j = i + 1; j < rects.length; j++) {
      const a = rects[i], b = rects[j];
      if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > .5 &&
          Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > .5) errors.push('overlap: ' + a.name + ' / ' + b.name);
    }
    return { errors };
  });
}

async function widgetHidden(page, id, root) {
  return page.evaluate(([widgetId, rootSelector]) => {
    const element = document.querySelector((rootSelector || '#game-board') + ' [data-widget="' + widgetId + '"]');
    return element ? Boolean(element.hidden) : null;
  }, [id, root]);
}

async function widgetText(page, id, root) {
  return page.evaluate(([widgetId, rootSelector]) => {
    const element = document.querySelector((rootSelector || '#game-board') + ' [data-widget="' + widgetId + '"] .widget-text');
    return element ? element.textContent : null;
  }, [id, root]);
}

async function main(data) {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const evidence = process.env.SCOREBOARD_CAPTURE_DIR || path.resolve('.scratch/soccer-mode/evidence/spectator');
  let cases = 0;
  try {
    const page = await browser.newPage();
    await page.route(/^https?:/, route => route.abort());
    await page.addInitScript(model => {
      window.pywebview = { api: { get_snapshot: () => Promise.resolve(model) } };
    }, data.optionalOff);
    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/soccer_spectator/index.html')).href);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.waitForFunction(() => document.querySelector('#canvas').dataset.revision !== undefined);
    await page.evaluate(() => document.fonts.ready.then(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))));

    // 1) All optional widgets off: shootout/cards/status blank, defaults
    // leave shots/saves/corners/fouls hidden too (visible: false).
    await page.evaluate(model => window.applyView(model), data.optionalOff);
    let metrics = await measureWidgets(page);
    assert.deepEqual(metrics.errors, [], `optional-off: ${JSON.stringify(metrics)}`);
    for (const id of ['status_message', 'status_clock', 'home_yellow', 'away_red', 'shootout_home', 'shootout_away']) {
      assert.equal(await widgetHidden(page, id), true, id + ' must be hidden when blank');
    }
    assert.equal(await widgetText(page, 'home_name'), 'EAGLES');
    assert.equal(await widgetText(page, 'period'), '1st Half');
    fs.mkdirSync(evidence, { recursive: true });
    await page.screenshot({ path: path.join(evidence, 'optional-off-1920x1080.png') });
    cases++;

    // 2) A layout that turns the stat/card/shootout widgets on, with every
    // optional field populated: no overlap even with all 23 widgets visible.
    await page.evaluate(layout => window.applyLayout(layout), data.allOnLayout);
    await page.evaluate(model => window.applyView(model), data.optionalOn);
    metrics = await measureWidgets(page);
    assert.deepEqual(metrics.errors, [], `optional-on: ${JSON.stringify(metrics)}`);
    for (const id of ['home_shots', 'away_saves', 'home_yellow', 'away_red', 'shootout_home', 'shootout_away',
                       'status_message', 'status_clock']) {
      assert.equal(await widgetHidden(page, id), false, id + ' must be visible once turned on and populated');
    }
    assert.equal(await widgetText(page, 'home_shots'), 'S 4');
    assert.equal(await widgetText(page, 'home_yellow'), 'Y 1');
    assert.equal(await widgetText(page, 'shootout_home'), '● ● ○');
    await page.screenshot({ path: path.join(evidence, 'optional-on-1920x1080.png') });
    cases++;

    // 3) FINAL hides the game clock (and its label) but keeps period, score,
    // and every stat widget on the wall.
    await page.evaluate(model => window.applyView(model), data.final);
    assert.equal(await widgetHidden(page, 'game_clock_value'), true, 'game_clock_value must hide on FINAL');
    assert.equal(await widgetHidden(page, 'game_clock_label'), true, 'game_clock_label must hide on FINAL');
    assert.equal(await widgetText(page, 'period'), 'Final');
    assert.equal(await widgetText(page, 'home_score'), String(data.final.teams.home.score));
    assert.equal(await widgetHidden(page, 'home_shots'), false, 'non-clock widgets stay on the wall at FINAL');
    await page.screenshot({ path: path.join(evidence, 'final-1920x1080.png') });
    cases++;

    // Back to a normal state: the clock returns.
    await page.evaluate(model => window.applyView(model), data.optionalOn);
    assert.equal(await widgetHidden(page, 'game_clock_value'), false);
    cases++;

    return { cases };
  } finally { await browser.close(); }
}
let input = ''; process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => main(JSON.parse(input)).then(result => console.log(JSON.stringify(result))).catch(error => { console.error(error); process.exitCode = 1; }));
