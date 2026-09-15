/* Registry isolation: the shared layout editor (`views/layout/*`, unchanged)
 * opened against a soccer-shaped `layout_state()` must show only soccer
 * widgets -- never a football one -- and must build its preview board with
 * `Board.build(root, 'soccer')` (spec section 5.3: "a soccer session never
 * sees football widgets or writes <root>/layouts.json").
 *
 * The stub bridge below answers with the real payload
 * `PresentationLayouts(soccer_paths, layout_module=soccer_layout).state()`
 * produced (see test_soccer_editor_browser.py), exactly like
 * `layout_editor.cjs` does for football's own state.
 */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

//: Labels that must never appear once the editor is showing soccer's
//: registry (spec section 5.1's soccer widgets are a disjoint id/label set).
const FOOTBALL_ONLY_LABELS = [
  'Quarter', 'Down', 'Distance to go', 'Play clock label', 'Play clock',
  'Ball on', 'Home timeouts', 'Away timeouts', 'Possession',
];

async function main(data) {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const checks = [];
  try {
    const page = await browser.newPage();
    await page.setViewportSize({ width: 1220, height: 780 });
    await page.route(/^https?:/, route => route.abort());

    await page.addInitScript(payload => {
      window.pywebview = {
        api: {
          layout_state: () => Promise.resolve(payload.state),
          get_snapshot: () => Promise.resolve(payload.snapshot),
          preview_layout: () => Promise.resolve(payload.validPreview),
          clamp_layout: () => Promise.resolve(payload.clamped),
          reset_widget: () => Promise.resolve(payload.resetWidget),
          save_layout: () => Promise.resolve(payload.saved),
          select_layout: () => Promise.resolve(payload.state),
          delete_layout: () => Promise.resolve(payload.state),
          rename_layout: () => Promise.resolve(payload.state),
          duplicate_layout: () => Promise.resolve(payload.state),
          reset_layout: () => Promise.resolve(payload.state),
        }
      };
    }, data);

    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/layout/index.html')).href);
    await page.waitForFunction(() => document.querySelectorAll('[data-select-widget]').length > 0);

    // --- Only soccer widgets are listed, none of football's -----------------
    const listed = await page.$$eval('[data-select-widget]', els => els.map(e => e.textContent));
    assert.equal(listed.length, data.state.widgets.length);
    for (const descriptor of data.state.widgets) {
      assert.ok(listed.some(text => text.startsWith(descriptor.label)), `missing ${descriptor.label}`);
    }
    for (const forbidden of FOOTBALL_ONLY_LABELS) {
      assert.ok(!listed.some(text => text.startsWith(forbidden)), `football label leaked: ${forbidden}`);
    }
    checks.push('soccer widget list only');

    // A soccer-only widget id (e.g. "period") is selectable and fills the
    // property panel from the soccer descriptor's own default.
    await page.click('[data-select-widget="period"]');
    const font = await page.evaluate(() => document.getElementById('prop-font_family').value);
    assert.equal(font, 'varsity');
    checks.push('soccer widget selectable');

    // --- The preview board is rebuilt with the soccer registry once the ----
    // editor switches screens (layout.js's own `switchScreen` -- unchanged,
    // spec section 5.3 -- calls `Board.build(boardRoot, descriptor.kind)`
    // whenever the screen id actually changes; its one-time startup literal
    // `Board.build(boardRoot, 'game')` runs before `layout_state()` resolves
    // and is never itself kind-aware, so the very first paint of the "Game"
    // screen briefly uses football's registry until any screen switch
    // happens -- see the report for this finding). Switching to Pre-game and
    // back to Game is exactly what an operator opening the Pre-game/Halftime
    // tabs does, and it leaves the board on the soccer registry for good.
    await page.click('[data-screen="pregame"]');
    await page.click('[data-screen="game"]');
    const boardKind = await page.evaluate(() => document.getElementById('game-board').dataset.boardKind);
    assert.equal(boardKind, 'soccer');
    checks.push('preview board kind is soccer after a screen switch');

    // The preview board actually places soccer widgets (e.g. period), never
    // a football-only one (e.g. quarter).
    const hasPeriodWidget = await page.evaluate(() => Boolean(document.querySelector('#game-board [data-widget="period"]')));
    const hasQuarterWidget = await page.evaluate(() => Boolean(document.querySelector('#game-board [data-widget="quarter"]')));
    assert.equal(hasPeriodWidget, true);
    assert.equal(hasQuarterWidget, false);
    checks.push('preview board draws soccer widgets only');

    // No page-level scroll (same house rule the football editor test checks).
    const scroll = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.scrollHeight]);
    const viewport = await page.evaluate(() => [innerWidth, innerHeight]);
    assert.ok(scroll[0] <= viewport[0] + 1 && scroll[1] <= viewport[1] + 400, `unexpected scroll ${scroll} vs ${viewport}`);
    checks.push('no unexpected page scroll');

    return { checks };
  } finally { await browser.close(); }
}
let input = ''; process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => main(JSON.parse(input)).then(result => console.log(JSON.stringify(result))).catch(error => { console.error(error); process.exitCode = 1; }));
