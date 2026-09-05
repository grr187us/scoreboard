const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

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
    assert.equal(await page.locator('.home .score').textContent(), '199');
    assert.equal(await page.locator('button,input,dialog,[data-command]').count(), 0);
    for (const [width, height] of [[1280,720], [1366,768], [1920,1080], [390,844]]) {
      await page.setViewportSize({width,height});
      for (const [index, model] of [...data.games, data.pregame, ...data.events].entries()) {
        await page.evaluate(model => window.applyView(model), model);
        const metrics = await page.evaluate(() => {
          const canvas = document.querySelector('#canvas').getBoundingClientRect();
          const safe = document.querySelector('#safe-area').getBoundingClientRect();
          const errors = [];
          const rects = [];
          for (const element of document.querySelectorAll('p')) {
            if (!element.getClientRects().length || !element.textContent.trim()) continue;
            const range = document.createRange(); range.selectNodeContents(element);
            const text = range.getBoundingClientRect();
            const box = element.getBoundingClientRect();
            if (text.left < safe.left-.5 || text.right > safe.right+.5 ||
                text.top < safe.top-.5 || text.bottom > safe.bottom+.5) errors.push('outside safe area: '+element.className);
            if (text.left < box.left-.5 || text.right > box.right+.5 ||
                text.top < box.top-.5 || text.bottom > box.bottom+.5) errors.push('text outside box: '+element.className+' text '+JSON.stringify(text.toJSON())+' box '+JSON.stringify(box.toJSON()));
            rects.push({name:element.className, left:text.left,right:text.right,top:text.top,bottom:text.bottom});
          }
          for (let i=0;i<rects.length;i++) for (let j=i+1;j<rects.length;j++) {
            const a=rects[i], b=rects[j];
            if (Math.min(a.right,b.right)-Math.max(a.left,b.left)>.5 &&
                Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>.5) errors.push('overlap: '+a.name+' / '+b.name);
          }
          return { errors, canvas: {width:canvas.width,height:canvas.height,x:canvas.x,y:canvas.y},
            scroll: [document.documentElement.scrollWidth,document.documentElement.scrollHeight],
            viewport:[innerWidth,innerHeight], inset: safe.left-canvas.left };
        });
        assert.deepEqual(metrics.errors, [], `${width}x${height} case ${index}: ${JSON.stringify(metrics)}`);
        assert.deepEqual(metrics.scroll, metrics.viewport);
        assert.ok(Math.abs(metrics.canvas.width/metrics.canvas.height-16/9)<.001);
        if (index >= 5) {
          assert.equal(await page.locator('#event-phase').textContent(), model.clocks.event.phase);
          assert.equal(await page.locator('#warmup').isVisible(), Boolean(model.clocks.event.warmup_follows));
          assert.equal(await page.locator('#game-board').isVisible(), false);
        }
        if (evidence && [3,4,5,7].includes(index)) {
          fs.mkdirSync(evidence,{recursive:true});
          await page.screenshot({path:path.join(evidence,`${width}x${height}-${index}.png`)});
          observations.push({width,height,index,...metrics});
        }
        cases++;
      }
    }
    for (const [model, expected] of [[data.zero,'0.0'],[data.blank,'—']]) {
      await page.evaluate(model => window.applyView(model), model);
      assert.equal(await page.locator('.play-clock').textContent(), expected);
      assert.equal(await page.locator('#play-label').isVisible(), true);
    }
    await page.evaluate(model => window.applyView(model), data.runningGame);
    assert.equal(await page.locator('#game-clock').evaluate(el => el.classList.contains('running-game')), true);
    assert.equal(await page.locator('#play-clock').evaluate(el => el.classList.contains('running-play')), false);
    await page.evaluate(model => window.applyView(model), data.runningPlay);
    assert.equal(await page.locator('#game-clock').evaluate(el => el.classList.contains('running-game')), false);
    assert.equal(await page.locator('#play-clock').evaluate(el => el.classList.contains('running-play')), true);
    assert.equal(await page.locator('.quarter').textContent(), '4th Quarter');
    await page.evaluate(() => {
      window.originalBind = window.ScoreboardRender.bindFields;
      window.ScoreboardRender.bindFields = () => { throw new Error('injected'); };
    });
    await page.evaluate(model => window.applyView(model), data.zero); // must not throw
    await page.evaluate(() => { window.ScoreboardRender.bindFields = window.originalBind; });
    await page.evaluate(model => window.applyView(model), data.zero);
    assert.equal(await page.locator('.play-clock').textContent(), '0.0');
    if (evidence) fs.writeFileSync(path.join(evidence,'measurements.json'),JSON.stringify(observations,null,2));
    return {cases};
  } finally { await browser.close(); }
}
let input=''; process.stdin.on('data', chunk => input+=chunk);
process.stdin.on('end', () => main(JSON.parse(input)).then(result => console.log(JSON.stringify(result))).catch(error => {console.error(error);process.exitCode=1;}));
