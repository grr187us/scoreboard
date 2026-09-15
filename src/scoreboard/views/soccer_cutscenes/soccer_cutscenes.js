/* Soccer Cutscenes -- the operator's small persistent trigger panel.
 *
 * Mirrors views/cutscenes/cutscenes.js (football; frozen) in shape: this
 * file holds no authoritative state and computes no soccer rule, no
 * countdown, and no duration. Python owns the whole program; the status
 * line and the badge on this window are copied verbatim from
 * `cutscenes.playing` in the operator view the host pushes here through
 * `window.applyView`.
 *
 * The one departure from football's version (spec section 7, owner choice
 * F): a GOAL is never nobody's, so there are two trigger buttons for the
 * one event -- GOAL HOME and GOAL AWAY -- each calling
 * `api.trigger('goal', team)`, and an "Play GOAL automatically" switch
 * (default on) that persists through `api.set_auto_trigger(event, enabled)`
 * so the operator's own GOAL press and the automatic trigger after an
 * accepted `add_goal` (agent B's SoccerBridge) both honour the same
 * preference.
 *
 * The bridge is SoccerCutscenesBridge: get_snapshot, state, trigger(event,
 * team), cancel, rescan, select_pack, set_auto_trigger, open_folder. There
 * is no `command` here and no `CommandType` value.
 */
(function () {
  'use strict';
  var api = null;
  var model = null; // the full operator view, pushed by applyView
  var stateData = null; // api.state(): events/packs/issues/folder/auto_trigger

  var statusEl = document.getElementById('status');
  var cancelButton = document.getElementById('cancel');
  var noticeEl = document.getElementById('notice');
  var issuesEl = document.getElementById('issues');
  var autoGoalCheckbox = document.getElementById('auto-goal');

  function notice(message) {
    noticeEl.textContent = message || '';
  }

  // Python computes `remaining_display`; this line only copies the two
  // strings it was handed. It never subtracts, formats, or ticks a clock.
  function renderStatus(cutscenes) {
    var playing = cutscenes && cutscenes.playing;
    if (playing) {
      var teamLabel = playing.team === 'away' ? 'AWAY' : 'HOME';
      statusEl.textContent = 'PLAYING: ' + String(playing.label || '').toUpperCase() +
        ' (' + teamLabel + ') · ' + playing.remaining_display;
      cancelButton.disabled = false;
    } else {
      statusEl.textContent = 'Ready';
      cancelButton.disabled = true;
    }
  }

  function render(view) {
    if (!view) return;
    model = view;
    renderStatus(model.cutscenes || {});
  }

  function renderPackSelect(event) {
    var select = document.querySelector('select[data-pack-for="' + event + '"]');
    if (!select || !stateData) return;
    var descriptor = (stateData.events || []).filter(function (item) { return item.id === event; })[0] || {};
    var packs = (stateData.packs || []).filter(function (pack) { return pack.event === event; });
    select.replaceChildren();
    packs.forEach(function (pack) {
      var option = document.createElement('option');
      option.value = pack.id;
      option.textContent = pack.name + (pack.builtin ? ' (built-in)' : '');
      select.appendChild(option);
    });
    if (descriptor.selected_pack_id) select.value = descriptor.selected_pack_id;
  }

  function renderIssues(issues) {
    issuesEl.replaceChildren();
    if (!issues || !issues.length) { issuesEl.hidden = true; return; }
    issuesEl.hidden = false;
    issues.forEach(function (issue) {
      var row = document.createElement('li');
      row.textContent = issue.message;
      issuesEl.appendChild(row);
    });
  }

  function renderAutoTrigger(autoTrigger) {
    var enabled = !autoTrigger || autoTrigger.goal !== false;
    autoGoalCheckbox.checked = enabled;
  }

  function renderState(state) {
    if (!state) return;
    stateData = state;
    renderPackSelect('goal');
    renderIssues(state.issues || []);
    renderAutoTrigger(state.auto_trigger || {});
  }

  function trigger(event, team) {
    if (!api) return;
    Promise.resolve(api.trigger(event, team)).then(function (result) {
      notice(result && result.message);
    }).catch(function (error) { notice('Could not trigger: ' + error); });
  }

  function cancel() {
    if (!api) return;
    Promise.resolve(api.cancel()).then(function (result) {
      notice(result && result.message);
    }).catch(function (error) { notice('Could not cancel: ' + error); });
  }

  document.getElementById('trigger-goal-home').addEventListener('click', function () {
    trigger('goal', 'home');
  });
  document.getElementById('trigger-goal-away').addEventListener('click', function () {
    trigger('goal', 'away');
  });
  cancelButton.addEventListener('click', cancel);

  autoGoalCheckbox.addEventListener('change', function () {
    if (!api) return;
    Promise.resolve(api.set_auto_trigger('goal', autoGoalCheckbox.checked)).then(function (result) {
      renderState(result); notice(result && result.message);
    }).catch(function (error) { notice('Could not save that setting: ' + error); });
  });

  document.getElementById('rescan').addEventListener('click', function () {
    if (!api) return;
    Promise.resolve(api.rescan()).then(function (result) {
      renderState(result); notice(result && result.message);
    }).catch(function (error) { notice('Rescan failed: ' + error); });
  });
  document.getElementById('open-folder').addEventListener('click', function () {
    if (!api) return;
    Promise.resolve(api.open_folder()).then(function (result) {
      notice(result && result.message);
    }).catch(function (error) { notice('Could not open the folder: ' + error); });
  });
  Array.prototype.forEach.call(document.querySelectorAll('select[data-pack-for]'), function (select) {
    select.addEventListener('change', function () {
      if (!api) return;
      var event = select.getAttribute('data-pack-for');
      Promise.resolve(api.select_pack(event, select.value)).then(function (result) {
        renderState(result); notice(result && result.message);
      }).catch(function (error) { notice('Could not select that pack: ' + error); });
    });
  });

  // This window's own hotkeys: 1/2 for GOAL HOME/AWAY (spec section 7 and
  // design_draft.md section 3, owner choice 5: numbers rather than a letter,
  // to avoid colliding with the operator window's stat-nudge letters), and
  // Shift+C to cancel, ignored while focus is in a select or input.
  document.addEventListener('keydown', function (event) {
    if (event.isComposing || event.altKey || event.ctrlKey || event.metaKey || event.repeat) return;
    var target = event.target;
    if (target && target.closest && target.closest('select, input, textarea, [contenteditable]')) return;
    if (event.key === '1' && !event.shiftKey) { event.preventDefault(); trigger('goal', 'home'); return; }
    if (event.key === '2' && !event.shiftKey) { event.preventDefault(); trigger('goal', 'away'); return; }
    if (event.key.toLowerCase() === 'c' && event.shiftKey) { event.preventDefault(); cancel(); return; }
  });

  window.applyView = render;

  // pywebview dispatches `pywebviewready` on WINDOW, never on document.
  function attachBridge() {
    api = window.pywebview.api;
    Promise.resolve(api.state()).then(renderState)
      .catch(function (error) { notice('Could not read cutscene packs: ' + error); });
    Promise.resolve(api.get_snapshot()).then(render)
      .catch(function (error) { notice('Could not read the scoreboard: ' + error); });
  }
  if (window.pywebview && window.pywebview.api) attachBridge();
  else window.addEventListener('pywebviewready', attachBridge);
}());
