// Screenshots of the refreshed operator page against the real bridge
// (tests/ui/bridge_server.py), idle and armed, at both U-001 viewports.
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

async function main(data) {
  const child = spawn(data.python, ['-u', 'tests/ui/bridge_server.py'], {stdio:['pipe','pipe','pipe']});
  const waiting = [];
  readline.createInterface({input:child.stdout}).on('line', line => waiting.shift()?.resolve(JSON.parse(line)));
  const rpc = request => new Promise((resolve,reject) => { waiting.push({resolve,reject}); child.stdin.write(JSON.stringify(request)+'\n'); });
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1093,height:614}});
    await page.exposeFunction('testSnapshot', () => rpc({op:'snapshot'}));
    await page.exposeFunction('testCommand', (...args) => rpc({op:'command',args}));
    await page.addInitScript(() => {
      window.pywebview = {api:{get_snapshot:()=>window.testSnapshot(),command:(...args)=>window.testCommand(...args),
        teams:()=>Promise.resolve({teams:[{name:'Tigers',short_name:'TIG',primary:'#F5AE08',secondary:'#111111'}],current:{}})}};
    });
    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/operator/index.html')).href);
    await page.waitForFunction(() => document.querySelector('#chip-game').textContent.includes('STOPPED'));
    await page.waitForTimeout(300);
    const out = data.out;
    await page.screenshot({path: path.join(out,'01-launch-teams-prompt-1093.png')});
    await page.keyboard.press('Escape');
    await page.screenshot({path: path.join(out,'02-idle-1093.png')});
    await page.locator('#home-arm').click();
    await page.screenshot({path: path.join(out,'03-armed-home-1093.png')});
    await page.locator('.team [data-command="add_score"][data-team="home"][data-points="6"]').click();
    await page.waitForTimeout(400);
    await page.locator('#undo').click();
    await page.waitForTimeout(200);
    await page.screenshot({path: path.join(out,'04-undo-dialog-1093.png')});
    await page.locator('#confirm-cancel').click();
    await page.locator('#open-game').click();
    await page.screenshot({path: path.join(out,'05-game-drawer-1093.png')});
    await page.keyboard.press('Escape');
    await page.locator('#open-corrections').click();
    await page.screenshot({path: path.join(out,'06-corrections-1093.png')});
    await page.keyboard.press('Escape');
    await page.setViewportSize({width:1366,height:768});
    await page.screenshot({path: path.join(out,'07-idle-1366.png')});
    await page.locator('#away-arm').click();
    await page.screenshot({path: path.join(out,'08-armed-away-1366.png')});
    const overflow = await page.evaluate(() => [document.documentElement.scrollHeight, document.documentElement.clientHeight, document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    console.log(JSON.stringify({overflow}));
  } finally { await browser.close(); child.stdin.end(); }
}
let input=''; process.stdin.on('data',c=>input+=c);
process.stdin.on('end',()=>main(JSON.parse(input)).catch(e=>{console.error(e);process.exitCode=1;}));
