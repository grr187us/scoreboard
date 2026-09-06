/* The widgetized spectator/editor board renderer.
 *
 * A "widget" is one positioned text box on the 16:9 logical canvas; a "free
 * element" (text/image/box) is an operator-added extra placed the same way.
 * Both come from a layout document (produced and validated in Python,
 * `scoreboard.presentation.layout`); a widget's and a text element's text
 * comes from the view model / `WIDGET_TEXTS` / the layout itself. This file
 * only ever *places* and *writes* values it is handed -- JavaScript copies
 * text from exactly three places -- the view model, `WIDGET_TEXTS`, and a
 * validated layout's `elements[].text` -- and computes none of it, matching
 * the house rule in `render.js`.
 *
 * The six data constants below (WIDGET_IDS, WIDGET_FIELDS, WIDGET_TEXTS,
 * OPTIONAL_WIDGET_IDS, DEFAULT_LAYOUT, FONT_FAMILIES) are written as strict
 * JSON literals -- double-quoted keys/strings, no trailing commas, no
 * comments inside the braces -- so a Python test can lift the text between
 * `=` and the closing `;` and `json.loads` it directly against the matching
 * Python constants in `scoreboard.presentation.layout`. Do not introduce
 * single quotes, trailing commas, or computed values inside those literals.
 *
 * Both the spectator page and the layout editor's live preview share this
 * file: `build`/`applyLayout`/`applyModel` only ever look inside the
 * `container` element passed to them, so two independent boards (the real
 * spectator canvas and the editor's preview canvas) can exist in the same
 * document without colliding.
 *
 * Every placed node -- widget or free element -- carries `data-item="<id>"`.
 * `build()` marks the container it fills with `data-board-root="1"`;
 * `applyLayout()` looks for that marker (falling back to the container it
 * was given) and reconciles the free-element nodes underneath it: creates
 * ones newly present in `layout.elements`, removes ones no longer present,
 * updates the rest, and inserts any new node just before the first widget
 * node so a widget always draws above an element at equal `z_index`.
 */

(function (global) {
  'use strict';

  var WIDGET_IDS = [
    "home_name", "home_score", "possession", "away_name", "away_score",
    "game_clock_label", "game_clock_value",
    "quarter", "down", "distance",
    "play_clock_label", "play_clock_value", "ball_on",
    "home_timeouts", "away_timeouts"
  ];

  /* Dotted path into the spectator view model. null means a static label
   * whose text comes from WIDGET_TEXTS instead of the model. */
  var WIDGET_FIELDS = {
    "home_name": "teams.home.name",
    "home_score": "teams.home.score",
    "possession": "football.possession_display",
    "away_name": "teams.away.name",
    "away_score": "teams.away.score",
    "game_clock_label": null,
    "game_clock_value": "clocks.game.display",
    "quarter": "quarter_display",
    "down": "football.down_display",
    "distance": "football.distance_display",
    "play_clock_label": null,
    "play_clock_value": "clocks.play.display",
    "ball_on": "football.ball_on_display",
    "home_timeouts": "football.home_timeouts_display",
    "away_timeouts": "football.away_timeouts_display"
  };

  /* Application-controlled label text. Operators may style/move/hide these
   * widgets, never edit the words. */
  var WIDGET_TEXTS = {
    "game_clock_label": "GAME CLOCK",
    "play_clock_label": "PLAY CLOCK"
  };

  /* Widgets whose value can legitimately be absent from a snapshot. When the
   * field is missing or its rendered text is empty, the widget is hidden
   * rather than drawn as an empty box. */
  var OPTIONAL_WIDGET_IDS = [
    "possession", "down", "distance", "ball_on",
    "home_timeouts", "away_timeouts"
  ];

  /* Mirrors scoreboard.presentation.layout.FONT_FAMILIES: the CSS font stack
   * for each font id. Every family here is already installed on Windows --
   * nothing is ever loaded from a network. */
  var FONT_FAMILIES = {
    "arial": "Arial, Helvetica, sans-serif",
    "arial_black": "'Arial Black', Arial, sans-serif",
    "impact": "Impact, 'Arial Black', sans-serif",
    "bahnschrift": "Bahnschrift, 'Segoe UI', Arial, sans-serif",
    "segoe": "'Segoe UI', Segoe, Arial, sans-serif",
    "segoe_black": "'Segoe UI Black', 'Segoe UI', Arial, sans-serif",
    "consolas": "Consolas, 'Courier New', monospace",
    "georgia": "Georgia, 'Times New Roman', serif",
    "verdana": "Verdana, Geneva, sans-serif",
    "trebuchet": "'Trebuchet MS', Arial, sans-serif"
  };

  /* Mirrors scoreboard.presentation.layout.default_layout(). Preserves the
   * pre-widget spectator arrangement: the clock label and both timeout
   * widgets start hidden because today's board never drew them, and
   * possession moves from an inline mark beside the team name to its own
   * widget centred between the two names. Every widget's v2 style
   * properties are set to their neutral defaults so this document renders
   * pixel-identical to the v1 board. */
  var DEFAULT_LAYOUT = {
  "schema_version": 2,
  "name": "Default",
  "safe_area": {
    "top": 0.04,
    "right": 0.04,
    "bottom": 0.04,
    "left": 0.04
  },
  "background": {
    "color": "#000000"
  },
  "widgets": {
    "home_name": {
      "id": "home_name",
      "visible": true,
      "x": 0.04,
      "y": 0.04,
      "width": 0.38,
      "height": 0.118,
      "font_scale": 0.028,
      "color": "#FFFFFF",
      "text_align": "center",
      "vertical_align": "middle",
      "font_weight": 700,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "home_score": {
      "id": "home_score",
      "visible": true,
      "x": 0.04,
      "y": 0.164,
      "width": 0.38,
      "height": 0.242,
      "font_scale": 0.112,
      "color": "#FFFFFF",
      "text_align": "center",
      "vertical_align": "middle",
      "font_weight": 700,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "possession": {
      "id": "possession",
      "visible": true,
      "x": 0.43,
      "y": 0.071,
      "width": 0.14,
      "height": 0.056,
      "font_scale": 0.026,
      "color": "#57E6A4",
      "text_align": "center",
      "vertical_align": "middle",
      "font_weight": 700,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "away_name": {
      "id": "away_name",
      "visible": true,
      "x": 0.58,
      "y": 0.04,
      "width": 0.38,
      "height": 0.118,
      "font_scale": 0.028,
      "color": "#FFFFFF",
      "text_align": "center",
      "vertical_align": "middle",
      "font_weight": 700,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "away_score": {
      "id": "away_score",
      "visible": true,
      "x": 0.58,
      "y": 0.164,
      "width": 0.38,
      "height": 0.242,
      "font_scale": 0.112,
      "color": "#FFFFFF",
      "text_align": "center",
      "vertical_align": "middle",
      "font_weight": 700,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "game_clock_label": {
      "id": "game_clock_label",
      "visible": false,
      "x": 0.4,
      "y": 0.412,
      "width": 0.2,
      "height": 0.052,
      "font_scale": 0.024,
      "color": "#CFCFCF",
      "text_align": "center",
      "vertical_align": "middle",
      "font_weight": 400,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "game_clock_value": {
      "id": "game_clock_value",
      "visible": true,
      "x": 0.04,
      "y": 0.47,
      "width": 0.92,
      "height": 0.2,
      "font_scale": 0.093,
      "color": "#FFFFFF",
      "text_align": "center",
      "vertical_align": "middle",
      "font_weight": 400,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "quarter": {
      "id": "quarter",
      "visible": true,
      "x": 0.04,
      "y": 0.699,
      "width": 0.44,
      "height": 0.126,
      "font_scale": 0.058,
      "color": "#FFFFFF",
      "text_align": "center",
      "vertical_align": "middle",
      "font_weight": 400,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "down": {
      "id": "down",
      "visible": true,
      "x": 0.11,
      "y": 0.875,
      "width": 0.15,
      "height": 0.059,
      "font_scale": 0.027,
      "color": "#CFCFCF",
      "text_align": "right",
      "vertical_align": "middle",
      "font_weight": 400,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "distance": {
      "id": "distance",
      "visible": true,
      "x": 0.272,
      "y": 0.875,
      "width": 0.15,
      "height": 0.059,
      "font_scale": 0.027,
      "color": "#CFCFCF",
      "text_align": "left",
      "vertical_align": "middle",
      "font_weight": 400,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "play_clock_label": {
      "id": "play_clock_label",
      "visible": true,
      "x": 0.5,
      "y": 0.733,
      "width": 0.21,
      "height": 0.059,
      "font_scale": 0.027,
      "color": "#FFFFFF",
      "text_align": "right",
      "vertical_align": "middle",
      "font_weight": 400,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "play_clock_value": {
      "id": "play_clock_value",
      "visible": true,
      "x": 0.718,
      "y": 0.678,
      "width": 0.242,
      "height": 0.168,
      "font_scale": 0.078,
      "color": "#FFFFFF",
      "text_align": "left",
      "vertical_align": "middle",
      "font_weight": 700,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "ball_on": {
      "id": "ball_on",
      "visible": true,
      "x": 0.48,
      "y": 0.854,
      "width": 0.48,
      "height": 0.101,
      "font_scale": 0.024,
      "color": "#CFCFCF",
      "text_align": "center",
      "vertical_align": "middle",
      "font_weight": 400,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "home_timeouts": {
      "id": "home_timeouts",
      "visible": false,
      "x": 0.04,
      "y": 0.412,
      "width": 0.2,
      "height": 0.052,
      "font_scale": 0.024,
      "color": "#CFCFCF",
      "text_align": "left",
      "vertical_align": "middle",
      "font_weight": 400,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    },
    "away_timeouts": {
      "id": "away_timeouts",
      "visible": false,
      "x": 0.76,
      "y": 0.412,
      "width": 0.2,
      "height": 0.052,
      "font_scale": 0.024,
      "color": "#CFCFCF",
      "text_align": "right",
      "vertical_align": "middle",
      "font_weight": 400,
      "z_index": 0,
      "font_family": "arial",
      "letter_spacing": 0.0,
      "text_transform": "none",
      "text_effect": "none",
      "background": null,
      "background_opacity": 1.0,
      "border_color": null,
      "border_width": 0.0,
      "corner_radius": 0.0,
      "padding": 0.0
    }
  },
  "elements": []
};

  /* Neutral defaults for a free element, keyed by `type`, used whenever a
   * property is missing from the layout document. These are not part of the
   * strict-JSON Python contract (elements are optional and heterogeneous),
   * just a tolerant local fallback so a partial element entry still draws
   * something reasonable instead of NaN-ing out a CSS custom property. */
  var ELEMENT_DEFAULTS = {
    text: {
      visible: true, x: 0, y: 0, width: 0.1, height: 0.1, z_index: 0, opacity: 1,
      background: null, background_opacity: 1, border_color: null, border_width: 0, corner_radius: 0,
      text: '', color: '#FFFFFF', font_scale: 0.03, font_family: 'arial', font_weight: 700,
      letter_spacing: 0, text_transform: 'none', text_effect: 'none',
      text_align: 'center', vertical_align: 'middle', padding: 0
    },
    image: {
      visible: true, x: 0, y: 0, width: 0.1, height: 0.1, z_index: 0, opacity: 1,
      background: null, background_opacity: 1, border_color: null, border_width: 0, corner_radius: 0,
      fit: 'contain'
    },
    box: {
      visible: true, x: 0, y: 0, width: 0.1, height: 0.1, z_index: 0, opacity: 1,
      background: null, background_opacity: 1, border_color: null, border_width: 0, corner_radius: 0
    }
  };

  var OPTIONAL_LOOKUP = {};
  for (var optionalIndex = 0; optionalIndex < OPTIONAL_WIDGET_IDS.length; optionalIndex += 1) {
    OPTIONAL_LOOKUP[OPTIONAL_WIDGET_IDS[optionalIndex]] = true;
  }

  function isOptional(id) {
    return OPTIONAL_LOOKUP[id] === true;
  }

  function isPlainObject(value) {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  function numberOr(value, fallback) {
    return typeof value === 'number' && isFinite(value) ? value : fallback;
  }

  function stringOr(value, fallback) {
    return typeof value === 'string' && value !== '' ? value : fallback;
  }

  function alignToJustify(value, fallback) {
    if (value === 'left') return 'flex-start';
    if (value === 'right') return 'flex-end';
    if (value === 'center') return 'center';
    return fallback;
  }

  function alignToItems(value, fallback) {
    if (value === 'top') return 'flex-start';
    if (value === 'bottom') return 'flex-end';
    if (value === 'middle') return 'center';
    return fallback;
  }

  /** Convert one '#RRGGBB' hex pair (e.g. "1a") to its numeric value using a
   * numeric-literal conversion rather than a string-parsing function, so the
   * radix is fixed by the literal itself and never ambiguous. */
  /* The same four raster types the Python schema accepts; anything else --
   * notably an SVG, which can carry a script -- is never placed in an <img>,
   * even in the editor's live preview before Python has had its say. */
  var IMAGE_SRC_PREFIX = /^data:image\/(png|jpeg|gif|webp);base64,/;

  /** Keep a 0..1 value inside 0..1 without arithmetic helpers. */
  function unit(value) {
    return value < 0 ? 0 : (value > 1 ? 1 : value);
  }

  function hexPairToNumber(pair) {
    return Number('0x' + pair);
  }

  /** Combine a '#RRGGBB' fill colour with a 0..1 opacity into an rgba()
   * string, or null if the colour is not usable. */
  function hexToRgba(hex, opacity) {
    if (typeof hex !== 'string' || hex.charAt(0) !== '#' || hex.length !== 7) {
      return null;
    }
    var r = hexPairToNumber(hex.slice(1, 3));
    var g = hexPairToNumber(hex.slice(3, 5));
    var b = hexPairToNumber(hex.slice(5, 7));
    if (!isFinite(r) || !isFinite(g) || !isFinite(b)) {
      return null;
    }
    var a = unit(numberOr(opacity, 1));
    return 'rgba(' + r + ',' + g + ',' + b + ',' + a + ')';
  }

  /** Toggle an element's hidden state from its two independent reasons: the
   * layout said "not visible", or (for an optional widget) the model gave it
   * nothing to show. Either reason hides it; neither call needs to know
   * about the other's most recent state. */
  function refreshHidden(element) {
    var visible = element.dataset.layoutVisible !== '0';
    var hasValue = element.dataset.hasValue !== '0';
    element.hidden = !(visible && hasValue);
  }

  /** Set the fill/border/corner-radius custom properties shared by every
   * widget and every free element (`--bg --bc --bw --br`). `source` is the
   * layout entry being applied; `fallback` supplies a value for any property
   * `source` omits. */
  function applyPaint(node, source, fallback) {
    var backgroundColor = typeof source.background === 'string' ? source.background
      : (typeof fallback.background === 'string' ? fallback.background : null);
    var backgroundOpacity = numberOr(source.background_opacity, numberOr(fallback.background_opacity, 1));
    var borderColor = typeof source.border_color === 'string' ? source.border_color
      : (typeof fallback.border_color === 'string' ? fallback.border_color : null);
    var borderWidth = numberOr(source.border_width, numberOr(fallback.border_width, 0));
    var cornerRadius = numberOr(source.corner_radius, numberOr(fallback.corner_radius, 0));

    var background = backgroundColor ? (hexToRgba(backgroundColor, backgroundOpacity) || 'transparent') : 'transparent';
    node.style.setProperty('--bg', background);
    node.style.setProperty('--bc', borderColor || 'transparent');
    node.style.setProperty('--bw', borderWidth);
    node.style.setProperty('--br', cornerRadius);
  }

  /** Set the text-styling custom properties shared by every widget and every
   * text element (`--ff --ls --tt --pad`) plus the effect class. */
  function applyTextStyle(node, source, fallback) {
    var fontFamilyKey = stringOr(source.font_family, stringOr(fallback.font_family, 'arial'));
    var fontStack = FONT_FAMILIES[fontFamilyKey] || FONT_FAMILIES.arial;
    var letterSpacing = numberOr(source.letter_spacing, numberOr(fallback.letter_spacing, 0));
    var textTransform = stringOr(source.text_transform, stringOr(fallback.text_transform, 'none'));
    var padding = numberOr(source.padding, numberOr(fallback.padding, 0));
    var textEffect = stringOr(source.text_effect, stringOr(fallback.text_effect, 'none'));

    node.style.setProperty('--ff', fontStack);
    node.style.setProperty('--ls', letterSpacing);
    node.style.setProperty('--tt', textTransform);
    node.style.setProperty('--pad', padding);

    node.classList.toggle('effect-shadow', textEffect === 'shadow');
    node.classList.toggle('effect-outline', textEffect === 'outline');
  }

  /** Empty the container and append one widget element per WIDGET_IDS, in
   * order. Re-buildable at any time; nothing here reads a layout or model.
   * Marks the container as the board root so `applyLayout` can find it even
   * when called with an outer wrapper (the spectator page's `#canvas`). */
  function build(container) {
    if (!container) {
      return;
    }
    container.innerHTML = '';
    container.dataset.boardRoot = '1';
    for (var index = 0; index < WIDGET_IDS.length; index += 1) {
      var id = WIDGET_IDS[index];
      var widget = document.createElement('div');
      widget.className = 'widget';
      widget.setAttribute('data-widget', id);
      widget.setAttribute('data-item', id);
      widget.dataset.layoutVisible = '1';
      widget.dataset.hasValue = '1';
      var text = document.createElement('span');
      text.className = 'widget-text';
      widget.appendChild(text);
      container.appendChild(widget);
    }
  }

  /** True when `entry` is well-formed enough to place on the board: a plain
   * object with a usable string `id`, a recognized `type`, and (for an
   * image) a `src` that at least looks like a data URI. Anything else is
   * skipped without throwing, exactly like a malformed widget. */
  function isValidElementEntry(entry) {
    if (!isPlainObject(entry) || typeof entry.id !== 'string' || entry.id === '') {
      return false;
    }
    if (entry.type !== 'text' && entry.type !== 'image' && entry.type !== 'box') {
      return false;
    }
    if (entry.type === 'image' && (typeof entry.src !== 'string' || !IMAGE_SRC_PREFIX.test(entry.src))) {
      return false;
    }
    return true;
  }

  /** Build a fresh, unstyled DOM node for one element `type`. Text elements
   * reuse the same `.widget-text` child as a widget so `board.css` styles
   * the text itself identically either way. */
  function buildElementNode(type) {
    var node = document.createElement('div');
    if (type === 'text') {
      node.className = 'widget element element-text';
      var text = document.createElement('span');
      text.className = 'widget-text';
      node.appendChild(text);
    } else if (type === 'image') {
      node.className = 'element element-image';
      var img = document.createElement('img');
      img.alt = '';
      node.appendChild(img);
    } else {
      node.className = 'element element-box';
    }
    return node;
  }

  /** Place and style one already-created element node from its layout
   * `entry`. Shared geometry/paint/opacity apply to every type; text and
   * image types layer their own additional properties on top. */
  function applyElementStyle(node, entry) {
    var defaults = ELEMENT_DEFAULTS[entry.type];
    var x = numberOr(entry.x, defaults.x);
    var y = numberOr(entry.y, defaults.y);
    var width = numberOr(entry.width, defaults.width);
    var height = numberOr(entry.height, defaults.height);
    var zIndex = numberOr(entry.z_index, defaults.z_index);
    var opacity = unit(numberOr(entry.opacity, defaults.opacity));
    var visible = typeof entry.visible === 'boolean' ? entry.visible : defaults.visible;

    node.style.setProperty('--x', x);
    node.style.setProperty('--y', y);
    node.style.setProperty('--w', width);
    node.style.setProperty('--h', height);
    node.style.setProperty('--op', opacity);
    node.style.zIndex = zIndex;
    node.hidden = !visible;

    applyPaint(node, entry, defaults);

    if (entry.type === 'text') {
      applyTextStyle(node, entry, defaults);
      var color = stringOr(entry.color, defaults.color);
      var fontScale = numberOr(entry.font_scale, defaults.font_scale);
      var fontWeight = numberOr(entry.font_weight, defaults.font_weight);
      var textAlign = alignToJustify(entry.text_align, alignToJustify(defaults.text_align, 'center'));
      var verticalAlign = alignToItems(entry.vertical_align, alignToItems(defaults.vertical_align, 'center'));
      node.style.setProperty('--fs', fontScale);
      node.style.setProperty('--color', color);
      node.style.setProperty('--fw', fontWeight);
      node.style.setProperty('--ta', textAlign);
      node.style.setProperty('--va', verticalAlign);
      var textElement = node.querySelector('.widget-text');
      var text = typeof entry.text === 'string' ? entry.text : defaults.text;
      if (textElement && textElement.textContent !== text) {
        textElement.textContent = text;
      }
    } else if (entry.type === 'image') {
      var fit = stringOr(entry.fit, defaults.fit);
      node.style.setProperty('--fit', fit);
      var img = node.querySelector('img');
      if (img && img.getAttribute('src') !== entry.src) {
        img.src = entry.src;
      }
    }
  }

  /** Reconcile the free-element nodes under `boardRoot` against `elements`:
   * create ones newly present, remove ones no longer present, update the
   * rest in place. New nodes land just before the first widget node so a
   * widget always draws above an element at equal `z_index`. */
  function reconcileElements(boardRoot, elements) {
    var existingById = {};
    var existingNodes = boardRoot.querySelectorAll('[data-element]');
    for (var nodeIndex = 0; nodeIndex < existingNodes.length; nodeIndex += 1) {
      existingById[existingNodes[nodeIndex].getAttribute('data-element')] = existingNodes[nodeIndex];
    }

    var seenIds = {};
    var firstWidget = boardRoot.querySelector('[data-widget]');

    for (var index = 0; index < elements.length; index += 1) {
      var entry = elements[index];
      if (!isValidElementEntry(entry) || seenIds[entry.id]) {
        continue;
      }
      seenIds[entry.id] = true;

      var node = existingById[entry.id];
      if (node && node.getAttribute('data-element-type') !== entry.type) {
        // The type changed, so the node's own shape (an <img> versus a text
        // span) no longer fits: drop it and start fresh below.
        node.parentNode.removeChild(node);
        node = null;
      }
      if (!node) {
        node = buildElementNode(entry.type);
        node.setAttribute('data-item', entry.id);
        node.setAttribute('data-element', entry.id);
        node.setAttribute('data-element-type', entry.type);
        boardRoot.insertBefore(node, firstWidget);
      }

      try {
        applyElementStyle(node, entry);
      } catch (error) {
        // A malformed single element entry must not break the rest of the board.
      }
    }

    for (var existingId in existingById) {
      if (Object.prototype.hasOwnProperty.call(existingById, existingId) && !seenIds[existingId]) {
        var stale = existingById[existingId];
        stale.parentNode.removeChild(stale);
      }
    }
  }

  /** Place and style every widget found under `container` from `layout`,
   * paint the board background on `container` itself, and reconcile the
   * free-element nodes under the board root. Tolerant of a missing/partial
   * layout: any absent piece -- the whole document, the widgets map, a
   * single widget's individual properties, or the elements list -- falls
   * back to something safe rather than throwing or leaving a widget
   * unstyled. */
  function applyLayout(container, layout) {
    if (!container) {
      return;
    }
    var safeLayout = isPlainObject(layout) ? layout : DEFAULT_LAYOUT;

    try {
      var background = isPlainObject(safeLayout.background) ? safeLayout.background : DEFAULT_LAYOUT.background;
      container.style.background = stringOr(background.color, DEFAULT_LAYOUT.background.color);
    } catch (error) {
      // Leave whatever background the container already had.
    }

    var boardRoot = container.querySelector('[data-board-root]') || container;

    var widgets = isPlainObject(safeLayout.widgets) ? safeLayout.widgets : DEFAULT_LAYOUT.widgets;
    for (var index = 0; index < WIDGET_IDS.length; index += 1) {
      var id = WIDGET_IDS[index];
      var element = container.querySelector('[data-widget="' + id + '"]');
      if (!element) {
        continue;
      }
      var fallback = DEFAULT_LAYOUT.widgets[id];
      var widget = isPlainObject(widgets[id]) ? widgets[id] : fallback;
      try {
        var x = numberOr(widget.x, fallback.x);
        var y = numberOr(widget.y, fallback.y);
        var width = numberOr(widget.width, fallback.width);
        var height = numberOr(widget.height, fallback.height);
        var fontScale = numberOr(widget.font_scale, fallback.font_scale);
        var color = stringOr(widget.color, fallback.color);
        var fontWeight = numberOr(widget.font_weight, fallback.font_weight);
        var textAlign = alignToJustify(widget.text_align, alignToJustify(fallback.text_align, 'center'));
        var verticalAlign = alignToItems(widget.vertical_align, alignToItems(fallback.vertical_align, 'center'));
        var zIndex = numberOr(widget.z_index, fallback.z_index);
        var visible = typeof widget.visible === 'boolean' ? widget.visible : fallback.visible;

        element.style.setProperty('--x', x);
        element.style.setProperty('--y', y);
        element.style.setProperty('--w', width);
        element.style.setProperty('--h', height);
        element.style.setProperty('--fs', fontScale);
        element.style.setProperty('--color', color);
        element.style.setProperty('--fw', fontWeight);
        element.style.setProperty('--ta', textAlign);
        element.style.setProperty('--va', verticalAlign);
        element.style.zIndex = zIndex;
        element.dataset.layoutVisible = visible ? '1' : '0';
        refreshHidden(element);

        applyPaint(element, widget, fallback);
        applyTextStyle(element, widget, fallback);
      } catch (error) {
        // A malformed single widget entry must not break the rest of the board.
      }
    }
    var safeAreaElement = container.querySelector('#safe-area');
    if (safeAreaElement) {
      var safeArea = isPlainObject(safeLayout.safe_area) ? safeLayout.safe_area : DEFAULT_LAYOUT.safe_area;
      var defaultSafeArea = DEFAULT_LAYOUT.safe_area;
      try {
        var top = numberOr(safeArea.top, defaultSafeArea.top) * 100;
        var right = numberOr(safeArea.right, defaultSafeArea.right) * 100;
        var bottom = numberOr(safeArea.bottom, defaultSafeArea.bottom) * 100;
        var left = numberOr(safeArea.left, defaultSafeArea.left) * 100;
        safeAreaElement.style.inset = top + '% ' + right + '% ' + bottom + '% ' + left + '%';
      } catch (error) {
        // Leave whatever inset the element already had.
      }
    }

    try {
      var elements = Array.isArray(safeLayout.elements) ? safeLayout.elements : [];
      reconcileElements(boardRoot, elements);
    } catch (error) {
      // Leave whatever free elements were already on the board.
    }
  }

  /** Write every widget's text found under `container` from `model`. A
   * static label (WIDGET_FIELDS[id] === null) always shows WIDGET_TEXTS[id].
   * Everything else reads ScoreboardRender.read(model, field); a missing or
   * empty value on an optional widget hides it, on any other widget it
   * simply renders an empty box. Never derives a value: text is only ever
   * copied from the model or from WIDGET_TEXTS, never computed or rounded.
   * Free elements are untouched here -- a text element's text is copied once
   * from the layout in applyLayout() and never from the model. */
  function applyModel(container, model) {
    if (!container || !window.ScoreboardRender) {
      return;
    }
    var read = window.ScoreboardRender.read;
    for (var index = 0; index < WIDGET_IDS.length; index += 1) {
      var id = WIDGET_IDS[index];
      var element = container.querySelector('[data-widget="' + id + '"]');
      if (!element) {
        continue;
      }
      try {
        var field = WIDGET_FIELDS[id];
        var value;
        if (field === null || field === undefined) {
          value = WIDGET_TEXTS[id] || '';
        } else {
          value = read(model, field);
        }
        var text = value === null || value === undefined ? '' : String(value);
        var textElement = element.querySelector('.widget-text');
        if (textElement && textElement.textContent !== text) {
          textElement.textContent = text;
        }
        element.dataset.hasValue = (!isOptional(id) || text !== '') ? '1' : '0';
        refreshHidden(element);
      } catch (error) {
        // Never let one bad widget stop the rest of the board from updating.
      }
    }
  }

  global.ScoreboardBoard = {
    WIDGET_IDS: WIDGET_IDS,
    WIDGET_FIELDS: WIDGET_FIELDS,
    WIDGET_TEXTS: WIDGET_TEXTS,
    OPTIONAL_WIDGET_IDS: OPTIONAL_WIDGET_IDS,
    DEFAULT_LAYOUT: DEFAULT_LAYOUT,
    FONT_FAMILIES: FONT_FAMILIES,
    build: build,
    applyLayout: applyLayout,
    applyModel: applyModel
  };
})(window);
