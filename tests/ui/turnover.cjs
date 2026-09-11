const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const {pathToFileURL} = require('node:url');
async function main(data) {
 const browser = await chromium.launch({channel:'msedge',headless:true});
 const errors=[]; let cases=0;
 const dir=process.env.SCOREBOARD_CAPTURE_DIR;
 if(dir) fs.mkdirSync(dir,{recursive:true});
 try {
  const page=await browser.newPage();
  page.on('pageerror',e=>errors.push(e.message));
  await page.route(/^https?:/,r=>{errors.push('network');return r.abort();});
  await page.addInitScript(data=>{window.pywebview={api:{get_snapshot:()=>Promise.resolve(data.view),get_layout:()=>Promise.resolve(data.layout)}};},data);
  await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/spectator/index.html')).href);
  await page.waitForFunction(()=>document.querySelector('#canvas').dataset.revision==='42');
  await page.evaluate(()=>document.fonts.ready);
  await page.clock.install(); await page.clock.pauseAt(new Date(Date.now()+1000));
  let elapsed=0;
  async function start(extra={}) {elapsed=0;await page.evaluate(p=>window.applyCutscene(p),{...data.program,...extra});}
  async function advance(ms) {
   elapsed+=ms;await page.clock.runFor(ms);
   await page.evaluate(age=>{
    for(const a of document.querySelector('#cutscene-stage').getAnimations({subtree:true})) {a.pause();a.currentTime=age;}
    for(const a of document.querySelector('#canvas').getAnimations({subtree:true})) {
     if(a.effect.target.matches('.widget, .element')) a.finish();
    }
   },elapsed);
  }
  async function capture(label) {if(dir) await page.screenshot({path:path.join(dir,label+'.png')});}
  async function art() {
   const m=await page.evaluate(()=>{
    const stage=document.querySelector('#cutscene-stage').getBoundingClientRect();
    const items=['.cs-impact-headline','.cs-impact-subline','.cs-impact-crest'].map(sel=>{
     const e=document.querySelector(sel),r=e.getBoundingClientRect();
     const range=document.createRange();range.selectNodeContents(e);const ink=range.getBoundingClientRect();
     return {text:e.textContent,opacity:getComputedStyle(e).opacity,top:r.top,bottom:r.bottom,
      fit:r.top>=stage.top && r.bottom<=stage.bottom && ink.left>=stage.left && ink.right<=stage.right};
    });
    return {items,old:document.querySelectorAll('.cs-to-ball,.cs-to-slab-red').length,
     wall:document.querySelectorAll('.cs-impact-shard').length};
   });
   assert.equal(m.items[0].text,'TURNOVER');assert.equal(m.items[1].text,"TIGER'S BALL");
   for(const i of m.items){assert.equal(i.opacity,'1');assert.ok(i.fit,JSON.stringify(m));}
   assert.ok(m.items[0].bottom<m.items[1].top);assert.ok(m.items[1].bottom<m.items[2].top);
   assert.equal(m.old,0);assert.equal(m.wall,12);
  }
  async function restored() {
   assert.equal(await page.locator('#canvas').getAttribute('data-layout'),data.layout.name);
   assert.equal(await page.locator('#cutscene-stage').evaluate(e=>e.hidden && !e.children.length),true);
  }
  for(const [width,height] of [[1920,1080],[1366,768],[640,360]]) {
   await page.setViewportSize({width,height});await start();await advance(100);await capture('barrier-'+width);
   await advance(350);await capture('impact-'+width);
   await advance(1150);await art();await capture('hold-'+width);
   assert.equal(await page.locator('.cs-impact-shard canvas').count(),12);
   await page.evaluate(v=>window.applyView(v),data.nextView);
   assert.equal(await page.locator('#game-board [data-widget="game_clock_value"]').innerText(),'8:39');
   await advance(3401);await restored();cases++;
  }
  for(const time of [100,900,2200]) {await start();await advance(time);await page.evaluate(()=>window.endCutscene(1));await advance(301);await restored();}
  await start();await advance(500);await start({play_id:2});await advance(5001);await restored();
  await start({play_id:3,elapsed_ms:3500});await art();
  assert.equal(await page.locator('.cs-impact-shock').evaluate(e=>getComputedStyle(e).display),'none');
  await advance(1501);await restored();
  await page.emulateMedia({reducedMotion:'reduce'});await start({play_id:4});await art();
  assert.equal(await page.locator('.cs-impact-chip').first().evaluate(e=>getComputedStyle(e).animationName),'none');
  await advance(5001);await restored();cases++;
  await page.emulateMedia({reducedMotion:'no-preference'});
  // Canvas failure must leave a readable CSS barrier and text, without errors.
  await page.evaluate(()=>{HTMLCanvasElement.prototype.getContext=()=>null;});
  await start({play_id:5});await advance(1700);await art();await advance(3301);await restored();cases++;
  return {cases,errors};
 } finally {await browser.close();}
}
let input='';process.stdin.setEncoding('utf8');process.stdin.on('data',c=>input+=c);
process.stdin.on('end',()=>main(JSON.parse(input)).then(r=>process.stdout.write(JSON.stringify(r))).catch(e=>{console.error(e.stack||e);process.exit(1);}));
