/* Presentation layout editor -- canvas gestures.
 *
 * Everything that turns a pointer or a key into a geometry change: drag to
 * move, drag a grip to resize, the marquee, the snap guides, the drag
 * readout chip, the right-click context menu, and zoom. This file never
 * calls the bridge -- every gesture ends by asking `app.commit()` (in
 * layout.js) to validate the result with Python and record it in history.
 *
 * `app` (built in layout.js) is the only thing this file depends on outside
 * itself: it carries the live draft, the selection, and a small set of
 * callbacks (`commit`, `liveRefresh`, `select`, ...). Nothing here reaches
 * into layout.js's closures directly.
 */

(function (global) {
  'use strict';

  var LayoutEditor = global.LayoutEditor;
  var S = LayoutEditor.State;

  var ZOOM_LEVELS = [50, 75, 100, 150, 200];
  var GRID = 0.005;
  var COARSE = 0.02;
  var SNAP = 0.008;

  var canvasEl = document.getElementById('canvas');
  var guideLayer = document.getElementById('guides');
  var handleLayer = document.getElementById('handles');
  var marqueeEl = document.getElementById('marquee');
  var readoutChip = document.getElementById('readout-chip');
  var contextMenu = document.getElementById('context-menu');
  var canvasScroll = document.getElementById('canvas-scroll');
  var zoomReadout = document.getElementById('zoom-readout');

  var drag = null;       // the gesture in progress, or null
  var marquee = null;    // marquee rectangle in progress, or null
  var fitWidth = 960;    // measured available width at 100% zoom
  var zoomLevel = 100;

  /* --- Geometry helpers scoped to the running app --------------------- */

  function precisionScale(app) {
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

  function minSize(app) {
    var limits = (app.state && app.state.limits) || {};
    return {
      width: typeof limits.min_widget_width === 'number' ? limits.min_widget_width : 0.02,
      height: typeof limits.min_widget_height === 'number' ? limits.min_widget_height : 0.02
    };
  }

  function pointerFraction(event) {
    var rect = canvasEl.getBoundingClientRect();
    if (!rect.width || !rect.height) {
      return null;
    }
    return {
      x: (event.clientX - rect.left) / rect.width,
      y: (event.clientY - rect.top) / rect.height
    };
  }

  function drawGuides(lines) {
    guideLayer.replaceChildren();
    lines.forEach(function (line) {
      var el = document.createElement('div');
      el.className = 'guide guide-' + line.axis;
      el.style.setProperty('--at', line.at);
      guideLayer.appendChild(el);
    });
  }

  function clearGuides() {
    guideLayer.replaceChildren();
  }

  function showReadout(text, event) {
    var panelRect = canvasScroll.getBoundingClientRect();
    readoutChip.textContent = text;
    readoutChip.style.left = (event.clientX - panelRect.left + 14) + 'px';
    readoutChip.style.top = (event.clientY - panelRect.top + 14) + 'px';
    readoutChip.hidden = false;
  }

  function hideReadout() {
    readoutChip.hidden = true;
  }

  function percentText(value) {
    return String(Math.round(value * 1000) / 10);
  }

  /* --- Handles ----------------------------------------------------------- */

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

  function renderSelection(app) {
    var ids = app.selection.ids;
    var single = ids.length === 1 ? S.getItem(app.screenDoc(), ids[0]) : null;
    handleLayer.hidden = !single || single.visible === false;
    if (single) {
      handleLayer.style.setProperty('--hx', single.x);
      handleLayer.style.setProperty('--hy', single.y);
      handleLayer.style.setProperty('--hw', single.width);
      handleLayer.style.setProperty('--hh', single.height);
    }
    var root = document.getElementById('game-board');
    var nodes = root.querySelectorAll('[data-item]');
    for (var i = 0; i < nodes.length; i += 1) {
      var id = nodes[i].getAttribute('data-item');
      nodes[i].classList.toggle('is-selected', S.isSelected(app.selection, id));
    }
  }

  /* --- Move / resize ------------------------------------------------------ */

  function moveItemTo(app, id, wantX, wantY) {
    var doc = app.screenDoc();
    var item = S.getItem(doc, id);
    if (!item) {
      return;
    }
    var kind = S.kindOf(doc, id);
    var bounds = S.boundsFor(doc, kind);
    var targets = S.snapTargets(doc, id);
    var scale = precisionScale(app);
    var lines = [];

    var x = S.snapToGrid(wantX, GRID);
    var capturedX = S.capture(wantX, item.width, targets.vertical, SNAP);
    if (capturedX) {
      x = capturedX.origin;
      lines.push({ axis: 'v', at: capturedX.at });
    }
    var y = S.snapToGrid(wantY, GRID);
    var capturedY = S.capture(wantY, item.height, targets.horizontal, SNAP);
    if (capturedY) {
      y = capturedY.origin;
      lines.push({ axis: 'h', at: capturedY.at });
    }

    S.setGeometry(item, 'x', S.clampRange(x, bounds.left, bounds.right - item.width), scale);
    S.setGeometry(item, 'y', S.clampRange(y, bounds.top, bounds.bottom - item.height), scale);
    drawGuides(lines);
  }

  /** Move every member of a group by one delta measured from `origins`, the
   * positions the members had when the gesture began. A drag delivers a
   * pointer event per frame, each carrying the *total* displacement so far,
   * so the delta must always be applied to the origin -- applying it to the
   * current position would add every frame's displacement to the last one's.
   * Callers with no gesture (a nudge) pass no origins and the current
   * positions are used. */
  function moveGroupBy(app, ids, dx, dy, origins) {
    var doc = app.screenDoc();
    var scale = precisionScale(app);
    var i;
    var item;
    if (!origins) {
      origins = {};
      for (i = 0; i < ids.length; i += 1) {
        item = S.getItem(doc, ids[i]);
        if (item) {
          origins[ids[i]] = { x: item.x, y: item.y };
        }
      }
    }
    // Put every member back where the gesture started so the clamp below
    // measures the delta against the same positions the delta was.
    for (i = 0; i < ids.length; i += 1) {
      item = S.getItem(doc, ids[i]);
      if (item && origins[ids[i]]) {
        S.setGeometry(item, 'x', origins[ids[i]].x, scale);
        S.setGeometry(item, 'y', origins[ids[i]].y, scale);
      }
    }
    var clamped = S.clampGroupDelta(doc, ids, dx, dy);
    for (i = 0; i < ids.length; i += 1) {
      item = S.getItem(doc, ids[i]);
      if (!item || !origins[ids[i]]) {
        continue;
      }
      S.setGeometry(item, 'x', origins[ids[i]].x + clamped.dx, scale);
      S.setGeometry(item, 'y', origins[ids[i]].y + clamped.dy, scale);
    }
  }

  function resizeTo(app, id, edge, point) {
    var doc = app.screenDoc();
    var item = S.getItem(doc, id);
    if (!item) {
      return;
    }
    var kind = S.kindOf(doc, id);
    var bounds = S.boundsFor(doc, kind);
    var targets = S.snapTargets(doc, id);
    var scale = precisionScale(app);
    var minimum = minSize(app);
    var right = item.x + item.width;
    var bottom = item.y + item.height;

    if (edge.indexOf('w') !== -1) {
      var newLeft = S.clampRange(S.snapToGrid(point.x, GRID), bounds.left, right - minimum.width);
      var capturedLeft = S.capture(point.x, 0, targets.vertical, SNAP);
      if (capturedLeft) {
        newLeft = S.clampRange(capturedLeft.origin, bounds.left, right - minimum.width);
      }
      S.setGeometry(item, 'x', newLeft, scale);
      S.setGeometry(item, 'width', right - newLeft, scale);
    }
    if (edge.indexOf('e') !== -1) {
      var newRight = S.clampRange(S.snapToGrid(point.x, GRID), item.x + minimum.width, bounds.right);
      var capturedRight = S.capture(point.x, 0, targets.vertical, SNAP);
      if (capturedRight) {
        newRight = S.clampRange(capturedRight.origin, item.x + minimum.width, bounds.right);
      }
      S.setGeometry(item, 'width', newRight - item.x, scale);
    }
    if (edge.indexOf('n') !== -1) {
      var newTop = S.clampRange(S.snapToGrid(point.y, GRID), bounds.top, bottom - minimum.height);
      S.setGeometry(item, 'y', newTop, scale);
      S.setGeometry(item, 'height', bottom - newTop, scale);
    }
    if (edge.indexOf('s') !== -1) {
      var newBottom = S.clampRange(S.snapToGrid(point.y, GRID), item.y + minimum.height, bounds.bottom);
      S.setGeometry(item, 'height', newBottom - item.y, scale);
    }
    clearGuides();
  }

  /* --- Pointer sequence ---------------------------------------------------- */

  function findItemNode(target) {
    return target.closest('#game-board [data-item]');
  }

  function visibleItemIds(draft) {
    var ids = [];
    var widgetIds = Object.keys(draft.widgets || {});
    for (var w = 0; w < widgetIds.length; w += 1) {
      var widget = draft.widgets[widgetIds[w]];
      if (widget && widget.visible !== false) {
        ids.push(widgetIds[w]);
      }
    }
    var elements = draft.elements || [];
    for (var e = 0; e < elements.length; e += 1) {
      if (elements[e].visible !== false) {
        ids.push(elements[e].id);
      }
    }
    return ids;
  }

  function intersects(a, b) {
    return a.x < b.x + b.width && a.x + a.width > b.x &&
      a.y < b.y + b.height && a.y + a.height > b.y;
  }

  function startMarquee(app, point, keepExisting) {
    marquee = { startX: point.x, startY: point.y, keep: keepExisting ? app.selection.ids.slice() : [] };
    marqueeEl.hidden = false;
  }

  function updateMarquee(app, point) {
    if (!marquee) {
      return;
    }
    var x0 = S.minNum(marquee.startX, point.x);
    var y0 = S.minNum(marquee.startY, point.y);
    var x1 = S.maxNum(marquee.startX, point.x);
    var y1 = S.maxNum(marquee.startY, point.y);
    marqueeEl.style.setProperty('--mx', x0);
    marqueeEl.style.setProperty('--my', y0);
    marqueeEl.style.setProperty('--mw', x1 - x0);
    marqueeEl.style.setProperty('--mh', y1 - y0);
    var box = { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
    var hit = [];
    var doc = app.screenDoc();
    var candidates = visibleItemIds(doc);
    for (var i = 0; i < candidates.length; i += 1) {
      var item = S.getItem(doc, candidates[i]);
      if (item && intersects(box, item)) {
        hit.push(candidates[i]);
      }
    }
    var merged = marquee.keep.slice();
    for (var j = 0; j < hit.length; j += 1) {
      if (merged.indexOf(hit[j]) === -1) {
        merged.push(hit[j]);
      }
    }
    app.select(merged);
  }

  function endMarquee() {
    marquee = null;
    marqueeEl.hidden = true;
  }

  function onPointerDown(app, event) {
    if (event.button !== 0) {
      return;
    }
    closeContextMenu(app);
    var handle = event.target.closest('[data-handle]');
    var itemNode = findItemNode(event.target);
    var point = pointerFraction(event);
    if (!point) {
      return;
    }

    if (handle && app.selection.ids.length === 1) {
      var id = app.selection.ids[0];
      drag = { kind: 'resize', id: id, edge: handle.getAttribute('data-handle') };
      capturePointer(event);
      return;
    }

    if (itemNode) {
      var itemId = itemNode.getAttribute('data-item');
      if (event.shiftKey) {
        app.toggleSelect(itemId);
      } else if (!S.isSelected(app.selection, itemId)) {
        app.select([itemId]);
      }
      if (!S.isSelected(app.selection, itemId)) {
        return; // shift-click just removed it from the selection
      }
      var ids = app.selection.ids.slice();
      var origins = {};
      for (var i = 0; i < ids.length; i += 1) {
        var member = S.getItem(app.screenDoc(), ids[i]);
        if (member) {
          origins[ids[i]] = { x: member.x, y: member.y };
        }
      }
      var grabbed = S.getItem(app.screenDoc(), itemId);
      drag = {
        kind: ids.length > 1 ? 'group' : 'move',
        id: itemId,
        ids: ids,
        origins: origins,
        grabX: point.x - grabbed.x,
        grabY: point.y - grabbed.y
      };
      capturePointer(event);
      return;
    }

    // Empty canvas: clear (unless extending) and start a marquee.
    if (!event.shiftKey) {
      app.clearSelection();
    }
    startMarquee(app, point, event.shiftKey);
    capturePointer(event);
  }

  function capturePointer(event) {
    canvasEl.classList.add('is-dragging');
    try {
      canvasEl.setPointerCapture(event.pointerId);
    } catch (error) {
      // Losing capture is survivable; pointermove still fires on the canvas.
    }
    event.preventDefault();
  }

  function onPointerMove(app, event) {
    var point = pointerFraction(event);
    if (!point) {
      return;
    }
    if (marquee) {
      updateMarquee(app, point);
      return;
    }
    if (!drag) {
      return;
    }
    // Only a pointer that actually moved turns this gesture into an edit;
    // a plain click that selects something must not dirty the draft.
    drag.moved = true;
    if (drag.kind === 'resize') {
      resizeTo(app, drag.id, drag.edge, point);
      var resized = S.getItem(app.screenDoc(), drag.id);
      showReadout('W ' + percentText(resized.width) + '%  H ' + percentText(resized.height) + '%', event);
    } else if (drag.kind === 'group') {
      var origin = drag.origins[drag.id];
      var dx = (point.x - drag.grabX) - origin.x;
      var dy = (point.y - drag.grabY) - origin.y;
      moveGroupBy(app, drag.ids, dx, dy, drag.origins);
      var moved = S.getItem(app.screenDoc(), drag.id);
      showReadout('X ' + percentText(moved.x) + '%  Y ' + percentText(moved.y) + '%', event);
    } else {
      moveItemTo(app, drag.id, point.x - drag.grabX, point.y - drag.grabY);
      var placed = S.getItem(app.screenDoc(), drag.id);
      showReadout('X ' + percentText(placed.x) + '%  Y ' + percentText(placed.y) + '%', event);
    }
    app.liveRefresh();
  }

  function onPointerUp(app, event) {
    var wasDragging = Boolean(drag);
    var edited = Boolean(drag && drag.moved);
    var wasMarquee = Boolean(marquee);
    drag = null;
    canvasEl.classList.remove('is-dragging');
    try {
      if (event && canvasEl.hasPointerCapture(event.pointerId)) {
        canvasEl.releasePointerCapture(event.pointerId);
      }
    } catch (error) {
      // Already released.
    }
    clearGuides();
    hideReadout();
    if (wasMarquee) {
      endMarquee();
    }
    if (edited) {
      app.commit();
    } else if (wasDragging || wasMarquee) {
      // Selection changed, the layout did not: redraw, record nothing.
      app.renderAll();
    }
  }

  /* --- Nudge, restack, align, distribute ----------------------------------- */

  function nudge(app, dx, dy, far) {
    if (!app.selection.ids.length) {
      return;
    }
    var step = far ? COARSE : GRID;
    moveGroupBy(app, app.selection.ids, dx * step, dy * step);
    app.commit();
  }

  function restack(app, direction) {
    var id = app.selection.primary;
    var item = id ? S.getItem(app.screenDoc(), id) : null;
    if (!item) {
      return;
    }
    var limits = (app.state && app.state.limits) || {};
    var low = typeof limits.min_z_index === 'number' ? limits.min_z_index : 0;
    var high = typeof limits.max_z_index === 'number' ? limits.max_z_index : 100;
    item.z_index = S.clampRange(item.z_index + direction, low, high);
    app.commit();
  }

  function toExtreme(app, toTop) {
    var id = app.selection.primary;
    var item = id ? S.getItem(app.screenDoc(), id) : null;
    if (!item) {
      return;
    }
    var limits = (app.state && app.state.limits) || {};
    var low = typeof limits.min_z_index === 'number' ? limits.min_z_index : 0;
    var high = typeof limits.max_z_index === 'number' ? limits.max_z_index : 100;
    item.z_index = toTop ? high : low;
    app.commit();
  }

  function boundsOf(app, ids) {
    var left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
    var doc = app.screenDoc();
    for (var i = 0; i < ids.length; i += 1) {
      var item = S.getItem(doc, ids[i]);
      if (!item) {
        continue;
      }
      left = S.minNum(left, item.x);
      top = S.minNum(top, item.y);
      right = S.maxNum(right, item.x + item.width);
      bottom = S.maxNum(bottom, item.y + item.height);
    }
    return { left: left, top: top, right: right, bottom: bottom };
  }

  /** With one item selected, align to the safe area (or canvas, for
   * image/box); with several, align to the selection's own bounding box. */
  function align(app, edge) {
    var ids = app.selection.ids;
    if (!ids.length) {
      return;
    }
    var doc = app.screenDoc();
    var scale = precisionScale(app);
    var group = ids.length > 1 ? boundsOf(app, ids) : null;
    for (var i = 0; i < ids.length; i += 1) {
      var item = S.getItem(doc, ids[i]);
      if (!item) {
        continue;
      }
      var ref = group || S.boundsFor(doc, S.kindOf(doc, ids[i]));
      if (edge === 'left') {
        S.setGeometry(item, 'x', ref.left, scale);
      } else if (edge === 'right') {
        S.setGeometry(item, 'x', ref.right - item.width, scale);
      } else if (edge === 'center') {
        S.setGeometry(item, 'x', (ref.left + ref.right) / 2 - item.width / 2, scale);
      } else if (edge === 'top') {
        S.setGeometry(item, 'y', ref.top, scale);
      } else if (edge === 'bottom') {
        S.setGeometry(item, 'y', ref.bottom - item.height, scale);
      } else if (edge === 'middle') {
        S.setGeometry(item, 'y', (ref.top + ref.bottom) / 2 - item.height / 2, scale);
      }
    }
    app.commit();
  }

  function distribute(app, axis) {
    var ids = app.selection.ids.slice();
    if (ids.length < 3) {
      return;
    }
    var doc = app.screenDoc();
    var scale = precisionScale(app);
    var prop = axis === 'h' ? 'x' : 'y';
    var size = axis === 'h' ? 'width' : 'height';
    ids.sort(function (a, b) {
      var ia = S.getItem(doc, a), ib = S.getItem(doc, b);
      return ia[prop] - ib[prop];
    });
    var first = S.getItem(doc, ids[0]);
    var last = S.getItem(doc, ids[ids.length - 1]);
    var span = (last[prop] + last[size]) - first[prop];
    var totalSize = 0;
    for (var i = 0; i < ids.length; i += 1) {
      totalSize += S.getItem(doc, ids[i])[size];
    }
    var gap = (span - totalSize) / (ids.length - 1);
    var cursor = first[prop] + first[size];
    for (var j = 1; j < ids.length - 1; j += 1) {
      var item = S.getItem(doc, ids[j]);
      cursor += gap;
      S.setGeometry(item, prop, cursor, scale);
      cursor += item[size];
    }
    app.commit();
  }

  /* --- Zoom ---------------------------------------------------------------- */

  function applyZoom() {
    var width = fitWidth * (zoomLevel / 100);
    canvasEl.style.setProperty('--preview-width', width + 'px');
    zoomReadout.textContent = String(zoomLevel) + '%';
  }

  function measureFit() {
    var rect = canvasScroll.getBoundingClientRect();
    var padding = 32;
    var availWidth = S.maxNum(rect.width - padding, 240);
    var availHeight = S.maxNum(rect.height - padding, 135);
    fitWidth = S.minNum(availWidth, availHeight * (16 / 9));
    applyZoom();
  }

  function setZoomLevel(level) {
    zoomLevel = level;
    applyZoom();
  }

  function zoomIn() {
    for (var i = 0; i < ZOOM_LEVELS.length; i += 1) {
      if (ZOOM_LEVELS[i] > zoomLevel) {
        setZoomLevel(ZOOM_LEVELS[i]);
        return;
      }
    }
  }

  function zoomOut() {
    for (var i = ZOOM_LEVELS.length - 1; i >= 0; i -= 1) {
      if (ZOOM_LEVELS[i] < zoomLevel) {
        setZoomLevel(ZOOM_LEVELS[i]);
        return;
      }
    }
  }

  function zoomFit() {
    setZoomLevel(100);
  }

  /* --- Context menu ---------------------------------------------------------- */

  function closeContextMenu() {
    contextMenu.hidden = true;
  }

  function openContextMenu(app, id, clientX, clientY) {
    if (id && !S.isSelected(app.selection, id)) {
      app.select([id]);
    }
    var kind = id ? S.kindOf(app.screenDoc(), id) : null;
    var isElement = S.isElementId(app.screenDoc(), id || '');
    var isWidget = kind === 'widget';
    Array.prototype.forEach.call(contextMenu.querySelectorAll('[data-context-for]'), function (node) {
      var scope = node.getAttribute('data-context-for');
      var show = scope === 'any' || (scope === 'element' && isElement) || (scope === 'widget' && isWidget);
      node.hidden = !show;
    });
    var panelRect = canvasScroll.getBoundingClientRect();
    contextMenu.style.left = (clientX - panelRect.left) + 'px';
    contextMenu.style.top = (clientY - panelRect.top) + 'px';
    contextMenu.hidden = false;
  }

  /* --- Wiring --------------------------------------------------------------- */

  function init(app) {
    buildHandles();
    canvasEl.addEventListener('pointerdown', function (event) { onPointerDown(app, event); });
    canvasEl.addEventListener('pointermove', function (event) { onPointerMove(app, event); });
    canvasEl.addEventListener('pointerup', function (event) { onPointerUp(app, event); });
    canvasEl.addEventListener('pointercancel', function (event) { onPointerUp(app, event); });
    canvasEl.addEventListener('contextmenu', function (event) {
      event.preventDefault();
      var itemNode = findItemNode(event.target);
      openContextMenu(app, itemNode ? itemNode.getAttribute('data-item') : null, event.clientX, event.clientY);
    });
    // A native ghost-drag of a preview <img> would otherwise fight the
    // editor's own move gesture; the drop handler below is the only drag
    // behaviour the canvas offers.
    canvasEl.addEventListener('dragstart', function (event) { event.preventDefault(); });
    canvasEl.addEventListener('dragover', function (event) { event.preventDefault(); });
    canvasEl.addEventListener('drop', function (event) {
      event.preventDefault();
      var files = event.dataTransfer && event.dataTransfer.files;
      if (files && files.length) {
        app.addImageFromFile(files[0]);
      }
    });
    if (global.ResizeObserver) {
      new ResizeObserver(measureFit).observe(canvasScroll);
    } else {
      global.addEventListener('resize', measureFit);
    }
    measureFit();
  }

  LayoutEditor.Canvas = {
    init: init,
    renderSelection: renderSelection,
    nudge: nudge,
    restack: restack,
    toFront: function (app) { toExtreme(app, true); },
    toBack: function (app) { toExtreme(app, false); },
    align: align,
    distribute: distribute,
    zoomIn: zoomIn,
    zoomOut: zoomOut,
    zoomFit: zoomFit,
    closeContextMenu: closeContextMenu,
    clearGuides: clearGuides
  };
})(window);
