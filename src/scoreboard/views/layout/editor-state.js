/* Presentation layout editor -- state layer.
 *
 * Pure data and geometry helpers: nothing in this file touches the DOM or the
 * bridge. Everything here operates on plain objects -- the draft layout
 * document, the history stack, the selection set -- so it can be exercised
 * without a page at all. `editor-canvas.js` and `editor-panels.js` call into
 * this module for every rule about where a rectangle is allowed to go, what a
 * newly added element looks like, and how the history/selection stacks are
 * shaped; `layout.js` owns the only calls to the bridge.
 *
 * A drag produces a pointer event per frame, and a bridge round trip per
 * frame is not a thing a webview can do -- so the gesture math below (snap,
 * clamp, safe-area boundary) has to live in the browser. Python still owns
 * the verdict: every gesture ends in preview_layout(), and Save is still
 * gated on what Python says.
 */

(function (global) {
  'use strict';

  var LayoutEditor = global.LayoutEditor = global.LayoutEditor || {};

  /* --- Small numeric helpers (Math. may only ever be followed by round) -- */

  function minNum(a, b) { return a < b ? a : b; }
  function maxNum(a, b) { return a > b ? a : b; }
  function apart(a, b) { var d = a - b; return d < 0 ? -d : d; }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function isFiniteNumber(value) {
    return typeof value === 'number' && isFinite(value);
  }

  /** A widget wider than its boundary would make low > high; letting the low
   * edge win keeps it on the board instead of inverting the box. */
  function clampRange(value, low, high) {
    if (high < low) {
      return low;
    }
    return value < low ? low : (value > high ? high : value);
  }

  function snapToGrid(value, grid) {
    return Math.round(value / grid) * grid;
  }

  /** Round to the schema's own coordinate precision. Repeated fractional
   * arithmetic otherwise leaves values like 0.16999999999999998 sitting in
   * the draft, and Python would round to the same place on save anyway. */
  function roundTo(value, scale) {
    return Math.round(value * scale) / scale;
  }

  /** Assign only a real, finite number. The last line of defence for the
   * draft: a geometry value that is not finite must never reach the layout
   * document, whatever produced it. */
  function setGeometry(target, prop, value, scale) {
    if (isFiniteNumber(value)) {
      target[prop] = roundTo(value, scale || 10000);
    }
  }

  /* --- Boundaries ---------------------------------------------------------
   *
   * A text element behaves like a widget: it must stay inside the safe area.
   * An image or box may cross the safe area -- a full-bleed backdrop is the
   * point -- but must stay inside the canvas.
   */

  function safeBounds(draft) {
    var area = (draft && draft.safe_area) ? draft.safe_area : null;
    var top = area && typeof area.top === 'number' ? area.top : 0.04;
    var right = area && typeof area.right === 'number' ? area.right : 0.04;
    var bottom = area && typeof area.bottom === 'number' ? area.bottom : 0.04;
    var left = area && typeof area.left === 'number' ? area.left : 0.04;
    return { left: left, top: top, right: 1 - right, bottom: 1 - bottom };
  }

  function canvasBounds() {
    return { left: 0, top: 0, right: 1, bottom: 1 };
  }

  /** Whether `id` names something backed by the safe area (a widget, or a
   * text element) rather than the full canvas (image/box). */
  function usesSafeArea(kind) {
    return kind === 'widget' || kind === 'text';
  }

  /** A box flagged `bleed` may overhang the canvas by up to half its span on
   * every side (BLEED_MIN/BLEED_MAX in Python) so a rotated bar or a light
   * sweep can start off-board; the board sections clip whatever crosses. */
  var BLEED_MIN = -0.5;
  var BLEED_MAX = 1.5;

  function bleedBounds() {
    return { left: BLEED_MIN, top: BLEED_MIN, right: BLEED_MAX, bottom: BLEED_MAX };
  }

  function isBleedBox(item) {
    return Boolean(item && item.type === 'box' && item.bleed === true);
  }

  /** `item` is optional: without it a box gets the plain canvas bounds. A
   * ticker, like a box, may sit anywhere inside the canvas. */
  function boundsFor(draft, kind, item) {
    if (usesSafeArea(kind)) {
      return safeBounds(draft);
    }
    return isBleedBox(item) ? bleedBounds() : canvasBounds();
  }

  /* --- Item lookup ---------------------------------------------------------
   *
   * An "item" is either a widget (keyed in draft.widgets) or an element
   * (found by id in draft.elements). Both expose the same geometry shape.
   */

  function getWidget(draft, id) {
    return (draft && draft.widgets) ? draft.widgets[id] || null : null;
  }

  function getElementIndex(draft, id) {
    var elements = (draft && draft.elements) || [];
    for (var index = 0; index < elements.length; index += 1) {
      if (elements[index].id === id) {
        return index;
      }
    }
    return -1;
  }

  function getElement(draft, id) {
    var index = getElementIndex(draft, id);
    return index === -1 ? null : draft.elements[index];
  }

  /** 'widget' | 'text' | 'image' | 'box' | 'ticker' | null */
  function kindOf(draft, id) {
    if (getWidget(draft, id)) {
      return 'widget';
    }
    var element = getElement(draft, id);
    return element ? element.type : null;
  }

  function getItem(draft, id) {
    return getWidget(draft, id) || getElement(draft, id);
  }

  function isElementId(draft, id) {
    return getElementIndex(draft, id) !== -1;
  }

  /** Elements for the layers rail: by descending z_index, then by the order
   * they already sit in the document (a stable secondary key). */
  function elementsForLayers(draft) {
    var elements = ((draft && draft.elements) || []).slice();
    var withIndex = elements.map(function (element, index) {
      return { element: element, index: index };
    });
    withIndex.sort(function (a, b) {
      if (a.element.z_index !== b.element.z_index) {
        return b.element.z_index - a.element.z_index;
      }
      return a.index - b.index;
    });
    return withIndex.map(function (entry) { return entry.element; });
  }

  /** Every visible item's edges/centres for a dragged item to snap against:
   * the safe-area boundary, the canvas centre, and the corresponding lines
   * of every other visible widget or element. */
  function snapTargets(draft, excludeId) {
    var bounds = safeBounds(draft);
    var vertical = [bounds.left, bounds.right, 0.5];
    var horizontal = [bounds.top, bounds.bottom, 0.5];

    function addTarget(item) {
      if (!item || item.visible === false) {
        return;
      }
      vertical.push(item.x, item.x + item.width / 2, item.x + item.width);
      horizontal.push(item.y, item.y + item.height / 2, item.y + item.height);
    }

    var widgetIds = Object.keys((draft && draft.widgets) || {});
    for (var w = 0; w < widgetIds.length; w += 1) {
      if (widgetIds[w] !== excludeId) {
        addTarget(draft.widgets[widgetIds[w]]);
      }
    }
    var elements = (draft && draft.elements) || [];
    for (var e = 0; e < elements.length; e += 1) {
      if (elements[e].id !== excludeId) {
        addTarget(elements[e]);
      }
    }
    return { vertical: vertical, horizontal: horizontal };
  }

  /** Pull `origin` onto the nearest target within `snap`, given the moving
   * box presents three lines of its own (near edge, centre, far edge). */
  function capture(origin, size, targets, snap) {
    var best = null;
    var offsets = [0, size / 2, size];
    for (var line = 0; line < targets.length; line += 1) {
      for (var which = 0; which < offsets.length; which += 1) {
        var distance = apart(origin + offsets[which], targets[line]);
        if (distance <= snap && (!best || distance < best.distance)) {
          best = { distance: distance, origin: targets[line] - offsets[which], at: targets[line] };
        }
      }
    }
    return best;
  }

  /* --- Element factories ---------------------------------------------------
   *
   * New elements get ids like text_1, image_1, box_1, skipping ids already
   * in use (by another element, or -- belt and braces -- by a widget id).
   */

  function nextElementId(draft, widgetIds, prefix) {
    var used = {};
    var elements = (draft && draft.elements) || [];
    for (var i = 0; i < elements.length; i += 1) {
      used[elements[i].id] = true;
    }
    for (var j = 0; j < (widgetIds || []).length; j += 1) {
      used[widgetIds[j]] = true;
    }
    var n = 1;
    while (used[prefix + '_' + n]) {
      n += 1;
    }
    return prefix + '_' + n;
  }

  var TEXT_STYLE_DEFAULTS = {
    color: '#FFFFFF',
    font_family: 'arial',
    font_scale: 0.03,
    font_weight: 700,
    letter_spacing: 0,
    text_transform: 'none',
    text_effect: 'none',
    text_align: 'center',
    vertical_align: 'middle',
    padding: 0
  };

  var FILL_DEFAULTS = {
    background: null,
    background_opacity: 1,
    border_color: null,
    border_width: 0,
    corner_radius: 0,
    corner_cut: 0,
    cut_corners: 'all'
  };

  function withFillDefaults(target) {
    var keys = ['background', 'background_opacity', 'border_color', 'border_width', 'corner_radius',
                'corner_cut', 'cut_corners'];
    for (var i = 0; i < keys.length; i += 1) {
      target[keys[i]] = FILL_DEFAULTS[keys[i]];
    }
    return target;
  }

  function makeTextElement(draft, widgetIds, zIndex) {
    var width = 0.24;
    var height = 0.08;
    var element = {
      id: nextElementId(draft, widgetIds, 'text'),
      type: 'text',
      visible: true,
      x: roundTo(0.5 - width / 2, 10000),
      y: roundTo(0.5 - height / 2, 10000),
      width: width,
      height: height,
      z_index: typeof zIndex === 'number' ? zIndex : 10,
      opacity: 1,
      text: 'NEW TEXT'
    };
    withFillDefaults(element);
    var textKeys = Object.keys(TEXT_STYLE_DEFAULTS);
    for (var i = 0; i < textKeys.length; i += 1) {
      element[textKeys[i]] = TEXT_STYLE_DEFAULTS[textKeys[i]];
    }
    return element;
  }

  function makeBoxElement(draft, widgetIds) {
    var width = 0.30;
    var height = 0.20;
    var element = {
      id: nextElementId(draft, widgetIds, 'box'),
      type: 'box',
      visible: true,
      x: roundTo(0.5 - width / 2, 10000),
      y: roundTo(0.5 - height / 2, 10000),
      width: width,
      height: height,
      z_index: 0,
      opacity: 1
    };
    withFillDefaults(element);
    element.background = '#1B222B';
    element.corner_radius = 0.01;
    return element;
  }

  /** A ticker is a band along the bottom of the board carrying announcement
   * lines. Its text style mirrors a text element's; `lines`/`mode`/
   * `speed_seconds` are its own. The defaults are pinned by the event-screens
   * spec (section 4) and match what the built-in welcome screens use. */
  function makeTickerElement(draft, widgetIds) {
    var element = {
      id: nextElementId(draft, widgetIds, 'ticker'),
      type: 'ticker',
      visible: true,
      x: 0,
      y: 0.89,
      width: 1,
      height: 0.1,
      z_index: 10,
      opacity: 1,
      lines: ['NEW ANNOUNCEMENT'],
      mode: 'scroll',
      speed_seconds: 30
    };
    withFillDefaults(element);
    element.background = '#0D2B5A';
    var textKeys = Object.keys(TEXT_STYLE_DEFAULTS);
    for (var i = 0; i < textKeys.length; i += 1) {
      element[textKeys[i]] = TEXT_STYLE_DEFAULTS[textKeys[i]];
    }
    element.color = '#DDE7F4';
    element.font_family = 'barlow_condensed';
    element.font_weight = 500;
    element.font_scale = 0.025;
    element.letter_spacing = 0.16;
    return element;
  }

  /** `naturalWidth`/`naturalHeight` come from the loaded `Image`; the width
   * fraction is fixed by the spec, and the height fraction is derived so the
   * image keeps its own aspect ratio on the 16:9 canvas. */
  function makeImageElement(draft, widgetIds, src, naturalWidth, naturalHeight) {
    var width = 0.30;
    var canvasAspect = 16 / 9;
    var ratio = (naturalWidth > 0 && naturalHeight > 0) ? (naturalHeight / naturalWidth) : (9 / 16);
    var height = width * canvasAspect * ratio;
    if (!isFiniteNumber(height) || height <= 0) {
      height = width;
    }
    var element = {
      id: nextElementId(draft, widgetIds, 'image'),
      type: 'image',
      visible: true,
      x: roundTo(0.5 - width / 2, 10000),
      y: roundTo(0.5 - height / 2, 10000),
      width: width,
      height: height,
      z_index: 0,
      opacity: 1,
      src: src,
      fit: 'contain'
    };
    withFillDefaults(element);
    return element;
  }

  /* --- History --------------------------------------------------------------
   *
   * A plain stack of draft clones, capped at 100 entries. A gesture, a
   * nudge, a restack, an add/duplicate/delete, a preset, a clamp, a reset,
   * and every committed control change push one entry; a live `input` event
   * updates the draft without pushing.
   */

  var HISTORY_LIMIT = 100;

  function createHistory(initialDraft) {
    return { stack: [clone(initialDraft)], index: 0 };
  }

  function pushHistory(history, draft) {
    var truncated = history.stack.slice(0, history.index + 1);
    truncated.push(clone(draft));
    if (truncated.length > HISTORY_LIMIT) {
      truncated = truncated.slice(truncated.length - HISTORY_LIMIT);
    }
    history.stack = truncated;
    history.index = history.stack.length - 1;
  }

  function canGoBack(history) {
    return history.index > 0;
  }

  function canGoForward(history) {
    return history.index < history.stack.length - 1;
  }

  function historyBack(history) {
    if (!canGoBack(history)) {
      return null;
    }
    history.index -= 1;
    return clone(history.stack[history.index]);
  }

  function historyForward(history) {
    if (!canGoForward(history)) {
      return null;
    }
    history.index += 1;
    return clone(history.stack[history.index]);
  }

  /* --- Selection ------------------------------------------------------------ */

  function createSelection() {
    return { ids: [], primary: null };
  }

  function isSelected(selection, id) {
    return selection.ids.indexOf(id) !== -1;
  }

  function selectOnly(selection, id) {
    selection.ids = id ? [id] : [];
    selection.primary = id || null;
  }

  function selectMany(selection, ids) {
    selection.ids = ids.slice();
    selection.primary = ids.length ? ids[ids.length - 1] : null;
  }

  function toggleMember(selection, id) {
    var at = selection.ids.indexOf(id);
    if (at === -1) {
      selection.ids.push(id);
    } else {
      selection.ids.splice(at, 1);
    }
    selection.primary = selection.ids.length ? id : null;
    if (at !== -1 && selection.ids.length && selection.primary === id) {
      selection.primary = selection.ids[selection.ids.length - 1];
    }
  }

  function clearSelection(selection) {
    selection.ids = [];
    selection.primary = null;
  }

  /* --- Group move (multi-select drag) ---------------------------------------
   *
   * The whole selection moves by one delta, clamped so that no member ever
   * leaves its own boundary (safe area for widgets/text, canvas for
   * image/box). The delta is narrowed once, using the most restrictive
   * member, then applied identically to every member.
   */

  function clampGroupDelta(draft, ids, dx, dy) {
    var lowDx = -Infinity, highDx = Infinity, lowDy = -Infinity, highDy = Infinity;
    for (var i = 0; i < ids.length; i += 1) {
      var item = getItem(draft, ids[i]);
      if (!item) {
        continue;
      }
      var bounds = boundsFor(draft, kindOf(draft, ids[i]), item);
      var itemLowDx = bounds.left - item.x;
      var itemHighDx = (bounds.right - item.width) - item.x;
      var itemLowDy = bounds.top - item.y;
      var itemHighDy = (bounds.bottom - item.height) - item.y;
      lowDx = maxNum(lowDx, itemLowDx);
      highDx = minNum(highDx, itemHighDx);
      lowDy = maxNum(lowDy, itemLowDy);
      highDy = minNum(highDy, itemHighDy);
    }
    return {
      dx: clampRange(dx, lowDx, highDx),
      dy: clampRange(dy, lowDy, highDy)
    };
  }

  LayoutEditor.State = {
    clone: clone,
    minNum: minNum,
    maxNum: maxNum,
    apart: apart,
    isFiniteNumber: isFiniteNumber,
    clampRange: clampRange,
    snapToGrid: snapToGrid,
    roundTo: roundTo,
    setGeometry: setGeometry,
    safeBounds: safeBounds,
    canvasBounds: canvasBounds,
    usesSafeArea: usesSafeArea,
    boundsFor: boundsFor,
    bleedBounds: bleedBounds,
    isBleedBox: isBleedBox,
    getWidget: getWidget,
    getElement: getElement,
    getElementIndex: getElementIndex,
    getItem: getItem,
    kindOf: kindOf,
    isElementId: isElementId,
    elementsForLayers: elementsForLayers,
    snapTargets: snapTargets,
    capture: capture,
    nextElementId: nextElementId,
    makeTextElement: makeTextElement,
    makeBoxElement: makeBoxElement,
    makeTickerElement: makeTickerElement,
    makeImageElement: makeImageElement,
    createHistory: createHistory,
    pushHistory: pushHistory,
    canGoBack: canGoBack,
    canGoForward: canGoForward,
    historyBack: historyBack,
    historyForward: historyForward,
    createSelection: createSelection,
    isSelected: isSelected,
    selectOnly: selectOnly,
    selectMany: selectMany,
    toggleMember: toggleMember,
    clearSelection: clearSelection,
    clampGroupDelta: clampGroupDelta
  };

  /* --- Icons ------------------------------------------------------------
   *
   * Inline SVG, 16px, stroke currentColor at 1.75px -- no icon fonts, no
   * emoji, nothing fetched. Each entry is the inner markup only; callers
   * wrap it in the outer <svg> tag with whatever aria attributes fit the
   * button that hosts it.
   */

  LayoutEditor.Icons = {
    text: '<path d="M3 4h10M8 4v9" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>',
    image: '<rect x="2.5" y="3" width="11" height="10" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.75"/><circle cx="6" cy="7" r="1.1" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M3.5 11.5l3-3 2.3 2.3 2-2 2.2 2.2" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>',
    box: '<rect x="2.5" y="2.5" width="11" height="11" rx="1.4" fill="none" stroke="currentColor" stroke-width="1.75"/>',
    ticker: '<rect x="1.5" y="5" width="13" height="6" rx="1" fill="none" stroke="currentColor" stroke-width="1.75"/><path d="M4 8h5M10.5 8h1.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>',
    field: '<circle cx="8" cy="8" r="5.2" fill="none" stroke="currentColor" stroke-width="1.75"/>',
    eye: '<path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8Z" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"/><circle cx="8" cy="8" r="2" fill="none" stroke="currentColor" stroke-width="1.75"/>',
    eyeOff: '<path d="M2 2l12 12M6.6 6.7A2 2 0 0 0 9.3 9.4M4 4.4C2.4 5.6 1.5 8 1.5 8S4 12.5 8 12.5c1.2 0 2.2-.3 3.1-.8M9.9 3.8c-.6-.2-1.2-.3-1.9-.3-4 0-6.5 4.5-6.5 4.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>',
    trash: '<path d="M3 4.5h10M6.3 4.5V3a1 1 0 0 1 1-1h1.4a1 1 0 0 1 1 1v1.5M6 7.3v4M10 7.3v4M4 4.5l.7 8.2a1 1 0 0 0 1 .9h4.6a1 1 0 0 0 1-.9l.7-8.2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    historyBack: '<path d="M4 8.5H12.5M4 8.5L7 5.5M4 8.5L7 11.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>',
    historyForward: '<path d="M12 8.5H3.5M12 8.5L9 5.5M12 8.5L9 11.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>',
    chevron: '<path d="M4.5 6l3.5 4 3.5-4" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>',
    zoomIn: '<circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10.3 10.3l3.2 3.2M7 5v4M5 7h4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    zoomOut: '<circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10.3 10.3l3.2 3.2M5 7h4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    layerFront: '<rect x="6" y="2" width="8" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.6"/><rect x="2" y="6" width="8" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    layerBack: '<rect x="2" y="2" width="8" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.6"/><rect x="6" y="6" width="8" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    layerUp: '<path d="M8 12V4M4.5 7.5L8 4l3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>',
    layerDown: '<path d="M8 4v8M4.5 8.5L8 12l3.5-3.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>',
    alignLeft: '<path d="M2.5 2v12M5 5h8M5 11h5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    alignCenterH: '<path d="M8 2v12M4.5 5.5h7M5.5 11.5h5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    alignRight: '<path d="M13.5 2v12M3 5h8M6 11h5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    alignTop: '<path d="M2 2.5h12M5 5v8M11 5v5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    alignMiddleV: '<path d="M2 8h12M5.5 4.5v7M11.5 5.5v5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    alignBottom: '<path d="M2 13.5h12M5 11V3M11 11V6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    distributeH: '<path d="M2.5 2v12M13.5 2v12M5.5 8h2M8.5 8h2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    distributeV: '<path d="M2 2.5h12M2 13.5h12M8 5.5v2M8 8.5v2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    plus: '<path d="M8 3v10M3 8h10" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>',
    close: '<path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>',
    board: '<rect x="2" y="3.5" width="12" height="9" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.75"/>'
  };

  function svgIcon(name, extraClass) {
    var body = LayoutEditor.Icons[name] || '';
    var cls = extraClass ? ' class="' + extraClass + '"' : '';
    return '<svg' + cls + ' viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">' + body + '</svg>';
  }

  LayoutEditor.svgIcon = svgIcon;
})(window);
