/* Presentation layout editor -- panels.
 *
 * Everything that is not the canvas: the layers rail, the inspector, the
 * library menu and its inline popovers, the presets gallery, and the status
 * bar's issues drawer. This file only ever reads `app.screenDoc()` / `app.state`
 * and writes DOM; property edits it makes are handed back to `app` (in
 * layout.js), which owns history and the bridge. `app.screenDoc()` is the
 * current screen's mini-document -- `app.draft` itself for the Game screen,
 * `app.draft.screens[app.screen]` for Pre-game/Halftime -- so every panel
 * below reads and edits whichever screen is on screen without knowing which
 * one that is.
 */

(function (global) {
  'use strict';

  var LayoutEditor = global.LayoutEditor;
  var S = LayoutEditor.State;
  var icon = LayoutEditor.svgIcon;

  function el(id) { return document.getElementById(id); }

  function percentText(value) {
    return String(Math.round(value * 1000) / 10);
  }

  function fromPercentInput(input) {
    return input.value === '' ? null : Number(input.value) / 100;
  }

  /* --- Layers rail --------------------------------------------------------- */

  function itemIcon(kind) {
    if (kind === 'text') return icon('text');
    if (kind === 'image') return icon('image');
    if (kind === 'box') return icon('box');
    if (kind === 'ticker') return icon('ticker');
    return icon('field');
  }

  /** Bring `host`'s children into line with the freshly built `fresh` nodes
   * while keeping every node whose tag has not changed, updating its
   * attributes and text in place. Why not `replaceChildren`: a mousedown on
   * a rail button blurs whichever inspector field the operator just typed
   * in, that field's native 'change' commits the draft, and the commit
   * re-renders this rail before the mouseup arrives. If the rebuild swapped
   * the button out, the browser would deliver the click to the old and new
   * targets' common ancestor (the row's parent), nothing would match
   * `[data-select-widget]`, and the first click after typing a value would
   * appear to do nothing. Morphing keeps the pressed node alive across the
   * commit, so the click lands where it was aimed. */
  function morphChildren(host, fresh) {
    var old = Array.prototype.slice.call(host.childNodes);
    var index;
    for (index = 0; index < fresh.length; index += 1) {
      if (index < old.length) {
        morphNode(old[index], fresh[index], host);
      } else {
        host.appendChild(fresh[index]);
      }
    }
    for (index = old.length - 1; index >= fresh.length; index -= 1) {
      host.removeChild(old[index]);
    }
  }

  function morphNode(oldNode, newNode, parent) {
    if (oldNode.nodeType !== newNode.nodeType || oldNode.nodeName !== newNode.nodeName) {
      parent.replaceChild(newNode, oldNode);
      return;
    }
    if (oldNode.nodeType === Node.TEXT_NODE) {
      if (oldNode.nodeValue !== newNode.nodeValue) {
        oldNode.nodeValue = newNode.nodeValue;
      }
      return;
    }
    if (oldNode.nodeType !== Node.ELEMENT_NODE) {
      return;
    }
    var attrIndex;
    for (attrIndex = oldNode.attributes.length - 1; attrIndex >= 0; attrIndex -= 1) {
      var staleName = oldNode.attributes[attrIndex].name;
      if (!newNode.hasAttribute(staleName)) {
        oldNode.removeAttribute(staleName);
      }
    }
    for (attrIndex = 0; attrIndex < newNode.attributes.length; attrIndex += 1) {
      var attribute = newNode.attributes[attrIndex];
      if (oldNode.getAttribute(attribute.name) !== attribute.value) {
        oldNode.setAttribute(attribute.name, attribute.value);
      }
    }
    morphChildren(oldNode, Array.prototype.slice.call(newNode.childNodes));
  }

  function buildRailRow(app, id, label, kind, visible, canDelete) {
    var row = document.createElement('div');
    row.className = 'rail-row';
    row.classList.toggle('is-current', S.isSelected(app.selection, id));
    row.classList.toggle('is-hidden', !visible);

    var select = document.createElement('button');
    select.type = 'button';
    select.className = 'rail-select';
    if (kind === 'widget') {
      select.setAttribute('data-select-widget', id);
    } else {
      select.setAttribute('data-select-element', id);
    }
    select.innerHTML = '<span class="rail-icon">' + itemIcon(kind) + '</span>'
      + '<span class="rail-label"></span>';
    select.querySelector('.rail-label').textContent = label + (visible ? '' : ' — hidden');
    row.appendChild(select);

    var eye = document.createElement('button');
    eye.type = 'button';
    eye.className = 'rail-eye';
    eye.setAttribute('data-toggle-visible', id);
    eye.setAttribute('aria-pressed', visible ? 'false' : 'true');
    eye.title = visible ? 'Hide' : 'Hidden — click to show';
    eye.setAttribute('aria-label', visible ? 'Hide' : 'Show (currently hidden)');
    eye.innerHTML = icon(visible ? 'eye' : 'eyeOff');
    row.appendChild(eye);

    if (canDelete) {
      var trash = document.createElement('button');
      trash.type = 'button';
      trash.className = 'rail-trash';
      trash.setAttribute('data-delete-element', id);
      trash.title = 'Delete';
      trash.setAttribute('aria-label', 'Delete');
      trash.innerHTML = icon('trash');
      row.appendChild(trash);
    }
    return row;
  }

  function elementLabel(element) {
    if (element.type === 'text') {
      var text = (element.text || '').trim();
      return text ? '“' + text + '”' : element.id;
    }
    if (element.type === 'ticker') {
      var lines = Object.prototype.toString.call(element.lines) === '[object Array]' ? element.lines : [];
      var first = typeof lines[0] === 'string' ? lines[0].trim() : '';
      return first ? 'Ticker “' + first + '”' : element.id;
    }
    return element.id;
  }

  /** Every free element type; the widget kind and the pseudo-kinds
   * ('board', 'multi', 'none') are not in it. */
  function isElementKind(kind) {
    return kind === 'text' || kind === 'image' || kind === 'box' || kind === 'ticker';
  }

  /** Kinds that carry the text style set (colour, face, size, tracking...). */
  function hasTextStyle(kind) {
    return kind === 'widget' || kind === 'text' || kind === 'ticker';
  }

  function renderLayers(app) {
    var boardRow = el('rail-board-row');
    boardRow.classList.toggle('is-current', app.selection.ids.length === 0 && app.boardSelected);

    var descriptor = app.screenDescriptor() || {};
    var doc = app.screenDoc();

    var groupsHost = el('rail-groups');
    var groupNodes = [];
    var groups = descriptor.widget_groups || [];
    groups.forEach(function (groupName) {
      var group = document.createElement('div');
      group.className = 'rail-group';
      var header = document.createElement('button');
      header.type = 'button';
      header.className = 'rail-group-header';
      header.setAttribute('data-group-toggle', groupName);
      header.setAttribute('aria-expanded', app.collapsedGroups[groupName] ? 'false' : 'true');
      header.innerHTML = '<span class="rail-chevron ' + (app.collapsedGroups[groupName] ? 'is-collapsed' : '') + '">'
        + icon('chevron') + '</span><span class="rail-group-title"></span>';
      header.querySelector('.rail-group-title').textContent = groupName;
      group.appendChild(header);

      var body = document.createElement('div');
      body.className = 'rail-group-body';
      body.hidden = Boolean(app.collapsedGroups[groupName]);
      var widgets = descriptor.widgets || [];
      widgets.forEach(function (widgetDescriptor) {
        if (widgetDescriptor.group !== groupName) {
          return;
        }
        var widget = (doc.widgets || {})[widgetDescriptor.id] || {};
        body.appendChild(buildRailRow(app, widgetDescriptor.id, widgetDescriptor.label, 'widget',
          Boolean(widget.visible), false));
      });
      group.appendChild(body);
      groupNodes.push(group);
    });
    morphChildren(groupsHost, groupNodes);

    var elementsBody = el('rail-elements-body');
    var elementRows = [];
    S.elementsForLayers(doc).forEach(function (element) {
      elementRows.push(buildRailRow(app, element.id, elementLabel(element), element.type,
        element.visible !== false, true));
    });
    morphChildren(elementsBody, elementRows);
    el('rail-elements-count').textContent = String((doc.elements || []).length);
  }

  /* --- Inspector ------------------------------------------------------------ */

  function selectionKind(app) {
    if (app.selection.ids.length === 0) {
      return app.boardSelected ? 'board' : 'none';
    }
    if (app.selection.ids.length > 1) {
      return 'multi';
    }
    return S.kindOf(app.screenDoc(), app.selection.ids[0]) || 'none';
  }

  function setHidden(id, hidden) {
    var node = el(id);
    if (node) {
      node.hidden = hidden;
    }
  }

  function populateSelectOnce(select, values, toOption) {
    if (select.childElementCount === values.length) {
      return;
    }
    select.replaceChildren();
    values.forEach(function (value) {
      var option = document.createElement('option');
      var pair = toOption(value);
      option.value = pair.value;
      option.textContent = pair.text;
      select.appendChild(option);
    });
  }

  function populateChoiceGroup(hostId, values, toLabel) {
    var host = el(hostId);
    if (host.childElementCount === values.length) {
      return;
    }
    host.replaceChildren();
    values.forEach(function (value) {
      var button = document.createElement('button');
      button.type = 'button';
      button.setAttribute('data-choice', value);
      button.setAttribute('data-choice-prop', host.getAttribute('data-prop'));
      button.textContent = toLabel ? toLabel(value) : value;
      host.appendChild(button);
    });
  }

  var WEIGHT_NAMES = { 400: 'Regular', 500: 'Medium', 600: 'Semibold', 700: 'Bold', 800: 'Extrabold', 900: 'Black' };

  function applyLimitsToInspector(limits) {
    var fontScaleInput = el('prop-font_scale');
    if (typeof limits.min_font_scale === 'number') {
      fontScaleInput.min = String(Math.round(limits.min_font_scale * 1000) / 10);
    }
    if (typeof limits.max_font_scale === 'number') {
      fontScaleInput.max = String(Math.round(limits.max_font_scale * 1000) / 10);
    }
    if (typeof limits.min_widget_width === 'number') {
      el('prop-width').min = String(Math.round(limits.min_widget_width * 1000) / 10);
    }
    if (typeof limits.min_widget_height === 'number') {
      el('prop-height').min = String(Math.round(limits.min_widget_height * 1000) / 10);
    }
    populateSelectOnce(el('prop-font_family'), limits.font_families || [], function (entry) {
      return { value: entry.id, text: entry.label };
    });
    populateSelectOnce(el('prop-font_weight'), limits.font_weights || [], function (weight) {
      return { value: String(weight), text: (WEIGHT_NAMES[weight] || '') + ' ' + weight };
    });
    populateSelectOnce(el('prop-fit'), limits.image_fits || ['contain', 'cover', 'fill'], function (value) {
      return { value: value, text: value };
    });
    populateSelectOnce(el('prop-cut_corners'), limits.cut_corner_sides || ['all', 'top', 'bottom', 'left', 'right'], function (value) {
      return { value: value, text: value === 'all' ? 'all corners' : value + ' corners' };
    });
    populateChoiceGroup('prop-text_align', limits.text_alignments || ['left', 'center', 'right']);
    populateChoiceGroup('prop-vertical_align', limits.vertical_alignments || ['top', 'middle', 'bottom']);
    populateChoiceGroup('prop-text_transform', limits.text_transforms || ['none', 'uppercase'], function (v) {
      return v === 'uppercase' ? 'AA' : 'Aa';
    });
    populateChoiceGroup('prop-text_effect', limits.text_effects || ['none', 'shadow', 'outline']);
    var textarea = el('prop-text');
    if (typeof limits.max_text_length === 'number') {
      textarea.maxLength = limits.max_text_length;
    }

    // Event-screens additions. Every list has a fallback equal to the schema
    // constant so the controls exist before Python starts reporting them.
    populateChoiceGroup('prop-orientation', limits.orientations || ORIENTATIONS_FALLBACK, function (value) {
      return ORIENTATION_LABELS[value] || value;
    });
    populateSelectOnce(el('prop-border_style'), limits.border_styles || BORDER_STYLES_FALLBACK, function (value) {
      return { value: value, text: value };
    });
    populateSelectOnce(el('prop-fill_kind'), ['none'].concat(limits.fill_kinds || FILL_KINDS_FALLBACK), function (value) {
      return { value: value, text: FILL_KIND_LABELS[value] || value };
    });
    populateSelectOnce(el('prop-animation_preset'), limits.animation_presets || ANIMATION_PRESETS_FALLBACK, function (value) {
      return { value: value, text: ANIMATION_LABELS[value] || value };
    });
    populateChoiceGroup('prop-mode', limits.ticker_modes || TICKER_MODES_FALLBACK, function (value) {
      return TICKER_MODE_LABELS[value] || value;
    });
    var assets = [{ id: '', label: 'Uploaded image' }].concat(limits.bundled_images || []);
    populateSelectOnce(el('prop-asset'), assets, function (entry) {
      return { value: entry.id, text: entry.label };
    });
    var rotate = el('prop-rotate_degrees');
    var maxRotate = typeof limits.max_rotate_degrees === 'number' ? limits.max_rotate_degrees : 180;
    rotate.min = String(-maxRotate);
    rotate.max = String(maxRotate);
    var seconds = el('prop-animation_seconds');
    if (typeof limits.max_animation_seconds === 'number') {
      seconds.max = String(limits.max_animation_seconds);
    }
    var linesArea = el('prop-lines');
    var maxLines = typeof limits.max_ticker_lines === 'number' ? limits.max_ticker_lines : 8;
    var maxLineLength = typeof limits.max_ticker_line_length === 'number' ? limits.max_ticker_line_length : 80;
    el('lines-note').textContent = 'Up to ' + maxLines + ' lines of ' + maxLineLength + ' characters, one per row.';
    linesArea.rows = maxLines < 4 ? maxLines : 4;
  }

  var ORIENTATIONS_FALLBACK = ['horizontal', 'vertical', 'vertical_flipped'];
  var ORIENTATION_LABELS = { horizontal: 'Across', vertical: 'Downward', vertical_flipped: 'Upward' };
  var BORDER_STYLES_FALLBACK = ['solid', 'dashed'];
  var FILL_KINDS_FALLBACK = ['linear', 'radial', 'stripes'];
  var FILL_KIND_LABELS = { none: 'Flat colour only', linear: 'Linear gradient', radial: 'Radial glow', stripes: 'Stripes' };
  var ANIMATION_PRESETS_FALLBACK = ['none', 'sweep', 'drift', 'scroll_x', 'marquee', 'blink_soft'];
  var ANIMATION_LABELS = {
    none: 'None', sweep: 'Light sweep', drift: 'Drift up and down', scroll_x: 'Scroll sideways',
    marquee: 'Marquee text', blink_soft: 'Soft blink'
  };
  var ANIMATION_MIN_FALLBACK = { sweep: 8, drift: 6, scroll_x: 10, marquee: 20, blink_soft: 1 };
  var TICKER_MODES_FALLBACK = ['scroll', 'rotate'];
  var TICKER_MODE_LABELS = { scroll: 'Scroll', rotate: 'Rotate lines' };
  var TICKER_SPEED_FALLBACK = { scroll: [20, 120], rotate: [3, 60] };

  /** The seconds an animation preset may not go under, from `state.limits`
   * with the schema's own table as the fallback. */
  function animationMinSeconds(limits, preset) {
    var table = (limits && limits.animation_min_seconds) || ANIMATION_MIN_FALLBACK;
    return typeof table[preset] === 'number' ? table[preset] : 1;
  }

  function animationMaxSeconds(limits) {
    return typeof limits.max_animation_seconds === 'number' ? limits.max_animation_seconds : 120;
  }

  /** `[low, high]` seconds for a ticker mode. */
  function tickerSpeedRange(limits, mode) {
    var table = (limits && limits.ticker_speed_range) || TICKER_SPEED_FALLBACK;
    var range = table[mode] || TICKER_SPEED_FALLBACK[mode] || [1, 120];
    return [Number(range[0]), Number(range[1])];
  }

  /** The bundled image entry (`{id, label, path}`) an `asset:<id>` src
   * names, or null. */
  function bundledImageFor(limits, src) {
    if (typeof src !== 'string' || src.indexOf('asset:') !== 0) {
      return null;
    }
    var key = src.slice('asset:'.length);
    var found = null;
    ((limits && limits.bundled_images) || []).forEach(function (entry) {
      if (entry && entry.id === key) {
        found = entry;
      }
    });
    return found || { id: key, label: key, path: null };
  }

  function setChoiceCurrent(hostId, value) {
    var host = el(hostId);
    Array.prototype.forEach.call(host.children, function (button) {
      button.classList.toggle('is-current', button.getAttribute('data-choice') === value);
    });
  }

  function setColorField(prefix, value) {
    var text = el(prefix);
    var swatch = el(prefix + '-swatch');
    var color = value || '#000000';
    text.value = value || '';
    swatch.value = color;
  }

  function renderInspector(app) {
    var kind = selectionKind(app);
    var title = el('inspector-title');

    setHidden('sec-position', kind === 'board' || kind === 'none');
    setHidden('sec-layer', kind === 'board' || kind === 'none' || kind === 'multi');
    setHidden('sec-text', !hasTextStyle(kind));
    setHidden('sec-fill', kind === 'board' || kind === 'none' || kind === 'multi');
    setHidden('sec-motion', kind !== 'widget' && kind !== 'text' && kind !== 'image' && kind !== 'box');
    setHidden('sec-ticker', kind !== 'ticker');
    setHidden('sec-image', kind !== 'image');
    setHidden('sec-actions', kind === 'board' || kind === 'none');
    setHidden('sec-board', kind !== 'board');
    setHidden('inspector-empty', kind !== 'none');

    setHidden('action-reset_widget', kind !== 'widget');
    setHidden('action-duplicate', !isElementKind(kind) && kind !== 'multi');
    setHidden('action-delete_element', !isElementKind(kind) && kind !== 'multi');

    setHidden('field-padding', !hasTextStyle(kind));
    setHidden('field-opacity', !isElementKind(kind) && kind !== 'multi');
    setHidden('field-text', kind !== 'text');
    setHidden('field-display_format', true);
    setHidden('field-fit_text', kind !== 'widget' && kind !== 'text');
    setHidden('field-orientation', kind !== 'widget' && kind !== 'text');
    setHidden('field-bleed', kind !== 'box');
    setHidden('field-fill-effect', kind !== 'box');
    setHidden('field-rotate', kind !== 'text' && kind !== 'image' && kind !== 'box');
    setHidden('align-distribute', kind !== 'multi');

    if (kind === 'board') {
      title.textContent = 'Board';
      renderBoardSection(app);
      return;
    }
    if (kind === 'none') {
      title.textContent = 'Nothing selected';
      return;
    }
    if (kind === 'multi') {
      title.textContent = app.selection.ids.length + ' items';
      renderMultiSection(app);
      return;
    }

    var id = app.selection.ids[0];
    var doc = app.screenDoc();
    var item = S.getItem(doc, id);
    if (!item) {
      title.textContent = 'Nothing selected';
      return;
    }
    var descriptor = null;
    var screenDescriptor = app.screenDescriptor() || {};
    (screenDescriptor.widgets || []).forEach(function (d) { if (d.id === id) descriptor = d; });
    title.textContent = descriptor ? descriptor.label : elementLabel(item);

    var formats = descriptor && descriptor.formats || [];
    if (kind === 'widget' && formats.length > 1) {
      setHidden('field-display_format', false);
      var formatSelect = el('prop-display_format');
      formatSelect.replaceChildren();
      formats.forEach(function (format) {
        var option = document.createElement('option');
        option.value = format.id;
        option.textContent = format.label;
        formatSelect.appendChild(option);
      });
      formatSelect.value = item.display_format || 'default';
    }

    applyLimitsToInspector(app.state.limits || {});

    app.suppress = true;
    try {
      el('prop-x').value = percentText(item.x);
      el('prop-y').value = percentText(item.y);
      el('prop-width').value = percentText(item.width);
      el('prop-height').value = percentText(item.height);
      el('prop-z_index').value = String(item.z_index);
      el('prop-visible').checked = Boolean(item.visible);
      el('prop-fit_text').checked = Boolean(item.fit_text);

      if (hasTextStyle(kind)) {
        setColorField('prop-color', item.color);
        el('prop-font_family').value = item.font_family || 'arial';
        el('prop-font_weight').value = String(item.font_weight);
        el('prop-font_scale').value = percentText(item.font_scale);
        el('prop-letter_spacing').value = String(item.letter_spacing);
        setChoiceCurrent('prop-text_transform', item.text_transform || 'none');
        setChoiceCurrent('prop-text_effect', item.text_effect || 'none');
        setChoiceCurrent('prop-text_align', item.text_align);
        setChoiceCurrent('prop-vertical_align', item.vertical_align);
        el('prop-padding').value = percentText(item.padding || 0);
        el('static-note').hidden = !(descriptor && descriptor.static_text);
        setChoiceCurrent('prop-orientation', item.orientation || 'horizontal');
      }
      if (kind === 'text') {
        el('prop-text').value = item.text || '';
      }
      if (kind === 'ticker') {
        renderTickerFields(app, item);
      } else {
        renderMotionFields(app, item);
      }
      if (kind !== 'widget' && kind !== 'board') {
        el('prop-opacity').value = percentText(typeof item.opacity === 'number' ? item.opacity : 1);
      }
      if (kind !== 'board') {
        el('prop-background-toggle').checked = Boolean(item.background);
        setColorField('prop-background', item.background);
        el('prop-background_opacity').value = percentText(
          typeof item.background_opacity === 'number' ? item.background_opacity : 1);
        setColorField('prop-border_color', item.border_color);
        el('prop-border_width').value = percentText(item.border_width || 0);
        el('prop-corner_radius').value = percentText(item.corner_radius || 0);
        el('prop-corner_cut').value = percentText(item.corner_cut || 0);
        el('prop-cut_corners').value = item.cut_corners || 'all';
        el('prop-border_style').value = item.border_style || 'solid';
        el('prop-rotate_degrees').value = String(typeof item.rotate_degrees === 'number' ? item.rotate_degrees : 0);
      }
      if (kind === 'box') {
        el('prop-bleed').checked = item.bleed === true;
        renderFillFields(item);
      }
      if (kind === 'image') {
        el('prop-fit').value = item.fit || 'contain';
        var bundled = bundledImageFor(app.state.limits || {}, item.src);
        el('prop-asset').value = bundled ? bundled.id : '';
        var thumb = el('prop-image-thumb');
        if (bundled) {
          if (bundled.path) {
            thumb.src = '../' + bundled.path;
          } else {
            thumb.removeAttribute('src');
          }
        } else if (item.src) {
          thumb.src = item.src;
        } else {
          thumb.removeAttribute('src');
        }
        el('prop-image-size').textContent = String(Math.round(item.width * 1000) / 10) + '% wide';
      }
    } finally {
      app.suppress = false;
    }
  }

  /** The gradient/stripes controls for a box: only the fields the chosen
   * kind uses are shown. Colour A/B are the first and last stops; anything
   * in between is preserved untouched by layout.js's composite write. */
  function renderFillFields(item) {
    var fill = item.fill && typeof item.fill === 'object' ? item.fill : null;
    var kindValue = fill && typeof fill.kind === 'string' ? fill.kind : 'none';
    el('prop-fill_kind').value = kindValue;
    var isGradient = kindValue === 'linear' || kindValue === 'radial';
    var isStripes = kindValue === 'stripes';
    setHidden('field-fill_angle', !(kindValue === 'linear' || isStripes));
    setHidden('field-fill_color_a', !(isGradient || isStripes));
    setHidden('field-fill_color_b', !isGradient);
    setHidden('field-fill_stripes', !isStripes);
    el('fill-color-a-label').textContent = isStripes ? 'Stripe colour' : 'Colour A';
    if (!fill) {
      return;
    }
    el('prop-fill_angle').value = String(typeof fill.angle === 'number' ? fill.angle : 0);
    if (isStripes) {
      setColorField('prop-fill_color_a', fill.color);
      el('prop-fill_opacity_a').value = percentText(typeof fill.opacity === 'number' ? fill.opacity : 1);
      el('prop-fill_on').value = percentText(typeof fill.on === 'number' ? fill.on : 0);
      el('prop-fill_off').value = percentText(typeof fill.off === 'number' ? fill.off : 0);
      return;
    }
    var stops = Object.prototype.toString.call(fill.stops) === '[object Array]' ? fill.stops : [];
    var first = stops[0] || {};
    var last = stops[stops.length - 1] || {};
    setColorField('prop-fill_color_a', first.color);
    el('prop-fill_opacity_a').value = percentText(typeof first.opacity === 'number' ? first.opacity : 1);
    setColorField('prop-fill_color_b', last.color);
    el('prop-fill_opacity_b').value = percentText(typeof last.opacity === 'number' ? last.opacity : 1);
  }

  function renderMotionFields(app, item) {
    var limits = app.state.limits || {};
    var animation = item.animation && typeof item.animation === 'object' ? item.animation : null;
    var preset = animation && typeof animation.preset === 'string' ? animation.preset : 'none';
    el('prop-animation_preset').value = preset;
    var seconds = el('prop-animation_seconds');
    var note = el('animation-note');
    if (preset === 'none') {
      setHidden('field-animation_seconds', true);
      note.textContent = 'Every animation pauses while Motion is off.';
      return;
    }
    setHidden('field-animation_seconds', false);
    var low = animationMinSeconds(limits, preset);
    seconds.min = String(low);
    seconds.value = String(typeof animation.duration_seconds === 'number' ? animation.duration_seconds : low);
    note.textContent = 'At least ' + low + ' s for this effect (the LED rules forbid fast flashing); at most '
      + animationMaxSeconds(limits) + ' s.';
  }

  function renderTickerFields(app, item) {
    var limits = app.state.limits || {};
    var lines = Object.prototype.toString.call(item.lines) === '[object Array]' ? item.lines : [];
    var linesArea = el('prop-lines');
    // Rewriting the textarea while the operator types would move the caret;
    // only refresh it when the draft's lines differ from what it shows.
    var shown = linesArea.value.split('\n').map(function (line) { return line.trim(); })
      .filter(function (line) { return line !== ''; });
    if (shown.join('\n') !== lines.join('\n')) {
      linesArea.value = lines.join('\n');
    }
    var mode = item.mode === 'rotate' ? 'rotate' : 'scroll';
    setChoiceCurrent('prop-mode', mode);
    var range = tickerSpeedRange(limits, mode);
    var speed = el('prop-speed_seconds');
    speed.min = String(range[0]);
    speed.max = String(range[1]);
    speed.value = String(typeof item.speed_seconds === 'number' ? item.speed_seconds : range[0]);
    el('speed-label').textContent = mode === 'rotate' ? 'Seconds per line' : 'Seconds per loop';
  }

  function renderMultiSection(app) {
    setHidden('distribute_h', app.selection.ids.length < 3);
    setHidden('distribute_v', app.selection.ids.length < 3);
  }

  function renderBoardSection(app) {
    var draft = app.screenDoc();
    app.suppress = true;
    try {
      var background = (draft.background && draft.background.color) || '#000000';
      setColorField('board-background_color', background);
      var area = draft.safe_area || {};
      el('board-safe_top').value = percentText(typeof area.top === 'number' ? area.top : 0.04);
      el('board-safe_right').value = percentText(typeof area.right === 'number' ? area.right : 0.04);
      el('board-safe_bottom').value = percentText(typeof area.bottom === 'number' ? area.bottom : 0.04);
      el('board-safe_left').value = percentText(typeof area.left === 'number' ? area.left : 0.04);
    } finally {
      app.suppress = false;
    }
    renderPresets(app);
  }

  function buildPresetCard(preset) {
    var card = document.createElement('div');
    card.className = 'preset-card';
    var name = document.createElement('h3');
    name.textContent = preset.name;
    var description = document.createElement('p');
    description.textContent = preset.description;
    var apply = document.createElement('button');
    apply.type = 'button';
    apply.setAttribute('data-apply-preset', preset.id);
    apply.textContent = 'Apply';
    card.appendChild(name);
    card.appendChild(description);
    card.appendChild(apply);
    return card;
  }

  /** The Game screen offers the four full-layout presets; Pre-game and
   * Halftime each offer their own screen_presets list from Python. Both
   * galleries (the toolbar menu and the inspector's Board section) always
   * show the current screen's set. */
  function currentPresets(app) {
    if (app.screen === 'game') {
      return (app.state && app.state.presets) || [];
    }
    var byScreen = (app.state && app.state.screen_presets) || {};
    return byScreen[app.screen] || [];
  }

  function renderPresets(app) {
    var presets = currentPresets(app);
    ['presets-gallery', 'presets-gallery-menu'].forEach(function (hostId) {
      var host = el(hostId);
      if (!host) {
        return;
      }
      host.replaceChildren();
      presets.forEach(function (preset) {
        host.appendChild(buildPresetCard(preset));
      });
    });
  }

  /* --- Library menu ---------------------------------------------------------- */

  function renderLibraryMenu(app) {
    el('active-layout-name').textContent = app.state.active || 'Default';
    el('dirty-dot').hidden = !app.dirty;
    var list = el('layout-menu-list');
    list.replaceChildren();
    (app.state.names || []).forEach(function (name) {
      var button = document.createElement('button');
      button.type = 'button';
      button.setAttribute('data-select-layout', name);
      button.setAttribute('role', 'menuitem');
      button.className = 'menu-item';
      button.classList.toggle('is-current', name === app.state.active);
      button.textContent = name;
      list.appendChild(button);
    });
    var isDefault = app.state.active === 'Default';
    var renameButton = el('menu-rename');
    var deleteButton = el('menu-delete');
    renameButton.disabled = isDefault;
    renameButton.title = isDefault ? 'The Default layout is always available' : 'Rename this layout';
    deleteButton.disabled = isDefault;
    deleteButton.title = isDefault ? 'The Default layout is always available' : 'Delete this layout';
    el('menu-discard').disabled = !app.dirty;
  }

  /* --- Screen switcher --------------------------------------------------------
   *
   * Built once from state.screens (Game / Pre-game / Halftime, in that
   * order) and re-marked on every render so its current tab always matches
   * app.screen. No screen id or label is ever written in the HTML: both
   * come from Python through state.screens.
   */

  function renderScreenSwitch(app) {
    var host = el('screen-switch');
    if (!host) {
      return;
    }
    var screens = (app.state && app.state.screens) || [];
    if (host.childElementCount !== screens.length) {
      host.replaceChildren();
      screens.forEach(function (descriptor, index) {
        var button = document.createElement('button');
        button.type = 'button';
        button.setAttribute('role', 'tab');
        button.setAttribute('data-screen', descriptor.id);
        button.title = descriptor.label + ' (Ctrl+' + (index + 1) + ')';
        button.textContent = descriptor.label;
        host.appendChild(button);
      });
    }
    Array.prototype.forEach.call(host.children, function (button) {
      var isCurrent = button.getAttribute('data-screen') === app.screen;
      button.setAttribute('aria-selected', isCurrent ? 'true' : 'false');
      button.classList.toggle('is-current', isCurrent);
    });
  }

  /* --- Issues / status bar ---------------------------------------------------- */

  function applyIssues(app, payload) {
    var issues = [];
    ['issues', 'errors', 'warnings'].forEach(function (key) {
      var list = payload && payload[key];
      if (Object.prototype.toString.call(list) === '[object Array]') {
        issues = issues.concat(list);
      }
    });
    var host = el('issue-list');
    host.replaceChildren();
    var errorCount = 0, warnCount = 0;
    issues.forEach(function (issue) {
      if (issue.severity === 'error') {
        errorCount += 1;
      } else {
        warnCount += 1;
      }
      var item = document.createElement('li');
      var button = document.createElement('button');
      button.type = 'button';
      button.className = issue.severity;
      if (issue.widget_id) {
        button.setAttribute('data-select-widget', issue.widget_id);
      }
      if (issue.screen) {
        // Names which screen this issue belongs to, so the click handler in
        // layout.js can switch there before selecting the item -- an issue
        // raised on Pre-game is otherwise unreachable while Game is showing.
        button.setAttribute('data-issue-screen', issue.screen);
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
    var summary = el('status-summary');
    if (errorCount === 0 && warnCount === 0) {
      summary.textContent = '✓ No problems';
      summary.className = 'status-summary is-ok';
    } else {
      var parts = [];
      if (errorCount) parts.push(errorCount + (errorCount === 1 ? ' error' : ' errors'));
      if (warnCount) parts.push(warnCount + (warnCount === 1 ? ' warning' : ' warnings'));
      summary.textContent = '⚠ ' + parts.join(' · ');
      summary.className = 'status-summary is-warn' + (errorCount ? ' is-error' : '');
    }
    el('save').disabled = errorCount > 0;
    el('save-as-open').disabled = errorCount > 0;
  }

  /* --- Popovers and menus ------------------------------------------------------ */

  var POPOVER_IDS = ['layout-menu-panel', 'presets-menu-panel', 'save-as-popover',
    'rename-layout-popover', 'duplicate-layout-popover', 'delete-layout-popover',
    'reset-layout-popover', 'replace-draft-popover', 'issues-drawer'];

  function closeAllPopovers() {
    POPOVER_IDS.forEach(function (id) {
      var node = el(id);
      if (node) {
        node.hidden = true;
      }
    });
    LayoutEditor.Canvas.closeContextMenu();
  }

  function togglePopover(id) {
    var node = el(id);
    var willOpen = node.hidden;
    closeAllPopovers();
    node.hidden = !willOpen;
    return !node.hidden;
  }

  LayoutEditor.Panels = {
    renderLayers: renderLayers,
    renderInspector: renderInspector,
    renderLibraryMenu: renderLibraryMenu,
    renderPresets: renderPresets,
    renderScreenSwitch: renderScreenSwitch,
    applyIssues: applyIssues,
    closeAllPopovers: closeAllPopovers,
    togglePopover: togglePopover,
    fromPercentInput: fromPercentInput,
    percentText: percentText,
    selectionKind: selectionKind,
    animationMinSeconds: animationMinSeconds,
    animationMaxSeconds: animationMaxSeconds,
    tickerSpeedRange: tickerSpeedRange,
    bundledImageFor: bundledImageFor
  };
})(window);
