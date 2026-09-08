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
    if (element.type === 'image') {
      return element.id;
    }
    return element.id;
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
    setHidden('sec-text', kind !== 'widget' && kind !== 'text');
    setHidden('sec-fill', kind === 'board' || kind === 'none' || kind === 'multi');
    setHidden('sec-image', kind !== 'image');
    setHidden('sec-actions', kind === 'board' || kind === 'none');
    setHidden('sec-board', kind !== 'board');
    setHidden('inspector-empty', kind !== 'none');

    setHidden('action-reset_widget', kind !== 'widget');
    setHidden('action-duplicate', kind !== 'text' && kind !== 'image' && kind !== 'box' && kind !== 'multi');
    setHidden('action-delete_element', kind !== 'text' && kind !== 'image' && kind !== 'box' && kind !== 'multi');

    setHidden('field-padding', kind !== 'widget' && kind !== 'text');
    setHidden('field-opacity', kind !== 'text' && kind !== 'image' && kind !== 'box' && kind !== 'multi');
    setHidden('field-text', kind !== 'text');
    setHidden('field-display_format', true);
    setHidden('field-fit_text', kind !== 'widget');
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

      if (kind === 'widget' || kind === 'text') {
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
      }
      if (kind === 'text') {
        el('prop-text').value = item.text || '';
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
      }
      if (kind === 'image') {
        el('prop-fit').value = item.fit || 'contain';
        var thumb = el('prop-image-thumb');
        if (item.src) {
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
    selectionKind: selectionKind
  };
})(window);
