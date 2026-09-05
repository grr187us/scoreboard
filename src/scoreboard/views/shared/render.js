/* Shared rendering helpers for both windows.
 *
 * These helpers only ever *write* what Python sent. Nothing here computes a
 * score, a clock, a phase, or a revision: every displayed value arrives
 * already formatted in the view model, so the operator readout, the spectator
 * board, and the persisted checkpoint cannot disagree.
 */

(function (global) {
  'use strict';

  /** Replace an element's text, leaving it alone if the value is unchanged. */
  function setText(element, value) {
    if (!element) {
      return;
    }
    var text = value === null || value === undefined ? '' : String(value);
    if (element.textContent !== text) {
      element.textContent = text;
    }
  }

  /** Toggle a class without disturbing the rest of the class list. */
  function setFlag(element, name, on) {
    if (element) {
      element.classList.toggle(name, Boolean(on));
    }
  }

  function show(element, visible) {
    if (element) {
      element.hidden = !visible;
    }
  }

  /** Every element carrying `data-field="path.to.value"` in one pass. */
  function bindFields(root, model) {
    var nodes = root.querySelectorAll('[data-field]');
    for (var index = 0; index < nodes.length; index += 1) {
      var node = nodes[index];
      setText(node, read(model, node.getAttribute('data-field')));
    }
  }

  /** Read a dotted path out of the view model, tolerating missing branches. */
  function read(model, path) {
    var parts = String(path).split('.');
    var value = model;
    for (var index = 0; index < parts.length; index += 1) {
      if (value === null || value === undefined) {
        return null;
      }
      value = value[parts[index]];
    }
    return value === undefined ? null : value;
  }

  /**
   * Wait for the Python API to be attached.
   *
   * A view must never assume the bridge exists: if it is missing, the page
   * says so plainly instead of throwing and rendering nothing.
   */
  function whenReady(callback) {
    if (global.pywebview && global.pywebview.api) {
      callback(global.pywebview.api);
      return;
    }
    global.addEventListener('pywebviewready', function () {
      callback(global.pywebview.api);
    });
  }

  global.ScoreboardRender = {
    setText: setText,
    setFlag: setFlag,
    show: show,
    bindFields: bindFields,
    read: read,
    whenReady: whenReady
  };
})(window);
