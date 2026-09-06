/* The built-in, code-authored cutscene scenes, and the registry that holds
 * them.
 *
 * A *scene* is a factory: `factory(stageEl, program) -> {mount(), unmount()}`.
 * `mount()` builds its DOM and appends it to `stageEl`; `unmount()` takes it
 * back off and cancels anything it started. `cutscene.js` owns the timeline
 * and calls both; a scene owns nothing but its own pixels.
 *
 * House rules a scene must keep:
 *
 * - Every word on screen comes from `program.texts`, which Python filled from
 *   the view model. A scene never reads game state and never formats a value.
 * - Every colour comes from `program.theme`, published by the player as the
 *   `--cs-*` custom properties on the stage element. No brand hex lives here.
 * - Everything is sized against `--stage-w` / `--stage-h` (the stage's pixel
 *   size, set by the player and re-published on resize), never against the
 *   viewport, so the same scene reads correctly on a 1920x1080 wall and in
 *   the 640-wide practice window.
 * - Nothing is loaded: no font, no image, no stylesheet, no network of any
 *   kind. All CSS these scenes need lives in `../cutscene.css`; inline SVG
 *   markup here is static text, and never carries operator-supplied words.
 *
 * The three registrations at the bottom use literal string ids on purpose:
 * `tests/unit/test_cutscene_schema.py` greps this file for
 * `register('claw_scratch'`, `register('first_down'`, and
 * `register('touchdown'` to prove the Python id constants and these scenes
 * cannot drift apart.
 */

(function (global) {
  'use strict';

  var doc = global.document;
  var factories = {};
  var order = [];

  function isPlainObject(value) {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  /** One string out of `program.texts`, or '' -- never a computed value. */
  function textOf(program, key) {
    var texts = isPlainObject(program) && isPlainObject(program.texts) ? program.texts : {};
    var value = texts[key];
    return typeof value === 'string' ? value : '';
  }

  /** The root node for a scene: marked `data-scene="<id>"` so the host, the
   * browser tests, and a real-runtime harness can all see which scene is up. */
  function sceneRoot(id, className) {
    var root = doc.createElement('div');
    root.className = 'cs-scene ' + className;
    root.setAttribute('data-scene', id);
    return root;
  }

  /** Append a text node with its own class. Text is always written as a text
   * node, never as markup: a team name is operator input. */
  function addText(parent, className, value) {
    var box = doc.createElement('div');
    box.className = className;
    var span = doc.createElement('span');
    span.textContent = value;
    box.appendChild(span);
    parent.appendChild(box);
    return box;
  }

  /** The standard shape of a scene that is just "build a tree, then remove
   * it": `build(root, program)` fills the root, `stop(root)` (optional) undoes
   * anything outside it. */
  function simpleScene(id, className, build, stop) {
    return function (stageEl, program) {
      var root = null;
      return {
        mount: function () {
          root = sceneRoot(id, className);
          build(root, program, stageEl);
          stageEl.appendChild(root);
        },
        unmount: function () {
          if (stop) {
            stop(root, stageEl);
          }
          if (root && root.parentNode) {
            root.parentNode.removeChild(root);
          }
          root = null;
        }
      };
    };
  }

  global.ScoreboardCutsceneScenes = {
    /** Add a scene under `id`. A repeat id replaces the previous factory. */
    register: function (id, factory) {
      if (typeof id !== 'string' || id === '' || typeof factory !== 'function') {
        return false;
      }
      if (!Object.prototype.hasOwnProperty.call(factories, id)) {
        order.push(id);
      }
      factories[id] = factory;
      return true;
    },
    /** Build the scene `id` against `stageEl`; null when the id is unknown. */
    create: function (id, stageEl, program) {
      if (!Object.prototype.hasOwnProperty.call(factories, id) || !stageEl) {
        return null;
      }
      return factories[id](stageEl, program);
    },
    /** Every registered id, in registration order. */
    ids: function () {
      return order.slice();
    }
  };

  var register = global.ScoreboardCutsceneScenes.register;

  /* ------------------------------------------------------------------ */
  /* claw_scratch -- the intro                                           */
  /* ------------------------------------------------------------------ */

  /* Four tiger claw slashes rake across whatever board is showing, in quick
   * succession: a wide red glow with a bright white core, drawn on with
   * `stroke-dasharray` (pathLength="100" makes every path's dash maths
   * identical regardless of its real length). The canvas takes a short shake
   * on the first slash. The whole group then fades as the board morphs to the
   * bar underneath it -- the fade's length is the intro's own duration, which
   * Python put in the program, so a shorter intro does not leave the slashes
   * hanging.
   *
   * The SVG below is static markup with no operator text anywhere in it,
   * which is why it may be assigned as a string at all. */
  var CLAW_MARKUP = [
    '<svg class="cs-claw-svg" viewBox="0 0 160 90" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">',
    '<g class="cs-claw-glow">',
    '<path class="cs-slash" pathLength="100" d="M 6 -12 C 26 20, 44 52, 58 104"/>',
    '<path class="cs-slash" pathLength="100" d="M 40 -12 C 60 20, 78 52, 92 104"/>',
    '<path class="cs-slash" pathLength="100" d="M 74 -12 C 94 20, 112 52, 126 104"/>',
    '<path class="cs-slash" pathLength="100" d="M 108 -12 C 128 20, 146 52, 160 104"/>',
    '</g>',
    '<g class="cs-claw-core">',
    '<path class="cs-slash" pathLength="100" d="M 6 -12 C 26 20, 44 52, 58 104"/>',
    '<path class="cs-slash" pathLength="100" d="M 40 -12 C 60 20, 78 52, 92 104"/>',
    '<path class="cs-slash" pathLength="100" d="M 74 -12 C 94 20, 112 52, 126 104"/>',
    '<path class="cs-slash" pathLength="100" d="M 108 -12 C 128 20, 146 52, 160 104"/>',
    '</g>',
    '</svg>'
  ].join('');

  /** How long the intro runs, straight from the program (Python's
   * INTRO_DURATION_MS). Falls back to a value only if the program omits it. */
  function introMs(program) {
    var intro = isPlainObject(program) && isPlainObject(program.intro) ? program.intro : {};
    var value = intro.duration_ms;
    return typeof value === 'number' && isFinite(value) && value > 0 ? value : 1400;
  }

  register('claw_scratch', function (stageEl, program) {
    var root = null;
    var shakeTimer = null;

    function canvasNode() {
      return doc.getElementById('canvas');
    }

    return {
      mount: function () {
        root = sceneRoot('claw_scratch', 'cs-claw');
        root.style.setProperty('--cs-intro-ms', introMs(program) + 'ms');
        root.innerHTML = CLAW_MARKUP;
        stageEl.appendChild(root);
        var canvas = canvasNode();
        if (canvas) {
          canvas.classList.add('shake');
          shakeTimer = global.setTimeout(function () {
            shakeTimer = null;
            canvas.classList.remove('shake');
          }, 520);
        }
      },
      unmount: function () {
        if (shakeTimer !== null) {
          global.clearTimeout(shakeTimer);
          shakeTimer = null;
        }
        var canvas = canvasNode();
        if (canvas) {
          canvas.classList.remove('shake');
        }
        if (root && root.parentNode) {
          root.parentNode.removeChild(root);
        }
        root = null;
      }
    };
  });

  /* ------------------------------------------------------------------ */
  /* first_down                                                          */
  /* ------------------------------------------------------------------ */

  /* A wide navy stage: yard-line stripes slide steadily sideways behind a red
   * chevron that sweeps left to right, and the headline slams in over both
   * with a gold outline. The team name settles underneath, and the whole
   * thing then holds still -- the calm hold is what makes it readable from
   * the far end of the stands. */
  register('first_down', simpleScene('first_down', 'cs-firstdown', function (root, program) {
    var field = doc.createElement('div');
    field.className = 'cs-fd-field';
    root.appendChild(field);

    var glow = doc.createElement('div');
    glow.className = 'cs-fd-glow';
    root.appendChild(glow);

    var chevron = doc.createElement('div');
    chevron.className = 'cs-fd-chevron';
    root.appendChild(chevron);

    var bar = doc.createElement('div');
    bar.className = 'cs-fd-bar';
    root.appendChild(bar);

    addText(root, 'cs-fd-headline', textOf(program, 'headline'));
    addText(root, 'cs-fd-subline', textOf(program, 'subline'));
  }));

  /* ------------------------------------------------------------------ */
  /* touchdown                                                           */
  /* ------------------------------------------------------------------ */

  /** How many rays the touchdown burst draws. Enough to read as a burst,
   * few enough that none of them flickers. */
  var TOUCHDOWN_RAYS = 16;

  /* Bigger and bolder: a slow navy-to-blue gradient drift behind a burst of
   * gold and red rays from the centre, the headline scaling in with one
   * bounce, and the team name and current score settling below it. No strobe
   * and no fast alternation -- the rays fan out once and then hold. */
  register('touchdown', simpleScene('touchdown', 'cs-touchdown', function (root, program) {
    var drift = doc.createElement('div');
    drift.className = 'cs-td-drift';
    root.appendChild(drift);

    var rays = doc.createElement('div');
    rays.className = 'cs-td-rays';
    for (var index = 0; index < TOUCHDOWN_RAYS; index += 1) {
      var ray = doc.createElement('div');
      ray.className = index % 2 === 0 ? 'cs-td-ray cs-td-ray-gold' : 'cs-td-ray cs-td-ray-red';
      // Geometry, not a displayed value: fan the rays evenly and stagger
      // their start so the burst opens rather than snapping on. The angle is
      // a custom property, not an inline `transform`, because the opening
      // animation animates `transform` and would otherwise replace it.
      ray.style.setProperty('--cs-ray-angle', (index * (360 / TOUCHDOWN_RAYS)) + 'deg');
      ray.style.animationDelay = (index * 28) + 'ms';
      rays.appendChild(ray);
    }
    root.appendChild(rays);

    var burst = doc.createElement('div');
    burst.className = 'cs-td-burst';
    root.appendChild(burst);

    addText(root, 'cs-td-headline', textOf(program, 'headline'));

    var line = doc.createElement('div');
    line.className = 'cs-td-line';
    addText(line, 'cs-td-team', textOf(program, 'team_name'));
    addText(line, 'cs-td-score', textOf(program, 'score'));
    root.appendChild(line);
  }));
})(window);
