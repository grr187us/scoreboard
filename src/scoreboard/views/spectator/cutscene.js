/* The spectator page's cutscene player.
 *
 * The host hands this file one *program* -- a single JSON document built in
 * Python (`scoreboard.presentation.cutscenes.build_program`) that already
 * carries every value the animation shows: the duration, the intro, the stage
 * rectangle, the temporary layout, the theme colours, and the words. This
 * file computes none of that. It owns exactly two things Python cannot own:
 * *when* each step happens on this page's clock, and *what DOM* is on screen.
 *
 * Two globals, called by `WindowHost` through `evaluate_js`:
 *
 *   window.applyCutscene(program)   -- start (or replace) a cutscene
 *   window.endCutscene(playId)      -- end that cutscene early
 *
 * plus `window.ScoreboardCutscenePlayer = {state(), scenes}` for tests.
 *
 * The timeline, all times relative to applyCutscene (spec section 6.2):
 *
 *   t = 0                       stage full-canvas, class `intro`, intro scene
 *                               mounts over whatever board is showing
 *   t = 45% of intro duration   the board morphs to program.layout (the
 *                               Broadcast bar) under a 600 ms transition
 *   t = intro duration          intro unmounts; the stage shrinks to
 *                               program.stage; the main scene mounts
 *   t = duration - outro_ms     class `outro` (CSS fade)
 *   t = duration                scene unmounts, stage hidden, the operator's
 *                               layout comes back, state idle
 *   t = duration + 1500         safety net: end anyway if something above
 *                               never ran. The page never waits on the host
 *                               to give the board back.
 *
 * Three rules this file exists to keep:
 *
 * 1. The board always comes back. Every path out -- natural end, the host's
 *    endCutscene, a replacing cutscene, a malformed program, a scene that
 *    throws, a media file that will not load -- ends with the operator's
 *    layout on the wall.
 * 2. Nothing is fetched. Media is a `file:///` URI set on an <img>/<video>
 *    `src`, which is what WebView2 allows; a scripted network read of a
 *    file:// URL is not, and this file makes none.
 * 3. The clocks keep ticking. `applyView` is untouched here: the bar under
 *    the stage keeps updating ten times a second all the way through.
 */

(function (global) {
  'use strict';

  var doc = global.document;
  var canvas = doc.getElementById('canvas');
  var stage = doc.getElementById('cutscene-stage');

  /** How long the widget-geometry transition runs when the board morphs. Must
   * match the transition duration in cutscene.css. */
  var MORPH_MS = 600;
  /** When the `morphing` class comes back off #canvas -- a little after the
   * transition ends so nothing is caught mid-glide. */
  var MORPH_CLEAR_MS = 700;
  /** The intro is ~45 % done when the board starts morphing underneath it.
   * Picked by screenshot rather than by arithmetic: the claw intro's gouges
   * widen at the same fraction (`cs-gouge-widen` in cutscene.css), so the
   * tears appear to open *onto* the Broadcast bar as it arrives. Moving this
   * without moving that keyframe breaks the illusion, not the timeline. */
  var MORPH_AT_FRACTION = 0.45;
  /** The safety net: if the timeline above somehow did not finish, end here. */
  var SAFETY_NET_MS = 1500;
  /** A cancelled cutscene fades out faster than a completed one. */
  var CANCEL_OUTRO_MS = 300;
  /** A <video> that has not reached `loadeddata` by now is treated as failed. */
  var MEDIA_TIMEOUT_MS = 2000;

  /** The playback state, or null when idle. */
  var current = null;
  /** Every pending setTimeout id for the current cutscene. */
  var timers = [];
  /** The id of the pending "take `morphing` back off #canvas" timeout. */
  var morphTimer = null;

  function isPlainObject(value) {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  function isFiniteNumber(value) {
    return typeof value === 'number' && isFinite(value);
  }

  function numberOr(value, fallback) {
    return isFiniteNumber(value) ? value : fallback;
  }

  function notBelowZero(value) {
    return value < 0 ? 0 : value;
  }

  function stringOr(value, fallback) {
    return typeof value === 'string' ? value : fallback;
  }

  function later(delayMs, callback) {
    var id = global.setTimeout(function () {
      try {
        callback();
      } catch (error) {
        // One broken step must never strand the board on the cutscene layout;
        // the safety net below still fires and restores it.
        console.error('Cutscene step failed', error);
      }
    }, notBelowZero(delayMs));
    timers.push(id);
    return id;
  }

  function clearTimers() {
    for (var index = 0; index < timers.length; index += 1) {
      global.clearTimeout(timers[index]);
    }
    timers = [];
  }

  function spectator() {
    return global.ScoreboardSpectator || null;
  }

  function setOverrideLayout(layoutDoc) {
    var api = spectator();
    if (!api || typeof api.setOverrideLayout !== 'function') {
      return false;
    }
    return api.setOverrideLayout(layoutDoc);
  }

  /** Turn on the 600 ms widget-geometry transition, run `change`, and take the
   * class back off once the glide has finished. The class lives on #canvas so
   * one rule in cutscene.css covers every widget and free element on both
   * boards without board.css knowing anything about cutscenes. */
  function morph(change) {
    if (canvas) {
      canvas.classList.add('morphing');
    }
    try {
      change();
    } finally {
      if (morphTimer !== null) {
        global.clearTimeout(morphTimer);
      }
      morphTimer = global.setTimeout(function () {
        morphTimer = null;
        if (canvas) {
          canvas.classList.remove('morphing');
        }
      }, MORPH_CLEAR_MS);
    }
  }

  /* ------------------------------------------------------------------ */
  /* The stage                                                           */
  /* ------------------------------------------------------------------ */

  /** The intro's rectangle: the whole canvas. */
  var FULL_CANVAS = { x: 0, y: 0, width: 1, height: 1 };

  /** The rectangle the stage is currently placed over, so a window resize can
   * re-publish --stage-w/--stage-h without knowing which phase we are in. */
  var stageRect = FULL_CANVAS;

  /** Place the stage over `rect` (fractions of the canvas) and publish its
   * pixel size as --stage-w / --stage-h so a scene can size its type and its
   * artwork against the stage rather than against the viewport. Geometry is
   * inline so the same helper serves the full-canvas intro and the smaller
   * scene rectangle; `.intro` only carries the intro's *look*. */
  function placeStage(rect) {
    stageRect = rect;
    var x = numberOr(rect.x, 0);
    var y = numberOr(rect.y, 0);
    var width = numberOr(rect.width, 1);
    var height = numberOr(rect.height, 1);
    stage.style.left = (x * 100) + '%';
    stage.style.top = (y * 100) + '%';
    stage.style.width = (width * 100) + '%';
    stage.style.height = (height * 100) + '%';
    var box = canvas ? canvas.getBoundingClientRect() : { width: 0, height: 0 };
    stage.style.setProperty('--stage-w', (box.width * width) + 'px');
    stage.style.setProperty('--stage-h', (box.height * height) + 'px');
  }

  /** Re-publish --stage-w/--stage-h after the window changes size, so a scene
   * mounted at one size still looks right at another. */
  function refreshStageSize() {
    if (!current) {
      return;
    }
    placeStage(stageRect);
  }

  /** Copy the program's palette onto the stage as custom properties. Every
   * built-in scene paints from these, so the brand colours arrive from Python
   * and are never written into this page's CSS. */
  function applyTheme(theme) {
    var names = ['navy', 'navy_elevated', 'blue', 'red', 'blue_light', 'white', 'mist', 'ink',
                 'gold', 'flag'];
    for (var index = 0; index < names.length; index += 1) {
      var name = names[index];
      var value = isPlainObject(theme) ? theme[name] : null;
      if (typeof value === 'string' && value !== '') {
        stage.style.setProperty('--cs-' + name.replace('_', '-'), value);
      }
    }
  }

  function showStage(visible) {
    stage.hidden = !visible;
    stage.setAttribute('aria-hidden', 'true');
  }

  function emptyStage() {
    while (stage.firstChild) {
      stage.removeChild(stage.firstChild);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Scenes                                                              */
  /* ------------------------------------------------------------------ */

  function registry() {
    return global.ScoreboardCutsceneScenes || null;
  }

  /** Mount one built-in scene by id. Returns the scene object (so it can be
   * unmounted) or null when the id is unknown or the scene throws. */
  function mountBuiltin(id, program) {
    var scenes = registry();
    if (!scenes || typeof scenes.create !== 'function') {
      console.error('Cutscene scene registry is missing');
      return null;
    }
    var scene = null;
    try {
      scene = scenes.create(id, stage, program);
    } catch (error) {
      console.error('Cutscene scene ' + id + ' could not be created', error);
      return null;
    }
    if (!scene) {
      console.error('Cutscene scene ' + id + ' is not registered');
      return null;
    }
    try {
      scene.mount();
    } catch (error) {
      console.error('Cutscene scene ' + id + ' failed to mount', error);
      return null;
    }
    return scene;
  }

  function unmountScene(scene) {
    if (!scene || typeof scene.unmount !== 'function') {
      return;
    }
    try {
      scene.unmount();
    } catch (error) {
      console.error('Cutscene scene failed to unmount', error);
    }
  }

  /** A pack's own media: a muted <video> or an <img> whose `src` is the
   * `file:///` URI Python put in the program, verbatim. If it errors -- or a
   * video never reaches `loadeddata` -- the built-in fallback the program
   * carries takes over for the rest of the cutscene, so a missing or
   * unplayable file costs the crowd nothing. */
  function createMediaScene(sceneSpec, program) {
    var root = null;
    var media = null;
    var timeoutId = null;
    var fallbackScene = null;
    var done = false;

    function clearWatchdog() {
      if (timeoutId !== null) {
        global.clearTimeout(timeoutId);
        timeoutId = null;
      }
    }

    function fallBack(reason) {
      if (done) {
        return;
      }
      done = true;
      clearWatchdog();
      console.error('Cutscene media unusable (' + reason + '); using the built-in scene instead');
      if (root && root.parentNode) {
        root.parentNode.removeChild(root);
      }
      root = null;
      media = null;
      var fallback = isPlainObject(sceneSpec.fallback) ? sceneSpec.fallback : null;
      var fallbackId = fallback ? stringOr(fallback.id, '') : '';
      if (fallbackId) {
        fallbackScene = mountBuiltin(fallbackId, program);
      }
    }

    return {
      mount: function () {
        root = doc.createElement('div');
        root.className = 'cutscene-scene cutscene-media';
        root.setAttribute('data-scene', 'media');
        var fit = sceneSpec.fit === 'contain' ? 'contain' : 'cover';
        root.style.setProperty('--cs-fit', fit);
        if (sceneSpec.type === 'video') {
          media = doc.createElement('video');
          media.autoplay = true;
          media.muted = true;
          media.setAttribute('muted', '');
          media.setAttribute('playsinline', '');
          media.setAttribute('preload', 'auto');
          media.loop = sceneSpec.loop === true;
          media.addEventListener('loadeddata', function () {
            done = true;
            clearWatchdog();
          });
          timeoutId = global.setTimeout(function () {
            timeoutId = null;
            fallBack('the video did not load in time');
          }, MEDIA_TIMEOUT_MS);
        } else {
          media = doc.createElement('img');
          media.alt = '';
          media.addEventListener('load', function () {
            done = true;
          });
        }
        media.addEventListener('error', function () {
          fallBack('the file could not be opened');
        });
        media.src = stringOr(sceneSpec.src, '');
        root.appendChild(media);
        stage.appendChild(root);
      },
      unmount: function () {
        done = true;
        clearWatchdog();
        if (media && media.tagName === 'VIDEO') {
          try {
            media.pause();
          } catch (error) {
            // A video that never started cannot be paused; nothing to do.
          }
        }
        if (root && root.parentNode) {
          root.parentNode.removeChild(root);
        }
        root = null;
        media = null;
        unmountScene(fallbackScene);
        fallbackScene = null;
      }
    };
  }

  /** Mount the program's main scene: a built-in, or the pack's media with the
   * built-in fallback standing by. */
  function mountMainScene(program) {
    var sceneSpec = program.scene;
    if (sceneSpec.type === 'builtin') {
      return mountBuiltin(stringOr(sceneSpec.id, ''), program);
    }
    var scene = createMediaScene(sceneSpec, program);
    try {
      scene.mount();
    } catch (error) {
      console.error('Cutscene media failed to mount', error);
      return null;
    }
    return scene;
  }

  /* ------------------------------------------------------------------ */
  /* Validation                                                          */
  /* ------------------------------------------------------------------ */

  /** Everything the timeline below depends on, checked once up front. A
   * program that fails here is ignored outright: the board is never touched,
   * so a bad push from a future host costs the wall nothing. */
  function validate(program) {
    if (!isPlainObject(program)) {
      return 'the program is not an object';
    }
    if (!isFiniteNumber(program.play_id)) {
      return 'play_id is missing or not a number';
    }
    if (!isFiniteNumber(program.duration_ms) || program.duration_ms <= 0) {
      return 'duration_ms is missing or not a positive number';
    }
    if (!isPlainObject(program.stage)) {
      return 'stage is missing';
    }
    if (!isPlainObject(program.layout) || !isPlainObject(program.layout.widgets)) {
      return 'layout is not a usable layout document';
    }
    if (!isPlainObject(program.scene)) {
      return 'scene is missing';
    }
    var type = program.scene.type;
    if (type !== 'builtin' && type !== 'video' && type !== 'image') {
      return 'scene.type is not one of builtin/video/image';
    }
    if (type === 'builtin' && !stringOr(program.scene.id, '')) {
      return 'a builtin scene needs an id';
    }
    if (type !== 'builtin' && !stringOr(program.scene.src, '')) {
      return 'a media scene needs a src';
    }
    return null;
  }

  /* ------------------------------------------------------------------ */
  /* The timeline                                                        */
  /* ------------------------------------------------------------------ */

  /** Unmount whatever is on the stage, hide it, and hand the board back. */
  function finish() {
    if (!current) {
      return;
    }
    clearTimers();
    unmountScene(current.introScene);
    unmountScene(current.scene);
    current = null;
    emptyStage();
    stage.classList.remove('intro');
    stage.classList.remove('outro');
    showStage(false);
    if (canvas) {
      canvas.classList.remove('shake');
    }
    morph(function () {
      setOverrideLayout(null);
    });
  }

  /** The tail of the timeline, shared by the natural end and an early end:
   * fade for `outroMs`, then restore. */
  function scheduleOutro(outroMs, delayMs) {
    later(delayMs, function () {
      if (!current) {
        return;
      }
      current.phase = 'outro';
      stage.style.setProperty('--cs-outro-ms', outroMs + 'ms');
      stage.classList.add('outro');
    });
    later(delayMs + outroMs, finish);
    later(delayMs + outroMs + SAFETY_NET_MS, function () {
      // The safety net. If every step above ran, `current` is already null and
      // this does nothing; if one of them did not, the board comes back here.
      if (current) {
        console.error('Cutscene safety net fired; restoring the board');
        finish();
      }
    });
  }

  /** Swap the stage from the full-canvas intro to the program's rectangle and
   * mount the main scene. */
  function beginMainScene() {
    if (!current) {
      return;
    }
    unmountScene(current.introScene);
    current.introScene = null;
    emptyStage();
    stage.classList.remove('intro');
    if (canvas) {
      canvas.classList.remove('shake');
    }
    placeStage(current.program.stage);
    current.phase = 'scene';
    current.scene = mountMainScene(current.program);
  }

  /**
   * Start (or replace) a cutscene. Returns true when the program was accepted.
   *
   * Three entries into the same timeline:
   *
   * - *fresh*: the full sequence, starting with the full-canvas intro over
   *   whatever board is showing.
   * - *replace* (a cutscene is already playing): the board is already on the
   *   Broadcast bar, so there is no morph to run and no full-canvas moment --
   *   the new program's intro plays inside the stage rectangle instead.
   * - *resume* (`elapsed_ms` > 0, from `api.get_cutscene()` on page load): the
   *   page joined mid-cutscene. Skip the intro entirely, put the override and
   *   the scene up at once, and run the rest of the timeline from what is
   *   left. The host still sends endCutscene; the safety net covers it if not.
   */
  global.applyCutscene = function (program) {
    var problem = validate(program);
    if (problem !== null) {
      console.error('Cutscene program ignored: ' + problem, program);
      return false;
    }

    var replacing = current !== null;
    var elapsed = notBelowZero(numberOr(program.elapsed_ms, 0));
    var remaining = notBelowZero(program.duration_ms - elapsed);
    var resuming = elapsed > 0;

    // Tear the old cutscene down without giving the board back: whatever the
    // new program is, it wants the bar, not the operator's layout.
    clearTimers();
    if (replacing) {
      unmountScene(current.introScene);
      unmountScene(current.scene);
    }
    emptyStage();
    stage.classList.remove('outro');

    var intro = isPlainObject(program.intro) ? program.intro : {};
    var introId = stringOr(intro.id, 'none');
    var introMs = notBelowZero(numberOr(intro.duration_ms, 0));
    var playsIntro = !resuming && introId !== 'none' && introMs > 0;
    var outroMs = notBelowZero(numberOr(program.outro_ms, 0));

    current = {
      program: program,
      play_id: program.play_id,
      phase: playsIntro ? 'intro' : 'scene',
      resumed: resuming,
      replaced: replacing,
      introScene: null,
      scene: null
    };

    applyTheme(program.theme);
    showStage(true);

    if (playsIntro && !replacing) {
      // Fresh: the intro owns the whole canvas, and the board morphs to the
      // bar underneath it 45 % of the way through.
      stage.classList.add('intro');
      placeStage(FULL_CANVAS);
      current.introScene = mountBuiltin(introId, program);
      later(introMs * MORPH_AT_FRACTION, function () {
        morph(function () {
          setOverrideLayout(program.layout);
        });
      });
      later(introMs, beginMainScene);
    } else if (playsIntro) {
      // Replacing: the bar is already up, so the intro plays inside the stage
      // rectangle rather than over the whole wall.
      placeStage(program.stage);
      setOverrideLayout(program.layout);
      current.introScene = mountBuiltin(introId, program);
      later(introMs, beginMainScene);
    } else {
      // No intro (or a resume): straight to the scene.
      placeStage(program.stage);
      if (replacing || resuming) {
        setOverrideLayout(program.layout);
      } else {
        morph(function () {
          setOverrideLayout(program.layout);
        });
      }
      current.scene = mountMainScene(program);
    }

    scheduleOutro(outroMs, notBelowZero(remaining - outroMs));
    return true;
  };

  /**
   * End the cutscene `playId` early (the operator pressed Cancel, or the
   * host's own timer expired first). A play id that is not the one playing is
   * ignored -- a late `end` for a cutscene that was already replaced must not
   * cut the new one short.
   */
  global.endCutscene = function (playId) {
    if (!current || playId !== current.play_id) {
      return false;
    }
    clearTimers();
    scheduleOutro(CANCEL_OUTRO_MS, 0);
    return true;
  };

  global.addEventListener('resize', refreshStageSize);

  global.ScoreboardCutscenePlayer = {
    /** What is playing, for tests and for a real-runtime harness. */
    state: function () {
      if (!current) {
        return { playing: false, play_id: null, phase: 'idle', event: null, scene_id: null, resumed: false };
      }
      return {
        playing: true,
        play_id: current.play_id,
        phase: current.phase,
        event: stringOr(current.program.event, null),
        scene_id: stringOr(current.program.scene.id, null),
        resumed: current.resumed
      };
    },
    scenes: registry()
  };
})(window);
