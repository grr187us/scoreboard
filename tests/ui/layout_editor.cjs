/* Drive the presentation layout editor v2 against a stub bridge.
 *
 * Every payload the stub returns was produced by the real Python
 * `PresentationLayouts` and `spectator_view_model` (see
 * test_layout_editor_browser.py), so the page is exercised against the shapes
 * it will actually receive rather than against hand-written fixtures.
 *
 * v2 replaces the plain widget list and 0..1 number boxes with a layers
 * rail, a percent-based inspector, and direct manipulation as the primary
 * route; this script is updated to match (element ids, `data-action` names,
 * percent-valued fields) and extended with the v2-only gestures: adding a
 * text element and a box, history back/forward, a multi-select drag, an
 * alignment command, and deleting an element.
 */

const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

async function main(data) {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const checks = [];
  try {
    const page = await browser.newPage();
    await page.setViewportSize({ width: 1220, height: 780 });
    await page.route(/^https?:/, route => route.abort());

    await page.addInitScript(payload => {
      window.__calls = [];
      const record = (name, args) => window.__calls.push({ name, args });
      // The stub answers with the real payloads Python produced. `preview` is
      // the one call that must branch, because the page uses it to decide
      // whether the draft can be saved.
      const invalid = draft => {
        const w = draft && draft.widgets && draft.widgets.ball_on;
        return Boolean(w && w.y > 0.9);
      };
      window.pywebview = {
        api: {
          layout_state: () => { record('layout_state'); return Promise.resolve(payload.state); },
          get_snapshot: () => { record('get_snapshot'); return Promise.resolve(payload.snapshot); },
          preview_layout: draft => {
            // A copy: the page hands over its live draft object, and the
            // ticker scenario below reads the draft as it stood at each step.
            record('preview_layout', JSON.parse(JSON.stringify(draft)));
            return Promise.resolve(invalid(draft) ? payload.invalidPreview : payload.validPreview);
          },
          clamp_layout: draft => { record('clamp_layout', draft); return Promise.resolve(payload.clamped); },
          reset_widget: (id, draft, screen) => { record('reset_widget', { id, screen }); return Promise.resolve(payload.resetWidget); },
          save_layout: (name, draft) => { record('save_layout', name); return Promise.resolve(payload.saved); },
          select_layout: name => { record('select_layout', name); return Promise.resolve(payload.state); },
          delete_layout: name => { record('delete_layout', name); return Promise.resolve(payload.state); },
          rename_layout: (oldName, newName) => { record('rename_layout', newName); return Promise.resolve(payload.state); },
          duplicate_layout: (name, newName) => { record('duplicate_layout', newName); return Promise.resolve(payload.state); },
          reset_layout: () => { record('reset_layout'); return Promise.resolve(payload.state); },
        }
      };
    }, data);

    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/layout/index.html')).href);
    await page.waitForFunction(() => document.querySelectorAll('[data-select-widget]').length > 0);

    // --- The widget list is generated from Python's descriptors, grouped ---
    const listed = await page.$$eval('[data-select-widget]', els => els.map(e => e.textContent));
    assert.equal(listed.length, data.state.widgets.length);
    for (const descriptor of data.state.widgets) {
      assert.ok(listed.some(text => text.startsWith(descriptor.label)),
        `missing ${descriptor.label}`);
    }
    // A hidden widget says so in words, not by colour alone.
    const hiddenLabel = data.state.widgets.find(w => !w.default.visible).label;
    assert.ok(listed.some(text => text.startsWith(hiddenLabel) && /hidden/.test(text)));
    checks.push('widget list');

    // --- Selecting fills every property control, as percentages ------------
    const pct = value => Math.round(value * 1000) / 10;
    await page.click('[data-select-widget="play_clock_value"]');
    const shown = await page.evaluate(() => {
      const value = id => document.getElementById(id).value;
      return {
        label: document.getElementById('inspector-title').textContent,
        x: value('prop-x'), y: value('prop-y'),
        width: value('prop-width'), height: value('prop-height'),
        font: value('prop-font_scale'), color: value('prop-color'),
        weight: value('prop-font_weight'),
        visible: document.getElementById('prop-visible').checked,
        align: document.querySelector('#prop-text_align .is-current').dataset.choice,
        valign: document.querySelector('#prop-vertical_align .is-current').dataset.choice,
      };
    });
    const expected = data.state.layout.widgets.play_clock_value;
    assert.equal(shown.label, 'Play clock');
    assert.equal(Number(shown.x), pct(expected.x));
    assert.equal(Number(shown.y), pct(expected.y));
    assert.equal(Number(shown.width), pct(expected.width));
    assert.equal(Number(shown.font), pct(expected.font_scale));
    assert.equal(shown.color, expected.color);
    assert.equal(Number(shown.weight), expected.font_weight);
    assert.equal(shown.visible, expected.visible);
    assert.equal(shown.align, expected.text_align);
    assert.equal(shown.valign, expected.vertical_align);
    checks.push('property panel');

    // --- Changing X moves the previewed widget -----------------------------
    await page.fill('#prop-x', '20.0');
    await page.dispatchEvent('#prop-x', 'input');
    const placed = await page.evaluate(() => {
      const canvas = document.querySelector('#canvas').getBoundingClientRect();
      const widget = document.querySelector('[data-item="play_clock_value"]').getBoundingClientRect();
      return { offset: (widget.left - canvas.left) / canvas.width };
    });
    assert.ok(Math.abs(placed.offset - 0.200) < 0.003, `preview at ${placed.offset}`);
    checks.push('numeric move');

    // --- Toggling visibility hides it in the preview -----------------------
    await page.uncheck('#prop-visible');
    assert.equal(await page.getAttribute('[data-item="play_clock_value"]', 'hidden') !== null, true);
    await page.check('#prop-visible');
    // Put it back where it started: the moved widget now sits on top of the
    // quarter, and the next check clicks the quarter in the preview.
    await page.fill('#prop-x', String(pct(expected.x)));
    await page.dispatchEvent('#prop-x', 'input');
    await page.dispatchEvent('#prop-x', 'change');
    checks.push('visibility toggle');

    // --- Clicking a widget in the preview selects it -----------------------
    await page.click('[data-item="quarter"]', { force: true });
    assert.equal(await page.textContent('#inspector-title'), 'Quarter');
    assert.ok((await page.evaluate(() =>
      document.querySelector('[data-select-widget="quarter"]').closest('.rail-row').className)).includes('is-current'));
    checks.push('preview selection');

    // --- An out-of-safe-area value reports and blocks Save -----------------
    await page.click('[data-select-widget="ball_on"]');
    await page.fill('#prop-y', '93.0');
    await page.dispatchEvent('#prop-y', 'input');
    await page.waitForFunction(() => document.getElementById('save').disabled === true);
    const issueText = await page.textContent('#issue-list');
    assert.ok(/Ball on/.test(issueText), `issues did not name the widget: ${issueText}`);
    assert.ok(/ERROR/.test(issueText));
    assert.equal(await page.isDisabled('#save'), true);
    assert.equal(await page.isDisabled('#save-as-open'), true);
    checks.push('validation blocks save');

    // Correcting it re-enables Save.
    await page.fill('#prop-y', '85.4');
    await page.dispatchEvent('#prop-y', 'input');
    await page.waitForFunction(() => document.getElementById('save').disabled === false);
    checks.push('validation clears');

    // --- Clicking an issue selects the widget it names ---------------------
    await page.fill('#prop-y', '93.0');
    await page.dispatchEvent('#prop-y', 'input');
    await page.waitForFunction(() => document.querySelectorAll('#issue-list button').length > 0);
    await page.click('[data-select-widget="quarter"]');
    // v2 keeps the issue list in a drawer behind the status summary; the
    // summary itself must already say there is an error before it is opened.
    assert.match(await page.textContent('#status-summary'), /1 error/);
    await page.click('#status-summary');
    await page.waitForSelector('#issue-list button', { state: 'visible' });
    await page.click('#issue-list button');
    assert.equal(await page.textContent('#inspector-title'), 'Ball on');
    checks.push('issue selects widget');

    // --- Reset this widget restores the default values ---------------------
    await page.click('#action-reset_widget');
    await page.waitForFunction(
      expectedY => Number(document.getElementById('prop-y').value) === expectedY,
      pct(data.state.layout.widgets.ball_on.y));
    checks.push('reset widget');

    // reset_widget must carry which screen the widget lives on -- the Game
    // screen while the switcher has not been touched yet.
    assert.ok(await page.evaluate(() =>
      window.__calls.some(c => c.name === 'reset_widget' && c.args && c.args.screen === 'game')));
    checks.push('reset widget names the screen');

    // --- Save as sends the typed name, with no blocking dialog -------------
    // v2 files Save as... under the layout-name menu in the top bar.
    await page.click('#layout-menu-button');
    await page.click('#save-as-open');
    await page.fill('#save-as-name', 'Night game');
    await page.click('[data-action="save_as_confirm"]');
    await page.waitForFunction(() =>
      window.__calls.some(c => c.name === 'save_layout' && c.args === 'Night game'));
    checks.push('save as');

    // --- Direct manipulation: drag, resize, nudge --------------------------
    //
    // These use real mouse and keyboard input rather than synthetic events,
    // so they exercise the same path an operator's hand does: pointer
    // capture, the snap, and the safe-area boundary.
    const geometry = id => page.evaluate(widgetId => {
      const el = document.querySelector(`#game-board [data-item="${widgetId}"]`);
      const read = name => Number(el.style.getPropertyValue(name));
      return { x: read('--x'), y: read('--y'), w: read('--w'), h: read('--h') };
    }, id);
    const canvasBox = async () => page.locator('#canvas').boundingBox();

    await page.click('[data-select-widget="quarter"]');
    const box = await canvasBox();
    const at = (fx, fy) => [box.x + fx * box.width, box.y + fy * box.height];

    // Drag it to the middle of the board.
    const start = await geometry('quarter');
    await page.mouse.move(...at(start.x + start.w / 2, start.y + start.h / 2));
    await page.mouse.down();
    await page.mouse.move(...at(0.5, 0.62), { steps: 8 });
    await page.mouse.up();
    const dragged = await geometry('quarter');
    assert.ok(dragged.x !== start.x || dragged.y !== start.y, 'the drag must move the widget');
    assert.equal(dragged.w, start.w, 'a move must not resize');
    assert.equal(dragged.h, start.h, 'a move must not resize');
    checks.push('drag to move');

    // Dragging far outside stops at the safe area rather than going out.
    const safe = data.state.layout.safe_area;
    await page.mouse.move(...at(dragged.x + dragged.w / 2, dragged.y + dragged.h / 2));
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 2, box.y + box.height * 2, { steps: 8 });
    await page.mouse.up();
    const pushed = await geometry('quarter');
    assert.ok(pushed.x + pushed.w <= 1 - safe.right + 1e-6, 'a drag must stop at the right edge');
    assert.ok(pushed.y + pushed.h <= 1 - safe.bottom + 1e-6, 'a drag must stop at the bottom edge');
    checks.push('safe area is a hard boundary');

    // A corner handle resizes without moving the opposite corner.
    const beforeResize = await geometry('quarter');
    await page.mouse.move(...at(beforeResize.x, beforeResize.y));
    await page.mouse.down();
    await page.mouse.move(...at(beforeResize.x - 0.04, beforeResize.y - 0.03), { steps: 6 });
    await page.mouse.up();
    const resized = await geometry('quarter');
    assert.ok(resized.w > beforeResize.w, 'dragging the NW handle out must widen the widget');
    assert.ok(
      Math.abs((resized.x + resized.w) - (beforeResize.x + beforeResize.w)) < 1e-6,
      'resizing from the north-west must hold the south-east corner still');
    checks.push('resize by handle');

    // Arrow keys and the on-screen arrows nudge, and Shift nudges further.
    // Leftwards: the boundary drag above left the widget against the right
    // safe edge, where a rightward nudge is (correctly) clamped to nothing.
    const beforeNudge = await geometry('quarter');
    await page.click('[data-action="nudge_left"]');
    const nudgedByButton = await geometry('quarter');
    assert.ok(nudgedByButton.x < beforeNudge.x, 'the arrow button must move it left');

    await page.locator('#canvas').click({ position: { x: 4, y: 4 } });
    await page.click('[data-select-widget="quarter"]');
    await page.keyboard.press('ArrowLeft');
    const nudgedByKey = await geometry('quarter');
    const fine = nudgedByButton.x - nudgedByKey.x;
    await page.keyboard.press('Shift+ArrowLeft');
    const nudgedFar = await geometry('quarter');
    assert.ok(fine > 0, 'the arrow key must move it left');
    assert.ok(nudgedByKey.x - nudgedFar.x > fine, 'Shift must move it further than a plain arrow');
    checks.push('nudge by key and button');

    // Typing in a field keeps its own arrow-key behaviour.
    const beforeTyping = await geometry('quarter');
    await page.focus('#prop-x');
    await page.keyboard.press('ArrowRight');
    assert.deepEqual(await geometry('quarter'), beforeTyping,
      'an arrow key inside a text field must not move the widget');
    checks.push('arrows leave fields alone');

    // --- History: undo/redo -------------------------------------------------
    await page.click('[data-select-widget="quarter"]');
    const beforeHistoryMove = await geometry('quarter');
    await page.click('[data-action="nudge_right"]');
    const afterHistoryMove = await geometry('quarter');
    assert.notEqual(afterHistoryMove.x, beforeHistoryMove.x);
    await page.click('[data-action="history_back"]');
    await page.waitForFunction(
      expected => {
        const el = document.querySelector('#game-board [data-item="quarter"]');
        return Number(el.style.getPropertyValue('--x')) === expected;
      },
      beforeHistoryMove.x);
    await page.click('[data-action="history_forward"]');
    await page.waitForFunction(
      expected => {
        const el = document.querySelector('#game-board [data-item="quarter"]');
        return Number(el.style.getPropertyValue('--x')) === expected;
      },
      afterHistoryMove.x);
    checks.push('history back and forward');

    // --- Add a text element and a box, then align and delete ---------------
    const elementCountBefore = await page.evaluate(() =>
      document.querySelectorAll('#rail-elements-body .rail-row').length);
    await page.click('[data-action="add_text"]');
    await page.waitForFunction(
      count => document.querySelectorAll('#rail-elements-body .rail-row').length === count,
      elementCountBefore + 1);
    assert.equal(await page.locator('[data-item^="text_"]').count(), 1);
    checks.push('add text element');

    await page.click('[data-action="add_box"]');
    await page.waitForFunction(
      count => document.querySelectorAll('#rail-elements-body .rail-row').length === count,
      elementCountBefore + 2);
    assert.equal(await page.locator('[data-item^="box_"]').count(), 1);
    checks.push('add box');

    // The box is selected after being added; align it left. A box may cross
    // the safe area (it is a full-bleed backdrop candidate), so aligning it
    // targets the canvas edge, not the safe-area inset -- the same boundary
    // rule that already governs where a box is allowed to be dragged.
    await page.click('[data-action="align_left"]');
    const boxGeometry = await page.evaluate(() => {
      const el = document.querySelector('[data-item^="box_"]');
      return Number(el.style.getPropertyValue('--x'));
    });
    assert.ok(Math.abs(boxGeometry - 0) < 1e-6, 'align left must snap to the canvas edge for a box');
    checks.push('align');

    // --- Multi-select drag: shift-click two widgets and move them together -
    await page.click('[data-select-widget="down"]');
    await page.click('[data-select-widget="distance"]', { modifiers: ['Shift'] });
    const downBefore = await geometry('down');
    const distanceBefore = await geometry('distance');
    const boxNow = await canvasBox();
    const atNow = (fx, fy) => [boxNow.x + fx * boxNow.width, boxNow.y + fy * boxNow.height];
    await page.mouse.move(...atNow(downBefore.x + downBefore.w / 2, downBefore.y + downBefore.h / 2));
    await page.mouse.down();
    await page.mouse.move(...atNow(downBefore.x + downBefore.w / 2, downBefore.y + downBefore.h / 2 + 0.05),
      { steps: 6 });
    await page.mouse.up();
    const downAfter = await geometry('down');
    const distanceAfter = await geometry('distance');
    assert.ok(downAfter.y > downBefore.y, 'the primary member of the selection must move');
    assert.ok(Math.abs((distanceAfter.y - distanceBefore.y) - (downAfter.y - downBefore.y)) < 1e-6,
      'every selected member must move by the same delta');
    checks.push('multi-select drag');

    // --- Delete removes the selected element, leaves widgets alone ---------
    await page.click('[data-item^="text_"]');
    await page.keyboard.press('Delete');
    await page.waitForFunction(() => document.querySelectorAll('[data-item^="text_"]').length === 0);
    assert.equal(await page.locator('[data-item="quarter"]').count(), 1,
      'deleting an element must never remove a widget');
    checks.push('delete element');

    // --- Ticker element (event screens, September 8, 2026) ------------------
    //
    // Add a ticker, type two lines, switch it to rotate mode, set its speed,
    // step back and forward through history, then delete it -- asserting the
    // draft after every step. The draft is read back from the last
    // preview_layout call, which the page makes after each edit.
    const lastDraft = () => page.evaluate(() => {
      const previews = window.__calls.filter(c => c.name === 'preview_layout');
      return previews[previews.length - 1].args;
    });
    const tickerIn = draft => (draft.elements || []).filter(e => e.type === 'ticker');
    const rowsBeforeTicker = await page.evaluate(() =>
      document.querySelectorAll('#rail-elements-body .rail-row').length);
    await page.click('[data-action="add_ticker"]');
    await page.waitForFunction(
      count => document.querySelectorAll('#rail-elements-body .rail-row').length === count,
      rowsBeforeTicker + 1);
    let ticker = tickerIn(await lastDraft());
    assert.equal(ticker.length, 1, 'adding a ticker must put exactly one in the draft');
    assert.deepEqual(
      { x: ticker[0].x, y: ticker[0].y, width: ticker[0].width, height: ticker[0].height },
      { x: 0, y: 0.89, width: 1, height: 0.1 });
    assert.deepEqual(ticker[0].lines, ['NEW ANNOUNCEMENT']);
    assert.equal(ticker[0].mode, 'scroll');
    assert.equal(ticker[0].speed_seconds, 30);
    assert.equal(ticker[0].font_family, 'barlow_condensed');
    assert.equal(await page.isVisible('#sec-ticker'), true, 'the Ticker section must open for it');
    assert.equal(await page.isVisible('#sec-motion'), false, 'a ticker takes no animation preset');
    assert.match(await page.textContent('#inspector-title'), /NEW ANNOUNCEMENT/);
    // The stub answers every preview with the Python payload for a
    // ticker-less draft, so the issue count for a ticker draft is not
    // asserted here; tests/unit/test_event_screens.py validates tickers.
    checks.push('add ticker');

    await page.fill('#prop-lines', 'GO TIGERS\n  SENIOR NIGHT  \n');
    await page.dispatchEvent('#prop-lines', 'input');
    // Leaving the field fires the native 'change' -- one history entry, as
    // an operator's typing would (a dispatched 'change' on top of it would
    // record the same draft twice and make the history steps below lie).
    await page.locator('#prop-lines').blur();
    ticker = tickerIn(await lastDraft());
    assert.deepEqual(ticker[0].lines, ['GO TIGERS', 'SENIOR NIGHT'],
      'lines split on newline, trimmed, empties dropped');
    checks.push('ticker lines');

    await page.click('#prop-mode [data-choice="rotate"]');
    ticker = tickerIn(await lastDraft());
    assert.equal(ticker[0].mode, 'rotate');
    assert.equal(await page.textContent('#speed-label'), 'Seconds per line');
    checks.push('ticker rotate mode');

    await page.fill('#prop-speed_seconds', '8');
    await page.dispatchEvent('#prop-speed_seconds', 'input');
    await page.locator('#prop-speed_seconds').blur();
    ticker = tickerIn(await lastDraft());
    assert.equal(ticker[0].speed_seconds, 8);
    checks.push('ticker speed');

    await page.click('[data-action="history_back"]');
    await page.waitForFunction(() => Number(document.getElementById('prop-speed_seconds').value) === 30);
    ticker = tickerIn(await lastDraft());
    assert.equal(ticker[0].speed_seconds, 30, 'history back must restore the previous speed');
    assert.equal(ticker[0].mode, 'rotate', 'history back steps one edit, not two');
    await page.click('[data-action="history_forward"]');
    await page.waitForFunction(() => Number(document.getElementById('prop-speed_seconds').value) === 8);
    ticker = tickerIn(await lastDraft());
    assert.equal(ticker[0].speed_seconds, 8, 'history forward must re-apply the speed');
    checks.push('ticker history');

    await page.click('#action-delete_element');
    await page.waitForFunction(
      count => document.querySelectorAll('#rail-elements-body .rail-row').length === count,
      rowsBeforeTicker);
    assert.equal(tickerIn(await lastDraft()).length, 0, 'deleting must remove the ticker from the draft');
    assert.equal(await page.locator('[data-item="quarter"]').count(), 1);
    checks.push('delete ticker');

    // --- The screen switcher: Pre-game has its own widgets, presets, and
    // elements, entirely separate from the Game screen's ---------------------
    await page.click('[data-screen="pregame"]');
    await page.waitForFunction(() =>
      document.querySelector('[data-screen="pregame"]').getAttribute('aria-selected') === 'true');
    assert.equal(await page.locator('#rail-groups [data-select-widget="event_clock"]').count(), 1,
      'the pre-game screen must show its own event widgets, not the game ones');
    assert.equal(await page.locator('#rail-groups [data-select-widget="quarter"]').count(), 0,
      'a game-only widget must not appear on the pre-game screen');
    checks.push('switch to pre-game');

    // Applying one of its screen presets (anything but the plain default)
    // replaces this screen's widgets/elements and re-validates the draft.
    // The draft is already dirty from every edit made above, so this opens
    // the "replace the draft" confirmation inline rather than applying at
    // once -- the same guard the Game screen's own presets use.
    // Picked by name rather than by array position, so this keeps working
    // however the preset list is ordered: "Matchup" (spec section 1.4) is
    // the pre-game preset with exactly one free element -- a "VS" mark --
    // which makes its effect on the elements rail unambiguous to assert.
    const pregamePreset = data.state.screen_presets.pregame.find(preset => preset.name === 'Matchup');
    await page.click('[data-action="presets_menu"]');
    await page.click(`#presets-gallery-menu [data-apply-preset="${pregamePreset.id}"]`);
    await page.click('[data-action="replace_draft_confirm"]');
    await page.waitForFunction(() => document.querySelectorAll('#rail-elements-body .rail-row').length === 1);
    checks.push('apply a pre-game preset');

    // A text element added here must land on the pre-game screen's own
    // element list, on top of the "VS" mark the preset just added.
    await page.click('[data-action="add_text"]');
    await page.waitForFunction(() => document.querySelectorAll('#rail-elements-body .rail-row').length === 2);
    checks.push('add text on the pre-game screen');

    // Switching back to Game must restore its own widget list -- the
    // pre-game edit above must not have leaked into it.
    await page.click('[data-screen="game"]');
    await page.waitForFunction(() =>
      document.querySelector('[data-screen="game"]').getAttribute('aria-selected') === 'true');
    assert.equal(await page.locator('#rail-groups [data-select-widget="quarter"]').count(), 1,
      'switching back to Game must restore its own widget list');
    checks.push('switch back to the game screen');

    // Saving still sends the whole document, screens and all.
    await page.click('#save');
    await page.waitForFunction(() =>
      window.__calls[window.__calls.length - 1].name === 'save_layout');
    checks.push('save after editing another screen');

    // --- The page itself never scrolls at 1220x780 --------------------------
    const scroll = await page.evaluate(() => {
      const de = document.documentElement;
      return { w: de.scrollWidth, cw: de.clientWidth, h: de.scrollHeight, ch: de.clientHeight };
    });
    assert.equal(scroll.w, scroll.cw, 'the editor page must not scroll horizontally');
    assert.equal(scroll.h, scroll.ch, 'the editor page must not scroll vertically');
    checks.push('no page scroll');

    // --- It is structurally incapable of sending a game command ------------
    assert.equal(await page.locator('[data-command]').count(), 0);
    const called = await page.evaluate(() => window.__calls.map(c => c.name));
    assert.ok(!called.includes('command'));
    checks.push('no game command');

    return { checks };
  } finally {
    await browser.close();
  }
}

let input = '';
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => main(JSON.parse(input))
  .then(result => console.log(JSON.stringify(result)))
  .catch(error => { console.error(error); process.exitCode = 1; }));
