const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

async function measureWidgets(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('#canvas').getBoundingClientRect();
    // Schema v3 removes the #safe-area guide element from the spectator page
    // entirely (it drew nothing); the default layout's and default screens'
    // safe_area is 0.04 on every side, so the boundary is computed straight
    // from the canvas rect instead of measuring a DOM node.
    const inset = 0.04;
    const safe = {
      left: canvas.left + inset * canvas.width,
      right: canvas.right - inset * canvas.width,
      top: canvas.top + inset * canvas.height,
      bottom: canvas.bottom - inset * canvas.height,
    };
    const errors = [];
    const rects = [];
    for (const element of document.querySelectorAll('[data-widget]')) {
      if (!element.getClientRects().length) continue; // hidden widget or hidden ancestor
      const textEl = element.querySelector('.widget-text');
      if (!textEl || !textEl.textContent.trim()) continue; // nothing drawn
      const range = document.createRange(); range.selectNodeContents(textEl);
      const text = range.getBoundingClientRect();
      const box = element.getBoundingClientRect();
      const name = element.getAttribute('data-widget');
      if (text.left < safe.left - .5 || text.right > safe.right + .5 ||
          text.top < safe.top - .5 || text.bottom > safe.bottom + .5) errors.push('outside safe area: ' + name);
      if (text.left < box.left - .5 || text.right > box.right + .5 ||
          text.top < box.top - .5 || text.bottom > box.bottom + .5) errors.push('text outside box: ' + name + ' text ' + JSON.stringify(text.toJSON()) + ' box ' + JSON.stringify(box.toJSON()));
      rects.push({ name, left: text.left, right: text.right, top: text.top, bottom: text.bottom });
    }
    for (let i = 0; i < rects.length; i++) for (let j = i + 1; j < rects.length; j++) {
      const a = rects[i], b = rects[j];
      if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > .5 &&
          Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > .5) errors.push('overlap: ' + a.name + ' / ' + b.name);
    }
    return {
      errors, canvas: { width: canvas.width, height: canvas.height, x: canvas.x, y: canvas.y },
      scroll: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
      viewport: [innerWidth, innerHeight], inset: safe.left - canvas.left,
    };
  });
}

// `root` scopes the lookup to one board section ('#game-board' or
// '#event-board'); it defaults to the whole document, which is unambiguous
// for every widget id except the four the "game" and "event" registries
// share (home_name/home_score/away_name/away_score) -- callers checking
// those on the event board must pass '#event-board' explicitly.
async function widgetBox(page, id, root) {
  return page.evaluate(([widgetId, rootSelector]) => {
    const element = document.querySelector((rootSelector || '') + ' [data-widget="' + widgetId + '"]');
    return element ? element.getBoundingClientRect().toJSON() : null;
  }, [id, root || '']);
}

async function widgetText(page, id, root) {
  return page.evaluate(([widgetId, rootSelector]) => {
    const element = document.querySelector((rootSelector || '') + ' [data-widget="' + widgetId + '"] .widget-text');
    return element ? element.textContent : null;
  }, [id, root || '']);
}

async function widgetHidden(page, id, root) {
  return page.evaluate(([widgetId, rootSelector]) => {
    const element = document.querySelector((rootSelector || '') + ' [data-widget="' + widgetId + '"]');
    return element ? Boolean(element.hidden) : null;
  }, [id, root || '']);
}

async function main(data) {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const evidence = process.env.SCOREBOARD_CAPTURE_DIR;
  const observations = [];
  let cases = 0;
  try {
    const page = await browser.newPage();
    await page.route(/^https?:/, route => route.abort());
    await page.addInitScript(model => {
      window.pywebview = { api: { get_snapshot: () => Promise.resolve(model) } };
    }, data.games[3]);
    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/spectator/index.html')).href);
    await page.waitForFunction(() => document.querySelector('#canvas').dataset.revision === '71');
    assert.equal(await widgetText(page, 'home_score'), '199');
    assert.equal(await page.locator('button,input,dialog,[data-command],[data-action]').count(), 0);

    for (const [width, height] of [[1280, 720], [1366, 768], [1920, 1080], [390, 844]]) {
      await page.setViewportSize({ width, height });
      for (const [index, model] of [...data.games, data.pregame, ...data.events].entries()) {
        await page.evaluate(model => window.applyView(model), model);
        const metrics = await measureWidgets(page);
        assert.deepEqual(metrics.errors, [], `${width}x${height} case ${index}: ${JSON.stringify(metrics)}`);
        assert.deepEqual(metrics.scroll, metrics.viewport);
        assert.ok(Math.abs(metrics.canvas.width / metrics.canvas.height - 16 / 9) < .001);
        if (index >= 5) {
          // Schema v3: the countdown board is a widget board (the "event"
          // registry) like the game board, not hand-written <p> markup with
          // fixed ids -- so these read the same [data-widget] nodes the
          // helpers above use for the game board.
          assert.equal(await widgetText(page, 'event_phase', '#event-board'), model.clocks.event.phase);
          assert.equal(await widgetHidden(page, 'warmup', '#event-board'), !model.clocks.event.warmup_display);
          if (model.clocks.event.warmup_display) {
            assert.equal(await widgetText(page, 'warmup', '#event-board'), model.clocks.event.warmup_display);
          }
          assert.equal(await page.locator('#game-board').isVisible(), false);
        }
        if (evidence && [3, 4, 5, 7].includes(index)) {
          fs.mkdirSync(evidence, { recursive: true });
          await page.screenshot({ path: path.join(evidence, `${width}x${height}-${index}.png`) });
          observations.push({ width, height, index, ...metrics });
        }
        cases++;
      }
    }

    // Restore a normal viewport for the remaining, non-matrix assertions.
    await page.setViewportSize({ width: 1280, height: 720 });

    for (const [model, expected] of [[data.zero, '0.0'], [data.blank, '—']]) {
      await page.evaluate(model => window.applyView(model), model);
      assert.equal(await widgetText(page, 'play_clock_value'), expected);
      assert.equal(await widgetHidden(page, 'play_clock_label'), false);
    }

    await page.evaluate(model => window.applyView(model), data.runningGame);
    assert.equal(await page.locator('[data-widget="game_clock_value"]').evaluate(el => el.classList.contains('running-game')), true);
    assert.equal(await page.locator('[data-widget="play_clock_value"]').evaluate(el => el.classList.contains('running-play')), false);
    await page.evaluate(model => window.applyView(model), data.runningPlay);
    assert.equal(await page.locator('[data-widget="game_clock_value"]').evaluate(el => el.classList.contains('running-game')), false);
    assert.equal(await page.locator('[data-widget="play_clock_value"]').evaluate(el => el.classList.contains('running-play')), true);
    assert.equal(await widgetText(page, 'quarter'), '4th Quarter');

    // An injected failure in the widget-text pipeline must not take down the
    // whole page: window.applyView's own try/catch keeps the last usable
    // board on screen and swallows the error.
    await page.evaluate(() => {
      window.originalApplyModel = window.ScoreboardBoard.applyModel;
      window.ScoreboardBoard.applyModel = () => { throw new Error('injected'); };
    });
    await page.evaluate(model => window.applyView(model), data.zero); // must not throw
    await page.evaluate(() => { window.ScoreboardBoard.applyModel = window.originalApplyModel; });
    await page.evaluate(model => window.applyView(model), data.zero);
    assert.equal(await widgetText(page, 'play_clock_value'), '0.0');

    // Re-establish a known-good baseline (default layout, a populated model)
    // before the layout-specific cases below.
    await page.evaluate(model => window.applyView(model), data.populated);

    // A custom layout: two widgets moved to known fractions of the canvas.
    // Their boxes -- not just their text -- must land exactly there.
    const moved = await page.evaluate(() => {
      const custom = JSON.parse(JSON.stringify(window.ScoreboardBoard.DEFAULT_LAYOUT));
      custom.name = 'Custom';
      custom.widgets.play_clock_label = Object.assign({}, custom.widgets.play_clock_label,
        { x: 0.10, y: 0.12, width: 0.22, height: 0.06 });
      custom.widgets.home_name = Object.assign({}, custom.widgets.home_name,
        { x: 0.50, y: 0.03, width: 0.30, height: 0.10 });
      window.applyLayout(custom);
      const canvas = document.querySelector('#canvas').getBoundingClientRect();
      const playClockLabel = document.querySelector('[data-widget="play_clock_label"]').getBoundingClientRect();
      const homeName = document.querySelector('[data-widget="home_name"]').getBoundingClientRect();
      return {
        canvas: canvas.toJSON(), playClockLabel: playClockLabel.toJSON(), homeName: homeName.toJSON(),
        layoutName: document.querySelector('#canvas').dataset.layout,
      };
    });
    assert.equal(moved.layoutName, 'Custom');
    const expectPlacement = (box, canvas, x, y, w, h) => {
      assert.ok(Math.abs(box.left - (canvas.left + x * canvas.width)) <= 1, `left ${JSON.stringify(box)}`);
      assert.ok(Math.abs(box.top - (canvas.top + y * canvas.height)) <= 1, `top ${JSON.stringify(box)}`);
      assert.ok(Math.abs(box.width - w * canvas.width) <= 1, `width ${JSON.stringify(box)}`);
      assert.ok(Math.abs(box.height - h * canvas.height) <= 1, `height ${JSON.stringify(box)}`);
    };
    expectPlacement(moved.playClockLabel, moved.canvas, 0.10, 0.12, 0.22, 0.06);
    expectPlacement(moved.homeName, moved.canvas, 0.50, 0.03, 0.30, 0.10);

    // A garbage layout payload must be rejected before it ever reaches the
    // board: the previous (custom, non-default) layout stays exactly as it
    // was, and window.applyLayout itself never throws.
    const afterGarbage = await page.evaluate(() => {
      const attempts = ['garbage', 42, null, {}, { widgets: 'nope' }, []];
      const thrown = [];
      for (const attempt of attempts) {
        try { window.applyLayout(attempt); } catch (error) { thrown.push(String(error)); }
      }
      const canvas = document.querySelector('#canvas').getBoundingClientRect();
      const playClockLabel = document.querySelector('[data-widget="play_clock_label"]').getBoundingClientRect();
      const homeName = document.querySelector('[data-widget="home_name"]').getBoundingClientRect();
      return {
        thrown, canvas: canvas.toJSON(), playClockLabel: playClockLabel.toJSON(), homeName: homeName.toJSON(),
        layoutName: document.querySelector('#canvas').dataset.layout,
      };
    });
    assert.deepEqual(afterGarbage.thrown, []);
    assert.equal(afterGarbage.layoutName, 'Custom');
    expectPlacement(afterGarbage.playClockLabel, afterGarbage.canvas, 0.10, 0.12, 0.22, 0.06);
    expectPlacement(afterGarbage.homeName, afterGarbage.canvas, 0.50, 0.03, 0.30, 0.10);

    // Back to the default layout for the remaining cases.
    await page.evaluate(() => window.applyLayout(window.ScoreboardBoard.DEFAULT_LAYOUT));

    // An optional field going empty hides just its own widget; the rest of
    // the board (a sibling optional widget, and an ordinary widget) is
    // unaffected.
    await page.evaluate(model => window.applyView(model), data.populated);
    assert.equal(await widgetHidden(page, 'down'), false);
    assert.equal(await widgetHidden(page, 'possession'), false);
    const withoutDown = await page.evaluate(model => {
      const clone = JSON.parse(JSON.stringify(model));
      clone.football.down_display = '';
      return clone;
    }, data.populated);
    await page.evaluate(model => window.applyView(model), withoutDown);
    assert.equal(await widgetHidden(page, 'down'), true);
    assert.equal(await widgetHidden(page, 'possession'), false);
    assert.equal(await widgetText(page, 'possession'), data.populated.football.possession_display);
    assert.equal(await widgetText(page, 'home_score'), String(data.populated.teams.home.score));
    // Restore the field and confirm the widget reappears.
    await page.evaluate(model => window.applyView(model), data.populated);
    assert.equal(await widgetHidden(page, 'down'), false);

    // game_clock_label / home_timeouts / away_timeouts are hidden under the
    // default layout even though their model text is present ...
    assert.equal(await widgetHidden(page, 'game_clock_label'), true);
    assert.equal(await widgetHidden(page, 'home_timeouts'), true);
    assert.equal(await widgetHidden(page, 'away_timeouts'), true);
    // ... and become visible, and correctly placed, once a layout turns
    // them on.
    const revealed = await page.evaluate(() => {
      const custom = JSON.parse(JSON.stringify(window.ScoreboardBoard.DEFAULT_LAYOUT));
      custom.widgets.game_clock_label = Object.assign({}, custom.widgets.game_clock_label, { visible: true });
      custom.widgets.home_timeouts = Object.assign({}, custom.widgets.home_timeouts, { visible: true });
      custom.widgets.away_timeouts = Object.assign({}, custom.widgets.away_timeouts, { visible: true });
      window.applyLayout(custom);
      const canvas = document.querySelector('#canvas').getBoundingClientRect();
      const box = id => document.querySelector('[data-widget="' + id + '"]').getBoundingClientRect().toJSON();
      return { canvas: canvas.toJSON(), gameClockLabel: box('game_clock_label'), homeTimeouts: box('home_timeouts'), awayTimeouts: box('away_timeouts') };
    });
    assert.equal(await widgetHidden(page, 'game_clock_label'), false);
    assert.equal(await widgetHidden(page, 'home_timeouts'), false);
    assert.equal(await widgetHidden(page, 'away_timeouts'), false);
    assert.equal(await widgetText(page, 'game_clock_label'), 'GAME CLOCK');
    assert.equal(await widgetText(page, 'home_timeouts'), data.populated.football.home_timeouts_display);
    assert.equal(await widgetText(page, 'away_timeouts'), data.populated.football.away_timeouts_display);
    // Expected geometry comes from the layout itself, not from literals: the
    // point of this check is that the renderer honours whatever Python sent,
    // and hard-coded numbers would only re-assert the default's own values.
    const defaults = await page.evaluate(() => window.ScoreboardBoard.DEFAULT_LAYOUT.widgets);
    for (const [id, measured] of [['game_clock_label', revealed.gameClockLabel],
                                  ['home_timeouts', revealed.homeTimeouts],
                                  ['away_timeouts', revealed.awayTimeouts]]) {
      const w = defaults[id];
      expectPlacement(measured, revealed.canvas, w.x, w.y, w.width, w.height);
    }
    // No overlap now that three more widgets are visible at once.
    const revealedMetrics = await measureWidgets(page);
    assert.deepEqual(revealedMetrics.errors, [], `revealed widgets: ${JSON.stringify(revealedMetrics)}`);

    if (evidence) fs.writeFileSync(path.join(evidence, 'measurements.json'), JSON.stringify(observations, null, 2));
    return { cases };
  } finally { await browser.close(); }
}
let input = ''; process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => main(JSON.parse(input)).then(result => console.log(JSON.stringify(result))).catch(error => { console.error(error); process.exitCode = 1; }));
