/* The presentation layout editor -- bootstrap.
 *
 * This window is presentation-only by construction. It holds no authoritative
 * state, it never calls a game command -- there is deliberately no path from
 * this file to bridge.command() -- and the only thing it can change is the
 * stored layout document that says where spectator widgets and decorative
 * elements are drawn.
 *
 * This file wires the other three modules together: `editor-state.js` (pure
 * draft/history/selection logic), `editor-canvas.js` (pointer gestures), and
 * `editor-panels.js` (the layers rail, inspector, menus, and status bar). It
 * owns every call to the bridge and is the only place that decides when a
 * change is significant enough to enter history.
 *
 * Nothing here computes a displayed value. Every string in the preview
 * arrives already formatted in the view model, exactly as on the spectator
 * board.
 */

(function () {
  'use strict';

  var R = window.ScoreboardRender;
  var Board = window.ScoreboardBoard;
  var LayoutEditor = window.LayoutEditor;
  var S = LayoutEditor.State;
  var Canvas = LayoutEditor.Canvas;
  var Panels = LayoutEditor.Panels;

  var clone = S.clone;

  function el(id) { return document.getElementById(id); }

  var boardRoot = el('game-board');
  var canvas = el('canvas');
  var alertLine = el('alert');

  var ACCEPTED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];

  var pendingReplaceId = null;
  var pendingPresetApply = null;

  /* --- The app object -----------------------------------------------------
   *
   * Every other module reaches the running editor only through this: the
   * live draft, the selection, the history stack, and a small set of verbs
   * (`commit`, `liveRefresh`, `select`, ...) that keep the preview, the
   * rail, and the inspector honest with each other.
   */
  var app = {
    api: null,
    state: null,
    draft: null,
    snapshot: null,
    dirty: false,
    suppress: false,
    boardSelected: true,
    collapsedGroups: {},
    selection: S.createSelection(),
    history: null,
    screen: 'game',
    motion: true
  };

  /* --- Screens -------------------------------------------------------------
   *
   * `app.draft` is always the full v3 document: the Game screen at its top
   * level, plus `screens.pregame` / `screens.halftime`. Everything that
   * edits or reads widgets/elements/safe_area/background for the screen
   * currently on screen goes through `app.screenDoc()` instead of touching
   * `app.draft` directly; history, preview, save, and clamp still see the
   * whole document.
   */

  app.screenDescriptor = function () {
    var found = null;
    ((app.state && app.state.screens) || []).forEach(function (descriptor) {
      if (descriptor.id === app.screen) {
        found = descriptor;
      }
    });
    return found;
  };

  app.screenDoc = function () {
    if (app.screen === 'game') {
      return app.draft;
    }
    app.draft.screens = app.draft.screens || {};
    if (!app.draft.screens[app.screen]) {
      app.draft.screens[app.screen] = { safe_area: {}, background: {}, widgets: {}, elements: [] };
    }
    return app.draft.screens[app.screen];
  };

  app.widgetIds = function () {
    return Object.keys((app.screenDoc() && app.screenDoc().widgets) || {});
  };

  /* Clears the selection, rebuilds the board root for the new screen's kind
   * (game or event), and re-renders every panel against the new screen. */
  app.switchScreen = function (screenId) {
    if (screenId === app.screen) {
      return;
    }
    var descriptor = null;
    ((app.state && app.state.screens) || []).forEach(function (candidate) {
      if (candidate.id === screenId) {
        descriptor = candidate;
      }
    });
    if (!descriptor) {
      return;
    }
    app.screen = screenId;
    S.clearSelection(app.selection);
    app.boardSelected = true;
    Board.build(boardRoot, descriptor.kind);
    app.renderAll();
    Panels.renderPresets(app);
  };

  function showAlert(message) {
    R.setText(alertLine, message);
    alertLine.hidden = false;
  }

  /* --- Motion switch ----------------------------------------------------------
   *
   * A host preference, not a layout property: `state.motion` reports it and
   * `api.set_motion` (when the bridge offers it) changes it for the wall and
   * every window at once. The preview honours it through the same
   * `data-motion` hook on #canvas that the spectator page uses -- the
   * renderer's kill switch reads that attribute; the editor never touches
   * an animation itself. Without the bridge method the switch is local to
   * this preview.
   */

  function applyMotion(enabled) {
    app.motion = enabled !== false;
    if (typeof Board.setMotion === 'function') {
      Board.setMotion(canvas, app.motion);
    }
    canvas.setAttribute('data-motion', app.motion ? 'on' : 'off');
    var button = el('motion-toggle');
    button.setAttribute('aria-pressed', app.motion ? 'true' : 'false');
    R.setText(el('motion-label'), app.motion ? 'Motion on' : 'Motion off');
  }

  function toggleMotionAction() {
    var wanted = !app.motion;
    if (!app.api || typeof app.api.set_motion !== 'function') {
      applyMotion(wanted);
      return;
    }
    Promise.resolve(app.api.set_motion(wanted)).then(function (payload) {
      if (!payload || payload.ok === false) {
        showAlert((payload && payload.message) || 'The motion setting could not be changed.');
        return;
      }
      // A full layout_state payload: adopt its library/limits, keep the draft.
      adoptState(payload, { resetDraft: false, announce: false });
      // adoptState reported the stored layout's issues; the draft on screen
      // is what the operator is judging, so ask about that again.
      app.validateDraft();
    }).catch(function (error) {
      showAlert('The motion setting could not be changed: ' + error);
    });
  }

  function clearAlert() {
    alertLine.hidden = true;
  }

  function precisionScale() {
    var limits = (app.state && app.state.limits) || {};
    var places = limits.coordinate_precision;
    if (typeof places !== 'number' || places <= 0) {
      return 10000;
    }
    var scale = 1;
    for (var i = 0; i < places; i += 1) {
      scale *= 10;
    }
    return scale;
  }

  function markSelectionDot() {
    el('dirty-dot').hidden = !app.dirty;
    // The library menu's "Discard changes" entry follows the same flag, and
    // the menu is only rebuilt when the library changes, so keep it current
    // here rather than waiting for the next library round trip.
    var discardEntry = el('menu-discard');
    if (discardEntry) {
      discardEntry.disabled = !app.dirty;
    }
  }

  function updateHistoryButtons() {
    var back = document.querySelector('[data-action="history_back"]');
    var forward = document.querySelector('[data-action="history_forward"]');
    back.disabled = !S.canGoBack(app.history);
    forward.disabled = !S.canGoForward(app.history);
  }

  /* --- Rendering ------------------------------------------------------------ */

  app.refreshPreview = function () {
    try {
      Board.applyLayout(canvas, app.screenDoc());
      if (app.snapshot) {
        Board.applyModel(boardRoot, app.snapshot);
      }
      Canvas.renderSelection(app);
    } catch (error) {
      // A preview that cannot draw must not take the editor down with it.
      showAlert('The preview could not be drawn: ' + error);
    }
  };

  app.liveRefresh = function () {
    app.refreshPreview();
  };

  app.renderAll = function () {
    app.refreshPreview();
    Panels.renderLayers(app);
    Panels.renderInspector(app);
    Panels.renderScreenSwitch(app);
    updateHistoryButtons();
    markSelectionDot();
  };

  app.markDirty = function (value) {
    app.dirty = Boolean(value);
    markSelectionDot();
  };

  app.validateDraft = function () {
    if (!app.api || !app.api.preview_layout) {
      return;
    }
    Promise.resolve(app.api.preview_layout(app.draft)).then(function (payload) {
      Panels.applyIssues(app, payload);
    }).catch(function (error) {
      showAlert('The layout could not be checked: ' + error);
    });
  };

  app.commit = function () {
    app.markDirty(true);
    S.pushHistory(app.history, app.draft);
    app.renderAll();
    app.validateDraft();
  };

  /* --- Selection -------------------------------------------------------- */

  app.select = function (ids) {
    S.selectMany(app.selection, ids);
    app.boardSelected = false;
    Panels.renderLayers(app);
    Panels.renderInspector(app);
    Canvas.renderSelection(app);
  };

  app.toggleSelect = function (id) {
    S.toggleMember(app.selection, id);
    app.boardSelected = false;
    Panels.renderLayers(app);
    Panels.renderInspector(app);
    Canvas.renderSelection(app);
  };

  app.selectBoard = function () {
    S.clearSelection(app.selection);
    app.boardSelected = true;
    Panels.renderLayers(app);
    Panels.renderInspector(app);
    Canvas.renderSelection(app);
  };

  app.clearSelection = function () {
    S.clearSelection(app.selection);
    app.boardSelected = false;
    Panels.renderLayers(app);
    Panels.renderInspector(app);
    Canvas.renderSelection(app);
  };

  app.selectAllVisible = function () {
    var ids = [];
    var doc = app.screenDoc();
    var widgets = doc.widgets || {};
    Object.keys(widgets).forEach(function (id) {
      if (widgets[id] && widgets[id].visible !== false) {
        ids.push(id);
      }
    });
    (doc.elements || []).forEach(function (element) {
      if (element.visible !== false) {
        ids.push(element.id);
      }
    });
    app.select(ids);
  };

  /* --- Elements ----------------------------------------------------------- */

  app.addElement = function (element) {
    var doc = app.screenDoc();
    doc.elements = doc.elements || [];
    doc.elements.push(element);
    app.select([element.id]);
    app.commit();
  };

  app.deleteSelectedElements = function () {
    var ids = app.selection.ids;
    var doc = app.screenDoc();
    var removedAny = false;
    doc.elements = (doc.elements || []).filter(function (element) {
      if (ids.indexOf(element.id) !== -1) {
        removedAny = true;
        return false;
      }
      return true;
    });
    if (!removedAny) {
      return;
    }
    app.clearSelection();
    app.commit();
  };

  app.duplicateSelected = function () {
    var ids = app.selection.ids;
    var doc = app.screenDoc();
    var widgetIds = app.widgetIds();
    var scale = precisionScale();
    var newIds = [];
    for (var i = 0; i < ids.length; i += 1) {
      var element = S.getElement(doc, ids[i]);
      if (!element) {
        continue; // widgets are never duplicated
      }
      var copy = clone(element);
      copy.id = S.nextElementId(doc, widgetIds, element.type);
      S.setGeometry(copy, 'x', S.clampRange(copy.x + 0.02, 0, 1 - copy.width), scale);
      S.setGeometry(copy, 'y', S.clampRange(copy.y + 0.02, 0, 1 - copy.height), scale);
      doc.elements.push(copy);
      newIds.push(copy.id);
    }
    if (!newIds.length) {
      return;
    }
    app.select(newIds);
    app.commit();
  };

  function toggleVisibleFor(id) {
    var item = S.getItem(app.screenDoc(), id);
    if (!item) {
      return;
    }
    item.visible = !item.visible;
    app.commit();
  }

  /* --- Images --------------------------------------------------------------- */

  function isAcceptedImageType(type) {
    return ACCEPTED_IMAGE_TYPES.indexOf(type) !== -1;
  }

  function maxImageBytes() {
    var limits = (app.state && app.state.limits) || {};
    return typeof limits.max_image_bytes === 'number' ? limits.max_image_bytes : 2000000;
  }

  app.addImageFromFile = function (file) {
    if (!file) {
      return;
    }
    if (!isAcceptedImageType(file.type)) {
      showAlert('That file is not a PNG, JPEG, GIF, or WEBP image.');
      return;
    }
    if (file.size > maxImageBytes()) {
      showAlert('That image is too large for the layout.');
      return;
    }
    var reader = new FileReader();
    reader.onload = function () {
      var dataUrl = reader.result;
      var probe = new Image();
      probe.onload = function () {
        var element = S.makeImageElement(app.screenDoc(), app.widgetIds(), dataUrl,
          probe.naturalWidth, probe.naturalHeight);
        app.addElement(element);
      };
      probe.onerror = function () {
        showAlert('That image could not be read.');
      };
      probe.src = dataUrl;
    };
    reader.onerror = function () {
      showAlert('That image could not be read.');
    };
    reader.readAsDataURL(file);
  };

  app.replaceImageForSelected = function (id, file) {
    var element = S.getElement(app.screenDoc(), id);
    if (!element || element.type !== 'image' || !file) {
      return;
    }
    if (!isAcceptedImageType(file.type)) {
      showAlert('That file is not a PNG, JPEG, GIF, or WEBP image.');
      return;
    }
    if (file.size > maxImageBytes()) {
      showAlert('That image is too large for the layout.');
      return;
    }
    var reader = new FileReader();
    reader.onload = function () {
      element.src = reader.result;
      app.commit();
    };
    reader.onerror = function () {
      showAlert('That image could not be read.');
    };
    reader.readAsDataURL(file);
  };

  /* --- Widget-only actions ---------------------------------------------------- */

  app.resetWidgetAction = function () {
    var id = app.selection.ids.length === 1 ? app.selection.ids[0] : null;
    if (!app.api || !app.api.reset_widget || !id || S.kindOf(app.screenDoc(), id) !== 'widget') {
      return;
    }
    Promise.resolve(app.api.reset_widget(id, app.draft, app.screen)).then(function (payload) {
      if (payload && payload.layout) {
        app.draft = clone(payload.layout);
        S.pushHistory(app.history, app.draft);
        app.markDirty(true);
        app.renderAll();
        Panels.applyIssues(app, payload);
      }
    }).catch(function (error) {
      showAlert('That widget could not be reset: ' + error);
    });
  };

  app.clampDraftAction = function () {
    if (!app.api || !app.api.clamp_layout) {
      return;
    }
    Promise.resolve(app.api.clamp_layout(app.draft)).then(function (payload) {
      if (payload && payload.layout) {
        app.draft = clone(payload.layout);
        S.pushHistory(app.history, app.draft);
        app.markDirty(true);
        app.renderAll();
        Panels.applyIssues(app, payload);
      }
    }).catch(function (error) {
      showAlert('The layout could not be fitted: ' + error);
    });
  };

  /* --- History -------------------------------------------------------------- */

  function goHistory(direction) {
    var next = direction < 0 ? S.historyBack(app.history) : S.historyForward(app.history);
    if (!next) {
      return;
    }
    app.draft = next;
    var doc = app.screenDoc();
    var stillThere = app.selection.ids.filter(function (id) { return Boolean(S.getItem(doc, id)); });
    S.selectMany(app.selection, stillThere);
    app.renderAll();
    app.validateDraft();
  }

  /* --- Talking to Python ------------------------------------------------------ */

  function adoptState(payload, options) {
    options = options || {};
    if (!payload) {
      return;
    }
    app.state = payload;
    if (options.resetDraft !== false) {
      app.draft = clone(payload.layout);
      app.history = S.createHistory(app.draft);
      S.clearSelection(app.selection);
      app.boardSelected = true;
      // The draft now equals what is stored: nothing is unsaved.
      app.markDirty(false);
    }
    applyMotion(payload.motion !== false);
    Panels.renderLibraryMenu(app);
    Panels.renderPresets(app);
    app.renderAll();
    Panels.applyIssues(app, payload);
    if (payload.message && options.announce !== false) {
      showAlert(payload.message);
    }
    // `fell_back` is also true on a first run, when nothing has ever been
    // saved; only a fall-back that *reported a problem* is damage worth an
    // alert. The plain first-run case is already covered by `message`.
    var fellBackIssues = payload.fell_back && payload.issues && payload.issues.length;
    if (fellBackIssues) {
      showAlert('The stored layout could not be read, so the built-in default is in use. '
        + 'Saving will replace the unreadable file.');
    }
  }

  function refreshSnapshot() {
    if (!app.api || !app.api.get_snapshot) {
      return;
    }
    Promise.resolve(app.api.get_snapshot()).then(function (model) {
      app.snapshot = model;
      app.refreshPreview();
    }).catch(function (error) {
      showAlert('The live board values could not be read: ' + error);
    });
  }

  function save(name) {
    if (!app.api || !app.api.save_layout) {
      return;
    }
    Promise.resolve(app.api.save_layout(name, app.draft)).then(function (payload) {
      if (payload && payload.ok) {
        clearAlert();
        adoptState(payload);
      } else {
        Panels.applyIssues(app, payload);
        showAlert((payload && payload.message) || 'That layout could not be saved.');
      }
    }).catch(function (error) {
      showAlert('That layout could not be saved: ' + error);
    });
  }

  function discard() {
    if (!app.api || !app.api.layout_state) {
      return;
    }
    Promise.resolve(app.api.layout_state()).then(function (payload) {
      clearAlert();
      adoptState(payload, { announce: false });
    }).catch(function (error) {
      showAlert('The saved layout could not be re-read: ' + error);
    });
  }

  function selectLayoutAction(name) {
    if (!app.api || !app.api.select_layout) {
      return;
    }
    Promise.resolve(app.api.select_layout(name)).then(function (payload) {
      adoptState(payload);
    }).catch(function (error) {
      showAlert('That layout could not be selected: ' + error);
    });
  }

  function renameLayoutAction(oldName, newName) {
    if (!app.api || !app.api.rename_layout) {
      return;
    }
    Promise.resolve(app.api.rename_layout(oldName, newName)).then(function (payload) {
      if (payload && payload.ok) {
        adoptState(payload);
      } else {
        showAlert((payload && payload.message) || 'That layout could not be renamed.');
      }
    }).catch(function (error) {
      showAlert('That layout could not be renamed: ' + error);
    });
  }

  function duplicateLayoutAction(name, newName) {
    if (!app.api || !app.api.duplicate_layout) {
      return;
    }
    Promise.resolve(app.api.duplicate_layout(name, newName)).then(function (payload) {
      if (payload && payload.ok) {
        adoptState(payload);
      } else {
        showAlert((payload && payload.message) || 'That layout could not be duplicated.');
      }
    }).catch(function (error) {
      showAlert('That layout could not be duplicated: ' + error);
    });
  }

  function deleteLayoutAction(name) {
    if (!app.api || !app.api.delete_layout) {
      return;
    }
    Promise.resolve(app.api.delete_layout(name)).then(function (payload) {
      adoptState(payload);
    }).catch(function (error) {
      showAlert('That layout could not be deleted: ' + error);
    });
  }

  function resetLayoutAction() {
    if (!app.api || !app.api.reset_layout) {
      return;
    }
    Promise.resolve(app.api.reset_layout()).then(function (payload) {
      adoptState(payload);
    }).catch(function (error) {
      showAlert('The layout could not be reset: ' + error);
    });
  }

  /* A dirty draft never loses work silently: both branches below stage their
   * apply function and ask first, exactly as v2 did for the single Game
   * preset list. */
  function confirmedApply(apply) {
    if (app.dirty) {
      pendingPresetApply = apply;
      Panels.togglePopover('replace-draft-popover');
    } else {
      apply();
    }
  }

  /* On the Game screen a preset is a full layout, but only its board pieces
   * are copied in -- the document's name and its event screens are kept. On
   * Pre-game/Halftime a preset is one screen mini-document, dropped wholesale
   * into draft.screens[app.screen]. */
  function applyPresetAction(id) {
    if (app.screen === 'game') {
      var preset = null;
      ((app.state && app.state.presets) || []).forEach(function (candidate) {
        if (candidate.id === id) {
          preset = candidate;
        }
      });
      if (!preset) {
        return;
      }
      confirmedApply(function () {
        var source = preset.layout;
        app.draft.safe_area = clone(source.safe_area);
        app.draft.background = clone(source.background);
        app.draft.widgets = clone(source.widgets);
        app.draft.elements = clone(source.elements);
        S.pushHistory(app.history, app.draft);
        app.markDirty(true);
        app.boardSelected = true;
        S.clearSelection(app.selection);
        app.renderAll();
        app.validateDraft();
      });
      return;
    }

    var screenPresets = (app.state && app.state.screen_presets && app.state.screen_presets[app.screen]) || [];
    var screenPreset = null;
    screenPresets.forEach(function (candidate) {
      if (candidate.id === id) {
        screenPreset = candidate;
      }
    });
    if (!screenPreset) {
      return;
    }
    confirmedApply(function () {
      app.draft.screens = app.draft.screens || {};
      app.draft.screens[app.screen] = clone(screenPreset.screen);
      S.pushHistory(app.history, app.draft);
      app.markDirty(true);
      app.boardSelected = true;
      S.clearSelection(app.selection);
      app.renderAll();
      app.validateDraft();
    });
  }

  /* --- Property edits ---------------------------------------------------------
   *
   * `input` updates the draft and the preview live, without touching
   * history. `change` (a control losing focus, a checkbox flipping, a
   * colour picker closing) is the point a gesture becomes a fact worth
   * stepping back to, so it pushes one history entry.
   */

  var NUMERIC_WIDGET_PROPS = {
    x: 1, y: 1, width: 1, height: 1, font_scale: 1, letter_spacing: 1,
    background_opacity: 1, border_width: 1, corner_radius: 1, corner_cut: 1, padding: 1,
    opacity: 1, z_index: 1, font_weight: 1
  };

  var PERCENT_PROPS = {
    x: 1, y: 1, width: 1, height: 1, font_scale: 1, background_opacity: 1,
    border_width: 1, corner_radius: 1, corner_cut: 1, padding: 1, opacity: 1,
    fill_opacity_a: 1, fill_opacity_b: 1, fill_on: 1, fill_off: 1
  };

  /* Controls whose value is not a property of its own but one piece of a
   * composite the schema stores as an object or a list: `animation`
   * ({preset, duration_seconds} or null), `fill` (a gradient/stripes
   * descriptor or null), a ticker's `lines`, and an image's bundled `asset`.
   * `writeComposite` below turns each into the exact schema shape. */
  var COMPOSITE_PROPS = {
    animation_preset: 1, animation_seconds: 1,
    fill_kind: 1, fill_angle: 1, fill_color_a: 1, fill_opacity_a: 1,
    fill_color_b: 1, fill_opacity_b: 1, fill_on: 1, fill_off: 1,
    lines: 1, asset: 1
  };

  var PLAIN_NUMBER_PROPS = { rotate_degrees: 1, speed_seconds: 1, fill_angle: 1, animation_seconds: 1 };

  function currentSingleItem() {
    if (app.selection.ids.length !== 1) {
      return null;
    }
    return S.getItem(app.screenDoc(), app.selection.ids[0]);
  }

  function valueForProp(prop, target) {
    if (prop === 'visible' || prop === 'fit_text' || prop === 'bleed') {
      return target.checked;
    }
    if (PERCENT_PROPS[prop]) {
      return Panels.fromPercentInput(target);
    }
    if (prop === 'z_index' || prop === 'font_weight' || prop === 'letter_spacing' || PLAIN_NUMBER_PROPS[prop]) {
      return target.value === '' ? null : Number(target.value);
    }
    if (prop === 'background') {
      return target.value === '' ? null : target.value;
    }
    return target.value;
  }

  function limitsNow() {
    return (app.state && app.state.limits) || {};
  }

  function finiteOr(value, fallback) {
    return S.isFiniteNumber(value) ? value : fallback;
  }

  /** A number bounded to `[low, high]` and rounded to schema precision, or
   * `fallback` when the input was not a finite number at all. */
  function boundedNumber(value, low, high, fallback) {
    if (!S.isFiniteNumber(value)) {
      return fallback;
    }
    return S.roundTo(S.clampRange(value, low, high), precisionScale());
  }

  function writeAnimation(item, prop, value) {
    var current = item.animation && typeof item.animation === 'object' ? item.animation : null;
    var preset = prop === 'animation_preset' ? value : (current ? current.preset : 'none');
    if (!preset || preset === 'none') {
      item.animation = null;
      return;
    }
    var low = Panels.animationMinSeconds(limitsNow(), preset);
    var high = Panels.animationMaxSeconds(limitsNow());
    var seconds = prop === 'animation_seconds' ? value : (current ? current.duration_seconds : null);
    item.animation = {
      preset: preset,
      duration_seconds: boundedNumber(finiteOr(seconds, low), low, high, low)
    };
  }

  function twoStops(colorA, opacityA, colorB, opacityB) {
    return [
      { color: colorA, opacity: opacityA, at: 0 },
      { color: colorB, opacity: opacityB, at: 1 }
    ];
  }

  /** Switch a box to a new fill kind, carrying over whatever the previous
   * descriptor already had (colours, angle, radial centre/radius, extra
   * stops) so changing the kind and back does not erase the operator's
   * numbers. Values the editor cannot show are preserved, never rebuilt. */
  function fillForKind(item, kind) {
    var previous = item.fill && typeof item.fill === 'object' ? item.fill : {};
    var previousStops = Object.prototype.toString.call(previous.stops) === '[object Array]' ? previous.stops : null;
    var baseColor = previous.color || (previousStops && previousStops[0] && previousStops[0].color)
      || item.background || '#FFFFFF';
    var baseOpacity = finiteOr(previous.opacity, previousStops && previousStops[0]
      ? finiteOr(previousStops[0].opacity, 1) : 1);
    if (kind === 'stripes') {
      return {
        kind: 'stripes',
        angle: boundedNumber(finiteOr(previous.angle, 45), 0, 360, 45),
        color: baseColor,
        opacity: boundedNumber(baseOpacity, 0, 1, 1),
        on: boundedNumber(finiteOr(previous.on, 0.002), 0.001, 0.5, 0.002),
        off: boundedNumber(finiteOr(previous.off, 0.008), 0, 1, 0.008)
      };
    }
    var stops = previousStops && previousStops.length >= 2
      ? clone(previousStops)
      : twoStops(baseColor, boundedNumber(baseOpacity, 0, 1, 1), previous.color || baseColor, 0);
    if (kind === 'radial') {
      return {
        kind: 'radial',
        center_x: boundedNumber(finiteOr(previous.center_x, 0.5), 0, 1, 0.5),
        center_y: boundedNumber(finiteOr(previous.center_y, 0), 0, 1, 0),
        radius_x: boundedNumber(finiteOr(previous.radius_x, 0.6), 0.05, 2, 0.6),
        radius_y: boundedNumber(finiteOr(previous.radius_y, 1), 0.05, 2, 1),
        stops: stops
      };
    }
    return {
      kind: 'linear',
      angle: boundedNumber(finiteOr(previous.angle, 0), 0, 360, 0),
      stops: stops
    };
  }

  function writeFill(item, prop, value) {
    if (prop === 'fill_kind') {
      item.fill = (!value || value === 'none') ? null : fillForKind(item, value);
      return;
    }
    var fill = item.fill && typeof item.fill === 'object' ? item.fill : null;
    if (!fill) {
      return; // the fields for a flat box are hidden; nothing to write
    }
    if (prop === 'fill_angle') {
      fill.angle = boundedNumber(value, 0, 360, finiteOr(fill.angle, 0));
      return;
    }
    if (fill.kind === 'stripes') {
      if (prop === 'fill_color_a') { fill.color = value; }
      if (prop === 'fill_opacity_a') { fill.opacity = boundedNumber(value, 0, 1, finiteOr(fill.opacity, 1)); }
      if (prop === 'fill_on') { fill.on = boundedNumber(value, 0.001, 0.5, finiteOr(fill.on, 0.002)); }
      if (prop === 'fill_off') { fill.off = boundedNumber(value, 0, 1, finiteOr(fill.off, 0.008)); }
      return;
    }
    if (Object.prototype.toString.call(fill.stops) !== '[object Array]' || fill.stops.length < 2) {
      fill.stops = twoStops(item.background || '#FFFFFF', 1, item.background || '#FFFFFF', 0);
    }
    var first = fill.stops[0];
    var last = fill.stops[fill.stops.length - 1];
    if (prop === 'fill_color_a') { first.color = value; }
    if (prop === 'fill_opacity_a') { first.opacity = boundedNumber(value, 0, 1, finiteOr(first.opacity, 1)); }
    if (prop === 'fill_color_b') { last.color = value; }
    if (prop === 'fill_opacity_b') { last.opacity = boundedNumber(value, 0, 1, finiteOr(last.opacity, 1)); }
  }

  function writeLines(item, value) {
    var maxLines = typeof limitsNow().max_ticker_lines === 'number' ? limitsNow().max_ticker_lines : 8;
    var lines = String(value || '').split('\n').map(function (line) { return line.trim(); })
      .filter(function (line) { return line !== ''; });
    item.lines = lines.slice(0, maxLines);
  }

  function writeAsset(item, value) {
    if (value) {
      item.src = 'asset:' + value;
      return;
    }
    // "Uploaded image" with nothing uploaded yet: keep whatever src the
    // element has (a bundled one stays until Replace image... supplies a
    // data URI), so the element never loses its picture.
  }

  function writeComposite(item, prop, value) {
    if (prop === 'animation_preset' || prop === 'animation_seconds') { writeAnimation(item, prop, value); return; }
    if (prop === 'lines') { writeLines(item, value); return; }
    if (prop === 'asset') { writeAsset(item, value); return; }
    writeFill(item, prop, value);
  }

  function applyPropertyValue(item, prop, value) {
    if (COMPOSITE_PROPS[prop]) {
      writeComposite(item, prop, value);
    } else if (prop === 'rotate_degrees') {
      var maxRotate = typeof limitsNow().max_rotate_degrees === 'number' ? limitsNow().max_rotate_degrees : 180;
      item.rotate_degrees = boundedNumber(value, -maxRotate, maxRotate, finiteOr(item.rotate_degrees, 0));
    } else if (prop === 'speed_seconds') {
      var range = Panels.tickerSpeedRange(limitsNow(), item.mode === 'rotate' ? 'rotate' : 'scroll');
      item.speed_seconds = boundedNumber(value, range[0], range[1], finiteOr(item.speed_seconds, range[0]));
    } else if (prop === 'mode') {
      item.mode = value;
      // The two modes measure speed differently (per loop / per line) and
      // have different legal ranges; keep the number legal for the new one.
      var newRange = Panels.tickerSpeedRange(limitsNow(), value === 'rotate' ? 'rotate' : 'scroll');
      item.speed_seconds = boundedNumber(finiteOr(item.speed_seconds, newRange[0]), newRange[0], newRange[1], newRange[0]);
    } else if (NUMERIC_WIDGET_PROPS[prop]) {
      S.setGeometry(item, prop, value, precisionScale());
    } else {
      item[prop] = value;
    }
  }

  function liveChangeProperty(prop, value) {
    var item = currentSingleItem();
    if (!item) {
      return;
    }
    applyPropertyValue(item, prop, value);
    app.dirty = true;
    markSelectionDot();
    app.liveRefresh();
    app.validateDraft();
  }

  /** A `change` event on any property control -- widget, element, or board --
   * is the point a gesture becomes a fact worth stepping back to. The value
   * itself was already written into the draft by the paired `input` handler
   * (or directly, for a control that only ever fires `change`); this just
   * records the resulting draft in history and brings every panel current. */
  function commitAfterPropertyChange() {
    S.pushHistory(app.history, app.draft);
    app.renderAll();
    app.validateDraft();
  }

  function valueForBoardProp(prop, target) {
    if (prop === 'background_color') {
      return target.value;
    }
    return Panels.fromPercentInput(target);
  }

  function liveChangeBoardProperty(prop, value) {
    var doc = app.screenDoc();
    doc.background = doc.background || { color: '#000000' };
    doc.safe_area = doc.safe_area || {};
    if (prop === 'background_color') {
      doc.background.color = value;
    } else if (S.isFiniteNumber(value)) {
      var key = prop.replace('safe_', '');
      doc.safe_area[key] = S.roundTo(value, precisionScale());
    }
    app.dirty = true;
    markSelectionDot();
    app.liveRefresh();
    app.validateDraft();
  }

  /* --- Wiring ------------------------------------------------------------------ */

  var ARROWS = {
    ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]
  };

  function handleAction(action) {
    Canvas.closeContextMenu();
    if (action === 'library_menu') { Panels.togglePopover('layout-menu-panel'); return; }
    if (action === 'presets_menu') { Panels.togglePopover('presets-menu-panel'); return; }
    if (action === 'toggle_issues') { Panels.togglePopover('issues-drawer'); return; }

    if (action === 'save') { save(app.state.active); return; }
    if (action === 'save_as_open') {
      Panels.togglePopover('save-as-popover');
      el('save-as-name').value = '';
      el('save-as-name').focus();
      return;
    }
    if (action === 'save_as_cancel') { el('save-as-popover').hidden = true; return; }
    if (action === 'save_as_confirm') {
      var newSaveName = el('save-as-name').value;
      el('save-as-popover').hidden = true;
      save(newSaveName);
      return;
    }

    if (action === 'duplicate_layout_open') {
      Panels.togglePopover('duplicate-layout-popover');
      el('duplicate-layout-name').value = app.state.active + ' copy';
      el('duplicate-layout-name').focus();
      return;
    }
    if (action === 'duplicate_layout_cancel') { el('duplicate-layout-popover').hidden = true; return; }
    if (action === 'duplicate_layout_confirm') {
      var duplicateName = el('duplicate-layout-name').value;
      el('duplicate-layout-popover').hidden = true;
      duplicateLayoutAction(app.state.active, duplicateName);
      return;
    }

    if (action === 'rename_layout_open') {
      Panels.togglePopover('rename-layout-popover');
      el('rename-layout-name').value = app.state.active;
      el('rename-layout-name').focus();
      return;
    }
    if (action === 'rename_layout_cancel') { el('rename-layout-popover').hidden = true; return; }
    if (action === 'rename_layout_confirm') {
      var renamedTo = el('rename-layout-name').value;
      el('rename-layout-popover').hidden = true;
      renameLayoutAction(app.state.active, renamedTo);
      return;
    }

    if (action === 'delete_layout_open') { Panels.togglePopover('delete-layout-popover'); return; }
    if (action === 'delete_layout_cancel') { el('delete-layout-popover').hidden = true; return; }
    if (action === 'delete_layout_confirm') {
      el('delete-layout-popover').hidden = true;
      deleteLayoutAction(app.state.active);
      return;
    }

    if (action === 'discard') { discard(); return; }
    if (action === 'reset_layout_ask') { Panels.togglePopover('reset-layout-popover'); return; }
    if (action === 'reset_layout_cancel') { el('reset-layout-popover').hidden = true; return; }
    if (action === 'reset_layout_confirm') {
      el('reset-layout-popover').hidden = true;
      resetLayoutAction();
      return;
    }

    if (action === 'replace_draft_confirm') {
      el('replace-draft-popover').hidden = true;
      if (pendingPresetApply) {
        pendingPresetApply();
        pendingPresetApply = null;
      }
      return;
    }
    if (action === 'replace_draft_cancel') {
      el('replace-draft-popover').hidden = true;
      pendingPresetApply = null;
      return;
    }

    if (action === 'history_back') { goHistory(-1); return; }
    if (action === 'history_forward') { goHistory(1); return; }

    if (action === 'add_text') { app.addElement(S.makeTextElement(app.screenDoc(), app.widgetIds())); return; }
    if (action === 'add_box') { app.addElement(S.makeBoxElement(app.screenDoc(), app.widgetIds())); return; }
    if (action === 'add_ticker') { app.addElement(S.makeTickerElement(app.screenDoc(), app.widgetIds())); return; }
    if (action === 'toggle_motion') { toggleMotionAction(); return; }
    if (action === 'add_image') { pendingReplaceId = null; el('image-file-input').click(); return; }
    if (action === 'replace_image') {
      pendingReplaceId = app.selection.ids.length === 1 ? app.selection.ids[0] : null;
      el('image-file-input').click();
      return;
    }

    if (action === 'zoom_in') { Canvas.zoomIn(); return; }
    if (action === 'zoom_out') { Canvas.zoomOut(); return; }
    if (action === 'zoom_fit') { Canvas.zoomFit(); return; }

    if (action === 'nudge_up') { Canvas.nudge(app, 0, -1, false); return; }
    if (action === 'nudge_down') { Canvas.nudge(app, 0, 1, false); return; }
    if (action === 'nudge_left') { Canvas.nudge(app, -1, 0, false); return; }
    if (action === 'nudge_right') { Canvas.nudge(app, 1, 0, false); return; }

    if (action === 'raise') { Canvas.restack(app, 1); return; }
    if (action === 'lower') { Canvas.restack(app, -1); return; }
    if (action === 'to_front') { Canvas.toFront(app); return; }
    if (action === 'to_back') { Canvas.toBack(app); return; }

    if (action === 'align_left') { Canvas.align(app, 'left'); return; }
    if (action === 'align_center') { Canvas.align(app, 'center'); return; }
    if (action === 'align_right') { Canvas.align(app, 'right'); return; }
    if (action === 'align_top') { Canvas.align(app, 'top'); return; }
    if (action === 'align_middle') { Canvas.align(app, 'middle'); return; }
    if (action === 'align_bottom') { Canvas.align(app, 'bottom'); return; }
    if (action === 'distribute_h') { Canvas.distribute(app, 'h'); return; }
    if (action === 'distribute_v') { Canvas.distribute(app, 'v'); return; }

    if (action === 'duplicate') { app.duplicateSelected(); return; }
    if (action === 'delete_element') { app.deleteSelectedElements(); return; }
    if (action === 'toggle_visible') {
      if (app.selection.primary) {
        toggleVisibleFor(app.selection.primary);
      }
      return;
    }
    if (action === 'reset_widget') { app.resetWidgetAction(); return; }
    if (action === 'clamp') { app.clampDraftAction(); return; }
  }

  document.addEventListener('click', function (event) {
    var target = event.target;

    var groupToggle = target.closest('[data-group-toggle]');
    if (groupToggle) {
      var groupName = groupToggle.getAttribute('data-group-toggle');
      app.collapsedGroups[groupName] = !app.collapsedGroups[groupName];
      Panels.renderLayers(app);
      return;
    }

    var toggleVisibleButton = target.closest('[data-toggle-visible]');
    if (toggleVisibleButton) {
      toggleVisibleFor(toggleVisibleButton.getAttribute('data-toggle-visible'));
      return;
    }

    var deleteElementButton = target.closest('[data-delete-element]');
    if (deleteElementButton) {
      app.select([deleteElementButton.getAttribute('data-delete-element')]);
      app.deleteSelectedElements();
      return;
    }

    var screenButton = target.closest('[data-screen]');
    if (screenButton) {
      app.switchScreen(screenButton.getAttribute('data-screen'));
      return;
    }

    var selectWidgetButton = target.closest('[data-select-widget]');
    if (selectWidgetButton) {
      var widgetId = selectWidgetButton.getAttribute('data-select-widget');
      // An issue named in the drawer may belong to a screen that is not on
      // screen; switch there first so the widget it names can be selected.
      var issueScreen = selectWidgetButton.getAttribute('data-issue-screen');
      if (issueScreen && issueScreen !== app.screen) {
        app.switchScreen(issueScreen);
      }
      if (event.shiftKey) { app.toggleSelect(widgetId); } else { app.select([widgetId]); }
      return;
    }

    var selectElementButton = target.closest('[data-select-element]');
    if (selectElementButton) {
      var elementId = selectElementButton.getAttribute('data-select-element');
      if (event.shiftKey) { app.toggleSelect(elementId); } else { app.select([elementId]); }
      return;
    }

    var selectBoardButton = target.closest('[data-select-board]');
    if (selectBoardButton) { app.selectBoard(); return; }

    var selectLayoutButton = target.closest('[data-select-layout]');
    if (selectLayoutButton) {
      selectLayoutAction(selectLayoutButton.getAttribute('data-select-layout'));
      el('layout-menu-panel').hidden = true;
      return;
    }

    var applyPresetButton = target.closest('[data-apply-preset]');
    if (applyPresetButton) { applyPresetAction(applyPresetButton.getAttribute('data-apply-preset')); return; }

    var choiceButton = target.closest('[data-choice-prop]');
    if (choiceButton) {
      var item = currentSingleItem();
      if (item) {
        applyPropertyValue(item, choiceButton.getAttribute('data-choice-prop'), choiceButton.getAttribute('data-choice'));
        app.commit();
      }
      return;
    }

    var actionButton = target.closest('[data-action]');
    if (actionButton) { handleAction(actionButton.getAttribute('data-action')); return; }

    if (!target.closest('.layout-menu, .presets-menu, .context-menu, .issues-drawer, #status-summary')) {
      Panels.closeAllPopovers();
    }
  });

  document.addEventListener('input', function (event) {
    if (app.suppress) {
      return;
    }
    var target = event.target;
    if (target.id === 'prop-color-swatch') {
      el('prop-color').value = target.value.toUpperCase();
      liveChangeProperty('color', el('prop-color').value);
      return;
    }
    if (target.id === 'prop-background-swatch') {
      el('prop-background').value = target.value.toUpperCase();
      liveChangeProperty('background', el('prop-background').value);
      return;
    }
    if (target.id === 'prop-border_color-swatch') {
      el('prop-border_color').value = target.value.toUpperCase();
      liveChangeProperty('border_color', el('prop-border_color').value);
      return;
    }
    if (target.id === 'prop-fill_color_a-swatch' || target.id === 'prop-fill_color_b-swatch') {
      var fillField = el(target.id.replace('-swatch', ''));
      fillField.value = target.value.toUpperCase();
      liveChangeProperty(fillField.getAttribute('data-prop'), fillField.value);
      return;
    }
    if (target.id === 'prop-background-toggle') {
      liveChangeProperty('background', target.checked ? (el('prop-background').value || '#1B222B') : null);
      return;
    }
    if (target.id === 'board-background_color-swatch') {
      el('board-background_color').value = target.value.toUpperCase();
      liveChangeBoardProperty('background_color', el('board-background_color').value);
      return;
    }
    var prop = target.getAttribute('data-prop');
    if (prop) { liveChangeProperty(prop, valueForProp(prop, target)); return; }
    var boardProp = target.getAttribute('data-board-prop');
    if (boardProp) { liveChangeBoardProperty(boardProp, valueForBoardProp(boardProp, target)); return; }
  });

  document.addEventListener('change', function (event) {
    if (app.suppress) {
      return;
    }
    var target = event.target;
    var swatchIds = ['prop-color-swatch', 'prop-background-swatch', 'prop-border_color-swatch',
      'prop-fill_color_a-swatch', 'prop-fill_color_b-swatch',
      'board-background_color-swatch', 'prop-background-toggle'];
    if (swatchIds.indexOf(target.id) !== -1) {
      // The paired text field already picked up the value on 'input'.
      commitAfterPropertyChange();
      return;
    }
    var prop = target.getAttribute('data-prop');
    if (prop) {
      // Re-applying is idempotent: this covers a control (a <select>, some
      // checkboxes) that only ever fires 'change', never 'input'.
      liveChangeProperty(prop, valueForProp(prop, target));
      commitAfterPropertyChange();
      return;
    }
    var boardProp = target.getAttribute('data-board-prop');
    if (boardProp) {
      liveChangeBoardProperty(boardProp, valueForBoardProp(boardProp, target));
      commitAfterPropertyChange();
    }
  });

  el('image-file-input').addEventListener('change', function (event) {
    var file = event.target.files && event.target.files[0];
    event.target.value = '';
    if (!file) {
      return;
    }
    if (pendingReplaceId) {
      var id = pendingReplaceId;
      pendingReplaceId = null;
      app.replaceImageForSelected(id, file);
    } else {
      app.addImageFromFile(file);
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      Panels.closeAllPopovers();
      var tag = event.target.tagName;
      if (tag !== 'INPUT' && tag !== 'SELECT' && tag !== 'TEXTAREA') {
        app.clearSelection();
      }
      return;
    }

    var ctrlLike = event.ctrlKey || event.metaKey;
    if (ctrlLike && (event.key === 's' || event.key === 'S')) {
      event.preventDefault();
      save(app.state.active);
      return;
    }

    var tag = event.target.tagName;
    var typing = tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA';
    if (typing) {
      return;
    }

    var arrow = ARROWS[event.key];
    if (arrow) {
      event.preventDefault();
      Canvas.nudge(app, arrow[0], arrow[1], event.shiftKey);
      return;
    }
    if (event.key === 'Delete' || event.key === 'Backspace') {
      event.preventDefault();
      app.deleteSelectedElements();
      return;
    }
    if (ctrlLike && (event.key === 'z' || event.key === 'Z')) {
      event.preventDefault();
      goHistory(event.shiftKey ? 1 : -1);
      return;
    }
    if (ctrlLike && (event.key === 'y' || event.key === 'Y')) {
      event.preventDefault();
      goHistory(1);
      return;
    }
    if (ctrlLike && (event.key === 'd' || event.key === 'D')) {
      event.preventDefault();
      app.duplicateSelected();
      return;
    }
    if (ctrlLike && (event.key === 'a' || event.key === 'A')) {
      event.preventDefault();
      app.selectAllVisible();
      return;
    }
    if (ctrlLike && (event.key === '1' || event.key === '2' || event.key === '3')) {
      event.preventDefault();
      var screens = (app.state && app.state.screens) || [];
      var screenTarget = screens[Number(event.key) - 1];
      if (screenTarget) {
        app.switchScreen(screenTarget.id);
      }
      return;
    }
    if (event.key === '+' || event.key === '=') { Canvas.zoomIn(); return; }
    if (event.key === '-') { Canvas.zoomOut(); return; }
  });

  /* --- Host entry points ------------------------------------------------ */

  /* The host pushes a layout whenever it changes anywhere, so a save made in
   * another window is reflected here. An unsaved draft is deliberately kept:
   * the operator's in-progress edit is not discarded behind their back. */
  window.applyLayout = function (layout) {
    if (!layout || app.dirty) {
      return;
    }
    app.draft = clone(layout);
    app.history = S.createHistory(app.draft);
    app.renderAll();
  };

  /* The host also pushes spectator view models; the preview follows the live
   * board so the operator judges the layout against real values. */
  window.applyView = function (model) {
    app.snapshot = model;
    app.refreshPreview();
  };

  /* The host pushes the motion preference to every window when it changes,
   * so a switch flipped here (or anywhere) is mirrored in this preview. */
  window.applyMotion = function (enabled) {
    applyMotion(enabled !== false);
  };

  Board.build(boardRoot, 'game');
  Canvas.init(app);

  R.whenReady(function (bridge) {
    app.api = bridge;
    Promise.resolve(app.api.layout_state()).then(function (payload) {
      adoptState(payload, { announce: false });
      refreshSnapshot();
    }).catch(function (error) {
      showAlert('The stored layouts could not be read: ' + error);
    });
  });
})();
