/* Drive the spectator page's cutscene player in an offline Edge page.
 *
 * Same shape as `spectator.cjs`: the real page is loaded from `file://` with
 * a stub `window.pywebview.api`, every assertion runs against the real DOM,
 * and the result is one JSON object on stdout.
 *
 * What this proves is the *plumbing contract*, not the artwork: the stage
 * appears, the board morphs to the cutscene's layout, a scene mounts, and --
 * on every path out (natural end, an early end from the host, a replacing
 * cutscene, a media file that will not open, a malformed program) -- the
 * operator's layout comes back and the stage goes away. The owner will
 * iterate on how the scenes look; none of that may quietly break this.
 */

const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

/* The spectator page is the one under test; the program below is built in the
 * page (it needs board.js's DEFAULT_LAYOUT) by this init script. Python's
 * `build_program` produces the same shape -- `tests/integration/
 * test_cutscene_player_contract.py` and Agent A's schema tests pin the key
 * names on both sides; this fixture only has to be a *valid* program. */
const PROGRAM_FIXTURE = () => {
  window.__makeProgram = function (overrides) {
    // The override layout: the default document renamed, plus the Broadcast
    // bar's box element, so "the override was applied" is observable as a
    // node the previous layout does not have.
    const layout = JSON.parse(JSON.stringify(window.ScoreboardBoard.DEFAULT_LAYOUT));
    layout.name = 'Cutscene';
    layout.elements = [{
      id: 'broadcast_bar', type: 'box',
      x: 0.0, y: 0.78, width: 1.0, height: 0.18,
      background: '#101820', corner_radius: 0.012, z_index: 0,
    }];
    // The v2 program shape: `team` is "home" or null (a penalty is nobody's),
    // `texts` has no `score` (the score stays on the Broadcast bar), and the
    // theme carries the penalty flag's yellow.
    const program = {
      schema_version: 1,
      play_id: 1,
      event: 'touchdown',
      label: 'Touchdown',
      team: 'home',
      pack_id: 'builtin:touchdown',
      duration_ms: 1500,
      intro: { id: 'claw_scratch', duration_ms: 200 },
      outro_ms: 100,
      stage: { x: 0.0, y: 0.0, width: 1.0, height: 0.70 },
      layout,
      scene: { type: 'builtin', id: 'touchdown' },
      theme: {
        navy: '#071B3A', navy_elevated: '#0D2B5A', blue: '#17468C',
        red: '#C8242B', blue_light: '#2C62AB', white: '#FFFFFF',
        mist: '#DDE7F4', ink: '#030711', gold: '#FFB703', flag: '#FFD500',
      },
      texts: { headline: 'TOUCHDOWN', subline: 'TIGERS', team_name: 'Tigers' },
    };
    return Object.assign(program, overrides || {});
  };
};

const stageHidden = page => page.evaluate(() => document.querySelector('#cutscene-stage').hidden);
const stageChildren = page => page.evaluate(() => document.querySelector('#cutscene-stage').children.length);
const layoutName = page => page.evaluate(() => document.querySelector('#canvas').dataset.layout);
const playerState = page => page.evaluate(() => window.ScoreboardCutscenePlayer.state());
const sceneIds = page => page.evaluate(() =>
  Array.from(document.querySelectorAll('#cutscene-stage [data-scene]')).map(n => n.getAttribute('data-scene')));
const hasBroadcastBar = page => page.evaluate(() =>
  Boolean(document.querySelector('#game-board [data-item="broadcast_bar"]')));

async function waitIdle(page, timeout) {
  await page.waitForFunction(() => window.ScoreboardCutscenePlayer.state().playing === false,
    undefined, { timeout: timeout || 4000 });
  // The restore happens in one step, but give the class removal its tick.
  await page.waitForFunction(() => document.querySelector('#cutscene-stage').hidden === true,
    undefined, { timeout: 1000 });
}

async function main(data) {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const checks = [];
  try {
    const page = await browser.newPage();
    await page.route(/^https?:/, route => route.abort());
    await page.addInitScript(model => {
      window.pywebview = { api: { get_snapshot: () => Promise.resolve(model) } };
    }, data.snapshot);
    await page.addInitScript(PROGRAM_FIXTURE);
    await page.goto(pathToFileURL(path.resolve('src/scoreboard/views/spectator/index.html')).href);
    await page.waitForFunction(() => document.querySelector('#canvas').dataset.revision === '42');

    // The idle baseline: the operator's layout, no stage, no scene.
    assert.equal(await layoutName(page), 'Default');
    assert.equal(await stageHidden(page), true);
    assert.equal(await hasBroadcastBar(page), false);
    assert.deepEqual(await playerState(page), {
      playing: false, play_id: null, phase: 'idle', event: null, scene_id: null, resumed: false,
    });
    // Registration order across the three scene files, in load order:
    // builtin.js (team-agnostic), tigers.js (the Tigers' branding), then
    // crowd.js (the v3 crowd prompt).
    assert.deepEqual(await page.evaluate(() => window.ScoreboardCutsceneScenes.ids()),
      ['claw_scratch', 'penalty', 'first_down', 'touchdown', 'turnover', 'make_some_noise']);
    // tigers.js and crowd.js build their scenes out of builtin.js's helpers
    // by these names.
    assert.deepEqual(await page.evaluate(() =>
      Object.keys(window.ScoreboardCutsceneScenes.helpers).sort()),
      ['addText', 'sceneRoot', 'simpleScene', 'textOf']);
    checks.push('idle baseline');

    // ---------------------------------------------------------------
    // 1. The whole timeline: intro, morph, scene, and a natural restore.
    // ---------------------------------------------------------------
    // One round trip: the intro is only 200 ms long, so everything about t=0
    // is read in a single evaluate rather than five.
    const atStart = await page.evaluate(() => {
      const accepted = window.applyCutscene(window.__makeProgram());
      const stage = document.querySelector('#cutscene-stage');
      const count = selector => stage.querySelectorAll(selector).length;
      return {
        accepted,
        hidden: stage.hidden,
        state: window.ScoreboardCutscenePlayer.state(),
        scenes: Array.from(stage.querySelectorAll('[data-scene]')).map(n => n.getAttribute('data-scene')),
        canvasHeight: document.querySelector('#canvas').getBoundingClientRect().height,
        stageHeight: stage.getBoundingClientRect().height,
        // The strike's three parts: the paw that swipes through (a lead copy
        // and two motion-trail ghosts), the four gouges it tears open, and
        // the debris it throws off the board.
        paws: count('.cs-paw-swipe'),
        gouges: count('.cs-gouge'),
        bits: count('.cs-claw-bit'),
        flashes: count('.cs-claw-flash'),
        shaking: document.querySelector('#canvas').classList.contains('shake'),
        flag: stage.style.getPropertyValue('--cs-flag'),
      };
    });
    assert.equal(atStart.accepted, true);
    assert.equal(atStart.hidden, false);
    assert.equal(atStart.state.playing, true);
    assert.equal(atStart.state.play_id, 1);
    assert.equal(atStart.state.phase, 'intro');
    assert.deepEqual(atStart.scenes, ['claw_scratch']);
    // The intro covers the whole canvas before the board morphs under it.
    assert.ok(Math.abs(atStart.stageHeight - atStart.canvasHeight) <= 1,
      `the intro stage must cover the canvas: ${JSON.stringify(atStart)}`);
    assert.equal(atStart.paws, 3, 'the paw swipes through with two motion-trail ghosts');
    assert.equal(atStart.gouges, 4, 'four claws, four gouges');
    assert.ok(atStart.bits >= 14 && atStart.bits <= 20, `debris count: ${atStart.bits}`);
    // Exactly one flash: the brand rule against strobing lives in the DOM as
    // well as in the keyframes.
    assert.equal(atStart.flashes, 1, 'the strike flashes once, never twice');
    assert.equal(atStart.shaking, true, 'the board takes the hit');
    // The whole theme reaches the stage, including v2's penalty yellow.
    assert.equal(atStart.flag, '#FFD500');
    checks.push('intro mounts full canvas');

    // Past the intro: the override layout is on the board and the main scene
    // has replaced the claw slashes.
    await page.waitForFunction(() => document.querySelector('#cutscene-stage [data-scene="touchdown"]') !== null,
      undefined, { timeout: 2000 });
    assert.equal(await layoutName(page), 'Cutscene');
    assert.equal(await hasBroadcastBar(page), true);
    assert.deepEqual(await sceneIds(page), ['touchdown']);
    assert.equal((await playerState(page)).phase, 'scene');
    // The scene stage is the program's rectangle, not the whole canvas.
    const sceneRect = await page.evaluate(() => {
      const canvas = document.querySelector('#canvas').getBoundingClientRect();
      const stage = document.querySelector('#cutscene-stage').getBoundingClientRect();
      return { canvasHeight: canvas.height, stageHeight: stage.height };
    });
    assert.ok(Math.abs(sceneRect.stageHeight - sceneRect.canvasHeight * 0.70) <= 1,
      `the scene stage must be the program's rectangle: ${JSON.stringify(sceneRect)}`);
    // The scene sizes itself from the stage, in px, published by the player.
    const stageWidth = await page.evaluate(() =>
      document.querySelector('#cutscene-stage').style.getPropertyValue('--stage-w'));
    assert.ok(/^[0-9.]+px$/.test(stageWidth), `--stage-w must be px: ${stageWidth}`);
    // The words on the stage are the program's, verbatim.
    const words = await page.evaluate(() =>
      document.querySelector('#cutscene-stage [data-scene="touchdown"]').textContent);
    assert.ok(words.includes('TOUCHDOWN'), `the headline must be on the stage: ${words}`);
    // The score is gone from the scene in v2: it stays on the Broadcast bar
    // under the stage, which is up and ticking the whole time. `14` is the
    // home score in the fixture snapshot, so its absence here is the check.
    assert.ok(!words.includes('14'), `the scene must show no score: ${words}`);
    checks.push('override applied and scene mounted');

    // The natural end (1500 ms) hands the board back on its own.
    await waitIdle(page, 3000);
    assert.equal(await layoutName(page), 'Default');
    assert.equal(await stageHidden(page), true);
    assert.equal(await stageChildren(page), 0);
    assert.equal(await hasBroadcastBar(page), false);
    checks.push('natural end restores');

    // ---------------------------------------------------------------
    // 2. An early end from the host restores well inside half a second.
    // ---------------------------------------------------------------
    await page.evaluate(() => window.applyCutscene(window.__makeProgram({ play_id: 2, duration_ms: 8000 })));
    await page.waitForFunction(() => window.ScoreboardCutscenePlayer.state().phase === 'scene',
      undefined, { timeout: 2000 });
    // A stale play id must never cut the current cutscene short.
    assert.equal(await page.evaluate(() => window.endCutscene(9999)), false);
    assert.equal((await playerState(page)).playing, true);
    const startedAt = Date.now();
    assert.equal(await page.evaluate(() => window.endCutscene(2)), true);
    await waitIdle(page, 2000);
    const restoreMs = Date.now() - startedAt;
    assert.ok(restoreMs < 500, `endCutscene must restore within 500 ms, took ${restoreMs} ms`);
    assert.equal(await layoutName(page), 'Default');
    assert.equal(await hasBroadcastBar(page), false);
    checks.push('early end restores');

    // ---------------------------------------------------------------
    // 3. A media pack whose file is not there falls back to the built-in.
    // ---------------------------------------------------------------
    await page.evaluate(() => window.applyCutscene(window.__makeProgram({
      play_id: 3,
      duration_ms: 8000,
      intro: { id: 'none', duration_ms: 0 },
      scene: {
        type: 'video',
        src: 'file:///C:/scoreboard-cutscene-does-not-exist/missing.webm',
        fit: 'cover',
        loop: false,
        fallback: { type: 'builtin', id: 'touchdown' },
      },
    })));
    await page.waitForFunction(() => document.querySelector('#cutscene-stage [data-scene="touchdown"]') !== null,
      undefined, { timeout: 5000 });
    assert.equal((await playerState(page)).play_id, 3);
    assert.equal(await layoutName(page), 'Cutscene');
    await page.evaluate(() => window.endCutscene(3));
    await waitIdle(page, 2000);
    checks.push('missing media falls back to the builtin');

    // ---------------------------------------------------------------
    // 4. Triggering while one plays replaces it -- one cutscene, one scene.
    // ---------------------------------------------------------------
    await page.evaluate(() => window.applyCutscene(window.__makeProgram({ play_id: 4, duration_ms: 8000 })));
    await page.waitForFunction(() => window.ScoreboardCutscenePlayer.state().phase === 'scene',
      undefined, { timeout: 2000 });
    await page.evaluate(() => window.applyCutscene(window.__makeProgram({
      play_id: 5,
      event: 'first_down',
      duration_ms: 8000,
      scene: { type: 'builtin', id: 'first_down' },
      texts: { headline: 'FIRST DOWN', subline: 'TIGERS', team_name: 'Tigers' },
    })));
    const replaced = await playerState(page);
    assert.equal(replaced.play_id, 5);
    assert.equal(replaced.event, 'first_down');
    await page.waitForFunction(() => document.querySelector('#cutscene-stage [data-scene="first_down"]') !== null,
      undefined, { timeout: 2000 });
    assert.deepEqual(await sceneIds(page), ['first_down'], 'a replaced cutscene must leave no scene behind');
    assert.ok((await page.evaluate(() =>
      document.querySelector('#cutscene-stage [data-scene="first_down"]').textContent)).includes('FIRST DOWN'));
    // The board never went back to the operator's layout in between.
    assert.equal(await layoutName(page), 'Cutscene');
    // The old cutscene's end is stale now and must be ignored.
    assert.equal(await page.evaluate(() => window.endCutscene(4)), false);
    assert.equal((await playerState(page)).playing, true);
    await page.evaluate(() => window.endCutscene(5));
    await waitIdle(page, 2000);
    assert.equal(await layoutName(page), 'Default');
    checks.push('a second cutscene replaces the first');

    // ---------------------------------------------------------------
    // 5. A malformed program is ignored and the board is untouched.
    // ---------------------------------------------------------------
    const before = await page.evaluate(() => ({
      layout: document.querySelector('#canvas').dataset.layout,
      homeScore: document.querySelector('[data-widget="home_score"]').getBoundingClientRect().toJSON(),
      widgets: document.querySelectorAll('#game-board [data-widget]').length,
    }));
    const rejected = await page.evaluate(() => {
      const good = window.__makeProgram();
      const attempts = [
        'garbage', 42, null, undefined, [], {},
        { play_id: 'one', duration_ms: 1500 },
        Object.assign({}, good, { play_id: null }),
        Object.assign({}, good, { duration_ms: 0 }),
        Object.assign({}, good, { stage: null }),
        Object.assign({}, good, { layout: { name: 'Broken' } }),
        Object.assign({}, good, { scene: { type: 'hologram', id: 'touchdown' } }),
        Object.assign({}, good, { scene: { type: 'builtin' } }),
        Object.assign({}, good, { scene: { type: 'video', fit: 'cover' } }),
      ];
      const results = [];
      const thrown = [];
      for (const attempt of attempts) {
        try { results.push(window.applyCutscene(attempt)); } catch (error) { thrown.push(String(error)); }
      }
      return { results, thrown, count: attempts.length };
    });
    assert.deepEqual(rejected.thrown, [], 'applyCutscene must never throw');
    assert.deepEqual(rejected.results, new Array(rejected.count).fill(false));
    assert.equal((await playerState(page)).playing, false);
    assert.equal(await stageHidden(page), true);
    assert.equal(await stageChildren(page), 0);
    const after = await page.evaluate(() => ({
      layout: document.querySelector('#canvas').dataset.layout,
      homeScore: document.querySelector('[data-widget="home_score"]').getBoundingClientRect().toJSON(),
      widgets: document.querySelectorAll('#game-board [data-widget]').length,
    }));
    assert.deepEqual(after, before, 'a rejected program must leave the board exactly as it was');
    checks.push('malformed program ignored');

    // ---------------------------------------------------------------
    // 6. A layout push during a cutscene lands when the cutscene ends.
    // ---------------------------------------------------------------
    await page.evaluate(() => window.applyCutscene(window.__makeProgram({ play_id: 6, duration_ms: 8000 })));
    await page.waitForFunction(() => window.ScoreboardCutscenePlayer.state().phase === 'scene',
      undefined, { timeout: 2000 });
    await page.evaluate(() => {
      const later = JSON.parse(JSON.stringify(window.ScoreboardBoard.DEFAULT_LAYOUT));
      later.name = 'Saved during the cutscene';
      window.applyLayout(later);
    });
    assert.equal(await layoutName(page), 'Cutscene', 'a layout push must not interrupt the cutscene');
    await page.evaluate(() => window.endCutscene(6));
    await waitIdle(page, 2000);
    assert.equal(await layoutName(page), 'Saved during the cutscene');
    checks.push('a layout push during a cutscene lands on restore');

    // ---------------------------------------------------------------
    // 7. A penalty has no claw intro: it is on the stage from t=0.
    // ---------------------------------------------------------------
    // Python gives `penalty` `intro: none` (the claws are Tigers-branded and
    // a flag is nobody's), so there is no full-canvas moment to wait through:
    // the override and the scene both have to be up on the first frame.
    const penalty = await page.evaluate(() => {
      const accepted = window.applyCutscene(window.__makeProgram({
        play_id: 7,
        event: 'penalty',
        label: 'Penalty',
        team: null,
        pack_id: 'builtin:penalty',
        duration_ms: 8000,
        intro: { id: 'none', duration_ms: 0 },
        scene: { type: 'builtin', id: 'penalty' },
        texts: { headline: 'FLAG ON THE PLAY', subline: 'PENALTY', team_name: '' },
      }));
      const stage = document.querySelector('#cutscene-stage');
      return {
        accepted,
        hidden: stage.hidden,
        state: window.ScoreboardCutscenePlayer.state(),
        scenes: Array.from(stage.querySelectorAll('[data-scene]')).map(n => n.getAttribute('data-scene')),
        words: stage.textContent,
        bar: Boolean(document.querySelector('#game-board [data-item="broadcast_bar"]')),
        canvasHeight: document.querySelector('#canvas').getBoundingClientRect().height,
        stageHeight: stage.getBoundingClientRect().height,
      };
    });
    assert.equal(penalty.accepted, true);
    assert.equal(penalty.hidden, false);
    assert.equal(penalty.state.phase, 'scene', 'a penalty never enters the intro phase');
    assert.deepEqual(penalty.scenes, ['penalty']);
    assert.equal(penalty.bar, true, 'the bar is up on the first frame, with no intro to wait for');
    // Straight to the program's rectangle: no full-canvas intro moment.
    assert.ok(Math.abs(penalty.stageHeight - penalty.canvasHeight * 0.70) <= 1,
      `the penalty stage must be the program's rectangle: ${JSON.stringify(penalty)}`);
    // Both words, verbatim from the program, and no team name anywhere.
    assert.ok(penalty.words.includes('FLAG ON THE PLAY'), penalty.words);
    assert.ok(penalty.words.includes('PENALTY'), penalty.words);
    assert.ok(!penalty.words.includes('Tigers'), `a penalty is nobody's: ${penalty.words}`);
    await page.evaluate(() => window.endCutscene(7));
    await waitIdle(page, 2000);
    assert.equal(await layoutName(page), 'Saved during the cutscene');
    checks.push('a penalty plays with no intro');

    // ---------------------------------------------------------------
    // 8. MAKE SOME NOISE has no claw intro either: on the stage from t=0.
    // ---------------------------------------------------------------
    // Cutscenes v3 (.scratch/cutscenes-v3/spec.md 2.1): at 5 s a 1.6 s claw
    // would eat a third of the scene, so Python gives `make_some_noise`
    // `intro: none`. Same first-frame contract as the penalty, plus the one
    // thing the crowd scene owns: its headline box (`.cs-mn-headline`) holds
    // the program's headline as a single text node, verbatim.
    const noise = await page.evaluate(() => {
      const accepted = window.applyCutscene(window.__makeProgram({
        play_id: 8,
        event: 'make_some_noise',
        label: 'Make some noise',
        team: 'home',
        pack_id: 'builtin:make_some_noise',
        duration_ms: 8000,
        intro: { id: 'none', duration_ms: 0 },
        scene: { type: 'builtin', id: 'make_some_noise' },
        texts: { headline: 'MAKE SOME NOISE', subline: 'TIGERS FANS', team_name: 'Tigers' },
      }));
      const stage = document.querySelector('#cutscene-stage');
      const headline = stage.querySelector('.cs-mn-headline span');
      return {
        accepted,
        hidden: stage.hidden,
        state: window.ScoreboardCutscenePlayer.state(),
        scenes: Array.from(stage.querySelectorAll('[data-scene]')).map(n => n.getAttribute('data-scene')),
        words: stage.textContent,
        headline: headline ? headline.textContent : null,
        bar: Boolean(document.querySelector('#game-board [data-item="broadcast_bar"]')),
        canvasHeight: document.querySelector('#canvas').getBoundingClientRect().height,
        stageHeight: stage.getBoundingClientRect().height,
      };
    });
    assert.equal(noise.accepted, true);
    assert.equal(noise.hidden, false);
    assert.equal(noise.state.phase, 'scene', 'make some noise never enters the intro phase');
    assert.equal(noise.state.event, 'make_some_noise');
    assert.deepEqual(noise.scenes, ['make_some_noise']);
    assert.equal(noise.bar, true, 'the bar is up on the first frame, with no intro to wait for');
    assert.ok(Math.abs(noise.stageHeight - noise.canvasHeight * 0.70) <= 1,
      `the make-some-noise stage must be the program's rectangle: ${JSON.stringify(noise)}`);
    assert.equal(noise.headline, 'MAKE SOME NOISE', `.cs-mn-headline span must hold the headline verbatim: ${noise.headline}`);
    assert.ok(noise.words.includes('TIGERS FANS'), noise.words);
    await page.evaluate(() => window.endCutscene(8));
    await waitIdle(page, 2000);
    assert.equal(await layoutName(page), 'Saved during the cutscene');
    checks.push('make some noise plays with no intro');

    // ---------------------------------------------------------------
    // 9. The page has gained no operator control and no game command.
    // ---------------------------------------------------------------
    assert.equal(await page.locator('button,input,dialog,[data-command],[data-action]').count(), 0);
    checks.push('no controls');

    return { checks };
  } finally { await browser.close(); }
}

let input = ''; process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => main(JSON.parse(input)).then(result => console.log(JSON.stringify(result))).catch(error => { console.error(error); process.exitCode = 1; }));
