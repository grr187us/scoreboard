const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

async function measure(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('#canvas').getBoundingClientRect();
    const ctx = document.createElement('canvas').getContext('2d');
    // Glyph ink, not the CSS line box: a fitted Impact score deliberately
    // fills its panel while its (invisible) line box overhangs the box.
    function inkRect(el, span) {
      const style = getComputedStyle(span);
      ctx.font = [style.fontStyle, style.fontWeight, style.fontSize, style.fontFamily].join(' ');
      ctx.letterSpacing = style.letterSpacing;
      let text = span.textContent;
      if (style.textTransform === 'uppercase') text = text.toUpperCase();
      const m = ctx.measureText(text);
      const range = document.createRange(); range.selectNodeContents(span);
      const line = range.getBoundingClientRect();
      // A text range's rect is the font's content area, so its top plus the
      // font ascent is the baseline.
      const baseline = line.top + m.fontBoundingBoxAscent;
      return {left: line.left, right: line.right,
              top: baseline - m.actualBoundingBoxAscent, bottom: baseline + m.actualBoundingBoxDescent};
    }
    const errors = [], texts = [];
    for (const el of document.querySelectorAll('[data-widget], .element-text')) {
      if (!el.getClientRects().length) continue;
      const span = el.querySelector('.widget-text');
      if (!span || !span.textContent.trim()) continue;
      const r = inkRect(el, span), b = el.getBoundingClientRect();
      const id = el.dataset.widget || el.dataset.element || el.id;
      if (r.left < b.left-1 || r.right > b.right+1 || r.top < b.top-1 || r.bottom > b.bottom+1)
        errors.push(`${id}: text outside box ${JSON.stringify(r)} / ${JSON.stringify(b.toJSON())}`);
      if (r.left < canvas.left+canvas.width*.04-1 || r.right > canvas.right-canvas.width*.04+1 ||
          r.top < canvas.top+canvas.height*.04-1 || r.bottom > canvas.bottom-canvas.height*.04+1)
        errors.push(`${id}: text outside safe area`);
      texts.push({id,left:r.left,right:r.right,top:r.top,bottom:r.bottom});
    }
    for (let i=0; i<texts.length; i++) for (const b of texts.slice(i+1)) {
      const a=texts[i];
      if (Math.min(a.right,b.right)-Math.max(a.left,b.left)>1 &&
          Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1) errors.push(`${a.id} overlaps ${b.id}`);
    }
    if (document.documentElement.scrollWidth !== innerWidth || document.documentElement.scrollHeight !== innerHeight)
      errors.push('page scrolls');
    return errors;
  });
}

async function main(data) {
  const browser = await chromium.launch({channel:'msedge',headless:true});
  let cases=0;
  try {
    const page = await browser.newPage();
    const errors=[]; page.on('pageerror',e=>errors.push(e.message));
    await page.route(/^https?:/,route=>route.abort());
    await page.addInitScript(data=>{
      window.pywebview={api:{get_snapshot:()=>Promise.resolve(data.models[0]),
                            get_layout:()=>Promise.resolve(data.layout)}};
    },data);
    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/spectator/index.html')).href);
    await page.waitForFunction(()=>typeof window.applyView==='function');
    // Bug 2: the very first render on the page is the only place the game
    // clock's fit can race the Grid preset's lazily-loaded Graduate face
    // (later renders find it already loaded). Apply the stopped 12:00 clock
    // here, before anything else has touched the page, then require the fit
    // to be correct once fonts have settled -- with no further model push,
    // since a real spectator sees the clock at rest for a while before it
    // ever starts.
    await page.evaluate(data=>{window.applyLayout(data.layout);window.applyView(data.clock_start);},data);
    await page.evaluate(()=>document.fonts.ready);
    assert.deepEqual(await measure(page),[],'game clock at rest before it has ever started');
    await page.evaluate(data=>{window.applyLayout(data.layout);window.applyView(data.models[0]);},data);
    const value=id=>page.locator(`#game-board [data-widget="${id}"] .widget-text`).textContent();
    for (const [width,height] of [[1920,1080],[1366,768],[1280,720],[640,360],[390,844]]) {
      await page.setViewportSize({width,height});
      for (const [index,model] of data.models.entries()) {
        await page.evaluate(model=>window.applyView(model),model);
        assert.deepEqual(await measure(page),[],`${width}x${height}, case ${index}`);
        assert.equal(await value('quarter'),model.quarter);
        assert.equal(await value('down'),model.football.down_display);
        assert.equal(await value('distance'),model.football.distance_value_display);
        assert.equal(await value('ball_on'),model.football.ball_on_value_display);
        for (const side of ['home','away']) {
          assert.equal(await value(`${side}_timeouts`),model.football[`${side}_timeouts_dots`]);
          assert.equal(await value(`${side}_score`),String(model.teams[side].score));
          assert.equal(await value(`${side}_name`),model.teams[side].name);
        }
        assert.equal(await value('game_clock_value'),model.clocks.game.display);
        assert.equal(await value('play_clock_value'),model.clocks.play.display);
        if (process.env.SCOREBOARD_CAPTURE_DIR && width===1920 && [0,4,6].includes(index)) {
          fs.mkdirSync(process.env.SCOREBOARD_CAPTURE_DIR,{recursive:true});
          await page.screenshot({path:path.join(process.env.SCOREBOARD_CAPTURE_DIR,`grid-${index}.png`)});
        }
        cases++;
      }
    }
    // Layout-only changes immediately rebind the existing model; no next tick.
    await page.setViewportSize({width:1920,height:1080});
    // Returning from an event screen fits names on the very first game frame.
    if (process.env.SCOREBOARD_CAPTURE_DIR) {
      for (const [name, model] of [['pregame', data.pregame], ['halftime', data.halftime]]) {
        await page.evaluate(model=>window.applyView(model), model);
        await page.screenshot({path:path.join(process.env.SCOREBOARD_CAPTURE_DIR,`grid-${name}.png`)});
      }
    }
    await page.evaluate(data=>{
      window.applyView({...data.models[1],lifecycle:'PRE_GAME'});
      window.applyView(data.models[1]);
    },data);
    assert.deepEqual(await measure(page),[]);
    const fittedName=page.locator('#game-board [data-widget="home_name"] .widget-text');
    assert.notEqual(await fittedName.evaluate(e=>e.style.fontSize),'');
    await page.evaluate(layout=>{
      const spaced=structuredClone(layout);
      spaced.widgets.home_name.letter_spacing=.2;
      spaced.widgets.home_name.padding=.005;
      window.applyLayout(spaced);
    },data.layout);
    assert.deepEqual(await measure(page),[]);
    await page.evaluate(layout=>window.applyLayout(layout),data.layout);
    await page.evaluate(model=>window.applyView(model),data.models[0]);
    assert.equal(await fittedName.evaluate(e=>e.style.fontSize),'');
    assert.deepEqual(await measure(page),[]);
    await page.evaluate(data=>{window.applyView(data.models[0]);window.applyLayout(data.classic);},data);
    assert.equal(await value('quarter'),'3rd Quarter');
    assert.equal(await value('distance'),'& 7');
    await page.evaluate(layout=>window.applyLayout(layout),data.layout);
    assert.equal(await value('quarter'),'3rd');
    assert.equal(await value('distance'),'7');
    // A partial snapshot clears optional formats instead of retaining stale text.
    await page.evaluate(()=>window.ScoreboardBoard.applyModel(document.querySelector('#game-board'),{}));
    assert.equal(await value('distance'),'');
    assert.equal(await page.locator('#game-board [data-widget="home_timeouts"]').isVisible(),false);

    const editor=await browser.newPage({viewport:{width:1220,height:780}});
    editor.on('pageerror',e=>errors.push(e.message));
    await editor.route(/^https?:/,route=>route.abort());
    await editor.addInitScript(data=>{
      window.__savedDraft=null;
      window.pywebview={api:{layout_state:()=>Promise.resolve(data.state),
        get_snapshot:()=>Promise.resolve(data.models[0]),preview_layout:()=>Promise.resolve(data.valid),
        save_layout:(name,draft)=>{window.__savedDraft=structuredClone(draft);return Promise.resolve({ok:true,state:data.state});}}};
    },data);
    await editor.goto(pathToFileURL(path.resolve('src/scoreboard/views/layout/index.html')).href);
    await editor.waitForSelector('[data-select-widget]');
    await editor.click('[data-action="presets_menu"]');
    await editor.click('#presets-gallery-menu [data-apply-preset="grid"]');
    if (await editor.locator('[data-action="replace_draft_confirm"]').isVisible())
      await editor.click('[data-action="replace_draft_confirm"]');
    if (await editor.locator('#presets-gallery-menu').isVisible()) await editor.click('[data-action="presets_menu"]');
    for (const [id,format,standard,formatted] of [
      ['quarter','ordinal','3rd Quarter','3rd'], ['distance','value','& 7','7'],
      ['home_timeouts','dots','TO 2','● ● ○'], ['down','ordinal','2nd','2nd'],
      ['ball_on','value','AWAY 35','35']]) {
      await editor.click(`[data-select-widget="${id}"]`);
      await editor.selectOption('#prop-display_format','default');
      assert.equal(await editor.locator(`#game-board [data-widget="${id}"] .widget-text`).textContent(),standard);
      await editor.selectOption('#prop-display_format',format);
      assert.equal(await editor.locator(`#game-board [data-widget="${id}"] .widget-text`).textContent(),formatted);
    }
    await editor.click('[data-select-widget="home_score"]');
    assert.equal(await editor.locator('#field-display_format').isVisible(),false);
    await editor.click('[data-select-widget="home_name"]');
    assert.equal(await editor.isChecked('#prop-fit_text'),true);
    await editor.uncheck('#prop-fit_text');
    await editor.check('#prop-fit_text');
    await editor.click('#save');
    await editor.waitForFunction(()=>window.__savedDraft!==null);
    assert.deepEqual(errors,[]);
    return {cases,savedDraft:await editor.evaluate(()=>window.__savedDraft)};
  } finally {await browser.close();}
}
let input='';process.stdin.setEncoding('utf8');process.stdin.on('data',c=>input+=c);
process.stdin.on('end',()=>main(JSON.parse(input)).then(result=>process.stdout.write(JSON.stringify(result)))
  .catch(error=>{console.error(error);process.exitCode=1;}));
