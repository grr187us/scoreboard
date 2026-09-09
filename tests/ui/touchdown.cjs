/* The touchdown's actual ten-second Python program on the offline file page:
 * the five-track claw, the strike, the hold, a live clock push, natural
 * completion, cancellation, replacement, a late join and reduced motion.
 * Optional captures are ignored local visual evidence. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

async function main(data) {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  const errors = [];
  let cases = 0;
  const captureDir = process.env.SCOREBOARD_CAPTURE_DIR;
  if (captureDir) fs.mkdirSync(captureDir, {recursive: true});
  const intro = data.program.intro.duration_ms;
  const total = data.program.duration_ms;
  try {
    const page = await browser.newPage();
    page.on('pageerror', e => errors.push(e.message));
    await page.route(/^https?:/, route => { errors.push('network request'); return route.abort(); });
    await page.addInitScript(data => {
      window.pywebview = {api: {get_snapshot: () => Promise.resolve(data.view),
        get_layout: () => Promise.resolve(data.layout)}};
    }, data);
    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/spectator/index.html')).href);
    await page.waitForFunction(() => document.querySelector('#canvas').dataset.revision === '42');
    await page.evaluate(() => document.fonts.ready);
    // The clock controls JS timers; sample CSS animations explicitly through
    // the browser animation API (CSS timelines do not use the JS fake clock).
    await page.clock.install();
    await page.clock.pauseAt(new Date(Date.now() + 1000));
    let elapsed = 0;
    async function start(extra = {}) {
      elapsed = 0;
      await page.evaluate(program => window.applyCutscene(program), {...data.program, ...extra});
    }
    async function advance(ms) {
      elapsed += ms;
      await page.clock.runFor(ms);
      await page.evaluate(({elapsed, intro}) => {
        const stage = document.querySelector('#cutscene-stage');
        const age = stage.querySelector('.cs-touchdown') ? Math.max(0, elapsed - intro) : elapsed;
        for (const animation of stage.getAnimations({subtree: true})) {
          if (!animation.effect.target.closest('[data-scene]')) continue;
          animation.pause(); animation.currentTime = age;
        }
        if (elapsed >= intro + 600) {
          for (const animation of document.querySelector('#canvas').getAnimations({subtree: true})) {
            if (animation.effect.target.matches('.widget, .element')) animation.finish();
          }
        }
      }, {elapsed, intro});
    }
    async function capture(label) {
      if (captureDir) await page.screenshot({path: path.join(captureDir, label + '.png')});
    }
    async function restored() {
      assert.equal(await page.locator('#canvas').getAttribute('data-layout'), data.layout.name);
      assert.equal(await page.locator('#cutscene-stage').evaluate(e => e.hidden && e.children.length === 0), true);
      assert.equal(await page.locator('#canvas').evaluate(e => e.classList.contains('shake')), false);
      assert.equal(await page.locator('#canvas').evaluate(e => e.style.getPropertyValue('--cs-shake')), '');
    }
    async function checkArt() {
      const m = await page.evaluate(() => {
        const stage = document.querySelector('#cutscene-stage').getBoundingClientRect();
        const text = document.querySelector('.cs-td-headline span');
        const range = document.createRange(); range.selectNodeContents(text);
        const word = range.getBoundingClientRect();
        const crest = document.querySelector('.cs-td-crest').getBoundingClientRect();
        const tag = document.querySelector('.cs-td-subline').getBoundingClientRect();
        const rip = document.querySelector('.cs-td-rip-track').getBoundingClientRect();
        const scene = document.querySelector('#cutscene-stage [data-scene="touchdown"]');
        return {headline: text.textContent, words: scene.textContent,
          opacity: getComputedStyle(text.parentNode).opacity,
          crestOpacity: getComputedStyle(document.querySelector('.cs-td-crest')).opacity,
          tagOpacity: getComputedStyle(document.querySelector('.cs-td-subline')).opacity,
          fits: word.left >= stage.left && word.right <= stage.right && word.top >= stage.top
            && word.bottom < crest.top && word.bottom < tag.top,
          clear: tag.right < rip.left && crest.right < tag.left && crest.bottom <= stage.bottom,
          rips: document.querySelectorAll('.cs-td-rip-track').length,
          stripes: document.querySelectorAll('.cs-td-stripe').length,
          embers: document.querySelectorAll('.cs-td-ember').length,
          scrolls: document.documentElement.scrollWidth > innerWidth || document.documentElement.scrollHeight > innerHeight};
      });
      assert.equal(m.headline, 'TOUCHDOWN');
      assert.equal(m.opacity, '1');
      assert.equal(m.crestOpacity, '1');
      assert.equal(m.tagOpacity, '1');
      assert.equal(m.fits, true, JSON.stringify(m));
      assert.equal(m.clear, true, JSON.stringify(m));
      assert.equal(m.rips, 4);
      assert.equal(m.stripes, 13);
      assert.ok(m.embers >= 30, `embers: ${m.embers}`);
      // No score anywhere in the scene: it stays on the bar underneath.
      assert.ok(!m.words.includes('14'), m.words);
      assert.equal(m.scrolls, false);
    }
    for (const [width, height] of [[1920, 1080], [1366, 768], [640, 360]]) {
      await page.setViewportSize({width, height});
      await start();
      // The strike lands on the board the moment the intro mounts.
      assert.equal(await page.evaluate(() => {
        const canvas = document.querySelector('#canvas');
        return canvas.classList.contains('shake') && Number(canvas.style.getPropertyValue('--cs-shake')) > 1;
      }), true, 'the touchdown strike shakes the board harder than the ordinary claw');
      await advance(500);
      assert.equal(await page.locator('.cs-td-claw-track').count(), 5);
      assert.equal(await page.locator('.cs-td-claw-flash').count(), 1);
      assert.equal(await page.locator('#canvas').evaluate(e => e.classList.contains('shake')), false);
      assert.equal(await page.evaluate(() => {
        const stage = document.querySelector('#cutscene-stage');
        return getComputedStyle(stage).backgroundColor === 'rgba(0, 0, 0, 0)';
      }), true, 'the claw intro must not dim the live scoreboard');
      // Filled tracks must stay separated after their actual SVG transforms:
      // compare cross-sections at the same height rather than envelopes.
      assert.equal(await page.evaluate(() => {
        const paths = [...document.querySelectorAll('.cs-td-claw .cs-field-claw-cut')];
        for (let y = 10; y <= 80; y += 5) {
          const hits = paths.map(p => {
            const inv = p.getCTM().inverse();
            const xs = [];
            for (let x = 0; x < 160; x += .25) {
              const point = new DOMPoint(x, y).matrixTransform(inv);
              if (p.isPointInFill(point)) xs.push(x);
            }
            return xs;
          });
          for (let i = 0; i < 4; i++) if (hits[i].length && hits[i + 1].length &&
            hits[i][hits[i].length - 1] >= hits[i + 1][0]) return false;
        }
        return paths.every(p => p.getBoundingClientRect().width > 0);
      }), true, 'claw tracks never intersect');
      await capture(`claw-${width}`);
      // Every entrance is over by scene time 2.1 s (the tag lands last).
      await advance(3200);
      await checkArt();
      await capture(`hold-${width}`);
      // A live view push must still update the clock without taking down art.
      await page.evaluate(view => window.applyView(view), data.nextView);
      assert.equal(await page.locator('#game-board [data-widget="game_clock_value"]').innerText(), '8:39');
      assert.equal(await page.locator('.cs-td-headline span').innerText(), 'TOUCHDOWN');
      await advance(total - elapsed + 1);
      await restored();
      cases++;
    }
    await start(); await advance(300);
    await page.evaluate(() => window.endCutscene(1)); await advance(301); await restored();
    await start(); await advance(intro + 900);
    await page.evaluate(() => window.endCutscene(1)); await advance(301); await restored();
    await start(); await advance(2000);
    await start({play_id: 2}); await advance(total + 1); await restored();
    // A late join gets the settled hold on its first frame, not the slam.
    await start({play_id: 3, elapsed_ms: total - 2000});
    assert.equal(await page.locator('.cs-touchdown.cs-td-resumed').count(), 1);
    assert.equal(await page.locator('.cs-td-shock').evaluate(e => getComputedStyle(e).display), 'none');
    await checkArt(); await advance(2001); await restored();
    await page.emulateMedia({reducedMotion: 'reduce'});
    await start({play_id: 5}); await advance(intro + 1); await checkArt();
    await advance(total - intro); await restored(); cases++;
    return {cases, errors};
  } finally { await browser.close(); }
}
let input = ''; process.stdin.setEncoding('utf8');
process.stdin.on('data', c => input += c);
process.stdin.on('end', () => main(JSON.parse(input)).then(r => process.stdout.write(JSON.stringify(r)))
  .catch(e => { console.error(e.stack || e); process.exit(1); }));
