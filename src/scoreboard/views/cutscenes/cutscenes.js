/* Cutscenes -- the operator's small persistent trigger panel.
 *
 * This file holds no authoritative state and computes no football rule, no
 * countdown, and no duration. Python owns the whole program: the status line
 * and the badge on this window are copied verbatim from `cutscenes.playing`
 * in the operator view that the host pushes here ten times a second through
 * `window.applyView`. Since cutscenes v2 this window makes no decision at
 * all -- there is no home/away choice to make. A cutscene is always the
 * Tigers' (or, for a penalty, nobody's); the event id alone tells Python
 * which side it is for (`EVENT_TEAM` in presentation/cutscenes.py). Five
 * events since cutscenes v3: first_down, touchdown, turnover, penalty,
 * make_some_noise -- one button, one key, and one pack picker each.
 *
 * The bridge is the small `CutscenesBridge`: get_snapshot, state, trigger,
 * cancel, rescan, select_pack, open_folder. There is no `command` here and
 * no `CommandType` value: triggering and cancelling are host actions, exactly
 * like opening this window in the first place.
 */
(function () {
  'use strict';
  var api = null;
  var model = null; // the full operator view, pushed by applyView
  var stateData = null; // api.state(): events/packs/issues/folder

  var statusEl = document.getElementById('status');
  var cancelButton = document.getElementById('cancel');
  var noticeEl = document.getElementById('notice');
  var issuesEl = document.getElementById('issues');

  function notice(message) {
    noticeEl.textContent = message || '';
  }

  // Python computes `remaining_display`; this line only copies the two
  // strings it was handed. It never subtracts, formats, or ticks a clock.
  function renderStatus(cutscenes) {
    var playing = cutscenes && cutscenes.playing;
    if (playing) {
      statusEl.textContent = 'PLAYING: ' + String(playing.label || '').toUpperCase() +
        ' · ' + playing.remaining_display;
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

  function renderState(state) {
    if (!state) return;
    stateData = state;
    renderPackSelect('first_down');
    renderPackSelect('touchdown');
    renderPackSelect('turnover');
    renderPackSelect('penalty');
    renderPackSelect('make_some_noise');
    renderIssues(state.issues || []);
  }

  function trigger(event) {
    if (!api) return;
    Promise.resolve(api.trigger(event)).then(function (result) {
      notice(result && result.message);
    }).catch(function (error) { notice('Could not trigger: ' + error); });
  }

  function cancel() {
    if (!api) return;
    Promise.resolve(api.cancel()).then(function (result) {
      notice(result && result.message);
    }).catch(function (error) { notice('Could not cancel: ' + error); });
  }

  document.getElementById('trigger-first-down').addEventListener('click', function () {
    trigger('first_down');
  });
  document.getElementById('trigger-touchdown').addEventListener('click', function () {
    trigger('touchdown');
  });
  document.getElementById('trigger-turnover').addEventListener('click', function () {
    trigger('turnover');
  });
  document.getElementById('trigger-penalty').addEventListener('click', function () {
    trigger('penalty');
  });
  document.getElementById('trigger-make-some-noise').addEventListener('click', function () {
    trigger('make_some_noise');
  });
  cancelButton.addEventListener('click', cancel);

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

  // This window's own hotkeys: D / T / O / F / L / Shift+C, the same six the
  // operator window's `host` keyboard bindings use, ignored while focus is in
  // a select or input so typing a folder path, say, never fires a trigger.
  // Each key names an event and nothing else -- there is no team to choose.
  // `L` is "get Loud" (the crowd prompt); `O` is the turnover.
  document.addEventListener('keydown', function (event) {
    if (event.isComposing || event.altKey || event.ctrlKey || event.metaKey || event.repeat) return;
    var target = event.target;
    if (target && target.closest && target.closest('select, input, textarea, [contenteditable]')) return;
    var key = event.key.toLowerCase();
    if (key === 'd' && !event.shiftKey) { event.preventDefault(); trigger('first_down'); return; }
    if (key === 't' && !event.shiftKey) { event.preventDefault(); trigger('touchdown'); return; }
    if (key === 'o' && !event.shiftKey) { event.preventDefault(); trigger('turnover'); return; }
    if (key === 'f' && !event.shiftKey) { event.preventDefault(); trigger('penalty'); return; }
    if (key === 'l' && !event.shiftKey) { event.preventDefault(); trigger('make_some_noise'); return; }
    if (key === 'c' && event.shiftKey) { event.preventDefault(); cancel(); return; }
  });

  window.applyView = render;

  // pywebview dispatches `pywebviewready` on WINDOW, never on document (see
  // the Field Assistant's own history of this bug). Attach the same way
  // whether the API is already present or arrives later.
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
