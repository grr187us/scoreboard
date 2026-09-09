/* The Tigers' own scenes: `first_down`, `touchdown` and `turnover`.
 *
 * First down uses stadium materials: seeded turf/chalk, a steel chain and
 * an orange padded marker. Touchdown is the tiger itself: a striped hide
 * torn open by four glowing claw tears with a quake, then gold metal type,
 * roar rings and embers. Turnover retains the TMSA
 * broadcast package (diagonal slabs, kinetic type, a burst and a readable
 * hold). All three show the existing TMSA crest and Python's event copy.
 *
 * It loads after `cutscenes/builtin.js` (which owns the registry, the intro,
 * and the penalty scene) and before `cutscene.js`, and it keeps every house
 * rule those files keep:
 *
 * - Words come only from `program.texts` (`headline`, `subline`,
 *   `team_name`), always through `textContent`. This file formats nothing.
 * - Brand colours come from `--cs-*` properties copied off `program.theme`.
 *   The first-down scene also uses neutral/natural material colours.
 * - Lengths come from `--stage-w` / `--stage-h`, the stage's own pixel size,
 *   so the same scene reads on a 1920x1080 wall and in the 640-wide
 *   practice window.
 * - Nothing is fetched. The one subresource is the crest image, set as the
 *   page-relative literal `cutscenes/tmsa-logo.png` on an `<img>` -- exactly
 *   the kind of load WebView2 allows from the `file:///` spectator page.
 * - Every node is created with `createElement` (or `createElementNS` for
 *   the touchdown's generated SVG), so operator words cannot reach a
 *   parser. The markup strings in this file are the touchdown's claw tear
 *   and hide container, and the turnover's football: static SVG constants
 *   named `*_MARKUP` that carry no text at all; the contract test lets only
 *   `*_MARKUP` identifiers be parsed as markup.
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
  /* first_down -- 5 s including intro/outro, "moving the chains"        */
  /* ------------------------------------------------------------------ */

  /* The field is a bounded, seeded raster painted ONCE and cached in memory.
   * CSS moves the camera, chain and marker; no render loop, timers, file or
   * graphics dependency is involved. Material colours are natural turf and
   * chalk, independent of the team's brand palette. If 2D canvas is absent,
   * the CSS grass/yard-line ground still leaves the scene and copy readable. */
  var fieldTexture = null;
  function paintField(canvas) {
    var ctx = canvas.getContext('2d');
    if (!ctx) { return; }
    if (!fieldTexture) {
      var texture = doc.createElement('canvas');
      texture.width = 1600;
      texture.height = 700;
      var ink = texture.getContext('2d');
      if (!ink) { return; }
      var next = sequence(0xF17D2026);
      var pixels = ink.createImageData(1600, 700);
      for (var y = 0; y < 700; y += 1) {
        var depth = y / 700;
        var mowing = Math.sin(Math.log(1 + depth * 8) * 12) > 0 ? 1 : 0.84;
        for (var x = 0; x < 1600; x += 1) {
          var grain = (next() - 0.5) * (14 + depth * 45);
          var light = (0.48 + depth * 0.52) * mowing;
          var i = (y * 1600 + x) * 4;
          pixels.data[i] = 29 * light + grain * 0.65;
          pixels.data[i + 1] = 65 * light + grain;
          pixels.data[i + 2] = 34 * light + grain * 0.55;
          pixels.data[i + 3] = 255;
        }
      }
      ink.putImageData(pixels, 0, 0);
      // Individual blades grow toward the lens; the density stays bounded.
      for (var blade = 0; blade < 15000; blade += 1) {
        var bx = next() * 1600;
        var by = next() * 700;
        var size = 1 + Math.pow(by / 700, 2) * 10;
        ink.strokeStyle = blade % 2 ? 'rgba(134,153,88,.28)' : 'rgba(4,20,11,.48)';
        ink.lineWidth = 0.5 + by / 700;
        ink.beginPath();
        ink.moveTo(bx, by);
        ink.lineTo(bx + (next() - 0.5) * size, by - size);
        ink.stroke();
      }
      // Chalk breaks up against the grass instead of looking like neon.
      var rows = [24, 62, 122, 219, 380, 642];
      for (var row = 0; row < rows.length; row += 1) {
        ink.fillStyle = 'rgba(229,230,210,.57)';
        ink.fillRect(0, rows[row], 1600, 1 + rows[row] * 0.012);
      }
      for (var tick = 0; tick < 22; tick += 1) {
        var ty = 700 * Math.pow(tick / 22, 2.5);
        var half = 6 + ty * 0.018;
        ink.fillStyle = 'rgba(229,230,210,.62)';
        ink.fillRect(770 - ty * 0.85, ty, half, 1 + ty * 0.005);
        ink.fillRect(850 + ty * 0.48, ty, half, 1 + ty * 0.005);
      }
      fieldTexture = texture;
    }
    canvas.width = fieldTexture.width;
    canvas.height = fieldTexture.height;
    ctx.drawImage(fieldTexture, 0, 0);
  }

  register('first_down', h.simpleScene('first_down', 'cs-firstdown', function (root, program) {
    // A display joining late must immediately show the readable hold, not
    // spend its remaining second replaying a hidden headline's entrance.
    if (program.elapsed_ms > 0) { root.classList.add('cs-fd-resumed'); }
    var world = addBox(root, 'cs-fd-world');
    addBox(world, 'cs-fd-sky');
    addBox(world, 'cs-fd-stands');
    addBox(world, 'cs-fd-lights cs-fd-lights-left');
    addBox(world, 'cs-fd-lights cs-fd-lights-right');
    var field = addBox(world, 'cs-fd-turf');
    var canvas = doc.createElement('canvas');
    canvas.className = 'cs-fd-grass';
    canvas.setAttribute('aria-hidden', 'true');
    field.appendChild(canvas);
    try { paintField(canvas); } catch (_error) { /* CSS turf remains usable. */ }
    addBox(world, 'cs-fd-field-shade');
    addBox(root, 'cs-fd-title-shade');

    var rig = addBox(root, 'cs-fd-rig');
    addBox(rig, 'cs-fd-contact-shadow');
    var chain = addBox(rig, 'cs-fd-chain');
    for (var link = 0; link < 36; link += 1) {
      var ring = addBox(chain, 'cs-fd-link' + (link % 2 ? ' cs-fd-link-edge' : ''));
      ring.style.left = (link * 2.45 - 3) + '%';
      ring.style.setProperty('--cs-link-sag', (Math.sin(link / 35 * Math.PI) * 0.17).toFixed(5));
    }
    var marker = addBox(rig, 'cs-fd-marker');
    addBox(marker, 'cs-fd-marker-shaft');
    addBox(marker, 'cs-fd-marker-collar');
    var target = addBox(marker, 'cs-fd-marker-target');
    addBox(target, 'cs-fd-marker-bolt');
    var dirt = addBox(root, 'cs-fd-dirt');
    var next = sequence(0xD17F);
    for (var clod = 0; clod < 24; clod += 1) {
      var particle = addBox(dirt, 'cs-fd-clod');
      particle.style.setProperty('--cs-dirt-x', ((next() - 0.5) * 0.22).toFixed(5));
      particle.style.setProperty('--cs-dirt-y', (-0.05 - next() * 0.15).toFixed(5));
      particle.style.setProperty('--cs-dirt-spin', (next() * 360).toFixed(2) + 'deg');
    }
    h.addText(root, 'cs-fd-headline', h.textOf(program, 'headline'));
    h.addText(root, 'cs-fd-subline', h.textOf(program, 'subline'));
    addCrest(root, 'cs-fd-crest', 0.13);
  }));

  /* ------------------------------------------------------------------ */
  /* touchdown -- 10 s, the tiger takes the wall                         */
  /* ------------------------------------------------------------------ */

  /* The intro's five-track claw has already torn the board open. This scene
   * is the animal behind it: 8400 ms on the stage, the last 600 of them the
   * player's fade. No score anywhere -- the score never left the Broadcast
   * bar under the stage.
   *
   *   0-520     the strike: four wide claw tears rip down the right of the
   *             wall in one staggered swipe, gold-white light pouring out
   *             of each cut with a red torn edge; the whole world takes one
   *             heavy quake and a shockwave ring leaves the strike
   *   600-1250  the word: TOUCHDOWN falls in from the lens as one piece of
   *             gold-and-white metal on an ink extrude, overshoots once and
   *             thumps the world a second time as it lands; one light sweep
   *             crosses it at 1400
   *   1250-1900 the roar: the crest punches in at the lower left, three
   *             rings expand out of it, TIGERS slams in on a red tag
   *   1400-     embers rise through the rest of the scene
   *   1900-7800 hold: the stripes drift, the light in the tears breathes,
   *             embers keep rising. The word never moves again.
   *
   * Everything above is CSS (tigers.css). This builder names the parts, puts
   * the two words on the stage, and deals the geometry: the stripes of the
   * hide and the embers are each one keyframe set reading per-piece custom
   * properties. The hide starts as a static `*_MARKUP` container whose
   * stripes are then built with the DOM API in the namespace the parsed
   * container already carries, so no markup string ever holds a computed
   * value and no namespace URL is written here. The tear is static markup:
   * the same torn-track shape as the intro, stamped four times. */

  /** A child element in `parent`'s own namespace, with a class. Structure
   * only: every attribute set on one of these is geometry. */
  function addSvg(parent, tag, className) {
    var node = doc.createElementNS(parent.namespaceURI, tag);
    if (className) { node.setAttribute('class', className); }
    parent.appendChild(node);
    return node;
  }

  /** The hide's container: the fur filter and the empty group the stripes
   * go into. Static, no text. */
  var TOUCHDOWN_HIDE_MARKUP = [
    '<svg class="cs-td-hide" viewBox="0 0 1000 1000" preserveAspectRatio="none"',
    ' aria-hidden="true" focusable="false">',
    '<defs><filter id="cs-td-fur" x="-5%" y="-5%" width="110%" height="110%">',
    '<feTurbulence type="fractalNoise" baseFrequency="0.004 0.014" numOctaves="3" seed="9" result="fur"/>',
    '<feDisplacementMap in="SourceGraphic" in2="fur" scale="14" xChannelSelector="R" yChannelSelector="G"/>',
    '</filter></defs>',
    '<g class="cs-td-fur" filter="url(#cs-td-fur)"></g>',
    '</svg>'
  ].join('');

  /** One claw tear, in the same 160x90 space and the same tapered shape as
   * the intro's tracks, so the strike on the wall is recognisably the same
   * claw that opened the board. Stamped four times through a torn-edge
   * filter; each stamp has an ink lip behind it, the light inside it, and a
   * red rim. Static markup, no text. */
  var TOUCHDOWN_RIP_PATH = 'M 0 0 C 1 22 13 52 31 89 C 24 56 8 24 0 0 Z';
  var TOUCHDOWN_RIP_PLACES = [
    'translate(30 10) scale(1.35 .9)',
    'translate(58 -4) scale(1.5 1.06)',
    'translate(88 -8) scale(1.55 1.1)',
    'translate(118 2) scale(1.4 .96)'
  ];
  var TOUCHDOWN_RIP_MARKUP = [
    '<svg class="cs-td-rip-svg" viewBox="0 0 160 90" preserveAspectRatio="xMidYMid meet"',
    ' aria-hidden="true" focusable="false">',
    '<defs>',
    '<filter id="cs-td-rip-torn" x="-30%" y="-10%" width="160%" height="120%">',
    '<feTurbulence type="fractalNoise" baseFrequency=".5" numOctaves="2" seed="71" result="grain"/>',
    '<feDisplacementMap in="SourceGraphic" in2="grain" scale="1.1" xChannelSelector="R" yChannelSelector="G"/>',
    '</filter>',
    '<linearGradient id="cs-td-rip-fill" x1="0" y1="0" x2="1" y2="0">',
    '<stop class="cs-td-rip-stop-edge" offset="0"/>',
    '<stop class="cs-td-rip-stop-warm" offset=".3"/>',
    '<stop class="cs-td-rip-stop-hot" offset=".5"/>',
    '<stop class="cs-td-rip-stop-warm" offset=".7"/>',
    '<stop class="cs-td-rip-stop-edge" offset="1"/>',
    '</linearGradient>',
    '</defs>',
    TOUCHDOWN_RIP_PLACES.map(function (place) {
      return '<g class="cs-td-rip-track" transform="' + place + '">'
        + '<g class="cs-td-rip-reveal">'
        + '<path class="cs-td-rip-lip" d="' + TOUCHDOWN_RIP_PATH + '"/>'
        + '<path class="cs-td-rip-light" d="' + TOUCHDOWN_RIP_PATH + '"/>'
        + '<path class="cs-td-rip-edge" d="' + TOUCHDOWN_RIP_PATH + '"/>'
        + '</g></g>';
    }).join(''),
    '</svg>'
  ].join('');

  /** The strike's centre, as fractions of the stage: the shockwave leaves
   * from here and the glow behind the tears sits on it. */
  var TOUCHDOWN_IMPACT_X = 0.72;
  var TOUCHDOWN_IMPACT_Y = 0.5;
  /** Stripes across the hide. A dozen reads as a tiger's flank from the back
   * row; two dozen reads as a barcode. */
  var TOUCHDOWN_STRIPES = 13;
  /** Embers through the hold. */
  var TOUCHDOWN_EMBERS = 34;
  /** Roar rings out of the crest. */
  var TOUCHDOWN_ROAR_RINGS = 3;

  /** The hide: tapered ink stripes over the navy ground, each a closed path
   * bulging to its own width at mid-height and leaning its own way, in a
   * 1000x1000 space stretched over the stage. Roughened once by a
   * turbulence filter so the edges read as fur rather than as vinyl. */
  function addHide(parent) {
    var box = addBox(parent, 'cs-td-hide-box');
    box.innerHTML = TOUCHDOWN_HIDE_MARKUP;
    var group = box.firstChild.lastChild;
    var next = sequence(0x7D5E01);
    var pitch = 1000 / TOUCHDOWN_STRIPES;
    for (var index = 0; index < TOUCHDOWN_STRIPES; index += 1) {
      var x0 = pitch * (index + 0.5) + spread(next, -18, 18);
      var lean = spread(next, -150, 150);
      var width = spread(next, 30, 78);
      var bulge = spread(next, -70, 70);
      var top = x0 - lean;
      var bottom = x0 + lean;
      var d = 'M ' + top.toFixed(1) + ' -60'
        + ' C ' + (x0 + bulge - width * 0.2).toFixed(1) + ' 300, ' + (x0 + bulge - width * 0.2).toFixed(1) + ' 700, '
        + bottom.toFixed(1) + ' 1060'
        + ' L ' + (bottom + width * 0.35).toFixed(1) + ' 1060'
        + ' C ' + (x0 + bulge + width).toFixed(1) + ' 700, ' + (x0 + bulge + width).toFixed(1) + ' 300, '
        + (top + width * 0.35).toFixed(1) + ' -60 Z';
      var stripe = addSvg(group, 'path', 'cs-td-stripe');
      stripe.setAttribute('d', d);
    }
    return box;
  }

  /** The embers: gold motes rising from the bottom edge through the hold,
   * each on its own lane, drift, size and cycle. They loop -- the hold is six
   * seconds and an ember's flight is four -- and start staggered so the first
   * cycle does not read as one wave. */
  function addEmbers(parent) {
    var field = addBox(parent, 'cs-td-embers');
    var next = sequence(0xE3B3);
    for (var index = 0; index < TOUCHDOWN_EMBERS; index += 1) {
      var ember = addBox(field, 'cs-td-ember');
      ember.style.left = spread(next, index % 3 === 0 ? 2 : 40, 98).toFixed(2) + '%';
      setStageLength(ember, '--cs-ed', 'w', spread(next, -0.06, 0.06));
      setStageLength(ember, '--cs-eh', 'h', -spread(next, 0.45, 0.95));
      setStageLength(ember, '--cs-es', 'h', spread(next, 0.007, 0.016));
      ember.style.animationDuration = Math.round(spread(next, 3200, 5200)) + 'ms';
      ember.style.animationDelay = Math.round(spread(next, 1400, 4600)) + 'ms';
    }
    return field;
  }

  register('touchdown', h.simpleScene('touchdown', 'cs-touchdown', function (root, program) {
    // A display joining late shows the settled hold at once, not the slam.
    if (program.elapsed_ms > 0) { root.classList.add('cs-td-resumed'); }

    var camera = addBox(root, 'cs-td-camera');
    var world = addBox(camera, 'cs-td-world');
    addBox(world, 'cs-td-ground');
    addHide(world);
    addBox(world, 'cs-td-shade');
    var glow = addBox(world, 'cs-td-rip-glow');
    setStageLength(glow, '--cs-ix', 'w', TOUCHDOWN_IMPACT_X);
    setStageLength(glow, '--cs-iy', 'h', TOUCHDOWN_IMPACT_Y);
    var rip = addBox(world, 'cs-td-rip');
    rip.innerHTML = TOUCHDOWN_RIP_MARKUP;
    var shock = addBox(world, 'cs-td-shock');
    setStageLength(shock, '--cs-ix', 'w', TOUCHDOWN_IMPACT_X);
    setStageLength(shock, '--cs-iy', 'h', TOUCHDOWN_IMPACT_Y);

    addEmbers(root);
    addBox(root, 'cs-td-vignette');

    h.addText(root, 'cs-td-headline', h.textOf(program, 'headline'));

    var roar = addBox(root, 'cs-td-roar');
    for (var ring = 0; ring < TOUCHDOWN_ROAR_RINGS; ring += 1) {
      var wave = addBox(roar, 'cs-td-roar-ring');
      wave.style.animationDelay = (1300 + ring * 150) + 'ms';
    }
    addCrest(root, 'cs-td-crest', 0.30);
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
