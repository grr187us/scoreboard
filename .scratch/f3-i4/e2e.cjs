/* End-to-end check for F3 and I4 against the REAL bridge (tests/ui/bridge_server.py).
 * Development evidence, not part of the suite.
 * Run: node .scratch/f3-i4/e2e.cjs
 */
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const assert = require('node:assert/strict');

const PYTHON = path.resolve('.venv/Scripts/python.exe');

async function main() {
  const child = spawn(PYTHON, ['-u', 'tests/ui/bridge_server.py'], { stdio: ['pipe', 'pipe', 'pipe'] });
  const waiting = [];
  let stderr = '';
  child.stderr.on('data', (chunk) => { stderr += chunk; });
  readline.createInterface({ input: child.stdout })
    .on('line', (line) => waiting.shift()?.resolve(JSON.parse(line)));
  child.on('exit', (code) => { if (code) waiting.splice(0).forEach((p) => p.reject(new Error(stderr))); });
  const rpc = (request) => new Promise((resolve, reject) => {
    waiting.push({ resolve, reject });
    child.stdin.write(JSON.stringify(request) + '\n');
  });

  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const findings = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1093, height: 614 } });
    const errors = [];
    page.on('pageerror', (error) => errors.push(String(error)));
    await page.route(/^https?:/, (route) => route.abort());
    await page.exposeFunction('testSnapshot', () => rpc({ op: 'snapshot' }));
    await page.exposeFunction('testCommand', (...args) => rpc({ op: 'command', args }));
    await page.addInitScript(() => {
      window.pywebview = { api: {
        get_snapshot: () => window.testSnapshot(),
        command: (...args) => window.testCommand(...args),
      } };
    });
    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/operator/index.html')).href);
    await page.waitForFunction(() => document.querySelector('#chip-game').textContent.includes('STOPPED'));

    const render = (view) => page.evaluate((v) => window.applyView(v), view);
    await render(await rpc({ op: 'reset' }));

    const settle = async () => {
      const snap = await rpc({ op: 'snapshot' });
      await page.waitForFunction(
        (rev) => document.querySelector('#chip-revision').textContent === 'Rev ' + rev, snap.revision);
      return snap;
    };
    const click = async (selector) => {
      const before = (await rpc({ op: 'snapshot' })).revision;
      await page.click(selector);
      await page.waitForFunction(
        (rev) => Number(document.querySelector('#chip-revision').textContent.slice(4)) > rev, before);
      return settle();
    };

    // --- F3: pressing TIMEOUT reaches Python and comes back to the wall ---
    const resting = await rpc({ op: 'snapshot' });
    findings.push(['resting chip', await page.textContent('#crowd-status')]);
    findings.push(['resting status.label', resting.status.label]);

    const afterTimeout = await click('#crowd-timeout');
    findings.push(['after TIMEOUT: status.label', afterTimeout.status.label]);
    findings.push(['after TIMEOUT: clock running', afterTimeout.status.clock.running]);
    findings.push(['after TIMEOUT: clock_display', afterTimeout.status.clock_display]);
    findings.push(['after TIMEOUT: revisions used', afterTimeout.revision - resting.revision]);
    findings.push(['after TIMEOUT: chip text', await page.textContent('#crowd-status')]);
    findings.push(['after TIMEOUT: crowd-clock text', await page.textContent('#crowd-clock')]);
    findings.push(['after TIMEOUT: button lit',
      await page.getAttribute('#crowd-timeout', 'class')]);

    // --- F3: the wall actually draws it ---
    const spectator = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    spectator.on('pageerror', (error) => errors.push('spectator: ' + String(error)));
    await spectator.route(/^https?:/, (route) => route.abort());
    await spectator.addInitScript((view) => {
      window.__v = view;
      window.pywebview = { api: { get_snapshot: () => Promise.resolve(window.__v) } };
    }, afterTimeout);
    await spectator.goto(pathToFileURL(path.resolve('src/scoreboard/views/spectator/index.html')).href);
    await spectator.waitForFunction(() => document.querySelector('#canvas').dataset.revision !== undefined);
    const wall = async () => spectator.evaluate(() => {
      const read = (id) => {
        const el = document.querySelector(`#game-board [data-item="${id}"]`);
        if (!el) return null;
        const box = el.getBoundingClientRect();
        return { text: el.textContent, hidden: el.hidden || box.width === 0 || box.height === 0 };
      };
      return { status_message: read('status_message'), status_clock: read('status_clock') };
    });
    findings.push(['wall with TIMEOUT raised', JSON.stringify(await wall())]);

    await spectator.evaluate(() => window.applyView(Object.assign({}, window.__v, {
      status: { label: null, active: false, display: '', clock_display: '',
                clock: { seconds: 0, running: false, display: '', status: 'STOPPED' } },
    })));
    findings.push(['wall with nothing raised', JSON.stringify(await wall())]);

    // --- I4: a crowd toggle does not spend the undo stack ---
    await render(await rpc({ op: 'reset' }));
    const scored = await click('[data-command="add_score"][data-team="home"][data-points="6"]');
    findings.push(['after +6: home score', scored.teams.home.score]);
    findings.push(['after +6: undo depth', scored.undo_depth]);
    await click('#crowd-flag');
    const afterFlag = await rpc({ op: 'snapshot' });
    findings.push(['after FLAG: undo depth', afterFlag.undo_depth]);
    findings.push(['after FLAG: next undo label', afterFlag.last_action.label]);
    const undone = await click('#undo');
    findings.push(['after UNDO: home score', undone.teams.home.score]);
    findings.push(['after UNDO: status still raised', undone.status.label]);

    // --- I4: two scores in a row are both reversible, newest first ---
    await render(await rpc({ op: 'reset' }));
    await click('[data-command="add_score"][data-team="home"][data-points="6"]');
    const two = await click('[data-command="add_score"][data-team="away"][data-points="3"]');
    findings.push(['two scores: depth', two.undo_depth]);
    findings.push(['two scores: history', JSON.stringify(two.undo_history.map((e) => e.label))]);
    await page.click('#last-action-button');
    findings.push(['history drawer open', !(await page.getAttribute('#history-drawer', 'hidden') !== null)]);
    findings.push(['history rows', await page.evaluate(
      () => Array.from(document.querySelectorAll('#history-list li')).map((li) => li.textContent))]);
    await page.click('#history-drawer [data-command="undo"]');
    await page.waitForFunction(() => document.querySelectorAll('#history-list li').length === 1);
    const back1 = await rpc({ op: 'snapshot' });
    findings.push(['after 1st undo: scores', `${back1.teams.home.score}-${back1.teams.away.score}`]);
    await page.click('#history-drawer [data-command="undo"]');
    await page.waitForFunction(() => document.querySelector('#history-list li.empty') !== null);
    const back2 = await rpc({ op: 'snapshot' });
    findings.push(['after 2nd undo: scores', `${back2.teams.home.score}-${back2.teams.away.score}`]);
    findings.push(['after 2nd undo: can_undo', back2.can_undo]);

    findings.push(['page errors', JSON.stringify(errors)]);
  } finally {
    await browser.close();
    child.kill();
  }
  for (const [label, value] of findings) console.log(String(label).padEnd(34), value);
}

main().catch((error) => { console.error(error); process.exit(1); });
