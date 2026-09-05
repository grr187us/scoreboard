const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const assert = require('node:assert/strict');

async function main(data) {
  const child = spawn(data.python, ['-u', 'tests/ui/bridge_server.py'], {stdio:['pipe','pipe','pipe']});
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
        open_test_window:()=>Promise.resolve({message:'Test spectator window opened.'})}};
    });
    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/operator/index.html')).href);
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
      // Barrier: the real bridge request completes before checking its rendered revision.
      const snapshot = await rpc({op:'snapshot'});
      await page.waitForFunction(rev=>document.querySelector('#chip-revision').textContent === 'Rev '+rev,snapshot.revision);
      return snapshot;
    }
    async function press(key) {
      const before=results.length;
      await page.keyboard.press(key);
      await expectResult(before);
      return settled();
    }
    async function expectResult(before) {
      const deadline=Date.now()+5000;
      while(results.length === before) {
        if(Date.now()>deadline) throw new Error('No bridge result for key');
        await new Promise(resolve=>setTimeout(resolve,5));
      }
    }
    const map = [
      ['Space','game_clock_start',{},'Space','Game clock Start / Stop'],
      ['2','play_clock_preset',{seconds:25},'2','Load play clock 25 (stopped)'],
      ['4','play_clock_preset',{seconds:40},'4','Load play clock 40 (stopped)'],
      ['p','play_clock_start',{},'P','Start play clock'],
      ['s','play_clock_stop',{},'S','Stop play clock'],
      ['q','quarter_forward',{},'Q','Quarter forward'],
      ['Shift+Q','quarter_back',{},'Shift+Q','Quarter back'],
      ['z','add_score',{team:'home',points:1},'Z','Home +1'],
      ['x','add_score',{team:'home',points:2},'X','Home +2'],
      ['c','add_score',{team:'home',points:3},'C','Home +3'],
      ['v','add_score',{team:'home',points:6},'V','Home +6'],
      ['n','add_score',{team:'away',points:1},'N','Away +1'],
      ['m','add_score',{team:'away',points:2},'M','Away +2'],
      [',','add_score',{team:'away',points:3},',','Away +3'],
      ['.','add_score',{team:'away',points:6},'.','Away +6'],
      ['Control+z','undo',{},'Ctrl+Z','Undo last reversible command']
    ];
    for (const [key,command,args] of map) {
      // Quarter actions always open a confirmation now; their dedicated block
      // below verifies that two-step path for both input adapters.
      if (key === 'q' || key === 'Shift+Q' || key === 'Control+z') continue;
      const model = await reset(); await press(key);
      assert.deepEqual(calls,[[command,{...args,source:'operator-keyboard'},model.revision]],key);
      assert.equal(results[0].accepted,true,key);
      if (key==='2'||key==='4') assert.equal(results[0].view.clocks.play.running,false);
    }
    await reset(); await press('Space'); calls.length=0;
    await press('Space'); assert.equal(calls[0][0],'game_clock_stop');

    await reset(); await press('Space');
    assert.equal(await page.locator('#game-display').evaluate(el=>el.classList.contains('running-game')),true);
    assert.equal(await page.locator('#game-state').evaluate(el=>el.classList.contains('running-game')),true);
    await reset(); await press('2'); await press('p');
    assert.equal(await page.locator('#play-display').evaluate(el=>el.classList.contains('running-play')),true);
    assert.equal(await page.locator('#play-state').evaluate(el=>el.classList.contains('running-play')),true);

    // OS repeat plus duplicate non-repeat keydowns; focused button must not also click.
    await reset(); await page.locator('[data-command="add_score"][data-team="home"][data-points="6"]').first().focus();
    await page.keyboard.down('v'); await expectResult(0);
    await page.keyboard.down('v'); await page.keyboard.down('v');
    await page.evaluate(()=>document.dispatchEvent(new KeyboardEvent('keydown',{key:'v',code:'KeyV',bubbles:true})));
    await page.keyboard.up('v'); await settled(); assert.equal(calls.length,1);
    await press('v'); assert.equal(calls.length,2);
    await reset(); await page.locator('[data-command="add_score"][data-team="home"][data-points="6"]').first().focus();
    await press('Space'); assert.equal(calls.length,1); assert.equal(calls[0][0],'game_clock_start');

    await reset(); await page.locator('[data-command="add_score"][data-team="home"][data-points="6"]').first().focus();
    await page.keyboard.down('Enter'); await expectResult(0);
    await page.keyboard.down('Enter'); await page.keyboard.down('Enter');
    await page.keyboard.up('Enter'); await settled();
    assert.equal(calls.length,1); assert.equal(calls[0][1].source,'operator-keyboard');

    // All actual editable controls plus textarea/select/nested contenteditable.
    await reset();
    await page.evaluate(()=>{
      for(const tag of ['textarea','select','div']) {
        const el=document.createElement(tag); el.id='test-'+tag;
        if(tag==='div') {el.contentEditable='true';el.innerHTML='<span>Editable</span>';}
        document.body.appendChild(el);
      }
      document.querySelectorAll('.drawer').forEach(el=>el.hidden=false);
    });
    const fields=await page.locator('input,textarea,select,[contenteditable]').all();
    for(const field of fields) {
      await field.focus();
      const before=calls.length;
      for(const [key] of map) await page.keyboard.press(key);
      assert.equal(calls.length,before,'shortcut leaked from '+await field.getAttribute('id'));
    }
    await page.evaluate(()=>document.querySelectorAll('[id^="test-"]').forEach(el=>el.remove()));
    await reset();
    const ignored=await page.evaluate(()=>{
      const events=[{key:'a',code:'KeyA'},{key:'z',code:'KeyZ',altKey:true},
        {key:'z',code:'KeyZ',metaKey:true},{key:'z',code:'KeyZ',ctrlKey:true,shiftKey:true},
        {key:'v',code:'KeyV',isComposing:true}];
      return events.map(args=>{
        const event=new KeyboardEvent('keydown',{...args,bubbles:true,cancelable:true});
        document.dispatchEvent(event);document.dispatchEvent(new KeyboardEvent('keyup',args));
        return event.defaultPrevented;
      });
    });
    assert.deepEqual(ignored,[false,false,false,false,false]); assert.equal(calls.length,0);

    // Same actual CONFIRMATION_REQUIRED round trip for mouse and keyboard.
    for(const source of ['operator-mouse','operator-keyboard']) {
      await reset(); await press('Space'); calls.length=0;results.length=0;
      const before=await rpc({op:'snapshot'});
      if(source==='operator-keyboard') await press('q');
      else {await page.locator('[data-command="quarter_forward"]').click();await expectResult(0);}
      await page.locator('#confirm-cancel').waitFor({state:'visible'});
      assert.equal(results[0].error.code,'CONFIRMATION_REQUIRED');
      assert.equal(results[0].view.revision,before.revision);
      const count=calls.length; await page.keyboard.press('v'); assert.equal(calls.length,count);
      await page.locator('#confirm-accept').click(); await expectResult(1); await settled();
      assert.deepEqual(calls,[['quarter_forward',{source},before.revision],
        ['quarter_forward',{source,confirmed:true},before.revision]]);
      assert.equal(results[1].accepted,true); assert.equal(results[1].view.clocks.game.running,false);
    }
    // PRE's stronger confirmation is identical for keyboard and direct
    // selection; the exact accepting label is an owner decision.
    for (const path of ['keyboard','direct']) {
      const pregame=await rpc({op:'pregame'}); await render(pregame);
      calls.length=0;results.length=0;
      if(path==='keyboard') await press('q');
      else { await page.locator('#open-corrections').click();
        await page.locator('[data-command="set_quarter"][data-label="1st"]').click(); await expectResult(0); }
      assert.equal(results[0].confirmation_required,true);
      assert.equal(await page.locator('#confirm-accept').textContent(),
        'Start 1st quarter — discard remaining pregame time');
      const count=calls.length; await page.locator('#confirm-cancel').click();
      assert.equal(calls.length,count);
    }
    await reset();await press('Space');await press('q');
    const cancelCount=calls.length;await page.keyboard.press('Escape');
    assert.equal(await page.locator('#confirm-dialog').isVisible(),false);
    assert.equal(calls.length,cancelCount);assert.equal(page.isClosed(),false);

    // A delayed confirmation cannot silently apply to a newer revision.
    await press('q');await page.locator('#confirm-accept').waitFor({state:'visible'});
    const revision=calls.at(-1)[2];
    const external=await rpc({op:'command',args:['add_score',{team:'away',points:3},revision]});
    await render(external.view);
    const count=results.length;await page.locator('#confirm-accept').click();await expectResult(count);
    assert.equal(calls.at(-1)[2],revision);assert.equal(results.at(-1).error.code,'STALE_REVISION');

    await reset();await page.locator('#open-corrections').click();
    await page.locator('#home-name-input').focus();await page.keyboard.press('Escape');
    assert.equal(await page.locator('#corrections').isVisible(),false);assert.equal(page.isClosed(),false);
    await page.locator('#open-help').click();
    const help=await page.locator('#shortcut-list tr').evaluateAll(rows=>rows.map(row=>Array.from(row.children).map(e=>e.textContent)));
    assert.deepEqual(help,[...map.map(row=>[row[3],row[4]]),['Esc','Close dialog / drawer']]);
    await page.keyboard.press('Escape');assert.equal(await page.locator('#shortcut-help').isVisible(),false);
    await page.locator('#open-advanced').click();
    assert.equal(await page.locator('#advanced-drawer').isVisible(),true);
    assert.equal(await page.locator('#open-test-window').isVisible(),true);
    await page.locator('#open-test-window').click();
    await page.locator('#alert').waitFor({state:'visible'});
    assert.equal(await page.locator('#alert').textContent(),'Test spectator window opened.');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#advanced-drawer').isVisible(),false);
    // Live controls must still fit after adding help at both operator modes.
    for(const viewport of [{width:1366,height:768},{width:1093,height:614}]) {
      await page.setViewportSize(viewport);
      const outside=await page.locator('button:visible').evaluateAll(buttons=>buttons.filter(b=>{
        const r=b.getBoundingClientRect();return r.left<0||r.top<0||r.right>innerWidth+.5||r.bottom>innerHeight+.5;
      }).map(b=>b.textContent));
      assert.deepEqual(outside,[]);
    }
    // The separate startup page has no live command adapter at all.
    const startup=await browser.newPage();
    await startup.addInitScript(()=>{
      window.startupChoices=[];
      window.pywebview={api:{get_recovery:()=>Promise.resolve({source:'BACKUP',message:'RECOVERED FROM BACKUP',
        checkpoint_at:'2026-09-04T12:00:00Z',can_resume:true,view:null,preserved_paths:[]}),
        resume_recovered_game:()=>window.startupChoices.push('resume'),
        start_new_game:()=>window.startupChoices.push('new')}};
    });
    await startup.goto(pathToFileURL(path.resolve('src/scoreboard/views/startup/index.html')).href);
    await startup.locator('#new').click();
    await startup.keyboard.press('Escape');
    assert.equal(await startup.locator('#new-confirm').isVisible(),false);
    for(const [key] of map) await startup.keyboard.press(key);
    assert.deepEqual(await startup.evaluate(()=>window.startupChoices),[]);
    assert.equal(startup.isClosed(),false);
    await startup.locator('#new').click();await startup.locator('#cancel').click();
    assert.deepEqual(await startup.evaluate(()=>window.startupChoices),[]);
    await startup.locator('#resume').click();
    assert.deepEqual(await startup.evaluate(()=>window.startupChoices),['resume']);
    await startup.close();

    const history=await rpc({op:'history'});
    assert.ok(history.some(row=>row.command==='add_score'&&row.source==='operator-keyboard'&&row.result==='ACCEPTED'));
    assert.ok(history.some(row=>row.command==='quarter_forward'&&row.source==='operator-keyboard'));
    assert.deepEqual(errors,[]);
    return {shortcuts:help.length,editableFields:fields.length};
  } finally { await browser.close();child.stdin.end(); }
}
let input='';process.stdin.on('data',chunk=>input+=chunk);
process.stdin.on('end',()=>main(JSON.parse(input)).then(result=>console.log(JSON.stringify(result))).catch(error=>{console.error(error);process.exitCode=1;}));
