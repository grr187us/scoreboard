/* The widgetized spectator/editor board renderer.
 *
 * A "widget" is one positioned text box on the 16:9 logical canvas; a "free
 * element" (text/image/box) is an operator-added extra placed the same way.
 * Both come from a layout document (produced and validated in Python,
 * `scoreboard.presentation.layout`); a widget's and a text element's text
 * comes from the view model / a widget-texts map / the layout itself. This
 * file only ever *places* and *writes* values it is handed -- JavaScript
 * copies text from exactly three places -- the view model, a widget-texts
 * map, and a validated layout's `elements[].text` -- and computes none of
 * it, matching the house rule in `render.js`.
 *
 * Schema v3 (presentation-screens spec) adds a second widget "kind": the
 * in-game board (registry "game", unchanged from v2) and the pre-game/
 * halftime countdown board (registry "event"). `build(container, kind)`
 * records which kind a board root is; `applyLayout`/`applyModel` read that
 * kind back off the root to pick the matching registry.
 *
 * The data constants below (WIDGET_IDS, WIDGET_FIELDS, WIDGET_TEXTS,
 * OPTIONAL_WIDGET_IDS, EVENT_WIDGET_IDS, EVENT_WIDGET_FIELDS,
 * EVENT_WIDGET_TEXTS, EVENT_OPTIONAL_WIDGET_IDS, FONT_FAMILIES,
 * DEFAULT_SCREENS, DEFAULT_LAYOUT) are written as strict JSON literals --
 * double-quoted keys/strings, no trailing commas, no comments inside the
 * braces -- so a Python test can lift the text between `=` and the closing
 * `;` and `json.loads` it directly against the matching Python constants in
 * `scoreboard.presentation.layout`. Do not introduce single quotes, trailing
 * commas, or computed values inside those literals. `DEFAULT_LAYOUT`'s
 * `screens` key is assigned right after its own literal, from the already
 * separately declared `DEFAULT_SCREENS` literal, so both stay pure JSON on
 * their own.
 *
 * Both the spectator page and the layout editor's live preview share this
 * file: `build`/`applyLayout`/`applyModel` only ever look inside the
 * `container` element passed to them, so independent boards (the spectator's
 * game and event sections, and the editor's preview canvas) can exist in the
 * same document without colliding.
 *
 * Every placed node -- widget or free element -- carries `data-item="<id>"`.
 * `build()` marks the container it fills with `data-board-root="1"` and
 * `data-board-kind="<kind>"`; `applyLayout()` looks for that marker (falling
 * back to the container it was given) and reconciles the free-element nodes
 * underneath it: creates ones newly present in the screen document's
 * `elements`, removes ones no longer present, updates the rest, and inserts
 * any new node just before the first widget node so a widget always draws
 * above an element at equal `z_index`.
 *
 * September 8, 2026 (event-screens spec section 3): a fourth element type,
 * `ticker`, a bundled-image `asset:` src, validated gradient `fill`s built
 * here from numbers only, a bounded named `animation` per node, rotation,
 * vertical text, a dashed border style and a motion kill switch
 * (`setMotion`). Animations are bound to nodes that persist: widgets are
 * built once, elements are reconciled in place by id, and `applyModel` --
 * the once-per-second path -- never rewrites an element node's structure or
 * an animation attribute, so a snapshot or a layout push never restarts a
 * running animation.
 */

(function (global) {
  'use strict';

  var WIDGET_IDS = [
    "home_name", "home_score", "possession", "away_name", "away_score",
    "game_clock_label", "game_clock_value",
    "quarter", "down", "distance",
    "play_clock_label", "play_clock_value", "ball_on",
    "home_timeouts", "away_timeouts",
    "status_message", "status_clock"
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
    "away_timeouts": "football.away_timeouts_display",
    "status_message": "status.display",
    "status_clock": "status.clock_display"
  };

  var WIDGET_FORMAT_FIELDS = {
  "quarter": {
    "ordinal": "quarter"
  },
  "down": {
    "ordinal": "football.down_display"
  },
  "distance": {
    "value": "football.distance_value_display"
  },
  "ball_on": {
    "value": "football.ball_on_value_display"
  },
  "home_timeouts": {
    "dots": "football.home_timeouts_dots"
  },
  "away_timeouts": {
    "dots": "football.away_timeouts_dots"
  }
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
    "home_timeouts", "away_timeouts",
    "status_message", "status_clock"
  ];

  /* The "event" registry: the pre-game/halftime countdown board (schema v3).
   * Mirrors scoreboard.presentation.layout.EVENT_WIDGET_IDS. */
  var EVENT_WIDGET_IDS = [
    "home_name", "home_score", "away_name", "away_score",
    "event_phase", "event_title", "event_clock", "warmup"
  ];

  /* Mirrors scoreboard.presentation.layout.EVENT_WIDGET_FIELDS. */
  var EVENT_WIDGET_FIELDS = {
    "home_name": "teams.home.name",
    "home_score": "teams.home.score",
    "away_name": "teams.away.name",
    "away_score": "teams.away.score",
    "event_phase": "clocks.event.phase",
    "event_title": "clocks.event.title",
    "event_clock": "clocks.event.display",
    "warmup": "clocks.event.warmup_display"
  };

  /* No static labels on the event screens: every event widget's text comes
   * from the view model. Mirrors scoreboard.presentation.layout.EVENT_WIDGET_TEXTS. */
  var EVENT_WIDGET_TEXTS = {};

  /* Hidden when the value is empty/None. Mirrors
   * scoreboard.presentation.layout.EVENT_OPTIONAL_WIDGET_IDS. */
  var EVENT_OPTIONAL_WIDGET_IDS = ["warmup"];

  /* Mirrors scoreboard.presentation.layout.FONT_FAMILIES: the CSS font stack
   * for each font id. Every family here is already installed on Windows --
   * nothing is ever loaded from a network. */
  var FONT_FAMILIES = {
    "arial": "Arial, Helvetica, sans-serif",
    "arial_black": "'Arial Black', Arial, sans-serif",
    "impact": "Impact, 'Arial Black', sans-serif",
    "bahnschrift": "Bahnschrift, 'Segoe UI', Arial, sans-serif",
    "bahnschrift_condensed": "'Bahnschrift Condensed', Bahnschrift, 'Segoe UI', Arial, sans-serif",
    "barlow_condensed": "'Barlow Condensed', 'Bahnschrift Condensed', Bahnschrift, Impact, sans-serif",
    "segoe": "'Segoe UI', Segoe, Arial, sans-serif",
    "segoe_black": "'Segoe UI Black', 'Segoe UI', Arial, sans-serif",
    "consolas": "Consolas, 'Courier New', monospace",
    "georgia": "Georgia, 'Times New Roman', serif",
    "verdana": "Verdana, Geneva, sans-serif",
    "trebuchet": "'Trebuchet MS', Arial, sans-serif",
    "varsity": "'Jersey M54', Graduate, Impact, 'Arial Black', sans-serif",
    "graduate": "Graduate, Impact, 'Arial Black', sans-serif"
  };

  /* Mirrors scoreboard.presentation.layout.default_layout()["screens"]: the
   * pre-game and halftime mini-documents. Geometry is identical between the
   * two screens; only `visible` differs (event_phase and warmup only show at
   * halftime). Every widget carries the same neutral v2 style defaults as
   * the game widgets above. */
  var DEFAULT_SCREENS = {
    "pregame": {
      "safe_area": {
        "top": 0.04,
        "right": 0.04,
        "bottom": 0.04,
        "left": 0.04
      },
      "background": {
        "color": "#071B3A"
      },
      "widgets": {
        "home_name": {
          "id": "home_name",
          "display_format": "default",
          "fit_text": true,
          "visible": true,
          "x": 0.191,
          "y": 0.63,
          "width": 0.235,
          "height": 0.208,
          "font_scale": 0.081,
          "color": "#FFFFFF",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 700,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.0,
          "text_transform": "uppercase",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        },
        "home_score": {
          "id": "home_score",
          "display_format": "default",
          "fit_text": true,
          "visible": false,
          "x": 0.191,
          "y": 0.84,
          "width": 0.235,
          "height": 0.05,
          "font_scale": 0.04,
          "color": "#FFFFFF",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 700,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "graduate",
          "letter_spacing": 0.0,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        },
        "away_name": {
          "id": "away_name",
          "display_format": "default",
          "fit_text": true,
          "visible": true,
          "x": 0.574,
          "y": 0.63,
          "width": 0.235,
          "height": 0.208,
          "font_scale": 0.081,
          "color": "#DDE7F4",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 700,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.0,
          "text_transform": "uppercase",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        },
        "away_score": {
          "id": "away_score",
          "display_format": "default",
          "fit_text": true,
          "visible": false,
          "x": 0.574,
          "y": 0.84,
          "width": 0.235,
          "height": 0.05,
          "font_scale": 0.04,
          "color": "#FFFFFF",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 700,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "graduate",
          "letter_spacing": 0.0,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        },
        "event_phase": {
          "id": "event_phase",
          "display_format": "default",
          "fit_text": true,
          "visible": false,
          "x": 0.1,
          "y": 0.04,
          "width": 0.8,
          "height": 0.05,
          "font_scale": 0.0266,
          "color": "#FFFFFF",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 700,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.1,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        },
        "event_title": {
          "id": "event_title",
          "display_format": "default",
          "fit_text": true,
          "visible": true,
          "x": 0.1,
          "y": 0.365,
          "width": 0.8,
          "height": 0.05,
          "font_scale": 0.0266,
          "color": "#F5AE08",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 600,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.3,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        },
        "event_clock": {
          "id": "event_clock",
          "display_format": "default",
          "fit_text": true,
          "visible": true,
          "x": 0.1,
          "y": 0.415,
          "width": 0.8,
          "height": 0.2,
          "font_scale": 0.148,
          "color": "#F5AE08",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 700,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "graduate",
          "letter_spacing": 0.0,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "animation": {
            "preset": "blink_soft",
            "duration_seconds": 1.0
          },
          "orientation": "horizontal"
        },
        "warmup": {
          "id": "warmup",
          "display_format": "default",
          "fit_text": true,
          "visible": false,
          "x": 0.3,
          "y": 0.84,
          "width": 0.4,
          "height": 0.05,
          "font_scale": 0.025,
          "color": "#DDE7F4",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 500,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.1,
          "text_transform": "uppercase",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        }
      },
      "elements": [
        {
          "id": "top_glow",
          "type": "box",
          "visible": true,
          "x": 0.0,
          "y": 0.0,
          "width": 1.0,
          "height": 0.52,
          "z_index": 0,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": {
            "kind": "radial",
            "center_x": 0.5,
            "center_y": 0.0,
            "radius_x": 0.6,
            "radius_y": 1.0,
            "stops": [
              {
                "color": "#2C62AB",
                "opacity": 0.5,
                "at": 0.0
              },
              {
                "color": "#2C62AB",
                "opacity": 0.0,
                "at": 0.72
              }
            ]
          },
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "light_sweep",
          "type": "box",
          "visible": true,
          "x": 0.33,
          "y": -0.2,
          "width": 0.34,
          "height": 1.4,
          "z_index": 1,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": {
            "kind": "linear",
            "angle": 90.0,
            "stops": [
              {
                "color": "#FFFFFF",
                "opacity": 0.0,
                "at": 0.0
              },
              {
                "color": "#FFFFFF",
                "opacity": 0.06,
                "at": 0.5
              },
              {
                "color": "#FFFFFF",
                "opacity": 0.0,
                "at": 1.0
              }
            ]
          },
          "animation": {
            "preset": "sweep",
            "duration_seconds": 11.0
          },
          "rotate_degrees": 0.0,
          "bleed": true
        },
        {
          "id": "home_rule",
          "type": "box",
          "visible": true,
          "x": 0.03,
          "y": 0.06,
          "width": 0.28,
          "height": 0.0056,
          "z_index": 0,
          "opacity": 1.0,
          "background": "#C8242B",
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "away_rule",
          "type": "box",
          "visible": true,
          "x": 0.69,
          "y": 0.06,
          "width": 0.28,
          "height": 0.0056,
          "z_index": 0,
          "opacity": 1.0,
          "background": "#2C62AB",
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "eyebrow",
          "type": "text",
          "visible": true,
          "x": 0.33,
          "y": 0.04,
          "width": 0.34,
          "height": 0.046,
          "z_index": 2,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.22,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "color": "#93A9C9",
          "font_scale": 0.0203,
          "font_weight": 600,
          "text_align": "center",
          "vertical_align": "middle",
          "text": "TMSA TIGERS FOOTBALL",
          "fit_text": true,
          "animation": null,
          "orientation": "horizontal",
          "rotate_degrees": 0.0
        },
        {
          "id": "welcome_to",
          "type": "text",
          "visible": true,
          "x": 0.1,
          "y": 0.09,
          "width": 0.8,
          "height": 0.055,
          "z_index": 2,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.3,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "color": "#DDE7F4",
          "font_scale": 0.0266,
          "font_weight": 500,
          "text_align": "center",
          "vertical_align": "middle",
          "text": "WELCOME TO",
          "fit_text": true,
          "animation": null,
          "orientation": "horizontal",
          "rotate_degrees": 0.0
        },
        {
          "id": "stadium_title",
          "type": "text",
          "visible": true,
          "x": 0.05,
          "y": 0.145,
          "width": 0.9,
          "height": 0.17,
          "z_index": 2,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.0,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "color": "#FFFFFF",
          "font_scale": 0.122,
          "font_weight": 700,
          "text_align": "center",
          "vertical_align": "middle",
          "text": "TIGER STADIUM",
          "fit_text": true,
          "animation": null,
          "orientation": "horizontal",
          "rotate_degrees": 0.0
        },
        {
          "id": "gold_rule",
          "type": "box",
          "visible": true,
          "x": 0.41,
          "y": 0.325,
          "width": 0.18,
          "height": 0.0069,
          "z_index": 0,
          "opacity": 1.0,
          "background": "#F5AE08",
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "crest_plate",
          "type": "box",
          "visible": true,
          "x": 0.04,
          "y": 0.63,
          "width": 0.117,
          "height": 0.208,
          "z_index": 1,
          "opacity": 1.0,
          "background": "#FFFFFF",
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0125,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "crest",
          "type": "image",
          "visible": true,
          "x": 0.0517,
          "y": 0.6508,
          "width": 0.0936,
          "height": 0.1664,
          "z_index": 2,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "src": "asset:tigers-crest",
          "fit": "contain",
          "animation": null,
          "rotate_degrees": 0.0
        },
        {
          "id": "versus",
          "type": "text",
          "visible": true,
          "x": 0.46,
          "y": 0.63,
          "width": 0.08,
          "height": 0.208,
          "z_index": 2,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "graduate",
          "letter_spacing": 0.0,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "color": "#F5AE08",
          "font_scale": 0.041,
          "font_weight": 700,
          "text_align": "center",
          "vertical_align": "middle",
          "text": "VS",
          "fit_text": true,
          "animation": null,
          "orientation": "horizontal",
          "rotate_degrees": 0.0
        },
        {
          "id": "opponent_slot",
          "type": "box",
          "visible": true,
          "x": 0.843,
          "y": 0.63,
          "width": 0.117,
          "height": 0.208,
          "z_index": 1,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": "#DDE7F4",
          "border_width": 0.0023,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "dashed",
          "fill": {
            "kind": "stripes",
            "angle": 45.0,
            "color": "#DDE7F4",
            "opacity": 0.14,
            "on": 0.002,
            "off": 0.008
          },
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "opponent_caption",
          "type": "text",
          "visible": true,
          "x": 0.843,
          "y": 0.63,
          "width": 0.117,
          "height": 0.208,
          "z_index": 2,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "consolas",
          "letter_spacing": 0.0,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "color": "#DDE7F4",
          "font_scale": 0.0188,
          "font_weight": 400,
          "text_align": "center",
          "vertical_align": "middle",
          "text": "OPPONENT\nLOGO",
          "fit_text": false,
          "animation": null,
          "orientation": "horizontal",
          "rotate_degrees": 0.0
        },
        {
          "id": "ticker_band",
          "type": "box",
          "visible": true,
          "x": 0.0,
          "y": 0.89,
          "width": 1.0,
          "height": 0.11,
          "z_index": 0,
          "opacity": 1.0,
          "background": "#0D2B5A",
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "ticker_rule",
          "type": "box",
          "visible": true,
          "x": 0.0,
          "y": 0.89,
          "width": 1.0,
          "height": 0.0042,
          "z_index": 1,
          "opacity": 1.0,
          "background": "#2C62AB",
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "ticker",
          "type": "ticker",
          "visible": true,
          "x": 0.0,
          "y": 0.89,
          "width": 1.0,
          "height": 0.1,
          "z_index": 10,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.16,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "color": "#DDE7F4",
          "font_scale": 0.025,
          "font_weight": 500,
          "text_align": "center",
          "vertical_align": "middle",
          "lines": [
            "WELCOME TO TIGER STADIUM",
            "SENIOR NIGHT — HONORING THE CLASS OF 2027",
            "CONCESSIONS OPEN BEHIND THE HOME STANDS",
            "NATIONAL ANTHEM AT 6:55",
            "SCIENCE · WISDOM · PEACE"
          ],
          "mode": "scroll",
          "speed_seconds": 30.0
        }
      ]
    },
    "halftime": {
      "safe_area": {
        "top": 0.04,
        "right": 0.04,
        "bottom": 0.04,
        "left": 0.04
      },
      "background": {
        "color": "#071B3A"
      },
      "widgets": {
        "home_name": {
          "id": "home_name",
          "display_format": "default",
          "fit_text": true,
          "visible": true,
          "x": 0.04,
          "y": 0.27,
          "width": 0.27,
          "height": 0.09,
          "font_scale": 0.045,
          "color": "#FFFFFF",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 700,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.0,
          "text_transform": "uppercase",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        },
        "home_score": {
          "id": "home_score",
          "display_format": "default",
          "fit_text": true,
          "visible": true,
          "x": 0.04,
          "y": 0.37,
          "width": 0.27,
          "height": 0.23,
          "font_scale": 0.141,
          "color": "#FFFFFF",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 700,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "graduate",
          "letter_spacing": 0.0,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        },
        "away_name": {
          "id": "away_name",
          "display_format": "default",
          "fit_text": true,
          "visible": true,
          "x": 0.69,
          "y": 0.27,
          "width": 0.27,
          "height": 0.09,
          "font_scale": 0.045,
          "color": "#FFFFFF",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 700,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.0,
          "text_transform": "uppercase",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        },
        "away_score": {
          "id": "away_score",
          "display_format": "default",
          "fit_text": true,
          "visible": true,
          "x": 0.69,
          "y": 0.37,
          "width": 0.27,
          "height": 0.23,
          "font_scale": 0.141,
          "color": "#FFFFFF",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 700,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "graduate",
          "letter_spacing": 0.0,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        },
        "event_phase": {
          "id": "event_phase",
          "display_format": "default",
          "fit_text": true,
          "visible": true,
          "x": 0.05,
          "y": 0.095,
          "width": 0.9,
          "height": 0.13,
          "font_scale": 0.092,
          "color": "#FFFFFF",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 700,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.04,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        },
        "event_title": {
          "id": "event_title",
          "display_format": "default",
          "fit_text": true,
          "visible": true,
          "x": 0.33,
          "y": 0.29,
          "width": 0.34,
          "height": 0.06,
          "font_scale": 0.0234,
          "color": "#F5AE08",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 600,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.26,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        },
        "event_clock": {
          "id": "event_clock",
          "display_format": "default",
          "fit_text": true,
          "visible": true,
          "x": 0.33,
          "y": 0.36,
          "width": 0.34,
          "height": 0.16,
          "font_scale": 0.092,
          "color": "#F5AE08",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 700,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "graduate",
          "letter_spacing": 0.0,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "animation": {
            "preset": "blink_soft",
            "duration_seconds": 1.0
          },
          "orientation": "horizontal"
        },
        "warmup": {
          "id": "warmup",
          "display_format": "default",
          "fit_text": true,
          "visible": true,
          "x": 0.42,
          "y": 0.655,
          "width": 0.34,
          "height": 0.086,
          "font_scale": 0.025,
          "color": "#DDE7F4",
          "text_align": "center",
          "vertical_align": "middle",
          "font_weight": 500,
          "z_index": 3,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.1,
          "text_transform": "uppercase",
          "text_effect": "none",
          "padding": 0.0,
          "animation": null,
          "orientation": "horizontal"
        }
      },
      "elements": [
        {
          "id": "top_glow",
          "type": "box",
          "visible": true,
          "x": 0.0,
          "y": 0.0,
          "width": 1.0,
          "height": 0.52,
          "z_index": 0,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": {
            "kind": "radial",
            "center_x": 0.5,
            "center_y": 0.0,
            "radius_x": 0.6,
            "radius_y": 1.0,
            "stops": [
              {
                "color": "#2C62AB",
                "opacity": 0.5,
                "at": 0.0
              },
              {
                "color": "#2C62AB",
                "opacity": 0.0,
                "at": 0.72
              }
            ]
          },
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "light_sweep",
          "type": "box",
          "visible": true,
          "x": 0.33,
          "y": -0.2,
          "width": 0.34,
          "height": 1.4,
          "z_index": 1,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": {
            "kind": "linear",
            "angle": 90.0,
            "stops": [
              {
                "color": "#FFFFFF",
                "opacity": 0.0,
                "at": 0.0
              },
              {
                "color": "#FFFFFF",
                "opacity": 0.06,
                "at": 0.5
              },
              {
                "color": "#FFFFFF",
                "opacity": 0.0,
                "at": 1.0
              }
            ]
          },
          "animation": {
            "preset": "sweep",
            "duration_seconds": 13.0
          },
          "rotate_degrees": 0.0,
          "bleed": true
        },
        {
          "id": "home_rule",
          "type": "box",
          "visible": true,
          "x": 0.03,
          "y": 0.06,
          "width": 0.28,
          "height": 0.0056,
          "z_index": 0,
          "opacity": 1.0,
          "background": "#C8242B",
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "away_rule",
          "type": "box",
          "visible": true,
          "x": 0.69,
          "y": 0.06,
          "width": 0.28,
          "height": 0.0056,
          "z_index": 0,
          "opacity": 1.0,
          "background": "#2C62AB",
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "eyebrow",
          "type": "text",
          "visible": true,
          "x": 0.33,
          "y": 0.04,
          "width": 0.34,
          "height": 0.046,
          "z_index": 2,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.22,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "color": "#93A9C9",
          "font_scale": 0.0203,
          "font_weight": 600,
          "text_align": "center",
          "vertical_align": "middle",
          "text": "TMSA TIGERS FOOTBALL",
          "fit_text": true,
          "animation": null,
          "orientation": "horizontal",
          "rotate_degrees": 0.0
        },
        {
          "id": "amber_rule",
          "type": "box",
          "visible": true,
          "x": 0.44,
          "y": 0.225,
          "width": 0.12,
          "height": 0.0069,
          "z_index": 0,
          "opacity": 1.0,
          "background": "#F5AE08",
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "home_panel",
          "type": "box",
          "visible": true,
          "x": 0.04,
          "y": 0.27,
          "width": 0.27,
          "height": 0.34,
          "z_index": 0,
          "opacity": 1.0,
          "background": "#0D2B5A",
          "background_opacity": 1.0,
          "border_color": "#2C62AB",
          "border_width": 0.0023,
          "corner_radius": 0.0,
          "corner_cut": 0.0141,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "home_banner",
          "type": "box",
          "visible": true,
          "x": 0.04,
          "y": 0.27,
          "width": 0.27,
          "height": 0.09,
          "z_index": 1,
          "opacity": 1.0,
          "background": "#17468C",
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0141,
          "cut_corners": "top",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "away_panel",
          "type": "box",
          "visible": true,
          "x": 0.69,
          "y": 0.27,
          "width": 0.27,
          "height": 0.34,
          "z_index": 0,
          "opacity": 1.0,
          "background": "#0D2B5A",
          "background_opacity": 1.0,
          "border_color": "#C8242B",
          "border_width": 0.0023,
          "corner_radius": 0.0,
          "corner_cut": 0.0141,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "away_banner",
          "type": "box",
          "visible": true,
          "x": 0.69,
          "y": 0.27,
          "width": 0.27,
          "height": 0.09,
          "z_index": 1,
          "opacity": 1.0,
          "background": "#A50021",
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0141,
          "cut_corners": "top",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "chip_box",
          "type": "box",
          "visible": true,
          "x": 0.24,
          "y": 0.655,
          "width": 0.16,
          "height": 0.086,
          "z_index": 0,
          "opacity": 1.0,
          "background": "#0D2B5A",
          "background_opacity": 1.0,
          "border_color": "#2C62AB",
          "border_width": 0.0023,
          "corner_radius": 0.0,
          "corner_cut": 0.006,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "chip_text",
          "type": "text",
          "visible": true,
          "x": 0.24,
          "y": 0.655,
          "width": 0.16,
          "height": 0.086,
          "z_index": 2,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.12,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "color": "#DDE7F4",
          "font_scale": 0.0219,
          "font_weight": 600,
          "text_align": "center",
          "vertical_align": "middle",
          "text": "SECOND HALF",
          "fit_text": true,
          "animation": null,
          "orientation": "horizontal",
          "rotate_degrees": 0.0
        },
        {
          "id": "ticker_band",
          "type": "box",
          "visible": true,
          "x": 0.0,
          "y": 0.89,
          "width": 1.0,
          "height": 0.11,
          "z_index": 0,
          "opacity": 1.0,
          "background": "#0D2B5A",
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "ticker_rule",
          "type": "box",
          "visible": true,
          "x": 0.0,
          "y": 0.89,
          "width": 1.0,
          "height": 0.0042,
          "z_index": 1,
          "opacity": 1.0,
          "background": "#2C62AB",
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "fill": null,
          "animation": null,
          "rotate_degrees": 0.0,
          "bleed": false
        },
        {
          "id": "ticker",
          "type": "ticker",
          "visible": true,
          "x": 0.0,
          "y": 0.89,
          "width": 1.0,
          "height": 0.1,
          "z_index": 10,
          "opacity": 1.0,
          "background": null,
          "background_opacity": 1.0,
          "border_color": null,
          "border_width": 0.0,
          "corner_radius": 0.0,
          "corner_cut": 0.0,
          "cut_corners": "all",
          "border_style": "solid",
          "font_family": "barlow_condensed",
          "letter_spacing": 0.16,
          "text_transform": "none",
          "text_effect": "none",
          "padding": 0.0,
          "color": "#DDE7F4",
          "font_scale": 0.025,
          "font_weight": 500,
          "text_align": "center",
          "vertical_align": "middle",
          "lines": [
            "SENIOR NIGHT — HONORING THE CLASS OF 2027",
            "TIGER BAND TAKES THE FIELD",
            "50/50 RAFFLE DRAWING AT THE START OF THE 3RD",
            "SCIENCE · WISDOM · PEACE"
          ],
          "mode": "scroll",
          "speed_seconds": 30.0
        }
      ]
    }
  };

  /* Mirrors scoreboard.presentation.layout.default_layout(). Preserves the
   * pre-widget spectator arrangement: the clock label and both timeout
   * widgets start hidden because today's board never drew them, and
   * possession moves from an inline mark beside the team name to its own
   * widget centred between the two names. Every widget's v2 style
   * properties are set to their neutral defaults so this document renders
   * pixel-identical to the v1 board. Schema v3 adds the `screens` key,
   * assigned separately below from DEFAULT_SCREENS so both literals stay
   * pure JSON on their own. */
  var DEFAULT_LAYOUT = {
    "schema_version": 3,
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
      },
      "status_message": {
        "id": "status_message",
        "visible": true,
        "x": 0.24,
        "y": 0.408,
        "width": 0.16,
        "height": 0.056,
        "font_scale": 0.026,
        "color": "#FFC845",
        "text_align": "center",
        "vertical_align": "middle",
        "font_weight": 800,
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
      },
      "status_clock": {
        "id": "status_clock",
        "visible": true,
        "x": 0.6,
        "y": 0.408,
        "width": 0.16,
        "height": 0.056,
        "font_scale": 0.026,
        "color": "#FFC845",
        "text_align": "center",
        "vertical_align": "middle",
        "font_weight": 800,
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
        "corner_cut": 0.0,
        "cut_corners": "all",
        "padding": 0.0,
        "border_style": "solid",
        "animation": null,
        "orientation": "horizontal",
        "display_format": "default",
        "fit_text": false
      }
    },
    "elements": []
  };

  /* Assigned outside the DEFAULT_LAYOUT literal so both stay pure JSON on
   * their own (see the header comment and spec section 2). */
  DEFAULT_LAYOUT.screens = DEFAULT_SCREENS;

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
    },
    ticker: {
      visible: true, x: 0, y: 0.89, width: 1, height: 0.1, z_index: 0, opacity: 1,
      background: null, background_opacity: 1, border_color: null, border_width: 0, corner_radius: 0,
      color: '#FFFFFF', font_scale: 0.025, font_family: 'arial', font_weight: 500,
      letter_spacing: 0, text_transform: 'none', text_effect: 'none',
      text_align: 'center', vertical_align: 'middle', padding: 0,
      lines: [], mode: 'scroll', speed_seconds: 30
    }
  };

  /* Mirrors scoreboard.presentation.layout.BUNDLED_IMAGES: the images that
   * ship inside views/ (path relative to views/). An image element whose
   * `src` is `asset:<key>` draws BUNDLED_IMAGES[key]; both pages that include
   * this file sit one level below views/, so the path is prefixed `../`.
   * Strict JSON, like the other contract literals. */
  var BUNDLED_IMAGES = {"tigers-crest": "shared/img/tigers-crest.png"};

  /* The animation presets board.css knows keyframes for (mirrors
   * scoreboard.presentation.layout.ANIMATION_PRESETS minus "none"). */
  var ANIMATION_LOOKUP = {sweep: true, drift: true, scroll_x: true, marquee: true, blink_soft: true};

  /* What a scrolling/static ticker puts between its lines (mirrors
   * scoreboard.presentation.layout.TICKER_SEPARATOR). */
  var TICKER_SEPARATOR = '  \u2022  ';

  var BUNDLED_IMAGE_KEY = /^asset:([a-z0-9-]{1,40})$/;

  function buildOptionalLookup(ids) {
    var lookup = {};
    for (var index = 0; index < ids.length; index += 1) {
      lookup[ids[index]] = true;
    }
    return lookup;
  }

  var OPTIONAL_LOOKUP = buildOptionalLookup(OPTIONAL_WIDGET_IDS);
  var EVENT_OPTIONAL_LOOKUP = buildOptionalLookup(EVENT_OPTIONAL_WIDGET_IDS);

  /* One registry per widget kind (spec section 2): which widget ids exist,
   * where their text comes from, which are optional, and which document
   * supplies a fallback for anything a real layout omits. Keyed by the
   * `data-board-kind` a board root carries (set by build()). */
  var REGISTRIES = {
    game: {
      ids: WIDGET_IDS,
      fields: WIDGET_FIELDS,
      texts: WIDGET_TEXTS,
      optionalLookup: OPTIONAL_LOOKUP,
      fallback: DEFAULT_LAYOUT
    },
    event: {
      ids: EVENT_WIDGET_IDS,
      fields: EVENT_WIDGET_FIELDS,
      texts: EVENT_WIDGET_TEXTS,
      optionalLookup: EVENT_OPTIONAL_LOOKUP,
      fallback: DEFAULT_SCREENS.pregame
    }
  };

  function registryForKind(kind) {
    return kind === 'event' ? REGISTRIES.event : REGISTRIES.game;
  }

  function registryForRoot(boardRoot) {
    return registryForKind(boardRoot && boardRoot.dataset ? boardRoot.dataset.boardKind : 'game');
  }

  function isOptionalIn(registry, id) {
    return registry.optionalLookup[id] === true;
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

  /** The URL an image element actually loads for its layout `src`: a data
   * URI as-is, a bundled `asset:<key>` as its packaged path, anything else
   * null. */
  function resolveImageSrc(src) {
    if (typeof src !== 'string') return null;
    if (IMAGE_SRC_PREFIX.test(src)) return src;
    var match = BUNDLED_IMAGE_KEY.exec(src);
    if (match && Object.prototype.hasOwnProperty.call(BUNDLED_IMAGES, match[1])) {
      return '../' + BUNDLED_IMAGES[match[1]];
    }
    return null;
  }

  /** A finite number within [low, high], else null. */
  function boundedNumber(value, low, high) {
    if (typeof value !== 'number' || !isFinite(value) || value < low || value > high) return null;
    return value;
  }

  /** The comma-separated colour stops of a gradient `fill`, or null when
   * any stop is malformed (2..4 stops, hex colours, 0..1 opacity, `at`
   * non-decreasing). */
  function gradientStops(stops) {
    if (!Array.isArray(stops) || stops.length < 2 || stops.length > 4) return null;
    var parts = [];
    var previous = 0;
    for (var i = 0; i < stops.length; i += 1) {
      var stop = stops[i];
      if (!isPlainObject(stop)) return null;
      var at = boundedNumber(stop.at, previous, 1);
      var opacity = boundedNumber(stop.opacity, 0, 1);
      var color = hexToRgba(stop.color, opacity === null ? 1 : opacity);
      if (at === null || opacity === null || !color) return null;
      previous = at;
      parts.push(color + ' ' + (at * 100) + '%');
    }
    return parts.join(', ');
  }

  /** Build the CSS background for a validated `fill` descriptor (spec
   * section 2.4) from its numbers and hex colours alone -- the document
   * never carries a CSS string. Returns {background, period} (period is the
   * stripes repeat in canvas-width fractions, else null), or null when the
   * descriptor is not one of the three known shapes, in which case the flat
   * `background` colour is used instead. */
  function fillToCss(fill) {
    if (!isPlainObject(fill)) return null;
    if (fill.kind === 'linear') {
      var angle = boundedNumber(fill.angle, 0, 360);
      var stops = gradientStops(fill.stops);
      if (angle === null || !stops) return null;
      return {background: 'linear-gradient(' + angle + 'deg, ' + stops + ')', period: null};
    }
    if (fill.kind === 'radial') {
      var cx = boundedNumber(fill.center_x, 0, 1);
      var cy = boundedNumber(fill.center_y, 0, 1);
      var rx = boundedNumber(fill.radius_x, 0.05, 2);
      var ry = boundedNumber(fill.radius_y, 0.05, 2);
      var radialStops = gradientStops(fill.stops);
      if (cx === null || cy === null || rx === null || ry === null || !radialStops) return null;
      return {background: 'radial-gradient(' + (rx * 100) + '% ' + (ry * 100) + '% at ' +
        (cx * 100) + '% ' + (cy * 100) + '%, ' + radialStops + ')', period: null};
    }
    if (fill.kind === 'stripes') {
      var stripeAngle = boundedNumber(fill.angle, 0, 360);
      var on = boundedNumber(fill.on, 0.001, 0.5);
      var off = boundedNumber(fill.off, 0, 1);
      var stripeOpacity = boundedNumber(fill.opacity, 0, 1);
      var stripeColor = hexToRgba(fill.color, stripeOpacity === null ? 1 : stripeOpacity);
      if (stripeAngle === null || on === null || off === null || stripeOpacity === null || !stripeColor) return null;
      var onLength = 'calc(var(--canvas-width) * ' + on + ')';
      var periodLength = 'calc(var(--canvas-width) * ' + (on + off) + ')';
      return {background: 'repeating-linear-gradient(' + stripeAngle + 'deg, ' + stripeColor + ' 0 ' + onLength +
        ', transparent ' + onLength + ' ' + periodLength + ')', period: on + off};
    }
    return null;
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
    var cornerCut = numberOr(source.corner_cut, numberOr(fallback.corner_cut, 0));
    var cutCorners = stringOr(source.cut_corners, stringOr(fallback.cut_corners, 'all'));
    var borderStyle = stringOr(source.border_style, stringOr(fallback.border_style, 'solid'));
    var fill = fillToCss('fill' in source ? source.fill : fallback.fill);

    var background = backgroundColor ? (hexToRgba(backgroundColor, backgroundOpacity) || 'transparent') : 'transparent';
    // A validated gradient fill wins over the flat colour; a fill of unknown
    // shape falls back to it. `--sx` is the stripes period the scroll_x
    // animation slides by, so the loop lands exactly on itself.
    node.style.setProperty('--bg', fill ? fill.background : background);
    if (fill && fill.period !== null) {
      node.style.setProperty('--sx', fill.period);
    } else {
      node.style.removeProperty('--sx');
    }
    node.style.setProperty('--bs', borderStyle === 'dashed' ? 'dashed' : 'solid');
    node.style.setProperty('--bc', borderColor || 'transparent');
    node.style.setProperty('--bw', borderWidth);
    node.style.setProperty('--br', cornerRadius);
    node.style.setProperty('--cut', cornerCut);
    // The chamfer is a CSS clip keyed on this attribute (board.css); an
    // uncut box keeps the plain border/radius path.
    if (cornerCut > 0) {
      node.dataset.cutCorners = cutCorners;
    } else {
      delete node.dataset.cutCorners;
    }
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
    node.dataset.font = fontFamilyKey;
    node.style.setProperty('--ls', letterSpacing);
    node.style.setProperty('--tt', textTransform);
    node.style.setProperty('--pad', padding);

    node.classList.toggle('effect-shadow', textEffect === 'shadow');
    node.classList.toggle('effect-outline', textEffect === 'outline');

    var orientation = stringOr(source.orientation, stringOr(fallback.orientation, 'horizontal'));
    if (orientation === 'vertical' || orientation === 'vertical_flipped') {
      if (node.dataset.orientation !== orientation) node.dataset.orientation = orientation;
    } else if (node.dataset.orientation !== undefined) {
      delete node.dataset.orientation;
    }
  }

  /** Set `data-anim`/`--anim-s` from the entry's validated `animation`
   * ({preset, duration_seconds}), or remove them when it is null. Each is
   * written only when its value actually changed: rewriting the same
   * attribute would be harmless, but a *different* animation name restarts
   * the animation, and a layout push that changes nothing must not. */
  function applyMotionAttributes(node, source, fallback) {
    var animation = 'animation' in source ? source.animation : fallback.animation;
    var preset = null;
    var seconds = null;
    if (isPlainObject(animation) && ANIMATION_LOOKUP[animation.preset] === true) {
      var duration = numberOr(animation.duration_seconds, 0);
      if (duration > 0) {
        preset = animation.preset;
        seconds = duration + 's';
      }
    }
    if (preset === null) {
      if (node.dataset.anim !== undefined) delete node.dataset.anim;
      if (node.style.getPropertyValue('--anim-s') !== '') node.style.removeProperty('--anim-s');
      return;
    }
    if (node.dataset.anim !== preset) node.dataset.anim = preset;
    if (node.style.getPropertyValue('--anim-s') !== seconds) node.style.setProperty('--anim-s', seconds);
  }

  /** Empty the container and append one widget element per the chosen
   * registry's ids, in order. Re-buildable at any time; nothing here reads a
   * layout or model. Marks the container as the board root -- with the kind
   * it was built as -- so `applyLayout`/`applyModel` can find it and pick
   * the matching registry, even when called with an outer wrapper (the
   * spectator page's `#canvas`). `kind` is `"game"` (default) or `"event"`. */
  function build(container, kind) {
    if (!container) {
      return;
    }
    var resolvedKind = kind === 'event' ? 'event' : 'game';
    var registry = registryForKind(resolvedKind);
    container.innerHTML = '';
    container.dataset.boardRoot = '1';
    container.dataset.boardKind = resolvedKind;
    for (var index = 0; index < registry.ids.length; index += 1) {
      var id = registry.ids[index];
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
    if (entry.type !== 'text' && entry.type !== 'image' && entry.type !== 'box' && entry.type !== 'ticker') {
      return false;
    }
    if (entry.type === 'image' && resolveImageSrc(entry.src) === null) {
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
    } else if (type === 'ticker') {
      node.className = 'widget element element-ticker';
      var track = document.createElement('div');
      track.className = 'ticker-track';
      node.appendChild(track);
    } else {
      node.className = 'element element-box';
    }
    return node;
  }

  /** The ticker's lines as the layout gave them: non-empty strings only. */
  function tickerLines(value) {
    var lines = [];
    if (Array.isArray(value)) {
      for (var i = 0; i < value.length; i += 1) {
        if (typeof value[i] === 'string' && value[i] !== '') lines.push(value[i]);
      }
    }
    return lines;
  }

  /** Whether animations may run for `node`: the motion kill switch
   * (`data-motion="off"` on a container) and the viewer's reduced-motion
   * preference both turn it off. */
  function motionEnabledFor(node) {
    if (node.closest && node.closest('[data-motion="off"]')) return false;
    if (global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
    return true;
  }

  function clearTickerTimer(node) {
    if (node._tickerTimer) {
      clearTimeout(node._tickerTimer);
      node._tickerTimer = null;
    }
  }

  /** Rotate mode: every `stepMs` fade the run out, swap in the next line,
   * fade back in. A chain of timeouts rather than one interval, so a rebuild
   * or removal can always cancel exactly the pending step. */
  function scheduleTickerStep(node, run, lines, index, stepMs) {
    node._tickerTimer = setTimeout(function () {
      run.classList.add('ticker-fade');
      node._tickerTimer = setTimeout(function () {
        var next = index + 1 < lines.length ? index + 1 : 0;
        run.textContent = lines[next];
        run.classList.remove('ticker-fade');
        scheduleTickerStep(node, run, lines, next, stepMs);
      }, 400);
    }, stepMs);
  }

  /** Build (or leave alone) a ticker node's track from its layout `entry`
   * (spec section 3.3). The track is rebuilt only when the lines, mode,
   * speed or motion state changed, so a layout push carrying the same
   * ticker never restarts it. Scroll: two identical runs slid by one run
   * (board.css). Rotate: one run, cross-faded line by line on a timer.
   * Motion off: one static run with every line, shrunk to fit. */
  function applyTicker(node, entry, defaults) {
    var lines = tickerLines(entry.lines);
    if (!lines.length) lines = tickerLines(defaults.lines);
    var mode = entry.mode === 'rotate' ? 'rotate' : 'scroll';
    var speed = numberOr(entry.speed_seconds, 0);
    if (!(speed > 0)) speed = mode === 'rotate' ? 5 : numberOr(defaults.speed_seconds, 30);
    var motion = motionEnabledFor(node);
    var key = lines.join('\n') + '|' + mode + '|' + speed + '|' + motion;
    node._tickerEntry = entry;
    if (node._tickerKey === key) return;
    node._tickerKey = key;
    clearTickerTimer(node);

    var track = node.querySelector('.ticker-track');
    if (!track) {
      track = document.createElement('div');
      track.className = 'ticker-track';
      node.appendChild(track);
    }
    track.textContent = '';
    var shownMode = motion ? mode : 'static';
    var runCount = shownMode === 'scroll' ? 2 : 1;
    var text = shownMode === 'scroll' ? lines.join(TICKER_SEPARATOR) + TICKER_SEPARATOR
      : (shownMode === 'rotate' ? (lines[0] || '') : lines.join(TICKER_SEPARATOR));
    var firstRun = null;
    for (var i = 0; i < runCount; i += 1) {
      var run = document.createElement('span');
      run.className = 'widget-text ticker-run';
      run.textContent = text;
      track.appendChild(run);
      if (!firstRun) firstRun = run;
    }
    node.dataset.tickerMode = shownMode;
    node.style.setProperty('--anim-s', speed + 's');
    // Only the static line shrinks to fit; a moving run keeps its size.
    node.dataset.fitText = shownMode === 'static' ? '1' : '0';
    node._fitKey = null;
    if (shownMode === 'rotate' && lines.length > 1) {
      scheduleTickerStep(node, firstRun, lines, 0, speed * 1000);
    }
    if (shownMode === 'static') fitWidgetText(node, firstRun);
  }

  /** Re-run applyTicker for every ticker under `root` from the entry it last
   * applied (after the motion switch flips, or the OS preference changes). */
  function refreshTickers(root) {
    var tickers = root.querySelectorAll('.element-ticker');
    for (var i = 0; i < tickers.length; i += 1) {
      var node = tickers[i];
      try {
        applyTicker(node, node._tickerEntry || {}, ELEMENT_DEFAULTS.ticker);
      } catch (error) {
        // One bad ticker must not stop the others from refreshing.
      }
    }
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

    if (entry.type !== 'ticker') {
      // Rotation (text/image/box) and the bounded animation; a ticker has
      // neither -- its motion is its own scroll/rotate mode below.
      node.style.setProperty('--rot', numberOr(entry.rotate_degrees, 0));
      applyMotionAttributes(node, entry, defaults);
    }

    if (entry.type === 'text' || entry.type === 'ticker') {
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
    }

    if (entry.type === 'text') {
      var textElement = node.querySelector('.widget-text');
      var text = typeof entry.text === 'string' ? entry.text : defaults.text;
      if (textElement && textElement.textContent !== text) {
        textElement.textContent = text;
      }
      // Opt-in single-line shrink-to-fit, exactly as for a widget; measured
      // once the node is laid out (fitWidgetText caches by geometry).
      node.dataset.fitText = entry.fit_text === true ? '1' : '0';
      node._fitKey = null;
      fitWidgetText(node, textElement);
    } else if (entry.type === 'image') {
      var fit = stringOr(entry.fit, defaults.fit);
      node.style.setProperty('--fit', fit);
      var img = node.querySelector('img');
      var src = resolveImageSrc(entry.src);
      if (img && src !== null && img.getAttribute('src') !== src) {
        img.src = src;
      }
    } else if (entry.type === 'ticker') {
      applyTicker(node, entry, defaults);
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
        clearTickerTimer(node);
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
        clearTickerTimer(stale);
        stale.parentNode.removeChild(stale);
      }
    }
  }

  /** Place and style every widget found under `container` from `screenDoc`,
   * paint the board background on `container` itself, and reconcile the
   * free-element nodes under the board root. `screenDoc` is a screen
   * document: the top level of a layout for the game board, or
   * `layout.screens.pregame` / `.halftime` for an event board (see
   * `screenDocument()` below). The widget id list and per-widget fallbacks
   * come from the board root's `data-board-kind` (set by `build()`).
   * Tolerant of a missing/partial document: any absent piece -- the whole
   * document, the widgets map, a single widget's individual properties, or
   * the elements list -- falls back to something safe rather than throwing
   * or leaving a widget unstyled. */
  function applyLayout(container, screenDoc) {
    if (!container) {
      return;
    }
    var boardRoot = container.querySelector('[data-board-root]') || container;
    var registry = registryForRoot(boardRoot);
    var safeDoc = isPlainObject(screenDoc) ? screenDoc : registry.fallback;

    try {
      var background = isPlainObject(safeDoc.background) ? safeDoc.background : registry.fallback.background;
      container.style.background = stringOr(background.color, registry.fallback.background.color);
    } catch (error) {
      // Leave whatever background the container already had.
    }

    var widgets = isPlainObject(safeDoc.widgets) ? safeDoc.widgets : registry.fallback.widgets;
    for (var index = 0; index < registry.ids.length; index += 1) {
      var id = registry.ids[index];
      var element = boardRoot.querySelector('[data-widget="' + id + '"]');
      if (!element) {
        continue;
      }
      var fallback = registry.fallback.widgets[id];
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
        element.dataset.displayFormat = stringOr(widget.display_format, 'default');
        element.dataset.fitText = widget.fit_text === true ? '1' : '0';
        element._fitKey = null;
        refreshHidden(element);

        applyPaint(element, widget, fallback);
        applyTextStyle(element, widget, fallback);
        applyMotionAttributes(element, widget, fallback);
      } catch (error) {
        // A malformed single widget entry must not break the rest of the board.
      }
    }
    var safeAreaElement = container.querySelector('#safe-area, [data-safe-area]');
    if (safeAreaElement) {
      var safeArea = isPlainObject(safeDoc.safe_area) ? safeDoc.safe_area : registry.fallback.safe_area;
      var defaultSafeArea = registry.fallback.safe_area;
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
      var elements = Array.isArray(safeDoc.elements) ? safeDoc.elements : [];
      reconcileElements(boardRoot, elements);
    } catch (error) {
      // Leave whatever free elements were already on the board.
    }
    // A board that is hidden right now (the spectator's event board before
    // its first snapshot) has no geometry to fit text elements against; note
    // it, and applyModel finishes the fit the first time the board has size.
    fitElementText(boardRoot);
    // A format edit must repaint immediately even while clocks are stopped.
    if (boardRoot._lastModel) applyModel(container, boardRoot._lastModel);
  }

  /** Fit every shrink-to-fit text element and static ticker under
   * `boardRoot` once it has a size; until then mark the fit as pending. */
  function fitElementText(boardRoot) {
    var box = boardRoot.getBoundingClientRect();
    boardRoot._elementFitPending = !(box.width && box.height);
    if (boardRoot._elementFitPending) return;
    var nodes = boardRoot.querySelectorAll('[data-element][data-fit-text="1"]');
    for (var i = 0; i < nodes.length; i += 1) {
      fitWidgetText(nodes[i], nodes[i].querySelector('.widget-text'));
    }
  }

  /** Mark the node that owns `textElement` as carrying colon spans (or
   * not), so board.css can blink only the colons of a clock. Written only on
   * change: the attribute is part of the blink's selector. */
  function setColonFlag(textElement, hasColon) {
    var owner = textElement.parentNode;
    if (!owner || !owner.dataset) return;
    if (hasColon) {
      if (owner.dataset.colon !== '1') owner.dataset.colon = '1';
    } else if (owner.dataset.colon !== undefined) {
      delete owner.dataset.colon;
    }
  }

  /** Write `text` into a widget's text node. A colon is wrapped in its own
   * span so a clock's separator can be raised to sit between the digits
   * (board.css, per font) and blinked on its own; the node's textContent
   * stays exactly `text`. The children always alternate text node, colon
   * span, text node, ... (empty text nodes included), so when the new text
   * has the same number of colon-separated parts as the current content the
   * text nodes are updated in place and the existing `.clock-colon` spans
   * -- and any animation running on them -- survive the tick. */
  function setWidgetText(textElement, text) {
    if (text.indexOf(':') === -1) {
      textElement.textContent = text;
      setColonFlag(textElement, false);
      return;
    }
    var parts = text.split(':');
    var children = textElement.childNodes;
    var inPlace = children.length === parts.length * 2 - 1;
    for (var c = 0; inPlace && c < children.length; c += 1) {
      var expectsText = c % 2 === 0;
      var isText = children[c].nodeType === 3;
      var isColon = !isText && children[c].nodeType === 1 && children[c].className === 'clock-colon';
      if (expectsText ? !isText : !isColon) inPlace = false;
    }
    if (inPlace) {
      for (var p = 0; p < parts.length; p += 1) {
        var textNode = children[p * 2];
        if (textNode.nodeValue !== parts[p]) textNode.nodeValue = parts[p];
      }
      setColonFlag(textElement, true);
      return;
    }
    textElement.textContent = '';
    for (var i = 0; i < parts.length; i += 1) {
      if (i > 0) {
        var colon = document.createElement('span');
        colon.className = 'clock-colon';
        colon.textContent = ':';
        textElement.appendChild(colon);
      }
      textElement.appendChild(document.createTextNode(parts[i]));
    }
    setColonFlag(textElement, true);
  }

  var measureContext = null;

  /** The rendered glyph height ("ink") of `text` in the widget's computed
   * font: what a spectator actually sees, as opposed to the CSS line box,
   * which for a display face such as Impact is nearly half again as tall as
   * the digits themselves. Measuring ink lets a score fill its panel the way
   * a real video board does. Returns null when the browser cannot measure. */
  function inkExtent(text, style) {
    if (!measureContext) {
      var canvas = document.createElement('canvas');
      measureContext = canvas.getContext && canvas.getContext('2d');
      if (!measureContext) return null;
    }
    measureContext.font = [style.fontStyle, style.fontWeight, style.fontSize, style.fontFamily].join(' ');
    if ('letterSpacing' in measureContext) measureContext.letterSpacing = style.letterSpacing;
    var metrics = measureContext.measureText(text);
    if (typeof metrics.actualBoundingBoxAscent !== 'number') return null;
    return {
      height: metrics.actualBoundingBoxAscent + metrics.actualBoundingBoxDescent,
      ascent: metrics.actualBoundingBoxAscent,
      descent: metrics.actualBoundingBoxDescent,
      fontAscent: typeof metrics.fontBoundingBoxAscent === 'number' ? metrics.fontBoundingBoxAscent : null
    };
  }

  /** Centre a fitted, middle-aligned line by its glyph ink rather than its
   * line box. A display face whose ascent and descent are unequal around
   * the capitals (Barlow Condensed, Graduate) otherwise sits visibly high or
   * low in a box authored to the ink height, and can overhang it. The nudge
   * is written in em so it stays right at any canvas size without being
   * re-measured. Vertical text and top/bottom alignment are left to the
   * line box. */
  function centreInk(element, textElement, style, vertical) {
    textElement.style.top = '';
    if (vertical || style.alignItems !== 'center') return;
    var spanStyle = window.getComputedStyle(textElement);
    var metrics = inkExtent(transformedText(textElement.textContent, spanStyle), spanStyle);
    if (!metrics || metrics.fontAscent === null) return;
    var range = document.createRange();
    range.selectNodeContents(textElement);
    var line = range.getBoundingClientRect();
    var fontSize = Number(spanStyle.fontSize.slice(0, -2));
    if (!line.height || !fontSize) return;
    // A text range's rect is the font's content area, so its top plus the
    // font ascent is the baseline; the ink sits between the actual ascent
    // and descent around it.
    var baseline = line.top + metrics.fontAscent;
    var inkCentre = baseline - metrics.ascent + metrics.height / 2;
    var box = element.getBoundingClientRect();
    var top = box.top + Number(style.borderTopWidth.slice(0, -2)) + Number(style.paddingTop.slice(0, -2));
    var bottom = box.bottom - Number(style.borderBottomWidth.slice(0, -2)) - Number(style.paddingBottom.slice(0, -2));
    var shift = (top + bottom) / 2 - inkCentre;
    if (shift > 0.5 || shift < -0.5) textElement.style.top = (shift / fontSize) + 'em';
  }

  function transformedText(text, style) {
    if (style.textTransform === 'uppercase') return text.toUpperCase();
    if (style.textTransform === 'lowercase') return text.toLowerCase();
    return text;
  }

  // Opt-in geometry fitting only: the snapshot text is never abbreviated.
  // Cache measurements across unchanged clock ticks; a layout edit clears it.
  function fitWidgetText(element, textElement) {
    if (!textElement) return;
    if (element.dataset.fitText !== '1') {
      textElement.style.fontSize = '';
      textElement.style.top = '';
      return;
    }
    var box = element.getBoundingClientRect();
    if (!box.width || !box.height) return;
    var style = window.getComputedStyle(element);
    var width = element.clientWidth - Number(style.paddingLeft.slice(0, -2)) - Number(style.paddingRight.slice(0, -2));
    var height = element.clientHeight - Number(style.paddingTop.slice(0, -2)) - Number(style.paddingBottom.slice(0, -2));
    var key = [textElement.textContent, width, height, style.fontSize, style.fontFamily,
      style.fontWeight, style.letterSpacing, style.textTransform].join('|');
    if (element._fitKey === key) return;
    element._fitKey = key;
    textElement.style.fontSize = '';
    // Width comes from the laid-out text (it honours tabular digits and
    // letter spacing); only the height is taken from the glyph ink.
    var range = document.createRange();
    range.selectNodeContents(textElement);
    var ink = range.getBoundingClientRect();
    // Vertical text: the range rect already describes both axes as drawn
    // (the glyph ink measurement is a horizontal line's height).
    var vertical = element.dataset.orientation === 'vertical' || element.dataset.orientation === 'vertical_flipped';
    var glyphs = vertical ? null : inkExtent(transformedText(textElement.textContent, style), style);
    if (glyphs) ink = {width: ink.width, height: glyphs.height};
    if (width <= 0 || height <= 0 || !ink.width || !ink.height) return;
    var factor = width / ink.width;
    if (height / ink.height < factor) factor = height / ink.height;
    if (factor < 1) textElement.style.fontSize = (factor * 96) + '%';
    centreInk(element, textElement, style, vertical);
  }

  /** Re-run every fitted widget's fit under every board root in the
   * document. A widget fitted before its web font finished loading (a lazy
   * `@font-face`, e.g. the Grid preset's Graduate face) is measured against
   * the invisible fallback face `font-display: block` substitutes meanwhile,
   * so the cached `_fitKey` -- keyed on the font-family *string*, not its
   * load state -- never notices the font swap and the stale, too-large size
   * sticks until the widget's text next changes. Clearing `_fitKey` first
   * forces `fitWidgetText` to re-measure against whatever font is actually
   * painted now. */
  function refitAllWidgetText() {
    var roots = document.querySelectorAll('[data-board-root]');
    for (var r = 0; r < roots.length; r += 1) {
      var elements = roots[r].querySelectorAll('[data-fit-text="1"]');
      for (var i = 0; i < elements.length; i += 1) {
        var element = elements[i];
        element._fitKey = null;
        fitWidgetText(element, element.querySelector('.widget-text'));
      }
    }
  }

  // A lazily-loaded web font (Graduate, via the Grid preset's `varsity`
  // family) can finish loading after the first fit already ran against its
  // fallback face; re-fit once it's actually available. Older browsers
  // without the Font Loading API just keep today's behaviour.
  if (global.document && document.fonts) {
    document.fonts.ready.then(refitAllWidgetText, function () {});
    document.fonts.addEventListener('loadingdone', refitAllWidgetText);
  }
  // The viewer's OS preference flipping mid-game is treated like the kill
  // switch: every ticker is rebuilt for its new mode.
  if (global.matchMedia) {
    try {
      var reducedMotion = global.matchMedia('(prefers-reduced-motion: reduce)');
      if (reducedMotion && reducedMotion.addEventListener) {
        reducedMotion.addEventListener('change', function () {
          if (global.document) refreshTickers(document);
        });
      }
    } catch (error) {
      // No media query support: tickers keep the mode they were built with.
    }
  }

  /** Write every widget's text found under `container` from `model`, using
   * the registry that matches the board root's `data-board-kind`. A static
   * label (registry.fields[id] === null) always shows registry.texts[id].
   * Everything else reads ScoreboardRender.read(model, field); a missing or
   * empty value on an optional widget hides it, on any other widget it
   * simply renders an empty box. Never derives a value: text is only ever
   * copied from the model or from the texts map, never computed or rounded.
   * Free elements are untouched here -- a text element's text is copied once
   * from the layout in applyLayout() and never from the model -- with one
   * deliberate exception: a text element's deferred shrink-to-fit, which
   * only sets a font size on its inner span once the board first has a size
   * and never rewrites an element node or an animation attribute. */
  function applyModel(container, model) {
    if (!container || !window.ScoreboardRender) {
      return;
    }
    var boardRoot = container.querySelector('[data-board-root]') || container;
    var registry = registryForRoot(boardRoot);
    var read = window.ScoreboardRender.read;
    boardRoot._lastModel = model;
    if (boardRoot._elementFitPending) fitElementText(boardRoot);
    for (var index = 0; index < registry.ids.length; index += 1) {
      var id = registry.ids[index];
      var element = boardRoot.querySelector('[data-widget="' + id + '"]');
      if (!element) {
        continue;
      }
      try {
        var field = registry.fields[id];
        var formats = boardRoot.dataset.boardKind === 'game' && WIDGET_FORMAT_FIELDS[id];
        var format = element.dataset.displayFormat;
        if (formats && Object.prototype.hasOwnProperty.call(formats, format)) field = formats[format];
        var value;
        if (field === null || field === undefined) {
          value = registry.texts[id] || '';
        } else {
          value = read(model, field);
        }
        var text = value === null || value === undefined ? '' : String(value);
        var textElement = element.querySelector('.widget-text');
        if (format === 'dots' && formats && formats.dots) {
          element.setAttribute('aria-label', stringOr(read(model, registry.fields[id]), ''));
        } else {
          element.removeAttribute('aria-label');
        }
        if (textElement && textElement.textContent !== text) {
          setWidgetText(textElement, text);
        }
        element.dataset.hasValue = (!isOptionalIn(registry, id) || text !== '') ? '1' : '0';
        refreshHidden(element);
        fitWidgetText(element, textElement);
      } catch (error) {
        // Never let one bad widget stop the rest of the board from updating.
      }
    }
  }

  /** Which screen a spectator lifecycle shows: `"pregame"` during PRE_GAME,
   * `"halftime"` during HALFTIME, otherwise the in-game screen. */
  function screenForLifecycle(lifecycle) {
    if (lifecycle === 'PRE_GAME') {
      return 'pregame';
    }
    if (lifecycle === 'HALFTIME') {
      return 'halftime';
    }
    return 'game';
  }

  /** The screen document for `screenId` inside `layout`: `layout` itself for
   * `"game"` (or any id that is not a known event screen); `layout.screens
   * [screenId]` when that is a plain object; otherwise `DEFAULT_SCREENS
   * [screenId]`. */
  function screenDocument(layout, screenId) {
    if (screenId !== 'pregame' && screenId !== 'halftime') {
      return layout;
    }
    var screens = isPlainObject(layout) && isPlainObject(layout.screens) ? layout.screens : null;
    var screen = screens && isPlainObject(screens[screenId]) ? screens[screenId] : null;
    return screen || DEFAULT_SCREENS[screenId];
  }

  /** The motion kill switch (spec section 3.2): `enabled === false` puts
   * `data-motion="off"` on `container` (board.css then stops every animation
   * beneath it), rebuilds each ticker under it as one static line, and
   * re-fits text; `true` removes the attribute and rebuilds the tickers in
   * their moving modes. A host preference, never game state. */
  function setMotion(container, enabled) {
    if (!container || !container.dataset) return;
    if (enabled === false) {
      if (container.dataset.motion !== 'off') container.dataset.motion = 'off';
    } else if (container.dataset.motion !== undefined) {
      delete container.dataset.motion;
    }
    refreshTickers(container);
    refitAllWidgetText();
  }

  global.ScoreboardBoard = {
    WIDGET_IDS: WIDGET_IDS,
    WIDGET_FIELDS: WIDGET_FIELDS,
    WIDGET_TEXTS: WIDGET_TEXTS,
    OPTIONAL_WIDGET_IDS: OPTIONAL_WIDGET_IDS,
    EVENT_WIDGET_IDS: EVENT_WIDGET_IDS,
    EVENT_WIDGET_FIELDS: EVENT_WIDGET_FIELDS,
    EVENT_WIDGET_TEXTS: EVENT_WIDGET_TEXTS,
    EVENT_OPTIONAL_WIDGET_IDS: EVENT_OPTIONAL_WIDGET_IDS,
    DEFAULT_LAYOUT: DEFAULT_LAYOUT,
    DEFAULT_SCREENS: DEFAULT_SCREENS,
    FONT_FAMILIES: FONT_FAMILIES,
    BUNDLED_IMAGES: BUNDLED_IMAGES,
    build: build,
    setMotion: setMotion,
    applyLayout: applyLayout,
    applyModel: applyModel,
    screenForLifecycle: screenForLifecycle,
    screenDocument: screenDocument
  };
})(window);
