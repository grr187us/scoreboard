/* The widgetized spectator/editor board renderer.
 *
 * A "widget" is one positioned text box on the 16:9 logical canvas. Its
 * position/size/style comes from a layout document (produced and validated in
 * Python, `scoreboard.presentation.layout`); its text comes from the view
 * model (also produced in Python). This file only ever *places* and *writes*
 * values it is handed -- it never computes a score, a clock, a down-and-
 * distance, or any other displayed string, matching the house rule in
 * `render.js`.
 *
 * The five data constants below (WIDGET_IDS, WIDGET_FIELDS, WIDGET_TEXTS,
 * OPTIONAL_WIDGET_IDS, DEFAULT_LAYOUT) are written as strict JSON literals --
 * double-quoted keys/strings, no trailing commas, no comments inside the
 * braces -- so a Python test can lift the text between `=` and the closing
 * `;` and `json.loads` it directly against the matching Python constants in
 * `scoreboard.presentation.layout`. Do not introduce single quotes, trailing
 * commas, or computed values inside those literals.
 *
 * Both the spectator page and the layout editor's live preview share this
 * file: `build`/`applyLayout`/`applyModel` only ever look inside the
 * `container` element passed to them, so two independent boards (the real
 * spectator canvas and the editor's preview canvas) can exist in the same
 * document without colliding.
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

  /* Mirrors scoreboard.presentation.layout.default_layout(). Preserves the
   * pre-widget spectator arrangement: the clock label and both timeout
   * widgets start hidden because today's board never drew them, and
   * possession moves from an inline mark beside the team name to its own
   * widget centred between the two names. */
  var DEFAULT_LAYOUT = {
  "schema_version": 1,
  "name": "Default",
  "safe_area": {
    "top": 0.04,
    "right": 0.04,
    "bottom": 0.04,
    "left": 0.04
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
      "z_index": 0
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
      "z_index": 0
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
      "z_index": 0
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
      "z_index": 0
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
      "z_index": 0
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
      "z_index": 0
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
      "z_index": 0
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
      "z_index": 0
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
      "z_index": 0
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
      "z_index": 0
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
      "z_index": 0
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
      "z_index": 0
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
      "z_index": 0
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
      "z_index": 0
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
      "z_index": 0
    }
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

  /** Toggle an element's hidden state from its two independent reasons: the
   * layout said "not visible", or (for an optional widget) the model gave it
   * nothing to show. Either reason hides it; neither call needs to know
   * about the other's most recent state. */
  function refreshHidden(element) {
    var visible = element.dataset.layoutVisible !== '0';
    var hasValue = element.dataset.hasValue !== '0';
    element.hidden = !(visible && hasValue);
  }

  /** Empty the container and append one widget element per WIDGET_IDS, in
   * order. Re-buildable at any time; nothing here reads a layout or model. */
  function build(container) {
    if (!container) {
      return;
    }
    container.innerHTML = '';
    for (var index = 0; index < WIDGET_IDS.length; index += 1) {
      var id = WIDGET_IDS[index];
      var widget = document.createElement('div');
      widget.className = 'widget';
      widget.setAttribute('data-widget', id);
      widget.dataset.layoutVisible = '1';
      widget.dataset.hasValue = '1';
      var text = document.createElement('span');
      text.className = 'widget-text';
      widget.appendChild(text);
      container.appendChild(widget);
    }
  }

  /** Place and style every widget found under `container` from `layout`.
   * Tolerant of a missing/partial layout: any absent piece -- the whole
   * document, the widgets map, or a single widget's individual properties --
   * falls back to DEFAULT_LAYOUT rather than throwing or leaving a widget
   * unstyled. */
  function applyLayout(container, layout) {
    if (!container) {
      return;
    }
    var safeLayout = isPlainObject(layout) ? layout : DEFAULT_LAYOUT;
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
  }

  /** Write every widget's text found under `container` from `model`. A
   * static label (WIDGET_FIELDS[id] === null) always shows WIDGET_TEXTS[id].
   * Everything else reads ScoreboardRender.read(model, field); a missing or
   * empty value on an optional widget hides it, on any other widget it
   * simply renders an empty box. Never derives a value: text is only ever
   * copied from the model or from WIDGET_TEXTS, never computed or rounded. */
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
    build: build,
    applyLayout: applyLayout,
    applyModel: applyModel
  };
})(window);
