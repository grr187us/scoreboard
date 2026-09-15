/* The soccer scene registry, and the one scene it holds: `goal`.
 *
 * Mirrors ../../spectator/cutscenes/builtin.js's registry shape exactly
 * (`register(id, factory)`, `create(id, stageEl, program)`, `ids()`,
 * `helpers`) under the same global name, `window.ScoreboardCutsceneScenes`,
 * so ../cutscene.js (soccer's copy of the generic player) runs unmodified.
 * This file *is* soccer's builtin.js -- there is no separate registry file
 * because soccer has exactly one event so far (spec section 7,
 * `SOCCER_CUTSCENE_EVENTS = ("goal",)`).
 *
 * A *scene* is a factory: `factory(stageEl, program) -> {mount(), unmount()}`.
 * `mount()` builds its DOM and appends it to `stageEl`; `unmount()` takes it
 * back off and cancels anything it started.
 *
 * House rules, identical to football's scene files (never touched -- this is
 * a fresh, soccer-only file):
 *
 * - Every word on screen comes from `program.texts`, which Python filled
 *   from the live spectator view (`scoreboard.presentation.soccer_cutscenes.
 *   build_program`). This file never reads game state and never formats a
 *   value. The scoring team's name reaches the screen only through
 *   `textContent` -- never concatenated into `innerHTML` -- since it is
 *   operator/roster input, not a static string.
 * - The one static markup string in this file, `GOAL_MARKUP`, carries no
 *   text at all: it is a net-ripple SVG built once and assigned with
 *   `innerHTML` exactly because it is a `*_MARKUP` constant with nothing
 *   dynamic in it.
 * - Every colour comes from `program.theme`, published by the player as the
 *   `--cs-*` custom properties on the stage element -- including soccer's
 *   own `--cs-home-primary`/`--cs-away-primary`, which key the scene's
 *   colour to whichever side actually scored (spec section 7's departure
 *   from football's fixed Tigers palette). No brand hex literal appears
 *   anywhere in this file or in soccer.css.
 * - No network URL scheme anywhere in this file: nothing is ever fetched.
 * - Sizes come from `--stage-w` / `--stage-h`, the stage's own pixel size,
 *   never the viewport.
 * - A display that joins mid-cutscene (`program.elapsed_ms > 0`) shows the
 *   settled hold immediately, via the `cs-goal-resumed` class, rather than
 *   replaying the entrance.
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

  /** The root node for a scene: marked `data-scene="<id>"`. */
  function sceneRoot(id, className) {
    var root = doc.createElement('div');
    root.className = 'cs-scene ' + className;
    root.setAttribute('data-scene', id);
    return root;
  }

  /** Append a text node with its own class. Text is always written as a
   * text node, never as markup: a team name is operator/roster input. */
  function addText(parent, className, value) {
    var box = doc.createElement('div');
    box.className = className;
    var span = doc.createElement('span');
    span.textContent = value;
    box.appendChild(span);
    parent.appendChild(box);
    return box;
  }

  /** A plain div with a class, appended to `parent`. Structure only. */
  function addBox(parent, className) {
    var box = doc.createElement('div');
    box.className = className;
    parent.appendChild(box);
    return box;
  }

  /** The standard shape of a scene that is just "build a tree, then remove
   * it": `build(root, program)` fills the root, `stop(root)` (optional)
   * undoes anything outside it. */
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
    create: function (id, stageEl, program) {
      if (!Object.prototype.hasOwnProperty.call(factories, id) || !stageEl) {
        return null;
      }
      return factories[id](stageEl, program);
    },
    ids: function () {
      return order.slice();
    },
    helpers: {
      sceneRoot: sceneRoot,
      addText: addText,
      textOf: textOf,
      simpleScene: simpleScene
    }
  };

  var register = global.ScoreboardCutsceneScenes.register;

  /* ------------------------------------------------------------------ */
  /* goal -- 7 s, no intro, team-coloured                                */
  /* ------------------------------------------------------------------ */

  /*   0.0-0.6s  a net-ripple sweep crosses the stage from the goal mouth,
   *             a one-shot forwards animation (never `both`: it must not
   *             hold its 0% state before playback starts, the house rule
   *             this file keeps for every delayed one-shot)
   *   0.4-2.0s  GOAL slams in, huge, centred, and holds
   *   1.0s      the scoring team's name fades in below the headline, set
   *             with `textContent` only
   *   2.0-6.5s  hold: embers drift, the ground colour keyed off whichever
   *             side scored (`--cs-home-primary`/`--cs-away-primary`)
   *   6.5-7.0s  the player's own outro fade
   */

  /** A static net-ripple sweep: concentric arcs plus a net-mesh wash, no
   * text anywhere in the markup. Static SVG assigned once with `innerHTML`
   * is allowed here specifically because it is this `*_MARKUP` constant. */
  var GOAL_MARKUP = [
    '<svg class="cs-goal-net-svg" viewBox="0 0 160 90" preserveAspectRatio="xMidYMid slice"',
    ' aria-hidden="true" focusable="false">',
    '<defs><pattern id="cs-goal-mesh" width="6" height="6" patternUnits="userSpaceOnUse">',
    '<path class="cs-goal-mesh-line" d="M 0 0 L 6 6 M 6 0 L 0 6"/>',
    '</pattern></defs>',
    '<rect class="cs-goal-mesh-fill" x="0" y="0" width="160" height="90" fill="url(#cs-goal-mesh)"/>',
    '<circle class="cs-goal-ring cs-goal-ring-a" cx="20" cy="45" r="6"/>',
    '<circle class="cs-goal-ring cs-goal-ring-b" cx="20" cy="45" r="6"/>',
    '<circle class="cs-goal-ring cs-goal-ring-c" cx="20" cy="45" r="6"/>',
    '</svg>'
  ].join('');

  /** Embers rising through the hold, the same per-piece custom-property
   * idiom football's touchdown scene uses -- geometry only, deterministic so
   * a screenshot taken today can be compared with one taken after an edit. */
  var GOAL_EMBERS = 24;

  function sequence(seed) {
    var state = seed >>> 0;
    return function () {
      state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
      return state / 4294967296;
    };
  }

  function spread(next, low, high) {
    return low + (high - low) * next();
  }

  function setStageLength(node, name, axis, factor) {
    node.style.setProperty(name, 'calc(var(--stage-' + axis + ') * ' + factor.toFixed(5) + ')');
  }

  function addEmbers(parent) {
    var field = addBox(parent, 'cs-goal-embers');
    var next = sequence(0x60A1);
    for (var index = 0; index < GOAL_EMBERS; index += 1) {
      var ember = addBox(field, 'cs-goal-ember');
      ember.style.left = spread(next, 4, 96).toFixed(2) + '%';
      setStageLength(ember, '--cs-ed', 'w', spread(next, -0.05, 0.05));
      setStageLength(ember, '--cs-eh', 'h', -spread(next, 0.4, 0.9));
      setStageLength(ember, '--cs-es', 'h', spread(next, 0.006, 0.014));
      ember.style.animationDuration = Math.round(spread(next, 3000, 5000)) + 'ms';
      ember.style.animationDelay = Math.round(spread(next, 0, 4000)) + 'ms';
    }
    return field;
  }

  register('goal', simpleScene('goal', 'cs-goal', function (root, program, stageEl) {
    // A display joining late shows the settled hold at once, not the slam.
    if (program.elapsed_ms > 0) {
      root.classList.add('cs-goal-resumed');
    }
    root.classList.add(program.team === 'away' ? 'cs-goal-away' : 'cs-goal-home');
    // Football's player (../spectator/cutscene.js, reused unchanged) copies
    // only its own theme names onto the stage, so the two soccer colours are
    // set here from the program: still Python's values, never this file's.
    var theme = program.theme || {};
    var stage = stageEl || root;
    ['home_primary', 'away_primary'].forEach(function (name) {
      if (typeof theme[name] === 'string' && theme[name] !== '') {
        stage.style.setProperty('--cs-' + name.replace('_', '-'), theme[name]);
      }
    });

    addBox(root, 'cs-goal-ground');
    var ripple = addBox(root, 'cs-goal-ripple');
    ripple.innerHTML = GOAL_MARKUP;
    addBox(root, 'cs-goal-vignette');

    addEmbers(root);

    addText(root, 'cs-goal-headline', textOf(program, 'headline'));
    addText(root, 'cs-goal-subline', textOf(program, 'subline'));
  }));
})(window);
