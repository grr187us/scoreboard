/* Drive the presentation layout editor against a stub bridge.
 *
 * Every payload the stub returns was produced by the real Python
 * `PresentationLayouts` and `spectator_view_model` (see
 * test_layout_editor_browser.py), so the page is exercised against the shapes
 * it will actually receive rather than against hand-written fixtures.
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
    await page.setViewportSize({ width: 1280, height: 720 });
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
            record('preview_layout');
            return Promise.resolve(invalid(draft) ? payload.invalidPreview : payload.validPreview);
          },
          clamp_layout: draft => { record('clamp_layout', draft); return Promise.resolve(payload.clamped); },
          reset_widget: (id, draft) => { record('reset_widget', id); return Promise.resolve(payload.resetWidget); },
          save_layout: (name, draft) => { record('save_layout', name); return Promise.resolve(payload.saved); },
          select_layout: name => { record('select_layout', name); return Promise.resolve(payload.state); },
          delete_layout: name => { record('delete_layout', name); return Promise.resolve(payload.state); },
          reset_layout: () => { record('reset_layout'); return Promise.resolve(payload.state); },
        }
      };
    }, data);

    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/layout/index.html')).href);
    await page.waitForFunction(() => document.querySelectorAll('#widget-list button').length > 0);

    // --- The widget list is generated from Python's descriptors ------------
    const listed = await page.$$eval('#widget-list button', els => els.map(e => e.textContent));
    assert.equal(listed.length, data.state.widgets.length);
    for (const descriptor of data.state.widgets) {
      assert.ok(listed.some(text => text.startsWith(descriptor.label)),
        `missing ${descriptor.label}`);
    }
    // A hidden widget says so in words, not by colour alone.
    const hiddenLabel = data.state.widgets.find(w => !w.default.visible).label;
    assert.ok(listed.some(text => text.startsWith(hiddenLabel) && /hidden/.test(text)));
    checks.push('widget list');

    // --- Selecting fills every property control ----------------------------
    await page.click('[data-select-widget="play_clock_value"]');
    const shown = await page.evaluate(() => {
      const value = id => document.getElementById(id).value;
      return {
        label: document.getElementById('selected-label').textContent,
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
    assert.equal(Number(shown.x), expected.x);
    assert.equal(Number(shown.y), expected.y);
    assert.equal(Number(shown.width), expected.width);
    assert.equal(Number(shown.font), expected.font_scale);
    assert.equal(shown.color, expected.color);
    assert.equal(Number(shown.weight), expected.font_weight);
    assert.equal(shown.visible, expected.visible);
    assert.equal(shown.align, expected.text_align);
    assert.equal(shown.valign, expected.vertical_align);
    checks.push('property panel');

    // --- Changing X moves the previewed widget -----------------------------
    await page.fill('#prop-x', '0.200');
    await page.dispatchEvent('#prop-x', 'input');
    const placed = await page.evaluate(() => {
      const canvas = document.querySelector('#canvas').getBoundingClientRect();
      const widget = document.querySelector('[data-widget="play_clock_value"]').getBoundingClientRect();
      return { offset: (widget.left - canvas.left) / canvas.width };
    });
    assert.ok(Math.abs(placed.offset - 0.200) < 0.002, `preview at ${placed.offset}`);
    checks.push('numeric move');

    // --- Toggling visibility hides it in the preview -----------------------
    await page.uncheck('#prop-visible');
    assert.equal(await page.getAttribute('[data-widget="play_clock_value"]', 'hidden') !== null, true);
    await page.check('#prop-visible');
    // Put it back where it started: the moved widget now sits on top of the
    // quarter, and the next check clicks the quarter in the preview.
    await page.fill('#prop-x', String(expected.x));
    await page.dispatchEvent('#prop-x', 'input');
    checks.push('visibility toggle');

    // --- Clicking a widget in the preview selects it -----------------------
    await page.click('[data-widget="quarter"]', { force: true });
    assert.equal(await page.textContent('#selected-label'), 'Quarter');
    assert.equal(await page.getAttribute('[data-select-widget="quarter"]', 'class'),
      await page.evaluate(() => document.querySelector('[data-select-widget="quarter"]').className));
    assert.ok((await page.evaluate(() =>
      document.querySelector('[data-select-widget="quarter"]').className)).includes('is-current'));
    checks.push('preview selection');

    // --- An out-of-safe-area value reports and blocks Save -----------------
    await page.click('[data-select-widget="ball_on"]');
    await page.fill('#prop-y', '0.930');
    await page.dispatchEvent('#prop-y', 'input');
    await page.waitForFunction(() => document.getElementById('save').disabled === true);
    const issueText = await page.textContent('#issue-list');
    assert.ok(/Ball on/.test(issueText), `issues did not name the widget: ${issueText}`);
    assert.ok(/ERROR/.test(issueText));
    assert.equal(await page.isDisabled('#save'), true);
    assert.equal(await page.isDisabled('#save-as-open'), true);
    checks.push('validation blocks save');

    // Correcting it re-enables Save.
    await page.fill('#prop-y', '0.854');
    await page.dispatchEvent('#prop-y', 'input');
    await page.waitForFunction(() => document.getElementById('save').disabled === false);
    checks.push('validation clears');

    // --- Clicking an issue selects the widget it names ---------------------
    await page.fill('#prop-y', '0.930');
    await page.dispatchEvent('#prop-y', 'input');
    await page.waitForFunction(() => document.querySelectorAll('#issue-list button').length > 0);
    await page.click('[data-select-widget="quarter"]');
    await page.click('#issue-list button');
    assert.equal(await page.textContent('#selected-label'), 'Ball on');
    checks.push('issue selects widget');

    // --- Reset this widget restores the default values ---------------------
    await page.click('[data-action="reset_widget"]');
    await page.waitForFunction(
      expectedY => Number(document.getElementById('prop-y').value) === expectedY,
      data.state.layout.widgets.ball_on.y);
    checks.push('reset widget');

    // --- Save as sends the typed name, with no blocking dialog -------------
    await page.click('[data-action="save_as_open"]');
    await page.fill('#save-as-name', 'Night game');
    await page.click('[data-action="save_as_confirm"]');
    await page.waitForFunction(() =>
      window.__calls.some(c => c.name === 'save_layout' && c.args === 'Night game'));
    checks.push('save as');

    // --- The page itself never scrolls at 1280x720 -------------------------
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
