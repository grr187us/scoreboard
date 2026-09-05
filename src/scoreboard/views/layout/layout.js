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
    } finally {
      suppress = false;
    }
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

  /* --- Editing ---------------------------------------------------------- */

  function changeProperty(prop, value) {
    var widget = currentWidget();
    if (!widget) {
      return;
    }
    widget[prop] = value;
    markDirty(true);
    renderPreview();
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
