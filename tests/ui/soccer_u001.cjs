const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const path = require('node:path');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');
const assert = require('node:assert/strict');

// U-001 at three viewports x four states, against the real bridge (spec
// section 4, design_draft.md 1.1's height budget). Mirrors the shape of
// football's own U-001 checks embedded in tests/ui/keyboard.cjs, but as its
// own script since soccer's states (armed / SHOOTOUT / alert) need seeding
// through the real bridge rather than a synthetic view.
async function main(data) {
  const child = spawn(data.python, ['-u', 'tests/ui/soccer_bridge_server.py'], {stdio:['pipe','pipe','pipe']});
  const waiting = [];
  let stderr = '';
  child.stderr.on('data', chunk => stderr += chunk);
  readline.createInterface({input:child.stdout}).on('line', line => waiting.shift()?.resolve(JSON.parse(line)));
  child.on('exit', code => { if (code) waiting.splice(0).forEach(p => p.reject(new Error(stderr))); });
  const rpc = request => new Promise((resolve,reject) => {
    waiting.push({resolve,reject}); child.stdin.write(JSON.stringify(request)+'\n');
  });
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const evidenceDir = path.resolve('.scratch/soccer-mode/evidence/u001');
  fs.mkdirSync(evidenceDir, {recursive:true});
  const measurements = {};
  try {
    const page = await browser.newPage();
    await page.route(/^https?:/, route => route.abort());
    await page.exposeFunction('testSnapshot', () => rpc({op:'snapshot'}));
    await page.exposeFunction('testCommand', async (...args) => {
      const result = await rpc({op:'command',args}); return result;
    });
    await page.addInitScript(() => {
      window.pywebview = {api:{get_snapshot:()=>window.testSnapshot(),command:(...args)=>window.testCommand(...args),
        trigger_cutscene:()=>Promise.resolve({message:'Cutscene triggered.'})}};
    });
    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/soccer_operator/index.html')).href);
    await page.waitForFunction(() => document.querySelector('#chip-game').textContent.includes('STOPPED'));

    async function render(view) { await page.evaluate(view=>window.applyView(view),view); }
    async function closeEverything() {
      await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
      await page.keyboard.press('Escape');
      await page.evaluate(()=>document.activeElement && document.activeElement.blur());
    }
    const longHome = 'EAGLES OF THE EASTERN CONFERE'.slice(0, 24);
    const longAway = 'TIGERS ATHLETIC ASSOCIATION'.slice(0, 24);

    async function stateIdle() {
      let view = await rpc({op:'seed', seed:{home_name:longHome, away_name:longAway, period:'1st'}});
      view = (await rpc({op:'command', args:['add_stat',{team:'home',stat:'shots',step:1},view.revision]})).view;
      await render(view);
      await closeEverything();
      return view;
    }
    async function stateArmed() {
      await stateIdle();
      await page.locator('#home-arm').click();
      return null;
    }
    async function stateShootout() {
      const view = await rpc({op:'seed', seed:{home_name:longHome, away_name:longAway,
        period:'SHOOTOUT', home_score:1, away_score:1,
        shootout_first_kicker:'home', shootout_kicks:[['home',true],['away',false]]}});
      await render(view);
      await closeEverything();
      return view;
    }
    async function stateAlert() {
      const view = await stateIdle();
      const alerted = Object.assign({}, view, {
        status: {display:'WEATHER', active:true, label:'WEATHER', clock_display:'29:42', clock:{running:true}},
        health: Object.assign({}, view.health, {persistence: {label:'NOT SAVED', saved:false,
          message:'The last save failed: disk full.'}}),
      });
      await render(alerted);
      return alerted;
    }

    const states = {idle: stateIdle, armed: stateArmed, shootout: stateShootout, alert: stateAlert};
    const viewports = [{w:1093,h:614},{w:1180,h:720},{w:1366,h:768}];

    for (const viewport of viewports) {
      await page.setViewportSize({width:viewport.w, height:viewport.h});
      for (const [name, setup] of Object.entries(states)) {
        await setup();
        await page.waitForTimeout(30);
        const metrics = await page.evaluate(() => ({
          scrollHeight: document.documentElement.scrollHeight,
          scrollWidth: document.documentElement.scrollWidth,
          innerHeight: window.innerHeight,
          innerWidth: window.innerWidth,
        }));
        const key = viewport.w+'x'+viewport.h+'-'+name;
        assert.ok(metrics.scrollHeight <= metrics.innerHeight + 1,
          key+': scrollHeight '+metrics.scrollHeight+' > innerHeight '+metrics.innerHeight);
        assert.ok(metrics.scrollWidth <= metrics.innerWidth + 1,
          key+': scrollWidth '+metrics.scrollWidth+' > innerWidth '+metrics.innerWidth);

        const outside = await page.locator('button:visible, input:visible').evaluateAll(nodes=>nodes.filter(n=>{
          const r=n.getBoundingClientRect();
          return r.left<0||r.top<0||r.right>innerWidth+.5||r.bottom>innerHeight+.5;
        }).map(n=>n.id||n.textContent));
        assert.deepEqual(outside, [], key+': controls outside the viewport: '+outside.join(', '));

        // 44px in the panels, 36px in the crowd/period bars (spec 4).
        const panels = await page.locator('.board button:visible').evaluateAll(nodes=>nodes
          .filter(b => b.getBoundingClientRect().height > 0 && b.getBoundingClientRect().height < 44 - 0.5)
          .map(b => b.id || b.textContent));
        const bars = await page.locator('.crowd-bar button:visible, .period-bar button:visible').evaluateAll(nodes=>nodes
          .filter(b => b.getBoundingClientRect().height > 0 && b.getBoundingClientRect().height < 36 - 0.5)
          .map(b => b.id || b.textContent));
        assert.deepEqual(panels, [], key+': panel controls under 44px: '+panels.join(', '));
        assert.deepEqual(bars, [], key+': bar controls under 36px: '+bars.join(', '));

        measurements[key] = metrics;
        await page.screenshot({path: path.join(evidenceDir, key+'.png')});
      }
    }

    return measurements;
  } finally { await browser.close(); child.stdin.end(); }
}
let input='';process.stdin.on('data',chunk=>input+=chunk);
process.stdin.on('end',()=>main(JSON.parse(input||'{}')).then(result=>console.log(JSON.stringify(result))).catch(error=>{console.error(error);process.exitCode=1;}));
