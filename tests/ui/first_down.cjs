/* Actual five-second Python program, offline file page, normal and reduced
 * motion. Optional captures are ignored local visual evidence. */
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
      await page.evaluate(({elapsed,intro}) => {
        const stage = document.querySelector('#cutscene-stage');
        const age = stage.querySelector('.cs-firstdown') ? Math.max(0,elapsed-intro) : elapsed;
        for (const animation of stage.getAnimations({subtree:true})) {
          if (!animation.effect.target.closest('[data-scene]')) continue;
          animation.pause(); animation.currentTime = age;
        }
        // At these sample times the 600 ms board morph has completed.
        if (elapsed >= intro + 600) {
          for (const animation of document.querySelector('#canvas').getAnimations({subtree:true})) {
            if (animation.effect.target.matches('.widget, .element')) animation.finish();
          }
        }
      }, {elapsed,intro:data.program.intro.duration_ms});
    }
    async function capture(label) {
      if (captureDir) await page.screenshot({path: path.join(captureDir, label + '.png')});
    }
    async function restored() {
      assert.equal(await page.locator('#canvas').getAttribute('data-layout'), data.layout.name);
      assert.equal(await page.locator('#cutscene-stage').evaluate(e => e.hidden && e.children.length === 0), true);
      assert.equal(await page.locator('#canvas').evaluate(e => e.classList.contains('shake')), false);
    }
    async function checkArt() {
      const measurements = await page.evaluate(() => {
        const stage = document.querySelector('#cutscene-stage').getBoundingClientRect();
        const text = document.querySelector('.cs-fd-headline span');
        const range = document.createRange(); range.selectNodeContents(text);
        const word = range.getBoundingClientRect();
        const marker = document.querySelector('.cs-fd-marker').getBoundingClientRect();
        const canvas = document.querySelector('.cs-fd-grass');
        return {headline: text.textContent, opacity: getComputedStyle(text.parentNode).opacity,
          fits: word.left >= stage.left && word.right < marker.left && word.bottom < stage.bottom,
          links: document.querySelectorAll('.cs-fd-link').length,
          drawn: canvas.width === 1600 && canvas.getContext('2d').getImageData(500,500,1,1).data[3] === 255,
          scrolls: document.documentElement.scrollWidth > innerWidth || document.documentElement.scrollHeight > innerHeight};
      });
      assert.equal(measurements.headline, 'FIRST DOWN');
      assert.equal(measurements.opacity, '1');
      assert.equal(measurements.fits, true, JSON.stringify(measurements));
      assert.equal(measurements.links, 36);
      assert.equal(measurements.drawn, true);
      assert.equal(measurements.scrolls, false);
    }
    for (const [width,height] of [[1920,1080], [1366,768], [640,360]]) {
      await page.setViewportSize({width,height});
      await start();
      await advance(500);
      assert.equal(await page.locator('.cs-field-claw-track').count(), 4);
      assert.equal(await page.evaluate(() => {
        const stage = document.querySelector('#cutscene-stage');
        const surface = document.querySelector('.cs-field-claw-surface');
        return getComputedStyle(stage).backgroundColor === 'rgba(0, 0, 0, 0)' &&
          getComputedStyle(surface).backgroundColor === 'rgba(0, 0, 0, 0)';
      }), true, 'the claw intro must not dim the live scoreboard');
      // Filled paths must stay separated after their actual SVG transforms.
      assert.equal(await page.evaluate(() => {
        const paths = [...document.querySelectorAll('.cs-field-claw-cut')];
        const boxes = paths.map(p => p.getBoundingClientRect());
        // Their envelopes overlap diagonally; compare cross-sections in SVG
        // space at the same height rather than rejecting valid diagonals.
        for (let y=15; y<=75; y+=5) {
          const hits = paths.map(p => {
            const inv = p.getCTM().inverse();
            const xs = [];
            for (let x=0; x<160; x+=.25) {
              const point = new DOMPoint(x,y).matrixTransform(inv);
              if (p.isPointInFill(point)) xs.push(x);
            }
            return xs;
          });
          for (let i=0;i<3;i++) if (hits[i].length && hits[i+1].length &&
            hits[i][hits[i].length-1] >= hits[i+1][0]) return false;
        }
        return boxes.every(b=>b.width>0);
      }), true, 'claw tracks never intersect');
      await capture(`claw-${width}`);
      await advance(2300);
      await checkArt();
      await capture(`hold-${width}`);
      // A live view push must still update the clock without taking down art.
      await page.evaluate(view => window.applyView(view), data.nextView);
      assert.equal(await page.locator('#game-board [data-widget="game_clock_value"]').innerText(), '8:39');
      await advance(2201);
      await restored();
      cases++;
    }
    await start(); await advance(300);
    await page.evaluate(() => window.endCutscene(1)); await advance(301); await restored();
    await start(); await advance(2500);
    await page.evaluate(() => window.endCutscene(1)); await advance(301); await restored();
    await start(); await advance(2000);
    await start({play_id:2}); await advance(5001); await restored();
    await start({play_id:3, elapsed_ms:4200});
    await checkArt(); await advance(801); await restored();
    // GPU/canvas setup can fail independently of the rest of the webview.
    // The CSS ground and headline must still mount and the board must return.
    await page.evaluate(program => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = () => { throw new Error('injected 2D failure'); };
      try { window.applyCutscene({...program,play_id:4,elapsed_ms:2000}); }
      finally { HTMLCanvasElement.prototype.getContext = original; }
    },data.program);
    assert.equal(await page.locator('.cs-fd-headline').innerText(), 'FIRST DOWN');
    assert.equal(await page.locator('.cs-fd-turf').evaluate(e => getComputedStyle(e).backgroundColor), 'rgb(28, 61, 34)');
    await advance(3001); await restored();
    await page.emulateMedia({reducedMotion:'reduce'});
    await start({play_id:5}); await advance(1601); await checkArt();
    await advance(3400); await restored(); cases++;
    return {cases,errors};
  } finally { await browser.close(); }
}
let input=''; process.stdin.setEncoding('utf8');
process.stdin.on('data',c=>input+=c);
process.stdin.on('end',()=>main(JSON.parse(input)).then(r=>process.stdout.write(JSON.stringify(r)))
  .catch(e=>{ console.error(e.stack || e); process.exit(1); }));
