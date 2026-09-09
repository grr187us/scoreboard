/* The scene registry, and the two scenes that belong to no team: the tiger
 * claw intro and the penalty flag.
 *
 * A *scene* is a factory: `factory(stageEl, program) -> {mount(), unmount()}`.
 * `mount()` builds its DOM and appends it to `stageEl`; `unmount()` takes it
 * back off and cancels anything it started. `cutscene.js` owns the timeline
 * and calls both; a scene owns nothing but its own pixels.
 *
 * The Tigers' own scenes (`first_down`, `touchdown`) live in `tigers.js`,
 * which loads after this file and reuses the helpers exposed here as
 * `ScoreboardCutsceneScenes.helpers`.
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
 *   markup here is a static `*_MARKUP` constant, and never carries
 *   operator-supplied words.
 *
 * The two registrations below use literal string ids on purpose:
 * `tests/unit/test_cutscene_schema.py` greps this folder for
 * `register('claw_scratch'` and `register('penalty'` to prove the Python id
 * constants and these scenes cannot drift apart.
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
    },
    /** The four helpers a scene file needs. `cutscenes/tigers.js` loads after
     * this file and builds its scenes out of exactly these, so the two scene
     * files cannot drift apart on how a root is marked or how a word reaches
     * the screen. */
    helpers: {
      sceneRoot: sceneRoot,
      addText: addText,
      textOf: textOf,
      simpleScene: simpleScene
    }
  };

  var register = global.ScoreboardCutsceneScenes.register;

  /** How long the intro runs, straight from the program (Python's
   * INTRO_DURATION_MS). Falls back to a value only if the program omits it. */
  function introMs(program) {
    var intro = isPlainObject(program) && isPlainObject(program.intro) ? program.intro : {};
    var value = intro.duration_ms;
    return typeof value === 'number' && isFinite(value) && value > 0 ? value : 1600;
  }

  /* ------------------------------------------------------------------ */
  /* claw_scratch -- the intro                                           */
  /* ------------------------------------------------------------------ */

  /* A strike, not four neon streaks.
   *
   * A big dark paw silhouette swipes diagonally across the whole wall in
   * 180 ms, dragging two blurred ghost copies behind it. In its wake four
   * uneven gouges *tear* open -- each one a filled tapered wedge with a
   * jagged inner edge, wiped on along its own length, white-hot for a
   * quarter of a second and then a red-and-gold rip with an ink outline, as
   * if light were coming through the board. One white impact flash, one
   * short heavy shake, and a spray of debris flung along the swipe. Around
   * the moment the board morphs to the Broadcast bar underneath (the
   * player's MORPH_AT_FRACTION, 45 %), the gouges widen and their glow
   * brightens -- the strike has opened the board onto the scene behind it.
   * Everything then fades out together, ending exactly at the intro's own
   * duration, which Python put in the program.
   *
   * The two SVG strings below are static markup with no operator text
   * anywhere in them, which is why they may be assigned as strings at all. */

  /** The paw: pad, four toes, four unsheathed claws, as one filled path with
   * nine subpaths. Authored upright in viewBox units around (22, 22); CSS
   * rotates it onto the swipe's heading and the swipe animation carries it
   * across. */
  var PAW_PATH = [
    // Four toes in an arc, each *overlapping* the pad -- a gap between them
    // and it reads as a spider rather than a paw, which is what a screenshot
    // caught the first time round, ...
    'M 0.5 20.5 C 0.5 13.9, 10.5 13.9, 10.5 20.5 C 10.5 27.1, 0.5 27.1, 0.5 20.5 Z',
    'M 11.0 13.5 C 11.0 6.5, 21.0 6.5, 21.0 13.5 C 21.0 20.7, 11.0 20.7, 11.0 13.5 Z',
    'M 23.0 13.5 C 23.0 6.5, 33.0 6.5, 33.0 13.5 C 33.0 20.7, 23.0 20.7, 23.0 13.5 Z',
    'M 33.5 21.0 C 33.5 14.4, 43.5 14.4, 43.5 21.0 C 43.5 27.6, 33.5 27.6, 33.5 21.0 Z',
    // ... each with a hooked claw out of its leading edge, ...
    'M 2.0 16.0 C -1.4 11.1, -5.0 6.9, -9.0 3.1 C -5.6 4.5, -0.6 8.1, 4.4 13.1 Z',
    'M 12.6 8.1 C 11.4 2.5, 10.2 -2.9, 9.0 -8.1 C 12.0 -3.9, 14.8 0.9, 16.6 5.9 Z',
    'M 27.6 5.9 C 29.4 0.9, 32.2 -3.9, 35.2 -8.1 C 34.0 -2.9, 32.8 2.5, 31.6 8.1 Z',
    'M 39.6 13.1 C 44.6 8.1, 49.6 4.5, 53.0 3.1 C 49.0 6.9, 45.4 11.1, 42.0 16.0 Z',
    // ... over the pad.
    'M 8.5 28.0 C 8.5 23.0, 15.0 20.0, 22.0 20.0 C 29.0 20.0, 35.5 23.0, 35.5 28.0'
      + ' C 35.5 37.0, 29.5 44.5, 22.0 44.5 C 14.5 44.5, 8.5 37.0, 8.5 28.0 Z'
  ].join(' ');

  /** One gouge, authored in its own space: 100 long along +x, pointed at both
   * ends, widest a third of the way in, and torn (five notches) down the
   * inner edge. Every gouge in the markup is this same shape placed by a
   * `translate/rotate/scale` -- which is what makes their lengths, angles and
   * spacing uneven without four hand-drawn paths. */
  var GOUGE_PATH = [
    'M 0 0',
    'C 9 -0.35, 23 -0.95, 33 -1.2',
    'C 52 -1.5, 76 -0.9, 100 0',
    'C 90 0.85, 86 2.4, 80 1.15',
    'C 75 0.35, 73 2.6, 66 1.5',
    'C 60 0.75, 58 2.9, 51 1.85',
    'C 45 1.15, 43 3.0, 36 1.9',
    'C 30 1.15, 27 2.6, 21 1.35',
    'C 14 0.7, 6 0.55, 0 0',
    'Z'
  ].join(' ');

  /** Where the four gouges sit: `translate(x, y) rotate(deg) scale(length /
   * 100)`, in the 160x90 viewBox. Their top ends are 17.6, 14.4 and 20.8
   * units apart -- 11 %, 9 % and 13 % of the width -- their angles differ by
   * a few degrees and their lengths by a third, so nothing about the rake
   * looks ruled. All four start above the wall and three of them finish past
   * its bottom edge: a claw does not stop politely inside the frame. */
  var GOUGE_PLACES = [
    'translate(26, -14) rotate(58) scale(1.30)',
    'translate(43.6, 6) rotate(61) scale(1.05)',
    'translate(58, -8) rotate(59) scale(1.42)',
    'translate(78.8, 4) rotate(62) scale(1.12)'
  ];

  function gougeMarkup() {
    var parts = [];
    for (var index = 0; index < GOUGE_PLACES.length; index += 1) {
      parts.push(
        '<g class="cs-gouge" transform="' + GOUGE_PLACES[index] + '">',
        '<g class="cs-gouge-open">',
        '<path class="cs-gouge-lip" d="' + GOUGE_PATH + '"/>',
        '<path class="cs-gouge-rip" d="' + GOUGE_PATH + '"/>',
        '<path class="cs-gouge-core" d="' + GOUGE_PATH + '"/>',
        '</g>',
        '</g>'
      );
    }
    return parts.join('');
  }

  var CLAW_MARKUP = [
    '<div class="cs-claw-flash"></div>',
    '<svg class="cs-claw-svg cs-claw-paw-svg" viewBox="0 0 160 90"',
    ' preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">',
    '<g class="cs-paw-swipe cs-paw-ghost-b"><g class="cs-paw-fit">',
    '<path class="cs-paw" d="' + PAW_PATH + '"/></g></g>',
    '<g class="cs-paw-swipe cs-paw-ghost-a"><g class="cs-paw-fit">',
    '<path class="cs-paw" d="' + PAW_PATH + '"/></g></g>',
    '<g class="cs-paw-swipe cs-paw-lead"><g class="cs-paw-fit">',
    '<path class="cs-paw" d="' + PAW_PATH + '"/></g></g>',
    '</svg>',
    '<svg class="cs-claw-svg cs-claw-tear-svg" viewBox="0 0 160 90"',
    ' preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">',
    '<defs><linearGradient id="cs-rip-fill" x1="0" y1="0" x2="0" y2="1">',
    '<stop class="cs-rip-edge" offset="0"/>',
    '<stop class="cs-rip-edge" offset="0.30"/>',
    '<stop class="cs-rip-hot" offset="0.44"/>',
    '<stop class="cs-rip-edge" offset="0.62"/>',
    '<stop class="cs-rip-edge" offset="1"/>',
    '</linearGradient></defs>',
    gougeMarkup(),
    '</svg>'
  ].join('');

  /** How many fragments the strike throws. Enough to read as debris off a
   * struck board, few enough that none of them is a distraction. */
  var DEBRIS_COUNT = 18;

  /** The debris. Built here rather than in the markup constant because each
   * fragment carries its own start point, throw vector and spin -- geometry,
   * not words, and never a value the crowd reads. The three multipliers below
   * are only there to spread eighteen fragments deterministically; nothing
   * about them is random, so every replay looks the same. */
  function addDebris(root) {
    var box = doc.createElement('div');
    box.className = 'cs-claw-debris';
    for (var index = 0; index < DEBRIS_COUNT; index += 1) {
      var a = ((index * 37) % 100) / 100;
      var b = ((index * 61) % 100) / 100;
      var c = ((index * 83) % 100) / 100;
      var bit = doc.createElement('div');
      var kind = index % 3;
      bit.className = 'cs-claw-bit '
        + (kind === 0 ? 'cs-claw-bit-navy' : (kind === 1 ? 'cs-claw-bit-white' : 'cs-claw-bit-red'))
        + (index % 4 === 3 ? ' cs-claw-bit-tri' : '');
      bit.style.left = (10 + a * 64) + '%';
      bit.style.top = (8 + b * 62) + '%';
      bit.style.setProperty('--cs-bit-size', (0.012 + c * 0.020).toFixed(4));
      bit.style.setProperty('--cs-bit-dx', (0.09 + c * 0.24).toFixed(4));
      bit.style.setProperty('--cs-bit-dy', (0.14 + a * 0.38).toFixed(4));
      bit.style.setProperty('--cs-bit-rot', (140 + ((index * 53) % 47) * 11) + 'deg');
      bit.style.animationDelay = (40 + ((index * 29) % 15) * 10) + 'ms';
      box.appendChild(bit);
    }
    root.appendChild(box);
  }

  /** How long the `shake` class stays on #canvas. A little past the shake
   * animation itself so nothing is caught mid-swing; `cutscene.js` also takes
   * the class off on every path out, so this timer is only the tidy case. */
  var SHAKE_CLEAR_MS = 400;

  /* First down's material opening: four translated copies of one curved
   * swipe. Middle digits contact slightly earlier; outer digits leave
   * shorter tracks. Their 21-unit lateral spacing exceeds the maximum tear
   * width throughout the stroke, including the opening animation. No
   * independently rotated gouges or unrelated cartoon paw silhouette. */
  var FIELD_CLAW_PATH = 'M 0 0 C 1 22 13 52 31 89 C 24 56 8 24 0 0 Z';
  var FIELD_CLAW_PLACES = [
    'translate(25 4) scale(1 .86)',
    'translate(46 -5)',
    'translate(67 -4)',
    'translate(88 5) scale(1 .88)'
  ];
  var FIELD_CLAW_MARKUP = [
    '<div class="cs-field-claw-surface"></div>',
    '<svg class="cs-field-claw-svg" viewBox="0 0 160 90"',
    ' preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">',
    '<defs><filter id="cs-field-torn-edge" x="-30%" y="-10%" width="160%" height="120%">',
    '<feTurbulence type="fractalNoise" baseFrequency=".65" numOctaves="2" seed="31" result="grain"/>',
    '<feDisplacementMap in="SourceGraphic" in2="grain" scale=".65" xChannelSelector="R" yChannelSelector="G"/>',
    '</filter></defs>',
    FIELD_CLAW_PLACES.map(function (place) {
      return '<g class="cs-field-claw-track" transform="' + place + '">'
        + '<g class="cs-field-claw-reveal">'
        + '<path class="cs-field-claw-shadow" d="' + FIELD_CLAW_PATH + '"/>'
        + '<path class="cs-field-claw-edge" d="' + FIELD_CLAW_PATH + '"/>'
        + '<path class="cs-field-claw-cut" d="' + FIELD_CLAW_PATH + '"/>'
        + '</g></g>';
    }).join(''),
    '</svg>'
  ].join('');

  /* Touchdown's opening: the same material claw as first down, but the
   * whole paw. Five tracks instead of four, each a third longer and wider,
   * spread 24 units apart (wider than any track's maximum tear, so the cuts
   * never merge), a single white impact flash, and a red bleed that pours
   * out of the cuts at the moment the board morphs beneath them. The board
   * itself takes a shake twice as heavy as the ordinary strike, through the
   * `--cs-shake` multiplier the cs-shake keyframes read. */
  var TOUCHDOWN_CLAW_PLACES = [
    'translate(12 8) scale(1.22 1.04)',
    'translate(36 -6) scale(1.3 1.18)',
    'translate(60 -12) scale(1.32 1.24)',
    'translate(84 -8) scale(1.3 1.18)',
    'translate(108 6) scale(1.22 1.04)'
  ];
  var TOUCHDOWN_CLAW_MARKUP = [
    '<div class="cs-td-claw-bleed"></div>',
    '<div class="cs-td-claw-flash"></div>',
    '<svg class="cs-field-claw-svg" viewBox="0 0 160 90"',
    ' preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">',
    '<defs><filter id="cs-td-torn-edge" x="-30%" y="-10%" width="160%" height="120%">',
    '<feTurbulence type="fractalNoise" baseFrequency=".55" numOctaves="2" seed="47" result="grain"/>',
    '<feDisplacementMap in="SourceGraphic" in2="grain" scale=".9" xChannelSelector="R" yChannelSelector="G"/>',
    '</filter></defs>',
    TOUCHDOWN_CLAW_PLACES.map(function (place) {
      return '<g class="cs-td-claw-track" transform="' + place + '">'
        + '<g class="cs-field-claw-reveal cs-td-claw-reveal">'
        + '<path class="cs-field-claw-shadow" d="' + FIELD_CLAW_PATH + '"/>'
        + '<path class="cs-field-claw-edge" d="' + FIELD_CLAW_PATH + '"/>'
        + '<path class="cs-field-claw-cut" d="' + FIELD_CLAW_PATH + '"/>'
        + '</g></g>';
    }).join(''),
    '</svg>'
  ].join('');

  /** How much heavier the touchdown strike shakes the board than the
   * ordinary claw (`cs-shake` in cutscene.css multiplies its offsets by
   * `--cs-shake`, which is 1 when unset). */
  var TOUCHDOWN_SHAKE = 2.2;

  register('claw_scratch', function (stageEl, program) {
    var root = null;
    var shakeTimer = null;

    function canvasNode() {
      return doc.getElementById('canvas');
    }

    return {
      mount: function () {
        if (program.event === 'first_down') {
          root = sceneRoot('claw_scratch', 'cs-field-claw');
          root.style.setProperty('--cs-intro-ms', introMs(program) + 'ms');
          root.innerHTML = FIELD_CLAW_MARKUP;
          stageEl.appendChild(root);
          return;
        }
        if (program.event === 'touchdown') {
          root = sceneRoot('claw_scratch', 'cs-field-claw cs-td-claw');
          root.style.setProperty('--cs-intro-ms', introMs(program) + 'ms');
          root.innerHTML = TOUCHDOWN_CLAW_MARKUP;
          stageEl.appendChild(root);
          var struck = canvasNode();
          if (struck) {
            struck.style.setProperty('--cs-shake', String(TOUCHDOWN_SHAKE));
            struck.classList.add('shake');
            shakeTimer = global.setTimeout(function () {
              shakeTimer = null;
              struck.classList.remove('shake');
              struck.style.removeProperty('--cs-shake');
            }, SHAKE_CLEAR_MS);
          }
          return;
        }
        root = sceneRoot('claw_scratch', 'cs-claw');
        root.style.setProperty('--cs-intro-ms', introMs(program) + 'ms');
        root.innerHTML = CLAW_MARKUP;
        addDebris(root);
        stageEl.appendChild(root);
        var canvas = canvasNode();
        if (canvas) {
          canvas.classList.add('shake');
          shakeTimer = global.setTimeout(function () {
            shakeTimer = null;
            canvas.classList.remove('shake');
          }, SHAKE_CLEAR_MS);
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
          canvas.style.removeProperty('--cs-shake');
        }
        if (root && root.parentNode) {
          root.parentNode.removeChild(root);
        }
        root = null;
      }
    };
  });

  /* ------------------------------------------------------------------ */
  /* penalty                                                             */
  /* ------------------------------------------------------------------ */

  /* Nobody's colours but the flag's. A penalty is not the Tigers' moment and
   * must not look like one: no red, no blue panel, no crest -- a yellow flag
   * arcing in over a navy vignette, landing with a bounce and a puff of dust,
   * two yellow slabs sliding in behind the words, and then a long calm hold.
   *
   * The headline is `program.texts.headline` as ONE text node. `FLAG` reads
   * as its own line because `::first-line` is sized so the second word cannot
   * fit beside it -- CSS does the breaking. Splitting the string in
   * JavaScript would be this file formatting a value, which is Python's job. */

  var PENALTY_FLAG_MARKUP = [
    '<svg class="cs-pen-flag-svg" viewBox="0 0 100 80" aria-hidden="true" focusable="false">',
    // A square of cloth with four corners and rippled edges -- a thrown flag,
    // not a beanbag. The weighted knot sits on the left-hand corner.
    '<path class="cs-pen-cloth" d="M 10 30',
    ' C 20 19, 32 9, 52 6 C 68 11, 79 27, 92 44',
    ' C 83 59, 63 61, 46 74 C 33 68, 15 51, 10 30 Z"/>',
    '<path class="cs-pen-fold" d="M 17 32 C 36 36, 58 41, 86 45"/>',
    '<path class="cs-pen-fold" d="M 51 11 C 50 30, 49 51, 47 69"/>',
    '<path class="cs-pen-fold" d="M 27 20 C 38 33, 52 47, 68 55"/>',
    '<circle class="cs-pen-knot" cx="11" cy="30" r="8"/>',
    '</svg>'
  ].join('');

  /** How many dust ellipses puff up where the flag lands. */
  var PENALTY_DUST = 3;

  register('penalty', simpleScene('penalty', 'cs-penalty', function (root, program) {
    var hatch = doc.createElement('div');
    hatch.className = 'cs-pen-hatch';
    root.appendChild(hatch);

    var slabBack = doc.createElement('div');
    slabBack.className = 'cs-pen-slab cs-pen-slab-back';
    root.appendChild(slabBack);

    var slabFront = doc.createElement('div');
    slabFront.className = 'cs-pen-slab cs-pen-slab-front';
    root.appendChild(slabFront);

    var rule = doc.createElement('div');
    rule.className = 'cs-pen-rule';
    root.appendChild(rule);

    addText(root, 'cs-pen-tag', textOf(program, 'subline'));
    addText(root, 'cs-pen-head', textOf(program, 'headline'));

    var dust = doc.createElement('div');
    dust.className = 'cs-pen-dust';
    for (var index = 0; index < PENALTY_DUST; index += 1) {
      var puff = doc.createElement('div');
      puff.className = 'cs-pen-puff';
      // Geometry only: three overlapping ellipses of different sizes so the
      // puff is not a single expanding circle.
      puff.style.setProperty('--cs-puff-scale', (1.0 + index * 0.55).toFixed(2));
      puff.style.setProperty('--cs-puff-shift', (index - 1) * 0.035 + '');
      puff.style.animationDelay = (700 + index * 60) + 'ms';
      dust.appendChild(puff);
    }
    root.appendChild(dust);

    var shadow = doc.createElement('div');
    shadow.className = 'cs-pen-shadow';
    root.appendChild(shadow);

    var fly = doc.createElement('div');
    fly.className = 'cs-pen-flag';
    var spin = doc.createElement('div');
    spin.className = 'cs-pen-flag-spin';
    spin.innerHTML = PENALTY_FLAG_MARKUP;
    fly.appendChild(spin);
    root.appendChild(fly);
  }));
})(window);
