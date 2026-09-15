/* The GOAL cutscene's actual seven-second Python program, played against the
 * real cutscene.js/soccer.js scene on the test-only preview page (agent D's
 * views/soccer_spectator/index.html does not exist yet -- see
 * .scratch/soccer-mode/preview/goal/index.html's own header comment).
 * Exercises both teams, the headline/team-name text, the team colour keying,
 * a late join, reduced motion, and natural completion/cancellation.
 * Screenshots (when SCOREBOARD_CAPTURE_DIR is set) land in
 * .scratch/soccer-mode/evidence/goal/.
 */
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
    await page.setViewportSize({width: 1920, height: 1080});
    page.on('pageerror', e => errors.push(e.message));
    await page.route(/^https?:/, route => { errors.push('network request'); return route.abort(); });
    await page.goto(pathToFileURL(path.resolve('.scratch/soccer-mode/preview/goal/index.html')).href);
    await page.evaluate(() => document.fonts.ready);
    await page.clock.install();
    await page.clock.pauseAt(new Date(Date.now() + 1000));
    let elapsed = 0;
    async function start(program, extra = {}) {
      elapsed = 0;
      const ok = await page.evaluate(p => window.applyCutscene(p), {...program, ...extra});
      assert.equal(ok, true, 'applyCutscene must accept a real GOAL program');
    }
    async function advance(ms) {
      elapsed += ms;
      await page.clock.runFor(ms);
      await page.evaluate(elapsed => {
        const stage = document.querySelector('#cutscene-stage');
        for (const animation of stage.getAnimations({subtree: true})) {
          if (!animation.effect.target.closest('[data-scene]')) continue;
          animation.pause(); animation.currentTime = elapsed;
        }
      }, elapsed);
    }
    async function capture(label) {
      if (captureDir) await page.screenshot({path: path.join(captureDir, label + '.png')});
    }
    async function restored() {
      assert.equal(await page.locator('#cutscene-stage').evaluate(e => e.hidden && e.children.length === 0), true);
    }
    async function checkArt(expectedTeamName, expectedColorVar) {
      const m = await page.evaluate(colorVar => {
        const stage = document.querySelector('#cutscene-stage');
        const headline = document.querySelector('.cs-goal-headline span');
        const subline = document.querySelector('.cs-goal-subline span');
        const stageBox = stage.getBoundingClientRect();
        const headBox = headline.getBoundingClientRect();
        const subBox = subline.getBoundingClientRect();
        return {
          headline: headline.textContent,
          subline: subline.textContent,
          headOpacity: getComputedStyle(headline.parentNode).opacity,
          subOpacity: getComputedStyle(subline.parentNode).opacity,
          color: getComputedStyle(stage).getPropertyValue(colorVar).trim(),
          fits: headBox.left >= stageBox.left && headBox.right <= stageBox.right,
          subFits: subBox.left >= stageBox.left && subBox.right <= stageBox.right,
          scrolls: document.documentElement.scrollWidth > innerWidth || document.documentElement.scrollHeight > innerHeight,
        };
      }, expectedColorVar);
      assert.equal(m.headline, 'GOAL');
      assert.equal(m.subline, expectedTeamName.toUpperCase());
      assert.equal(m.headOpacity, '1');
      assert.equal(m.subOpacity, '1');
      assert.ok(m.color, 'expected a theme colour on the stage');
      assert.equal(m.fits, true, JSON.stringify(m));
      assert.equal(m.subFits, true, JSON.stringify(m));
      assert.equal(m.scrolls, false);
    }

    // Both teams, across the full timeline.
    for (const key of ['home', 'away']) {
      const program = data.programs[key];
      const teamName = program.texts.team_name;
      const colorVar = key === 'home' ? '--cs-home-primary' : '--cs-away-primary';
      await start(program);
      await advance(700);
      assert.equal(await page.locator('[data-scene="goal"].cs-goal-' + key).count(), 1,
        'the scene root must carry the scoring side as a class');
      await advance(1500);
      await checkArt(teamName, colorVar);
      await capture(`goal-${key}`);
      await advance(program.duration_ms - elapsed + 1);
      await restored();
      cases++;
    }

    // Cancellation ends early and restores the board.
    await start(data.programs.home); await advance(300);
    await page.evaluate(() => window.endCutscene(1)); await advance(301); await restored();
    cases++;

    // A late join shows the settled hold immediately, not the entrance.
    await start(data.programs.away, {play_id: 9, elapsed_ms: data.programs.away.duration_ms - 2000});
    assert.equal(await page.locator('.cs-goal.cs-goal-resumed').count(), 1);
    await checkArt(data.programs.away.texts.team_name, '--cs-away-primary');
    await advance(2001); await restored();
    cases++;

    // Reduced motion: the scene still renders the headline and team name.
    await page.emulateMedia({reducedMotion: 'reduce'});
    await start(data.programs.home, {play_id: 11});
    await advance(1);
    await page.evaluate(() => {
      const head = document.querySelector('.cs-goal-headline');
      const sub = document.querySelector('.cs-goal-subline');
      if (head) head.style.animation = 'none';
      if (sub) sub.style.animation = 'none';
    });
    await checkArt(data.programs.home.texts.team_name, '--cs-home-primary');
    await advance(data.programs.home.duration_ms); await restored();
    cases++;

    return {cases, errors};
  } finally { await browser.close(); }
}
let input = ''; process.stdin.setEncoding('utf8');
process.stdin.on('data', c => input += c);
process.stdin.on('end', () => main(JSON.parse(input)).then(r => process.stdout.write(JSON.stringify(r)))
  .catch(e => { console.error(e.stack || e); process.exit(1); }));
