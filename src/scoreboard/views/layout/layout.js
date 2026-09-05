/* The presentation layout editor.
 *
 * This window is presentation-only by construction. It holds no authoritative
 * state, it never calls a game command -- there is deliberately no path from
 * this file to bridge.command() -- and the only thing it can change is the
 * stored layout document that says where spectator widgets are drawn.
 *
 * It stores exactly two kinds of ephemeral view state: the draft layout the
 * operator is editing but has not saved, and which widget is selected. The
 * preview is the real spectator renderer (ScoreboardBoard) fed the real
 * snapshot, so what the operator sees here is what the board will do.
 *
 * Nothing here computes a displayed value. Every string in the preview arrives
 * already formatted in the view model, exactly as on the spectator board.
 */

(function () {
  'use strict';

  var R = window.ScoreboardRender;
  var Board = window.ScoreboardBoard;

  var api = null;
  var state = null;      // the last layout_state() payload from Python
  var draft = null;      // the layout document being edited
  var selected = null;   // widget id
  var snapshot = null;   // the read-only spectator view model, for the preview
  var dirty = false;
  var suppress = false;  // guards control writes made while re-rendering

  var boardRoot = document.getElementById('game-board');
  var canvas = document.getElementById('canvas');
  var alertLine = document.getElementById('alert');
  var saveButton = document.getElementById('save');

  var NUMERIC_PROPS = ['x', 'y', 'width', 'height', 'font_scale', 'z_index'];
  var CHOICE_PROPS = ['text_align', 'vertical_align'];

  var guideLayer = document.getElementById('guides');
  var handleLayer = document.getElementById('handles');

  /* Direct manipulation happens in the browser because it has to: a drag
   * produces a pointer event per frame, and a bridge round trip per frame is
   * not a thing a webview can do. So the editor owns the *gesture* -- pixels
   * to fractions, snapping, and the safe-area boundary -- and Python still
   * owns the *verdict*: every gesture ends in preview_layout(), and Save is
   * still gated on what Python says. Nothing here computes a game value, and
   * the limits below that could drift from the schema are read from Python's
   * limits() rather than written down again. */
  var GRID = 0.005;          // one nudge, and the number inputs' own step
  var COARSE = 0.02;         // Shift+arrow, and four grid cells
  var SNAP = 0.008;          // how close an edge must be to be captured
  var MIN_SIZE = { width: 0.02, height: 0.02 };  // replaced from limits()
  var PRECISION_SCALE = 10000;                   // 10^coordinate_precision

  var drag = null;           // the gesture in progress, or null

  /* --- Small helpers ---------------------------------------------------- */

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function showAlert(message) {
    R.setText(alertLine, message);
    alertLine.hidden = false;
  }

  function clearAlert() {
    alertLine.hidden = true;
  }

  function widgetDescriptor(id) {
    var widgets = (state && state.widgets) || [];
    for (var index = 0; index < widgets.length; index += 1) {
      if (widgets[index].id === id) {
        return widgets[index];
      }
    }
    return null;
  }

  function currentWidget() {
    if (!draft || !selected || !draft.widgets) {
      return null;
    }
    return draft.widgets[selected] || null;
  }

  function markDirty(isDirty) {
    dirty = Boolean(isDirty);
    document.getElementById('dirty-chip').hidden = !dirty;
  }

  /* --- Rendering -------------------------------------------------------- */

  /** Redraw the preview from the draft layout and the last snapshot. */
  function renderPreview() {
    try {
      Board.applyLayout(canvas, draft);
      if (snapshot) {
        Board.applyModel(boardRoot, snapshot);
      }
      markSelection();
    } catch (error) {
      // A preview that cannot draw must not take the editor down with it.
      showAlert('The preview could not be drawn: ' + error);
    }
  }

  function markSelection() {
    var nodes = boardRoot.querySelectorAll('[data-widget]');
    for (var index = 0; index < nodes.length; index += 1) {
      R.setFlag(nodes[index], 'is-selected', nodes[index].dataset.widget === selected);
    }
  }

  function renderWidgetList() {
    var host = document.getElementById('widget-list');
    host.replaceChildren();
    (state.widgets || []).forEach(function (descriptor) {
      var widget = draft.widgets[descriptor.id] || {};
      var item = document.createElement('li');
      var button = document.createElement('button');
      button.type = 'button';
      button.setAttribute('data-select-widget', descriptor.id);
      // The label is the human name; hidden state is spelled out in words,
      // never carried by colour alone.
      button.textContent = descriptor.label + (widget.visible ? '' : ' — hidden');
      button.classList.toggle('is-current', descriptor.id === selected);
      button.classList.toggle('is-hidden', !widget.visible);
      item.appendChild(button);
      host.appendChild(item);
    });
  }

  function renderChoiceGroup(prop, values) {
    var host = document.getElementById('prop-' + prop);
    if (!host || host.childElementCount === values.length) {
      return;
    }
    host.replaceChildren();
    values.forEach(function (value) {
      var button = document.createElement('button');
      button.type = 'button';
      button.setAttribute('data-choice', value);
      button.setAttribute('data-choice-prop', prop);
      button.textContent = value;
      host.appendChild(button);
    });
  }

  function renderWeights(values) {
    var select = document.getElementById('prop-font_weight');
    if (select.childElementCount === values.length) {
      return;
    }
    select.replaceChildren();
    values.forEach(function (value) {
      var option = document.createElement('option');
      option.value = String(value);
      option.textContent = String(value);
      select.appendChild(option);
    });
  }

  /** Apply the limits Python reported to the numeric controls. */
  function applyLimits(limits) {
    MIN_SIZE.width = limits.min_widget_width;
    MIN_SIZE.height = limits.min_widget_height;
    // Keep the editor's rounding on exactly the same place as the schema's.
    var places = limits.coordinate_precision;
    if (typeof places === 'number' && places > 0) {
      var scale = 1;
      for (var step = 0; step < places; step += 1) {
        scale *= 10;
      }
      PRECISION_SCALE = scale;
    }
    var font = document.getElementById('prop-font_scale');
    font.min = String(limits.min_font_scale);
    font.max = String(limits.max_font_scale);
    document.getElementById('prop-width').min = String(limits.min_widget_width);
    document.getElementById('prop-height').min = String(limits.min_widget_height);
    var z = document.getElementById('prop-z_index');
    z.min = String(limits.min_z_index);
    z.max = String(limits.max_z_index);
    renderChoiceGroup('text_align', limits.text_alignments);
    renderChoiceGroup('vertical_align', limits.vertical_alignments);
    renderWeights(limits.font_weights);
  }

  function renderProperties() {
    var widget = currentWidget();
    var descriptor = selected ? widgetDescriptor(selected) : null;
    document.getElementById('property-form').hidden = !widget;
    document.getElementById('no-selection').hidden = Boolean(widget);
    R.setText(document.getElementById('selected-label'),
      descriptor ? descriptor.label : 'nothing selected');
    if (!widget) {
      return;
    }
    suppress = true;
    try {
      document.getElementById('prop-visible').checked = Boolean(widget.visible);
      NUMERIC_PROPS.forEach(function (prop) {
        document.getElementById('prop-' + prop).value = String(widget[prop]);
      });
      document.getElementById('prop-color').value = widget.color;
      document.getElementById('prop-color-swatch').value = widget.color;
      document.getElementById('prop-font_weight').value = String(widget.font_weight);
      CHOICE_PROPS.forEach(function (prop) {
        var host = document.getElementById('prop-' + prop);
        Array.prototype.forEach.call(host.children, function (button) {
          button.classList.toggle('is-current', button.dataset.choice === widget[prop]);
        });
      });
      // A fixed label can be moved and restyled, but its wording belongs to
      // the application; say so rather than offering a text box that is not
      // there.
      document.getElementById('static-note').hidden = !(descriptor && descriptor.static_text);
      R.setText(document.getElementById('stack-readout'), 'Now ' + widget.z_index);
    } finally {
      suppress = false;
    }
  }

  /** Build the eight resize handles once. They carry their compass point in
   * `data-handle`; everything else about them is CSS. */
  function buildHandles() {
    var edges = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
    handleLayer.replaceChildren();
    edges.forEach(function (edge) {
      var handle = document.createElement('div');
      handle.className = 'handle handle-' + edge;
      handle.setAttribute('data-handle', edge);
      handleLayer.appendChild(handle);
    });
  }

  function renderIssues(payload) {
    // A successful read reports under `issues`; a refused save reports under
    // `errors`/`warnings`. Show whichever the bridge sent, so a rejection is
    // never silently blank.
    var issues = [];
    ['issues', 'errors', 'warnings'].forEach(function (key) {
      var list = payload && payload[key];
      if (Object.prototype.toString.call(list) === '[object Array]') {
        issues = issues.concat(list);
      }
    });
    var host = document.getElementById('issue-list');
    host.replaceChildren();
    var errors = 0;
    issues.forEach(function (issue) {
      if (issue.severity === 'error') {
        errors += 1;
      }
      var item = document.createElement('li');
      var button = document.createElement('button');
      button.type = 'button';
      button.className = issue.severity;
      if (issue.widget_id) {
        button.setAttribute('data-select-widget', issue.widget_id);
      }
      var severity = document.createElement('span');
      severity.className = 'severity';
      severity.textContent = issue.severity === 'error' ? 'ERROR' : 'WARNING';
      button.appendChild(severity);
      button.appendChild(document.createTextNode(issue.message));
      item.className = issue.severity;
      item.appendChild(button);
      host.appendChild(item);
    });
    document.getElementById('issue-empty').hidden = issues.length > 0;
    // Saving an invalid layout is not offered at all, rather than refused
    // afterwards.
    saveButton.disabled = errors > 0;
    document.getElementById('save-as-open').disabled = errors > 0;
  }

  /* --- Talking to Python ------------------------------------------------ */

  function adoptState(payload, options) {
    options = options || {};
    if (!payload) {
      return;
    }
    state = payload;
    applyLimits(payload.limits);
    if (options.resetDraft !== false) {
      draft = clone(payload.layout);
      markDirty(false);
    }
    if (!selected || !draft.widgets[selected]) {
      selected = (payload.widgets && payload.widgets.length) ? payload.widgets[0].id : null;
    }
    renderLayoutNames(payload);
    renderWidgetList();
    renderProperties();
    renderPreview();
    renderHandles();
    renderIssues(payload);
    if (payload.message && options.announce !== false) {
      showAlert(payload.message);
    }
    if (payload.fell_back) {
      showAlert('The stored layout could not be read, so the built-in default is in use. '
        + 'Saving will replace the unreadable file.');
    }
  }

  function renderLayoutNames(payload) {
    var select = document.getElementById('layout-select');
    select.replaceChildren();
    (payload.names || []).forEach(function (name) {
      var option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      option.selected = name === payload.active;
      select.appendChild(option);
    });
  }

  /** Ask Python to validate the draft. It writes nothing and publishes nothing. */
  function validateDraft() {
    if (!api || !api.preview_layout) {
      return;
    }
    Promise.resolve(api.preview_layout(draft)).then(function (payload) {
      renderIssues(payload);
    }).catch(function (error) {
      showAlert('The layout could not be checked: ' + error);
    });
  }

  function refreshSnapshot() {
    if (!api || !api.get_snapshot) {
      return;
    }
    Promise.resolve(api.get_snapshot()).then(function (model) {
      snapshot = model;
      renderPreview();
    }).catch(function (error) {
      // The board values are a convenience for judging the layout; losing them
      // must not stop the operator editing it.
      showAlert('The live board values could not be read: ' + error);
    });
  }

  /* --- Geometry ---------------------------------------------------------
   *
   * All of it in fractions of the canvas, the same units the layout document
   * and board.js already use, so nothing is converted twice.
   */

  function clampRange(value, low, high) {
    // A widget wider than the safe area would make low > high; letting the
    // low edge win keeps it on the board instead of inverting the box.
    if (high < low) {
      return low;
    }
    return value < low ? low : (value > high ? high : value);
  }

  function snapToGrid(value) {
    return Math.round(value / GRID) * GRID;
  }

  function apart(a, b) {
    var difference = a - b;
    return difference < 0 ? -difference : difference;
  }

  /** The safe area as edges rather than insets, which is what every caller
   * below actually wants. Falls back to the schema default if the draft has
   * no usable safe area, so a gesture never throws. */
  function safeBounds() {
    var area = (draft && draft.safe_area) ? draft.safe_area : null;
    var top = area && typeof area.top === 'number' ? area.top : 0.04;
    var right = area && typeof area.right === 'number' ? area.right : 0.04;
    var bottom = area && typeof area.bottom === 'number' ? area.bottom : 0.04;
    var left = area && typeof area.left === 'number' ? area.left : 0.04;
    return { left: left, top: top, right: 1 - right, bottom: 1 - bottom };
  }

  /** Every edge and centre line a dragged widget can snap to: the safe-area
   * boundary, the canvas centre, and the corresponding lines of every other
   * visible widget. Returns two lists of plain numbers. */
  function snapTargets(excludeId) {
    var bounds = safeBounds();
    var vertical = [bounds.left, bounds.right, 0.5];
    var horizontal = [bounds.top, bounds.bottom, 0.5];
    var ids = Object.keys(draft.widgets || {});
    for (var index = 0; index < ids.length; index += 1) {
      var id = ids[index];
      if (id === excludeId) {
        continue;
      }
      var other = draft.widgets[id];
      if (!other || !other.visible) {
        continue;
      }
      vertical.push(other.x, other.x + other.width / 2, other.x + other.width);
      horizontal.push(other.y, other.y + other.height / 2, other.y + other.height);
    }
    return { vertical: vertical, horizontal: horizontal };
  }

  /** Pull `value` onto the nearest target within SNAP, given that the moving
   * box presents three lines of its own (near edge, centre, far edge).
   * Returns the adjusted origin and the line that captured it, if any. */
  function capture(origin, size, targets) {
    var best = null;
    var offsets = [0, size / 2, size];
    for (var line = 0; line < targets.length; line += 1) {
      for (var which = 0; which < offsets.length; which += 1) {
        var distance = apart(origin + offsets[which], targets[line]);
        if (distance <= SNAP && (!best || distance < best.distance)) {
          best = { distance: distance, origin: targets[line] - offsets[which], at: targets[line] };
        }
      }
    }
    return best;
  }

  function drawGuides(lines) {
    guideLayer.replaceChildren();
    lines.forEach(function (line) {
      var element = document.createElement('div');
      element.className = 'guide guide-' + line.axis;
      element.style.setProperty('--at', line.at);
      guideLayer.appendChild(element);
    });
  }

  function clearGuides() {
    guideLayer.replaceChildren();
  }

  /** Position the eight resize handles over the selected widget, or hide
   * them when nothing is selected. */
  function renderHandles() {
    var widget = currentWidget();
    handleLayer.hidden = !widget || !widget.visible;
    if (handleLayer.hidden) {
      return;
    }
    handleLayer.style.setProperty('--hx', widget.x);
    handleLayer.style.setProperty('--hy', widget.y);
    handleLayer.style.setProperty('--hw', widget.width);
    handleLayer.style.setProperty('--hh', widget.height);
  }

  /** Where the pointer is, as a fraction of the canvas, or null when the
   * canvas has no area to measure against.
   *
   * A zero-sized canvas is not hypothetical -- it is what a collapsed or
   * not-yet-laid-out preview reports -- and dividing by it yields NaN, which
   * would be written straight into the draft. board.js then falls back to the
   * built-in default for that widget, so the operator sees the widget jump
   * home rather than an error. Refusing the gesture is the honest answer. */
  function pointerFraction(event) {
    var rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) {
      return null;
    }
    return {
      x: (event.clientX - rect.left) / rect.width,
      y: (event.clientY - rect.top) / rect.height
    };
  }

  /** Assign only a real number. The last line of defence for the draft: a
   * geometry value that is not finite must never reach the layout document,
   * whatever produced it. */
  function setGeometry(widget, prop, value) {
    if (typeof value === 'number' && isFinite(value)) {
      // Round to the schema's own precision. Repeated fractional arithmetic
      // otherwise leaves values like 0.16999999999999998 in the number
      // fields, and Python would round them to the same place on save
      // anyway -- so the operator may as well be shown what will be stored.
      widget[prop] = Math.round(value * PRECISION_SCALE) / PRECISION_SCALE;
    }
  }

  /* --- Gestures ---------------------------------------------------------- */

  /** Move the selected widget to a snapped, in-bounds position. */
  function moveTo(widget, wantX, wantY) {
    var bounds = safeBounds();
    var targets = snapTargets(selected);
    var lines = [];

    var x = snapToGrid(wantX);
    var capturedX = capture(wantX, widget.width, targets.vertical);
    if (capturedX) {
      x = capturedX.origin;
      lines.push({ axis: 'v', at: capturedX.at });
    }
    var y = snapToGrid(wantY);
    var capturedY = capture(wantY, widget.height, targets.horizontal);
    if (capturedY) {
      y = capturedY.origin;
      lines.push({ axis: 'h', at: capturedY.at });
    }

    // The hard boundary. A drag stops at the safe area rather than being
    // allowed out and flagged, so a gesture can never build a layout that
    // Save then refuses.
    setGeometry(widget, 'x', clampRange(x, bounds.left, bounds.right - widget.width));
    setGeometry(widget, 'y', clampRange(y, bounds.top, bounds.bottom - widget.height));
    drawGuides(lines);
  }

  /** Resize the selected widget by moving one edge or corner. `edge` is a
   * compass string: n, s, e, w, or a corner such as `nw`. */
  function resizeTo(widget, edge, point) {
    var bounds = safeBounds();
    var targets = snapTargets(selected);
    var right = widget.x + widget.width;
    var bottom = widget.y + widget.height;

    if (edge.indexOf('w') !== -1) {
      var newLeft = clampRange(snapToGrid(point.x), bounds.left, right - MIN_SIZE.width);
      var capturedLeft = capture(point.x, 0, targets.vertical);
      if (capturedLeft) {
        newLeft = clampRange(capturedLeft.origin, bounds.left, right - MIN_SIZE.width);
      }
      setGeometry(widget, 'x', newLeft);
      setGeometry(widget, 'width', right - newLeft);
    }
    if (edge.indexOf('e') !== -1) {
      var newRight = clampRange(snapToGrid(point.x), widget.x + MIN_SIZE.width, bounds.right);
      var capturedRight = capture(point.x, 0, targets.vertical);
      if (capturedRight) {
        newRight = clampRange(capturedRight.origin, widget.x + MIN_SIZE.width, bounds.right);
      }
      setGeometry(widget, 'width', newRight - widget.x);
    }
    if (edge.indexOf('n') !== -1) {
      var newTop = clampRange(snapToGrid(point.y), bounds.top, bottom - MIN_SIZE.height);
      setGeometry(widget, 'y', newTop);
      setGeometry(widget, 'height', bottom - newTop);
    }
    if (edge.indexOf('s') !== -1) {
      var newBottom = clampRange(snapToGrid(point.y), widget.y + MIN_SIZE.height, bounds.bottom);
      setGeometry(widget, 'height', newBottom - widget.y);
    }
    clearGuides();
  }

  /** Redraw everything a gesture touches, without a bridge call. */
  function refreshGeometry() {
    renderPreview();
    renderHandles();
    renderProperties();
  }

  /** End a gesture: let Python have the last word, and record the change. */
  function settle() {
    clearGuides();
    markDirty(true);
    renderWidgetList();
    validateDraft();
  }

  canvas.addEventListener('pointerdown', function (event) {
    if (event.button !== 0) {
      return;
    }
    var handle = event.target.closest('[data-handle]');
    var widgetElement = event.target.closest('#game-board [data-widget]');
    if (!handle && !widgetElement) {
      return;
    }
    if (widgetElement && widgetElement.dataset.widget !== selected) {
      select(widgetElement.dataset.widget);
    }
    var widget = currentWidget();
    if (!widget) {
      return;
    }
    var point = pointerFraction(event);
    if (!point) {
      return;
    }
    drag = {
      edge: handle ? handle.dataset.handle : null,
      grabX: point.x - widget.x,
      grabY: point.y - widget.y
    };
    // Capture keeps the gesture alive if the pointer outruns the widget.
    // Losing it is survivable -- the move handler still fires on the canvas --
    // so a refusal must not abort the drag.
    try {
      canvas.setPointerCapture(event.pointerId);
    } catch (error) {
      drag.uncaptured = true;
    }
    canvas.classList.add('is-dragging');
    event.preventDefault();
  });

  canvas.addEventListener('pointermove', function (event) {
    if (!drag) {
      return;
    }
    var widget = currentWidget();
    if (!widget) {
      return;
    }
    var point = pointerFraction(event);
    if (!point) {
      return;
    }
    if (drag.edge) {
      resizeTo(widget, drag.edge, point);
    } else {
      moveTo(widget, point.x - drag.grabX, point.y - drag.grabY);
    }
    refreshGeometry();
  });

  function endDrag(event) {
    if (!drag) {
      return;
    }
    var wasCaptured = !drag.uncaptured;
    drag = null;
    canvas.classList.remove('is-dragging');
    try {
      if (wasCaptured && event && canvas.hasPointerCapture(event.pointerId)) {
        canvas.releasePointerCapture(event.pointerId);
      }
    } catch (error) {
      // Already released by the browser; nothing to undo.
    }
    settle();
  }

  canvas.addEventListener('pointerup', endDrag);
  canvas.addEventListener('pointercancel', endDrag);

  /** One nudge, from an arrow key or an on-screen arrow button. */
  function nudge(dx, dy, far) {
    var widget = currentWidget();
    if (!widget) {
      return;
    }
    var step = far ? COARSE : GRID;
    var bounds = safeBounds();
    setGeometry(widget, 'x', clampRange(snapToGrid(widget.x + dx * step),
      bounds.left, bounds.right - widget.width));
    setGeometry(widget, 'y', clampRange(snapToGrid(widget.y + dy * step),
      bounds.top, bounds.bottom - widget.height));
    refreshGeometry();
    settle();
  }

  var ARROWS = {
    ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]
  };

  document.addEventListener('keydown', function (event) {
    var step = ARROWS[event.key];
    if (!step || !selected) {
      return;
    }
    // Never steal an arrow key from a field the operator is typing in.
    var tag = event.target.tagName;
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') {
      return;
    }
    event.preventDefault();
    nudge(step[0], step[1], event.shiftKey);
  });

  /** Move the selection one place up or down the stacking order. */
  function restack(direction) {
    var widget = currentWidget();
    if (!widget) {
      return;
    }
    var limits = state && state.limits ? state.limits : {};
    var low = typeof limits.min_z_index === 'number' ? limits.min_z_index : 0;
    var high = typeof limits.max_z_index === 'number' ? limits.max_z_index : 100;
    widget.z_index = clampRange(widget.z_index + direction, low, high);
    refreshGeometry();
    settle();
  }

  /* --- Editing ---------------------------------------------------------- */

  function changeProperty(prop, value) {
    var widget = currentWidget();
    if (!widget) {
      return;
    }
    widget[prop] = value;
    markDirty(true);
    renderPreview();
    renderHandles();
    renderWidgetList();
    validateDraft();
  }

  function numberFrom(input) {
    // An empty or non-numeric field is left to Python to reject; the editor
    // never silently substitutes a value of its own.
    return input.value === '' ? null : Number(input.value);
  }

  document.addEventListener('input', function (event) {
    if (suppress) {
      return;
    }
    var target = event.target;
    if (target.id === 'prop-color-swatch') {
      var text = document.getElementById('prop-color');
      text.value = target.value.toUpperCase();
      changeProperty('color', text.value);
      return;
    }
    var prop = target.getAttribute('data-prop');
    if (!prop) {
      return;
    }
    if (prop === 'visible') {
      changeProperty('visible', target.checked);
    } else if (prop === 'color') {
      changeProperty('color', target.value);
    } else if (prop === 'font_weight') {
      changeProperty('font_weight', Number(target.value));
    } else if (NUMERIC_PROPS.indexOf(prop) !== -1) {
      changeProperty(prop, numberFrom(target));
    }
  });

  document.addEventListener('change', function (event) {
    if (suppress) {
      return;
    }
    if (event.target.id === 'layout-select') {
      selectLayout(event.target.value);
    }
  });

  /* --- Clicks ----------------------------------------------------------- */

  document.addEventListener('click', function (event) {
    var previewWidget = event.target.closest('#game-board [data-widget]');
    if (previewWidget) {
      select(previewWidget.dataset.widget);
      return;
    }
    var button = event.target.closest('button');
    if (!button) {
      return;
    }
    if (button.dataset.selectWidget) {
      select(button.dataset.selectWidget);
      return;
    }
    if (button.dataset.choiceProp) {
      changeProperty(button.dataset.choiceProp, button.dataset.choice);
      renderProperties();
      return;
    }
    if (button.dataset.action) {
      handleAction(button.dataset.action);
    }
  });

  function select(id) {
    selected = id;
    renderWidgetList();
    renderProperties();
    markSelection();
    renderHandles();
    clearGuides();
  }

  function handleAction(action) {
    if (action === 'save') {
      save(state.active);
    } else if (action === 'save_as_open') {
      document.getElementById('save-as').hidden = false;
      document.getElementById('save-as-name').focus();
    } else if (action === 'save_as_cancel') {
      document.getElementById('save-as').hidden = true;
    } else if (action === 'save_as_confirm') {
      var name = document.getElementById('save-as-name').value;
      document.getElementById('save-as').hidden = true;
      save(name);
    } else if (action === 'discard') {
      discard();
    } else if (action === 'reset_widget') {
      resetWidget();
    } else if (action === 'clamp') {
      clampDraft();
    } else if (action === 'reset_layout_ask') {
      document.getElementById('reset-confirm').hidden = false;
    } else if (action === 'reset_layout_cancel') {
      document.getElementById('reset-confirm').hidden = true;
    } else if (action === 'reset_layout_confirm') {
      document.getElementById('reset-confirm').hidden = true;
      resetLayout();
    } else if (action === 'nudge_left') {
      nudge(-1, 0, false);
    } else if (action === 'nudge_right') {
      nudge(1, 0, false);
    } else if (action === 'nudge_up') {
      nudge(0, -1, false);
    } else if (action === 'nudge_down') {
      nudge(0, 1, false);
    } else if (action === 'raise') {
      restack(1);
    } else if (action === 'lower') {
      restack(-1);
    }
  }

  function save(name) {
    if (!api || !api.save_layout) {
      return;
    }
    Promise.resolve(api.save_layout(name, draft)).then(function (payload) {
      if (payload && payload.ok) {
        clearAlert();
        adoptState(payload);
      } else {
        // Nothing was written; the previously saved layout is untouched.
        renderIssues(payload);
        showAlert((payload && payload.message) || 'That layout could not be saved.');
      }
    }).catch(function (error) {
      showAlert('That layout could not be saved: ' + error);
    });
  }

  function discard() {
    if (!api || !api.layout_state) {
      return;
    }
    Promise.resolve(api.layout_state()).then(function (payload) {
      clearAlert();
      adoptState(payload, { announce: false });
    }).catch(function (error) {
      showAlert('The saved layout could not be re-read: ' + error);
    });
  }

  function selectLayout(name) {
    if (!api || !api.select_layout) {
      return;
    }
    Promise.resolve(api.select_layout(name)).then(function (payload) {
      adoptState(payload);
    }).catch(function (error) {
      showAlert('That layout could not be selected: ' + error);
    });
  }

  function resetWidget() {
    if (!api || !api.reset_widget || !selected) {
      return;
    }
    Promise.resolve(api.reset_widget(selected, draft)).then(function (payload) {
      if (payload && payload.layout) {
        draft = clone(payload.layout);
        markDirty(true);
        renderWidgetList();
        renderProperties();
        renderPreview();
        renderIssues(payload);
      }
    }).catch(function (error) {
      showAlert('That widget could not be reset: ' + error);
    });
  }

  function clampDraft() {
    if (!api || !api.clamp_layout) {
      return;
    }
    Promise.resolve(api.clamp_layout(draft)).then(function (payload) {
      if (payload && payload.layout) {
        draft = clone(payload.layout);
        markDirty(true);
        renderWidgetList();
        renderProperties();
        renderPreview();
        renderIssues(payload);
      }
    }).catch(function (error) {
      showAlert('The layout could not be fitted: ' + error);
    });
  }

  function resetLayout() {
    if (!api || !api.reset_layout) {
      return;
    }
    Promise.resolve(api.reset_layout()).then(function (payload) {
      adoptState(payload);
    }).catch(function (error) {
      showAlert('The layout could not be reset: ' + error);
    });
  }

  /* --- Host entry points ------------------------------------------------ */

  /* The host pushes a layout whenever it changes anywhere, so a save made in
   * another window is reflected here. An unsaved draft is deliberately kept:
   * the operator's in-progress edit is not discarded behind their back. */
  window.applyLayout = function (layout) {
    if (!layout) {
      return;
    }
    if (!dirty) {
      draft = clone(layout);
      renderWidgetList();
      renderProperties();
      renderPreview();
    }
  };

  /* The host also pushes spectator view models; the preview follows the live
   * board so the operator judges the layout against real values. */
  window.applyView = function (model) {
    snapshot = model;
    renderPreview();
  };

  Board.build(boardRoot);

  buildHandles();

  R.whenReady(function (bridge) {
    api = bridge;
    Promise.resolve(api.layout_state()).then(function (payload) {
      adoptState(payload, { announce: false });
      refreshSnapshot();
    }).catch(function (error) {
      showAlert('The stored layouts could not be read: ' + error);
    });
  });
})();
