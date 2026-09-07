const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

async function measure(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('#canvas').getBoundingClientRect();
    const errors = [], textRects = [];
    for (const el of document.querySelectorAll('[data-widget], .element-text')) {
      if (!el.getClientRects().length) continue;
      const span = el.querySelector('.widget-text');
      if (!span || !span.textContent.trim()) continue;
      const range = document.createRange(); range.selectNodeContents(span);
      const r = range.getBoundingClientRect(), b = el.getBoundingClientRect();
      const id = el.dataset.widget || el.dataset.element || el.id;
      if (r.left < b.left - 1 || r.right > b.right + 1 || r.top < b.top - 1 || r.bottom > b.bottom + 1)
        errors.push(`${id}: text outside box ${JSON.stringify(r.toJSON())} / ${JSON.stringify(b.toJSON())}`);
      if (r.left < canvas.left + canvas.width * .04 - 1 || r.right > canvas.right - canvas.width * .04 + 1 ||
          r.top < canvas.top + canvas.height * .04 - 1 || r.bottom > canvas.bottom - canvas.height * .04 + 1)
        errors.push(`${id}: outside safe area`);
      textRects.push({id, left:r.left, right:r.right, top:r.top, bottom:r.bottom});
    }
    for (let i = 0; i < textRects.length; i++) for (const b of textRects.slice(i + 1)) {
      const a = textRects[i];
      if (Math.min(a.right,b.right) - Math.max(a.left,b.left) > 1 &&
          Math.min(a.bottom,b.bottom) - Math.max(a.top,b.top) > 1)
        errors.push(`overlap: ${a.id} / ${b.id}`);
    }
    if (document.documentElement.scrollWidth !== innerWidth || document.documentElement.scrollHeight !== innerHeight)
      errors.push('page scrolls');
    return errors;
  });
}

async function main(data) {
  const browser = await chromium.launch({channel:'msedge', headless:true});
  let cases = 0;
  try {
    const page = await browser.newPage();
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.route(/^https?:/, route => route.abort());
    await page.addInitScript(data => {
      window.pywebview = {api:{get_snapshot:() => Promise.resolve(data.games[0]),
        get_layout:() => Promise.resolve(data.layout)}};
    }, data);
    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/spectator/index.html')).href);
    await page.waitForFunction(() => typeof window.applyLayout === 'function');
    await page.evaluate(data => { window.applyLayout(data.layout); window.applyView(data.games[0]); }, data);
    await page.evaluate(() => document.fonts.ready);
    for (const [width,height] of [[1920,1080],[1366,768],[1280,720],[640,360],[390,844]]) {
      await page.setViewportSize({width,height});
      for (const [index, model] of [...data.games,...data.events].entries()) {
        await page.evaluate(model => window.applyView(model), model);
        assert.deepEqual(await measure(page), [], `${width}x${height}, case ${index}`);
        const root = index < data.games.length ? '#game-board' : '#event-board';
        for (const side of ['home','away']) {
          assert.equal(await page.locator(`${root} [data-widget="${side}_score"]`).innerText(), String(model.teams[side].score));
          assert.equal(await page.locator(`${root} [data-widget="${side}_name"]`).innerText(), model.teams[side].name);
        }
        if (index < data.games.length) {
          assert.equal(await page.locator(`${root} [data-widget="game_clock_value"]`).innerText(), model.clocks.game.display);
          assert.equal(await page.locator(`${root} [data-widget="play_clock_value"]`).innerText(), model.clocks.play.display);
        } else {
          assert.equal(await page.locator(`${root} [data-widget="event_clock"]`).innerText(), model.clocks.event.display);
          assert.equal(await page.locator(`${root} [data-widget="warmup"]`).isVisible(), Boolean(model.clocks.event.warmup_display));
        }
        if (process.env.SCOREBOARD_CAPTURE_DIR && width === 1920 && [0,7,8].includes(index)) {
          fs.mkdirSync(process.env.SCOREBOARD_CAPTURE_DIR,{recursive:true});
          await page.screenshot({path:path.join(process.env.SCOREBOARD_CAPTURE_DIR,`stadium-${index}.png`)});
        }
        cases++;
      }
    }
    await page.setViewportSize({width:1920,height:1080});
    for (const model of [data.games[0],data.events[0],data.events[1]]) {
      await page.evaluate(model => window.applyView(model),model);
      await page.evaluate(program => window.applyCutscene({...program,play_id:700,elapsed_ms:0}),data.cutscene);
      await page.evaluate(() => window.endCutscene(700));
      await page.waitForFunction(name => !window.ScoreboardCutscenePlayer.state().playing &&
        document.querySelector('#canvas').dataset.layout === name &&
        !document.querySelector('#canvas').classList.contains('morphing'),data.layout.name);
      assert.deepEqual(await measure(page),[]);
      assert.equal(await page.locator('#game-board').isVisible(),model.lifecycle === 'IN_PROGRESS');
      assert.equal(await page.locator('#canvas').getAttribute('data-layout'),data.layout.name);
    }
    assert.deepEqual(errors,[]);

    const editor = await browser.newPage({viewport:{width:1220,height:780}});
    editor.on('pageerror', e => errors.push(e.message));
    await editor.route(/^https?:/,route => route.abort());
    await editor.addInitScript(data => {
      window.__savedDraft = null;
      window.pywebview = {api:{
        layout_state:() => Promise.resolve(data.state), get_snapshot:() => Promise.resolve(data.games[0]),
        preview_layout:() => Promise.resolve(data.valid),
        save_layout:(name,draft) => {
          window.__savedDraft = structuredClone(draft);
          return Promise.resolve({ok:true,state:data.state});
        }
      }};
    },data);
    await editor.goto(pathToFileURL(path.resolve('src/scoreboard/views/layout/index.html')).href);
    await editor.waitForSelector('[data-select-widget]');
    for (const [screen,id] of [['game','stadium'],['pregame','pregame_stadium'],['halftime','halftime_stadium']]) {
      await editor.click(`[data-screen="${screen}"]`);
      if (!await editor.locator('#presets-gallery-menu').isVisible())
        await editor.click('[data-action="presets_menu"]');
      await editor.click(`#presets-gallery-menu [data-apply-preset="${id}"]`);
      if (await editor.locator('[data-action="replace_draft_confirm"]').isVisible())
        await editor.click('[data-action="replace_draft_confirm"]');
      await editor.waitForSelector('#rail-elements-body [data-select-element="home_panel"]');
      if (await editor.locator('#presets-gallery-menu').isVisible())
        await editor.click('[data-action="presets_menu"]');
    }
    await editor.click('#save');
    await editor.waitForFunction(() => window.__savedDraft !== null);
    assert.deepEqual(errors,[]);
    return {cases,savedDraft:await editor.evaluate(() => window.__savedDraft)};
  } finally { await browser.close(); }
}
let input=''; process.stdin.setEncoding('utf8'); process.stdin.on('data',c => input+=c);
process.stdin.on('end',() => main(JSON.parse(input)).then(result => process.stdout.write(JSON.stringify(result)))
  .catch(error => {console.error(error);process.exitCode=1;}));
