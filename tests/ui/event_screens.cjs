// Broadcast Welcome / Kickoff Clock / Fifty Yard Line event screens on the
// real spectator page (event-screens spec section 3.5): glyphs inside their
// boxes and the 4 % safe area, no overlaps, team bars that fit, a ticker that
// carries every line, no running animation with motion off, and -- with
// motion on -- animations bound to nodes that persist across snapshots.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const VIEWPORTS = [[1920, 1080], [1366, 768], [640, 360]];

// Every measurable check for the currently drawn event board. `lines` is the
// screen's ticker lines (from the layout, so the test never derives them).
async function measure(page, lines, motion) {
  return page.evaluate(([lines, motion]) => {
    const board = document.querySelector('#event-board');
    const canvas = document.querySelector('#canvas').getBoundingClientRect();
    const errors = [], rects = [];
    const moving = new Set(['sweep', 'drift', 'scroll_x']);
    const ctx = document.createElement('canvas').getContext('2d');
    // Glyph ink, not the CSS line box (as grid.cjs measures): a fitted
    // numeral deliberately fills its box while its invisible line box
    // overhangs it. Vertical text is measured by its range rect on both
    // axes, exactly as board.js fits it.
    function inkRect(el, span) {
      const range = document.createRange(); range.selectNodeContents(span);
      const line = range.getBoundingClientRect();
      if (el.dataset.orientation) return line;
      const style = getComputedStyle(span);
      ctx.font = [style.fontStyle, style.fontWeight, style.fontSize, style.fontFamily].join(' ');
      ctx.letterSpacing = style.letterSpacing;
      let text = span.textContent;
      if (style.textTransform === 'uppercase') text = text.toUpperCase();
      const m = ctx.measureText(text);
      const baseline = line.top + m.fontBoundingBoxAscent;
      return {left: line.left, right: line.right,
              top: baseline - m.actualBoundingBoxAscent, bottom: baseline + m.actualBoundingBoxDescent};
    }
    for (const el of board.querySelectorAll('[data-widget], .element-text')) {
      if (!el.getClientRects().length) continue;
      if (el.closest('.element-ticker') || moving.has(el.dataset.anim)) continue;
      const span = el.querySelector('.widget-text');
      if (!span || !span.textContent.trim()) continue;
      const r = inkRect(el, span), b = el.getBoundingClientRect();
      const id = el.dataset.item;
      if (r.left < b.left - 1 || r.right > b.right + 1 || r.top < b.top - 1 || r.bottom > b.bottom + 1)
        errors.push(`${id}: text outside box ${JSON.stringify(r)} / ${JSON.stringify(b.toJSON())}`);
      if (r.left < canvas.left + canvas.width * .04 - 1 || r.right > canvas.right - canvas.width * .04 + 1 ||
          r.top < canvas.top + canvas.height * .04 - 1 || r.bottom > canvas.bottom - canvas.height * .04 + 1)
        errors.push(`${id}: outside safe area ${JSON.stringify(r)}`);
      rects.push({id, left: r.left, right: r.right, top: r.top, bottom: r.bottom});
    }
    for (let i = 0; i < rects.length; i++) for (const b of rects.slice(i + 1)) {
      const a = rects[i];
      if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 &&
          Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1) errors.push(`overlap: ${a.id} / ${b.id}`);
    }
    // The Kickoff Clock team bars are tight (spec section 9.4). Elements do
    // not nest, so "the bar's content" is every glyph rect drawn inside the
    // bar's rectangle; each must stay inside it. The bar's own scroll width
    // may exceed its client width only by its border ring: a chamfered box
    // paints its border with a ::before stretched over the border box.
    for (const id of ['home_bar', 'away_bar']) {
      const bar = board.querySelector(`[data-element="${id}"]`);
      if (!bar) continue;
      const cs = getComputedStyle(bar);
      const ring = parseFloat(cs.borderLeftWidth) + parseFloat(cs.borderRightWidth);
      if (bar.scrollWidth > bar.clientWidth + ring + 1) errors.push(`${id}: content wider than the bar`);
      const b = bar.getBoundingClientRect();
      for (const t of rects) {
        const cx = (t.left + t.right) / 2, cy = (t.top + t.bottom) / 2;
        if (cx < b.left || cx > b.right || cy < b.top || cy > b.bottom) continue;
        if (t.left < b.left - 1 || t.right > b.right + 1 || t.top < b.top - 1 || t.bottom > b.bottom + 1)
          errors.push(`${id}: ${t.id} spills out of the bar`);
      }
    }
    const ticker = board.querySelector('[data-element="ticker"]');
    if (!ticker) errors.push('no ticker element');
    else {
      const runs = [...ticker.querySelectorAll('.ticker-run')].map(r => r.textContent);
      const shown = runs.join('  ');
      if (ticker.dataset.tickerMode === 'rotate') {
        if (!lines.includes(runs[0])) errors.push(`ticker shows "${runs[0]}", not one of its lines`);
      } else {
        for (const line of lines) if (!shown.includes(line)) errors.push(`ticker is missing "${line}"`);
      }
      if (motion === 'off' && ticker.dataset.tickerMode !== 'static') errors.push('ticker still moving with motion off');
    }
    if (motion === 'off') {
      const running = document.getAnimations().filter(a => a.effect && a.effect.target && board.contains(a.effect.target) &&
        a.playState !== 'idle' && a.playState !== 'paused');
      if (running.length) errors.push('running animations with motion off: ' + running.map(a => a.animationName).join(','));
    }
    if (document.documentElement.scrollWidth !== innerWidth || document.documentElement.scrollHeight !== innerHeight)
      errors.push('page scrolls');
    return errors;
  }, [lines, motion]);
}

// Motion on: hold the Animation objects of the sweep, the ticker track and
// the clock colon, tick the board 1100 ms later with a different clock
// text, and require the same objects with a strictly later currentTime.
async function checkPersistence(page, entry, models) {
  const held = await page.evaluate(() => {
    const q = s => document.querySelector('#event-board ' + s);
    const sweep = q('[data-element="light_sweep"]');
    const ticker = q('[data-element="ticker"]');
    const track = ticker && ticker.querySelector('.ticker-track');
    const colon = q('[data-widget="event_clock"] .clock-colon');
    window.__held = {
      sweep: sweep ? sweep.getAnimations()[0] : null, track: track ? track.getAnimations()[0] : null,
      colon: colon ? colon.getAnimations()[0] : null, colonEl: colon,
    };
    const t = a => (a ? a.currentTime : null);
    window.__time = {sweep: t(window.__held.sweep), track: t(window.__held.track), colon: t(window.__held.colon)};
    return {sweep: !!window.__held.sweep, track: !!window.__held.track, colon: !!window.__held.colon,
            tickerMode: ticker ? ticker.dataset.tickerMode : null, clockAnim: q('[data-widget="event_clock"]').dataset.anim || null,
            colonName: window.__held.colon ? window.__held.colon.animationName : null};
  });
  if (entry.id.endsWith('_welcome')) assert.ok(held.sweep, `${entry.id}: light_sweep has no running animation`);
  if (held.tickerMode === 'scroll') assert.ok(held.track, `${entry.id}: scrolling ticker has no animation`);
  if (entry.id.endsWith('_welcome') || entry.id.endsWith('_kickoff_clock'))
    assert.equal(held.clockAnim, 'blink_soft', `${entry.id}: event_clock is not on blink_soft`);
  if (held.clockAnim === 'blink_soft') {
    assert.ok(held.colon, `${entry.id}: no colon animation`);
    assert.equal(held.colonName, 'sb-blink');
  }
  await page.waitForTimeout(1100);
  await page.evaluate(model => window.applyView(model), models[1]);
  const after = await page.evaluate(() => {
    const q = s => document.querySelector('#event-board ' + s);
    const h = window.__held, t = window.__time;
    const sweep = q('[data-element="light_sweep"]');
    const ticker = q('[data-element="ticker"]');
    const track = ticker && ticker.querySelector('.ticker-track');
    const colon = q('[data-widget="event_clock"] .clock-colon');
    const now = {sweep: sweep ? sweep.getAnimations()[0] : null, track: track ? track.getAnimations()[0] : null,
                 colon: colon ? colon.getAnimations()[0] : null};
    const same = k => !h[k] || (now[k] === h[k] && now[k].currentTime > t[k] && now[k].playState === 'running');
    return {sweep: same('sweep'), track: same('track'), colon: same('colon'), colonEl: !h.colonEl || colon === h.colonEl,
            clock: q('[data-widget="event_clock"] .widget-text').textContent};
  });
  assert.equal(after.clock, models[1].clocks.event.display, `${entry.id}: clock text did not change`);
  for (const key of ['sweep', 'track', 'colon', 'colonEl'])
    assert.ok(after[key], `${entry.id}: ${key} animation or node was recreated by a snapshot`);
}

async function main(data) {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  let cases = 0;
  try {
    const page = await browser.newPage();
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.route(/^https?:/, route => route.abort());
    await page.addInitScript(data => {
      window.pywebview = {api: {get_snapshot: () => Promise.resolve(data.models.pregame[0]),
        get_layout: () => Promise.resolve(data.screens[0].layout), get_motion: () => Promise.resolve(true)}};
    }, data);
    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/spectator/index.html')).href);
    await page.waitForFunction(() => typeof window.applyLayout === 'function' && typeof window.applyMotion === 'function');
    for (const entry of data.screens) {
      const models = data.models[entry.screen];
      const screenDoc = entry.layout.screens[entry.screen];
      const tickerEntry = (screenDoc.elements || []).find(e => e.id === 'ticker');
      const lines = tickerEntry ? tickerEntry.lines : [];
      await page.evaluate(([layout, model]) => { window.applyLayout(layout); window.applyView(model); }, [entry.layout, models[0]]);
      await page.evaluate(() => document.fonts.ready);
      for (const [width, height] of VIEWPORTS) {
        await page.setViewportSize({width, height});
        for (const motion of ['on', 'off']) {
          await page.evaluate(on => window.applyMotion(on), motion === 'on');
          for (const [index, model] of models.entries()) {
            await page.evaluate(model => window.applyView(model), model);
            assert.deepEqual(await measure(page, lines, motion), [], `${entry.id} ${width}x${height} motion ${motion}, model ${index}`);
            assert.equal(await page.locator('#event-board [data-widget="event_clock"]').innerText(), model.clocks.event.display);
            assert.equal(await page.locator('#event-board [data-widget="warmup"]').isVisible(), Boolean(model.clocks.event.warmup_display));
            if (index === 0 && process.env.SCOREBOARD_CAPTURE_DIR) {
              fs.mkdirSync(process.env.SCOREBOARD_CAPTURE_DIR, {recursive: true});
              await page.screenshot({path: path.join(process.env.SCOREBOARD_CAPTURE_DIR, `${entry.id}-${motion}-${width}.png`)});
            }
            cases++;
          }
          if (motion === 'on' && width === 1920) {
            await page.evaluate(model => window.applyView(model), models[0]);
            await checkPersistence(page, entry, models);
          }
        }
      }
      await page.evaluate(() => window.applyMotion(true));
    }
    assert.deepEqual(errors, []);
    return {cases};
  } finally { await browser.close(); }
}
let input = ''; process.stdin.setEncoding('utf8'); process.stdin.on('data', c => input += c);
process.stdin.on('end', () => main(JSON.parse(input)).then(result => process.stdout.write(JSON.stringify(result)))
  .catch(error => { console.error(error); process.exitCode = 1; }));
