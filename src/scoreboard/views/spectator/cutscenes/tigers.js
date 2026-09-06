/* The Tigers' own scenes: `first_down`, `touchdown` and `turnover`.
 *
 * These three are the branded ones -- TMSA navy/red/blue, the TMSA crest, and
 * the language of a modern broadcast package: hard diagonal slabs, kinetic
 * type revealed under a moving mask, one light sweep, one burst that opens
 * and settles, then a long calm hold that a spectator in the back row can
 * actually read. `.scratch/cutscenes-v2/spec.md` sections 1, 6.1 and 6.2 are
 * the brief for the first two and `.scratch/cutscenes-v3/spec.md` section 3
 * for the turnover; this file is the build.
 *
 * It loads after `cutscenes/builtin.js` (which owns the registry, the intro,
 * and the penalty scene) and before `cutscene.js`, and it keeps every house
 * rule those files keep:
 *
 * - Words come only from `program.texts` (`headline`, `subline`,
 *   `team_name`), always through `textContent`. This file formats nothing.
 * - Colours come only from the `--cs-*` custom properties the player copies
 *   off `program.theme`. No brand hex is written here or in `tigers.css`.
 * - Lengths come from `--stage-w` / `--stage-h`, the stage's own pixel size,
 *   so the same scene reads on a 1920x1080 wall and in the 640-wide
 *   practice window.
 * - Nothing is fetched. The one subresource is the crest image, set as the
 *   page-relative literal `cutscenes/tmsa-logo.png` on an `<img>` -- exactly
 *   the kind of load WebView2 allows from the `file:///` spectator page.
 * - Every node is created with `createElement`, so operator words cannot
 *   reach a parser. The one markup string in this file is the turnover's
 *   football, a static SVG constant named `FOOTBALL_MARKUP` that carries no
 *   text at all; the contract test lets only `*_MARKUP` identifiers be
 *   parsed as markup.
 *
 * The `register('first_down', ...)`, `register('touchdown', ...)` and
 * `register('turnover', ...)` calls use literal ids on purpose: the Python
 * mirror test greps the scene files for them so the id constants and the
 * scenes cannot drift.
 */

(function (global) {
  'use strict';

  var doc = global.document;
  var registry = global.ScoreboardCutsceneScenes;
  if (!registry || typeof registry.register !== 'function') {
    // The registry is the only thing this file needs from builtin.js. Without
    // it there is nothing to register into, and a thrown error here would
    // land in the middle of the spectator page's load.
    return;
  }

  /* ------------------------------------------------------------------ */
  /* Helpers                                                             */
  /* ------------------------------------------------------------------ */

  /* builtin.js publishes its four scene helpers on the registry. They are
   * copied below under the same names so this file also runs standalone (and
   * so a reader of this file can see exactly what a scene is allowed to do);
   * when the registry offers them, the registry's win. */

  function isPlainObject(value) {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  /** One string out of `program.texts`, or '' -- never a computed value. */
  function textOf(program, key) {
    var texts = isPlainObject(program) && isPlainObject(program.texts) ? program.texts : {};
    var value = texts[key];
    return typeof value === 'string' ? value : '';
  }

  /** The root node for a scene, marked `data-scene="<id>"`. */
  function sceneRoot(id, className) {
    var root = doc.createElement('div');
    root.className = 'cs-scene ' + className;
    root.setAttribute('data-scene', id);
    return root;
  }

  /** Append a text node with its own class. Always a text node, never
   * markup: a team name is operator input. */
  function addText(parent, className, value) {
    var box = doc.createElement('div');
    box.className = className;
    var span = doc.createElement('span');
    span.textContent = value;
    box.appendChild(span);
    parent.appendChild(box);
    return box;
  }

  /** "Build a tree, then remove it" -- the shape of both scenes here. Every
   * moving part is a CSS animation inside the root, so taking the root off
   * the stage is what cancels the scene; there are no timers to clear. */
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

  var localHelpers = {
    sceneRoot: sceneRoot,
    addText: addText,
    textOf: textOf,
    simpleScene: simpleScene
  };
  var h = registry.helpers || localHelpers;
  var register = registry.register;

  /** A plain div with a class, appended to `parent`. Structure only -- every
   * one of these is painted entirely by `tigers.css`. */
  function addBox(parent, className) {
    var box = doc.createElement('div');
    box.className = className;
    parent.appendChild(box);
    return box;
  }

  /** Set one length-valued custom property in stage units. Scenes never
   * write px: `--stage-w`/`--stage-h` are inherited from the stage element,
   * so `calc(var(--stage-w) * f)` is the same fraction of the wall and of
   * the practice window. */
  function setStageLength(node, name, axis, factor) {
    node.style.setProperty(name, 'calc(var(--stage-' + axis + ') * ' + factor.toFixed(5) + ')');
  }

  /** A tiny deterministic generator, seeded per scene. The confetti needs
   * eighty different-looking pieces; it does not need them to differ between
   * two plays of the same cutscene, and a fixed sequence means a screenshot
   * taken today can be compared with one taken after an edit. */
  function sequence(seed) {
    var state = seed >>> 0;
    return function () {
      // A 32-bit LCG (Numerical Recipes' constants); geometry only.
      state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
      return state / 4294967296;
    };
  }

  /** `low` .. `high`, from the generator. */
  function spread(next, low, high) {
    return low + (high - low) * next();
  }

  /* ------------------------------------------------------------------ */
  /* The crest                                                           */
  /* ------------------------------------------------------------------ */

  /* The TMSA reference art is 218x174 with a blue triangle bleeding off the
   * left edge, a red diagonal bar off the right edge, and a grey band across
   * the bottom -- page furniture from the sheet it was lifted from, not part
   * of the mark. The crest shows only the tiger head and the TMSA wordmark:
   * the natural rectangle x 30..164, y 12..158 (134 x 146 source pixels,
   * measured off the decoded PNG). `.cs-crest-window` is that rectangle's
   * aspect ratio with `overflow: hidden`; the image inside is scaled up
   * uniformly by 218/134 and pushed left/up by the crop offsets, so it is
   * cropped and never stretched. The numbers live here, next to the
   * measurement that produced them; tigers.css only consumes them. */
  var CREST_SOURCE_WIDTH = 218;
  var CREST_SOURCE_HEIGHT = 174;
  var CREST_CROP_X = 30;
  var CREST_CROP_Y = 12;
  var CREST_CROP_WIDTH = 134;
  var CREST_CROP_HEIGHT = 146;

  /** Build the crest: a white rounded panel with a navy inner stroke, a soft
   * drop shadow, and the cropped mark inside it. `heightFactor` is the
   * panel's window height as a fraction of the stage height (kept at or
   * under ~30 % -- the art is low-resolution raster and must not be pushed
   * past its own detail). */
  function addCrest(parent, className, heightFactor) {
    var crest = addBox(parent, 'cs-crest ' + className);
    setStageLength(crest, '--cs-crest-h', 'h', heightFactor);
    crest.style.setProperty('--cs-crest-aspect', (CREST_CROP_WIDTH / CREST_CROP_HEIGHT).toFixed(5));
    crest.style.setProperty('--cs-crest-scale', ((CREST_SOURCE_WIDTH / CREST_CROP_WIDTH) * 100).toFixed(4) + '%');
    crest.style.setProperty('--cs-crest-left', ((-CREST_CROP_X / CREST_CROP_WIDTH) * 100).toFixed(4) + '%');
    crest.style.setProperty('--cs-crest-top', ((-CREST_CROP_Y / CREST_CROP_HEIGHT) * 100).toFixed(4) + '%');

    var panel = addBox(crest, 'cs-crest-panel');
    var window_ = addBox(panel, 'cs-crest-window');
    var image = doc.createElement('img');
    image.className = 'cs-crest-img';
    image.alt = '';
    image.src = 'cutscenes/tmsa-logo.png';
    window_.appendChild(image);
    return crest;
  }

  /* ------------------------------------------------------------------ */
  /* first_down -- 7 s, "moving the chains"                              */
  /* ------------------------------------------------------------------ */

  /* The hero image is the broadcast yellow line sweeping across the field.
   *
   *   0-500    a navy field in perspective rushes toward the camera and
   *            eases into a slow drift
   *   200-700  a red slab slams in from the left over an ink shadow slab; a
   *            thinner blue slab slides in under it from the right
   *   500-1000 the gold first-down marker sweeps left to right and stops at
   *            78 % with a small overshoot, white leading edge first
   *   600-1200 FIRST DOWN wipes out from behind the red slab under a moving
   *            clip-path; a light sweep crosses it once at 1300
   *   1000-1500 the crest drops in at the left; TIGERS rises into the blue slab
   *   1500-6400 hold: the field drifts, the marker's glow breathes
   *
   * Everything above is CSS (tigers.css); this builder only names the parts
   * and puts the two words on the stage. */

  /** The field's hash-mark columns: two rows of short ticks inside the
   * perspective plane, at a third and two thirds of its width. */
  var FIELD_HASHES = 2;

  register('first_down', h.simpleScene('first_down', 'cs-firstdown', function (root, program) {
    var field = addBox(root, 'cs-fd-field');
    var plane = addBox(field, 'cs-fd-plane');
    for (var hash = 0; hash < FIELD_HASHES; hash += 1) {
      var ticks = addBox(plane, 'cs-fd-hash');
      // Geometry, not a value: the two hash columns straddle the middle of
      // the plane, so they converge on the vanishing point instead of
      // raking across the stage as two stray diagonals.
      ticks.style.left = (46.5 + hash * 6) + '%';
    }
    addBox(field, 'cs-fd-horizon');
    addBox(root, 'cs-fd-vignette');

    addBox(root, 'cs-fd-pool');
    addBox(root, 'cs-fd-marker');

    addBox(root, 'cs-fd-slab-shadow');
    addBox(root, 'cs-fd-slab-blue');
    addBox(root, 'cs-fd-slab-red');
    addBox(root, 'cs-fd-accent');
    addBox(root, 'cs-fd-rule');
    addBox(root, 'cs-fd-hatch');

    h.addText(root, 'cs-fd-headline', h.textOf(program, 'headline'));
    h.addText(root, 'cs-fd-subline', h.textOf(program, 'subline'));
    addCrest(root, 'cs-fd-crest', 0.27);
  }));

  /* ------------------------------------------------------------------ */
  /* touchdown -- 10 s, the biggest moment of the game                   */
  /* ------------------------------------------------------------------ */

  /* Three beats and then a long hold. No score anywhere: the score never
   * left the Broadcast bar under the stage.
   *
   *   0-350     beat 1, the hit: a blue slab from the left and a red slab
   *             from the right slam together on a skewed centre seam, an
   *             ink gap between them and a white flash along it; the whole
   *             scene takes a 3 % camera push
   *   300-1300  beat 2, the word: TOUCHDOWN wipes in under a moving
   *             clip-path -- white, ink extrude, gold stroke -- then one
   *             light sweep crosses it
   *   900-2200  beat 3, the burst: rays open once behind the slabs and
   *             settle, and confetti fans up and out from behind the word
   *   1300-2000 the crest lands at the lower left with weight; TIGERS
   *             slides in on an ink tag beside it
   *   2000-9400 hold: the slabs drift apart 1-2 %, the rays breathe, the
   *             confetti finishes falling. The word never moves again. */

  /** Rays in the burst. Few and wide reads as light; many and thin reads as
   * a 2010 clip-art starburst, which is the note this scene exists to fix. */
  var TOUCHDOWN_RAYS = 12;
  /** Confetti pieces. Enough to fill the fan, few enough that each one's own
   * arc is visible rather than a wall of noise. */
  var TOUCHDOWN_CONFETTI = 84;
  /** The confetti palette, in the order pieces are dealt from it. Gold is an
   * accent -- one piece in nine, never a run of them. */
  var CONFETTI_COLOURS = [
    'cs-td-c-red', 'cs-td-c-white', 'cs-td-c-blue', 'cs-td-c-red',
    'cs-td-c-blue', 'cs-td-c-white', 'cs-td-c-gold', 'cs-td-c-blue',
    'cs-td-c-red'
  ];

  /** The fan: launch every piece from behind the word, up and out, then let
   * it fall with drift. Each piece gets its own apex, landing point, spin,
   * size and delay as custom properties; one keyframe set in tigers.css
   * reads them, so eighty-four pieces cost eighty-four elements and one
   * animation definition. */
  function addConfetti(parent) {
    var fan = addBox(parent, 'cs-td-confetti');
    var next = sequence(0x7A9B31);
    for (var index = 0; index < TOUCHDOWN_CONFETTI; index += 1) {
      var piece = addBox(fan, 'cs-td-piece ' + CONFETTI_COLOURS[index % CONFETTI_COLOURS.length]);
      // Fan the pieces out symmetrically: even indices go left, odd right,
      // with the reach growing as the burst opens.
      var side = index % 2 === 0 ? -1 : 1;
      var reach = spread(next, 0.06, 0.62) * side;
      setStageLength(piece, '--cs-cx', 'w', reach);
      setStageLength(piece, '--cs-apex', 'h', -spread(next, 0.26, 0.72));
      setStageLength(piece, '--cs-fall', 'h', spread(next, 0.34, 0.66));
      setStageLength(piece, '--cs-cw', 'w', spread(next, 0.0050, 0.0120));
      setStageLength(piece, '--cs-ch', 'h', spread(next, 0.016, 0.034));
      piece.style.setProperty('--cs-spin', Math.round(spread(next, 240, 1080)) * side + 'deg');
      // Staggered starts and a range of flight times: the burst opens once
      // over the first second and the last piece is down before 4.5 s, which
      // is where the spec puts the end of the burst.
      piece.style.animationDelay = Math.round(spread(next, 60, 1000)) + 'ms';
      piece.style.animationDuration = Math.round(spread(next, 3300, 4300)) + 'ms';
    }
    return fan;
  }

  register('touchdown', h.simpleScene('touchdown', 'cs-touchdown', function (root, program) {
    addBox(root, 'cs-td-ground');

    var rays = addBox(root, 'cs-td-rays');
    for (var index = 0; index < TOUCHDOWN_RAYS; index += 1) {
      var ray = addBox(rays, index % 3 === 0 ? 'cs-td-ray cs-td-ray-white' : 'cs-td-ray cs-td-ray-gold');
      // Geometry, not a displayed value: fan the rays evenly and stagger
      // their opening. The angle is a custom property rather than an inline
      // `transform` because the opening animation owns `transform`.
      ray.style.setProperty('--cs-ray-angle', (index * (360 / TOUCHDOWN_RAYS)).toFixed(2) + 'deg');
      ray.style.animationDelay = (900 + index * 34) + 'ms';
    }

    addBox(root, 'cs-td-slab-blue-shadow');
    addBox(root, 'cs-td-slab-blue');
    addBox(root, 'cs-td-slab-red-shadow');
    addBox(root, 'cs-td-slab-red');
    addBox(root, 'cs-td-seam');
    addBox(root, 'cs-td-flash');
    addBox(root, 'cs-td-hatch');
    addBox(root, 'cs-td-vignette');
    addBox(root, 'cs-td-glow');

    addConfetti(root);

    addBox(root, 'cs-td-rule');
    h.addText(root, 'cs-td-headline', h.textOf(program, 'headline'));
    addCrest(root, 'cs-td-crest', 0.28);
    h.addText(root, 'cs-td-subline', h.textOf(program, 'subline'));
  }));

  /* ------------------------------------------------------------------ */
  /* turnover -- 7 s, "possession flips"                                 */
  /* ------------------------------------------------------------------ */

  /* The claw intro (1600 ms, builtin.js) has already hit the board; this
   * scene then gets 5400 ms on the stage, the last 600 of them the player's
   * fade. The one image that says "turnover" on a broadcast is the
   * possession arrow reversing, so that is the whole opening beat:
   *
   *   0-450     a train of big blue chevrons pointing right rushes in from
   *             the left over a navy-to-ink ground
   *   450       the FLIP: the row mirrors and turns red -- one step, no
   *             tween -- a white flash line crosses it and decays in 120 ms,
   *             and the root takes one heavy 1 % shake. From here the
   *             chevrons march steadily left and settle to ~20 % behind
   *             everything else
   *   350-800   an ink shadow slab and then a red slab slam in from the
   *             RIGHT (the mirror of the first down's entry) across the
   *             upper 55 %; a thin blue slab slides under them from the left
   *   300-950   a football tumbles in from off-stage right along a shallow
   *             arc, spinning two full turns, with two red ghost copies
   *             trailing it, and lands in the left third with a small
   *             bounce; eight gold sparks fly out once and are gone by 1500
   *   700-1300  TURNOVER wipes in right-to-left under a moving clip-path --
   *             the reverse of the other scenes, to match the flip -- white,
   *             ink extrude, red stroke; one light sweep at 1400
   *   1100-1700 the crest drops in beside the ball; TIGERS BALL slides in on
   *             an ink tag to its right, in gold (the one accent use)
   *   1700-4800 hold: the chevrons drift left, the ball rocks two degrees,
   *             the slabs drift 1 % apart. The word never moves again.
   *
   * Everything above is CSS (tigers.css); this builder names the parts, puts
   * the two words on the stage, and deals the sparks' directions. */

  /** The football: a prolate ball in ink with a mist edge, a lighter
   * highlight along the top, a white lace line with its cross stitches, and
   * two end stripes. Static markup, no text, no ids (it is stamped three
   * times: the ball and its two ghosts). */
  var FOOTBALL_MARKUP = [
    '<svg class="cs-to-ball-svg" viewBox="0 0 200 120" aria-hidden="true" focusable="false">',
    '<path class="cs-to-ball-body" d="M 4 60 Q 100 -12 196 60 Q 100 132 4 60 Z"/>',
    '<path class="cs-to-ball-sheen" d="M 22 48 Q 100 2 178 48 Q 100 26 22 48 Z"/>',
    '<path class="cs-to-ball-stripe" d="M 42 39 Q 35 60 42 81"/>',
    '<path class="cs-to-ball-stripe" d="M 158 39 Q 165 60 158 81"/>',
    '<path class="cs-to-ball-lace" d="M 68 60 L 132 60"/>',
    '<path class="cs-to-ball-stitch" d="M 78 52 L 78 68 M 89 52 L 89 68 M 100 52 L 100 68',
    ' M 111 52 L 111 68 M 122 52 L 122 68"/>',
    '</svg>'
  ].join('');

  /** Chevrons visible across the stage at once. Six big ones read as a
   * possession arrow from the bleachers; a dozen small ones read as a
   * loading bar. */
  var TURNOVER_CHEVRONS = 6;
  /** One chevron's pitch, as a fraction of the stage width. Six pitches
   * centred on the stage put the row's centre exactly at 50 %, so mirroring
   * the row at the flip lands every chevron on a chevron. */
  var CHEVRON_PITCH = 0.155;
  /** Extra chevrons dealt off both ends of the row so the leftward march
   * during the hold never shows an empty gap entering from the right. */
  var CHEVRON_OVERRUN = 1;
  /** Gold sparks at the landing. Eight, flung once, fading by 1500 ms. */
  var TURNOVER_SPARKS = 8;

  /** The chevron train: a mirrorable row holding a marching belt of
   * chevrons. Each chevron is a clip-path polygon painted by tigers.css; the
   * `left` set here is geometry, not a displayed value. */
  function addChevronTrain(parent) {
    var train = addBox(parent, 'cs-to-train');
    var row = addBox(train, 'cs-to-row');
    var belt = addBox(row, 'cs-to-belt');
    var margin = (1 - TURNOVER_CHEVRONS * CHEVRON_PITCH) / 2;
    for (var index = -CHEVRON_OVERRUN; index < TURNOVER_CHEVRONS + CHEVRON_OVERRUN; index += 1) {
      var chevron = addBox(belt, 'cs-to-chev');
      chevron.style.left = ((margin + index * CHEVRON_PITCH) * 100).toFixed(3) + '%';
    }
    return train;
  }

  /** The ball in flight: the path wrapper carries the arc, the rock wrapper
   * the slow tilt of the hold, and the spin wrapper the tumble. Three
   * elements because each one animates `transform` on its own. */
  function addFootball(parent, className) {
    var path = addBox(parent, 'cs-to-ball ' + className);
    var rock = addBox(path, 'cs-to-ball-rock');
    var spin = addBox(rock, 'cs-to-ball-spin');
    spin.innerHTML = FOOTBALL_MARKUP;
    return path;
  }

  /** The sparks: eight short gold streaks from the landing point, each with
   * its own direction and reach as custom properties that one keyframe set
   * in tigers.css reads. They fan over the upper half-circle -- the ball
   * landed on something, so the sparks go up and out, never down. */
  function addSparks(parent) {
    var burst = addBox(parent, 'cs-to-sparks');
    var next = sequence(0x54F1A9);
    for (var index = 0; index < TURNOVER_SPARKS; index += 1) {
      var spark = addBox(burst, 'cs-to-spark');
      // Evenly spaced around the top half, jittered so it is not a fan of
      // spokes, with a different reach for each.
      var angle = -Math.PI * ((index + 0.5) / TURNOVER_SPARKS) + spread(next, -0.18, 0.18);
      var reach = spread(next, 0.07, 0.15);
      setStageLength(spark, '--cs-sx', 'w', Math.cos(angle) * reach);
      setStageLength(spark, '--cs-sy', 'w', Math.sin(angle) * reach);
      spark.style.setProperty('--cs-sa', (angle * 180 / Math.PI).toFixed(1) + 'deg');
      spark.style.animationDelay = Math.round(spread(next, 930, 1010)) + 'ms';
    }
    return burst;
  }

  register('turnover', h.simpleScene('turnover', 'cs-turnover', function (root, program) {
    addBox(root, 'cs-to-ground');

    addBox(root, 'cs-to-slab-shadow');
    addBox(root, 'cs-to-slab-blue');
    addBox(root, 'cs-to-slab-red');

    addChevronTrain(root);
    addBox(root, 'cs-to-flash');
    addBox(root, 'cs-to-hatch');
    addBox(root, 'cs-to-vignette');

    h.addText(root, 'cs-to-headline', h.textOf(program, 'headline'));

    addBox(root, 'cs-to-ball-shadow');
    addFootball(root, 'cs-to-ball-ghost cs-to-ball-ghost-b');
    addFootball(root, 'cs-to-ball-ghost cs-to-ball-ghost-a');
    addFootball(root, 'cs-to-ball-real');
    addSparks(root);

    addBox(root, 'cs-to-rule');
    addCrest(root, 'cs-to-crest', 0.26);
    h.addText(root, 'cs-to-subline', h.textOf(program, 'subline'));
  }));
})(window);
