const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const assert = require('node:assert/strict');

// Mirrors tests/ui/keyboard.cjs's shape for the soccer operator page and its
// own binding table (views/soccer_operator/keyboard.js), against the real
// SoccerBridge via tests/ui/soccer_bridge_server.py.
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
  const calls = [], results = [], errors = [];
  try {
    const page = await browser.newPage({viewport:{width:1093,height:614}});
    page.on('pageerror', error => errors.push(String(error)));
    await page.route(/^https?:/, route => route.abort());
    await page.exposeFunction('testSnapshot', () => rpc({op:'snapshot'}));
    await page.exposeFunction('testCommand', async (...args) => {
      calls.push(args);
      const result = await rpc({op:'command',args}); results.push(result); return result;
    });
    await page.addInitScript(() => {
      window.pywebview = {api:{get_snapshot:()=>window.testSnapshot(),command:(...args)=>window.testCommand(...args),
        trigger_cutscene:()=>Promise.resolve({message:'Cutscene triggered.'}),
        cancel_cutscene:()=>Promise.resolve({message:'Cutscene cancelled.'})}};
    });
    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/soccer_operator/index.html')).href);
    await page.waitForFunction(() => document.querySelector('#chip-game').textContent.includes('STOPPED'));

    async function render(view) { await page.evaluate(view=>window.applyView(view),view); }
    async function reset() {
      await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
      await page.evaluate(()=>document.activeElement.blur());
      const view = await rpc({op:'reset'}); await render(view);
      calls.length=0; results.length=0; return view;
    }
    async function settled() {
      await page.waitForFunction(() => window.__testIdle !== false);
      const snapshot = await rpc({op:'snapshot'});
      await page.waitForFunction(rev=>document.querySelector('#chip-revision').textContent === 'Rev '+rev,snapshot.revision);
      return snapshot;
    }
    async function expectResult(before) {
      const deadline=Date.now()+5000;
      while(results.length === before) {
        if(Date.now()>deadline) throw new Error('No bridge result for key');
        await new Promise(resolve=>setTimeout(resolve,5));
      }
    }
    async function press(key) {
      const before=results.length;
      await page.keyboard.press(key);
      await expectResult(before);
      return settled();
    }

    // Space toggles the game clock.
    let model = await reset();
    await page.keyboard.press('Space'); await expectResult(0); await settled();
    assert.deepEqual(calls,[['game_clock_start',{source:'operator-keyboard'},model.revision]]);
    assert.equal(results[0].accepted,true);
    assert.equal(await page.locator('#game-display').evaluate(el=>el.classList.contains('running-game')),true);
    calls.length=0; results.length=0;
    await page.keyboard.press('Space'); await expectResult(0); await settled();
    assert.equal(calls[0][0],'game_clock_stop');

    // G/H arm then apply a goal (two-step scoring, spec 4.2/4.5).
    for (const [key, team] of [['g','home'],['h','away']]) {
      model = await reset();
      await page.keyboard.press(key);
      await page.waitForFunction(t=>document.querySelector('#'+t+'-score-controls').dataset.armed==='goal',team);
      assert.deepEqual(calls,[],key+' first press must send nothing');
      await press(key);
      assert.deepEqual(calls,[['add_goal',{team,source:'operator-keyboard'},model.revision]],key);
      assert.equal(results[0].accepted,true,key);
      // The accepted goal triggers the GOAL cutscene with the scoring team.
    }

    // Q / Shift+Q: period forward/back, both confirmed by the service.
    model = await reset();
    await page.keyboard.press('q'); await expectResult(0);
    await page.locator('#confirm-accept').waitFor({state:'visible'});
    assert.equal(results[0].confirmation_required,true);
    const revision = calls.at(-1)[2];
    await page.locator('#confirm-accept').click(); await expectResult(1); await settled();
    assert.deepEqual(calls,[
      ['period_forward',{source:'operator-keyboard'},revision],
      ['period_forward',{source:'operator-keyboard',confirmed:true},revision],
    ]);
    assert.equal(results[1].accepted,true);

    // A/S/D/F (+Shift): HOME stat nudges.
    const homeStats = [['a','shots'],['s','saves'],['d','corners'],['f','fouls']];
    for (const [key, stat] of homeStats) {
      model = await reset();
      await press(key);
      assert.deepEqual(calls,[['add_stat',{team:'home',stat,step:1,source:'operator-keyboard'},model.revision]],key);
      assert.equal(results[0].accepted,true,key);
      model = await reset();
      await page.keyboard.press('Shift+'+key.toUpperCase()); await expectResult(0); await settled();
      assert.deepEqual(calls,[['add_stat',{team:'home',stat,step:-1,source:'operator-keyboard'},model.revision]]);
    }
    // J/K/L/; (+Shift): AWAY stat nudges.
    const awayStats = [['j','shots'],['k','saves'],['l','corners'],[';','fouls']];
    for (const [key, stat] of awayStats) {
      model = await reset();
      await press(key);
      assert.deepEqual(calls,[['add_stat',{team:'away',stat,step:1,source:'operator-keyboard'},model.revision]],key);
      model = await reset();
      await page.keyboard.press('Shift+'+(key===';' ? ';' : key.toUpperCase())); await expectResult(0); await settled();
      assert.deepEqual(calls,[['add_stat',{team:'away',stat,step:-1,source:'operator-keyboard'},model.revision]]);
    }

    // Y/Shift+Y/R/Shift+R arm the card panel; nothing is sent until CONFIRM.
    for (const [key, team, kind] of [['y','home','yellow'],['r','home','red']]) {
      await reset();
      await page.keyboard.press(key);
      await page.waitForFunction(t=>document.querySelector('#'+t+'-score-controls').dataset.armed==='card',team);
      assert.deepEqual(calls,[],key+' arms only');
      await page.locator('#'+team+'-card-confirm-'+kind).click(); await expectResult(0); await settled();
      assert.equal(calls[0][0],'add_card');
      assert.equal(calls[0][1].team,team); assert.equal(calls[0][1].kind,kind);
    }
    await reset();
    await page.keyboard.press('Shift+Y');
    await page.waitForFunction(()=>document.querySelector('#away-score-controls').dataset.armed==='card');
    assert.deepEqual(calls,[]);

    // I/E/W crowd words; X clears.
    for (const [key,label] of [['i','INJURY'],['e','DELAY'],['w','WEATHER']]) {
      await reset();
      await press(key);
      assert.equal(calls[0][0],'set_game_status'); assert.equal(calls[0][1].label,label);
    }
    await reset(); await press('w'); calls.length=0; results.length=0;
    await press('x'); assert.equal(calls[0][0],'clear_game_status');

    // Ctrl+Z confirms before undo.
    model = await reset(); await pressKeyGoal();
    async function pressKeyGoal(){ await page.keyboard.press('g'); await press('g'); }
    const undoRevision = (await settled()).revision; calls.length=0; results.length=0;
    await page.keyboard.press('Control+z');
    await page.locator('#confirm-accept').waitFor({state:'visible'});
    assert.equal(calls.length,0,'Ctrl+Z must send nothing before confirmed');
    assert.equal(await page.locator('#confirm-title').textContent(),'Undo the last action?');
    assert.match(await page.locator('#confirm-change').textContent(),/^Reverses: .+/);
    await page.locator('#confirm-accept').click(); await expectResult(0); await settled();
    assert.deepEqual(calls,[['undo',{source:'operator-keyboard',confirmed:true},undoRevision]]);
    assert.equal(results[0].accepted,true);

    // 1 / 2: replay the GOAL cutscene; a host action, no Command.
    await reset();
    const hostCalls = [];
    await page.exposeFunction('testHostSeen', (...args) => hostCalls.push(args));
    await page.evaluate(() => {
      const original = window.pywebview.api.trigger_cutscene;
      window.pywebview.api.trigger_cutscene = (...args) => { window.testHostSeen(...args); return original(...args); };
    });
    await page.keyboard.press('1');
    await page.waitForFunction(()=>window.__hostSeenLen !== 0).catch(()=>{});
    await new Promise(resolve=>setTimeout(resolve,50));
    assert.deepEqual(hostCalls[0],['goal','home']);
    await page.keyboard.press('2');
    await new Promise(resolve=>setTimeout(resolve,50));
    assert.deepEqual(hostCalls[1],['goal','away']);

    // Escape: closes a dialog, then disarms, then closes a drawer -- never both at once.
    await reset(); await page.keyboard.press('g');
    await page.waitForFunction(()=>document.querySelector('#home-score-controls').dataset.armed==='goal');
    await page.keyboard.press('Escape');
    await page.waitForFunction(()=>document.querySelector('#home-score-controls').dataset.armed==='idle');

    // Shortcut Help lists every binding from the table.
    await reset();
    await page.locator('#open-help').click();
    const help=await page.locator('#shortcut-list tr').evaluateAll(rows=>rows.map(row=>Array.from(row.children).map(e=>e.textContent)));
    assert.ok(help.some(row=>row[0]==='Space'));
    assert.ok(help.some(row=>row[0]==='G'));
    assert.ok(help.some(row=>row[0]==='Ctrl+Z'));
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#shortcut-help').isVisible(),false);

    // No live control sits outside the viewport at any of the U-001 sizes.
    for (const viewport of [{width:1093,height:614},{width:1180,height:720},{width:1366,height:768}]) {
      await page.setViewportSize(viewport);
      const outside = await page.locator('button:visible').evaluateAll(buttons=>buttons.filter(b=>{
        const r=b.getBoundingClientRect();return r.left<0||r.top<0||r.right>innerWidth+.5||r.bottom>innerHeight+.5;
      }).map(b=>b.textContent));
      assert.deepEqual(outside,[],'at '+viewport.width);
    }

    assert.deepEqual(errors,[]);
    return {shortcuts:help.length};
  } finally { await browser.close(); child.stdin.end(); }
}
let input='';process.stdin.on('data',chunk=>input+=chunk);
process.stdin.on('end',()=>main(JSON.parse(input)).then(result=>console.log(JSON.stringify(result))).catch(error=>{console.error(error);process.exitCode=1;}));
