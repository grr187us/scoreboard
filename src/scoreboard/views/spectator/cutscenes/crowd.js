/* The crowd scene: `make_some_noise`.
 *
 * A five-second prompt to the stands, built in the same language as the
 * Tigers' own scenes in tigers.js -- TMSA navy/red/blue, the TMSA crest, hard
 * diagonal slabs, kinetic type revealed under a moving mask, one light sweep,
 * and then a calm hold. The idea is a *live level meter*: the wall is telling
 * the crowd it is listening. `.scratch/cutscenes-v3/spec.md` section 4 is the
 * brief; this file is the build.
 *
 * It loads after `cutscenes/tigers.js` and before `cutscene.js`, and keeps
 * every house rule the other scene files keep:
 *
 * - Words come only from `program.texts` (`headline`, `subline`), always
 *   through `textContent`. This file formats nothing: the headline wraps into
 *   MAKE / SOME / NOISE because crowd.css gives it a box two words cannot
 *   share, not because anything here split a string.
 * - Colours come only from the `--cs-*` custom properties the player copies
 *   off `program.theme`. No brand hex is written here or in `crowd.css`.
 * - Lengths come from `--stage-w` / `--stage-h`, the stage's own pixel size,
 *   so the same scene reads on a 1920x1080 wall and in the 640-wide practice
 *   window.
 * - Nothing is fetched. The one subresource is the crest image, set as the
 *   page-relative literal `cutscenes/tmsa-logo.png` on an `<img>` -- exactly
 *   the kind of load WebView2 allows from the `file:///` spectator page.
 * - Nothing here is built from a markup string at all: every node is created
 *   with `createElement`, so operator words cannot reach a parser.
 *
 * The `register('make_some_noise', ...)` call at the bottom uses a literal id
 * on purpose: the Python mirror test greps the scene files for it so the id
 * constants and the scenes cannot drift.
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

  /** "Build a tree, then remove it" -- the shape of the scene here. Every
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
   * one of these is painted entirely by `crowd.css`. */
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

  /** A tiny deterministic generator, seeded per scene. The meter needs twelve
   * bars that do not bounce in step; it does not need them to differ between
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
  /* make_some_noise -- 5 s, "a live level meter"                        */
  /* ------------------------------------------------------------------ */

  /* No intro: the stage is on the wall at t = 0 while the board morphs to
   * the bar underneath it, so the slabs are already landing in the first
   * frame rather than leaving the stage empty.
   *
   *   0-350     navy-to-ink ground with the hatch and vignette; a red slab
   *             slams in from the left over an ink shadow slab and covers the
   *             left ~58 %; a blue slab slides in from the right under it
   *   0-4400    bass rings: three thin white rings expand from behind the
   *             word, one every 500 ms (120 BPM), each fading as it grows
   *   250-1000  MAKE SOME NOISE -- one text node, wrapped by CSS into three
   *             lines -- is revealed top to bottom under a moving clip-path;
   *             a light sweep crosses it once at 1300
   *   500-4400  the meter on the blue slab: twelve chunky bars with gold peak
   *             caps, each bouncing on its own period
   *   900-1400  TIGERS FANS slides in on an ink tag under the word; the crest
   *             lands at the lower left with weight
   *   1000-4400 the word punches on the beat, 3.5 %, felt rather than seen
   *   1400-4400 hold: rings, meter, punch; nothing else moves
   *   4400-5000 the player's outro fade
   *
   * Everything above is CSS (crowd.css); this builder only names the parts
   * and puts the two words on the stage. */

  /** Bass rings in flight at once. Three at 500 ms apart, each living 900 ms,
   * is one ring being born as the oldest dies. */
  var NOISE_RINGS = 3;
  /** Milliseconds between rings: 120 BPM. */
  var NOISE_BEAT_MS = 500;
  /** Bars in the meter. Twelve is few enough that each one is a chunky
   * column a spectator can see move, and many enough to read as a meter. */
  var NOISE_BARS = 12;
  /** The three bounce shapes the bars are dealt from, so no two neighbours
   * share a curve and the meter never settles into a wave. */
  var BAR_SHAPES = ['cs-mn-bar-a', 'cs-mn-bar-b', 'cs-mn-bar-c'];

  /** The meter: twelve tracks, each with a bar and a peak cap. Every bar gets
   * its own floor, ceiling, period and phase as custom properties; one
   * keyframe set per shape in crowd.css reads them. The phase is a negative
   * delay so the meter is already mid-motion when it rises into view. */
  function addMeter(parent) {
    var meter = addBox(parent, 'cs-mn-meter');
    var next = sequence(0x5EED0C);
    for (var index = 0; index < NOISE_BARS; index += 1) {
      var track = addBox(meter, 'cs-mn-track');
      var bar = addBox(track, 'cs-mn-bar ' + BAR_SHAPES[index % BAR_SHAPES.length]);
      var cap = addBox(track, 'cs-mn-cap');
      var period = Math.round(spread(next, 380, 720));
      var phase = -Math.round(spread(next, 0, period));
      // The middle of the meter runs hotter than the ends, the way a real
      // spectrum display does; the floor never drops to nothing.
      var centre = 1 - Math.abs(index - (NOISE_BARS - 1) / 2) / (NOISE_BARS / 2);
      var high = spread(next, 0.62, 0.95) * (0.78 + 0.22 * centre);
      var low = spread(next, 0.12, 0.26);
      track.style.setProperty('--cs-bar-hi', (high * 100).toFixed(1) + '%');
      track.style.setProperty('--cs-bar-lo', (low * 100).toFixed(1) + '%');
      bar.style.animationDuration = period + 'ms';
      bar.style.animationDelay = phase + 'ms';
      cap.style.animationDuration = period + 'ms';
      cap.style.animationDelay = phase + 'ms';
    }
    return meter;
  }

  register('make_some_noise', h.simpleScene('make_some_noise', 'cs-noise', function (root, program) {
    addBox(root, 'cs-mn-ground');

    addBox(root, 'cs-mn-slab-blue');
    addBox(root, 'cs-mn-slab-shadow');
    addBox(root, 'cs-mn-slab-red');
    addBox(root, 'cs-mn-seam');

    var rings = addBox(root, 'cs-mn-rings');
    for (var index = 0; index < NOISE_RINGS; index += 1) {
      var ring = addBox(rings, 'cs-mn-ring');
      ring.style.animationDelay = (index * NOISE_BEAT_MS) + 'ms';
    }

    addBox(root, 'cs-mn-hatch');
    addBox(root, 'cs-mn-vignette');

    addMeter(root);

    h.addText(root, 'cs-mn-headline', h.textOf(program, 'headline'));
    h.addText(root, 'cs-mn-subline', h.textOf(program, 'subline'));
    addCrest(root, 'cs-mn-crest', 0.22);
  }));
})(window);
