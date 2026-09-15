/* Soccer Field Assistant (spec section 6). Deliberately small: unlike
 * football's field assistant, no football rule is calculated anywhere near
 * this file -- there is no field, no down, no distance. This page only
 * collects the operator's explicit big-button press (which stat, which card,
 * which shootout kick, who kicks first) and an optional player number, and
 * asks Python (`preview_assist`) what pressing CONFIRM will do. Python alone
 * decides the label and the resulting value; Python alone submits
 * (`finalize_assist`), tagged `source: "field-assistant"`, through the same
 * allow-list host/soccer_field_assistant.py enforces server-side. This page
 * has no path to change the score, run any clock, change the period, or
 * undo anything -- those controls simply do not exist here.
 *
 * Live sync (mirrors views/field_assistant/field_assistant.js exactly, spec
 * section 6 "Live sync"): every push from the scoreboard is adopted as the
 * new base revision; Confirm is never disabled by a change made elsewhere. A
 * refused STALE_REVISION shows a toast and one more Confirm finishes. */
(function () {
  'use strict';
  var api, model, baseRevision = null, draft = null;
  // The one action pressed and not yet confirmed, e.g.
  // {kind:'stat', team:'home', stat:'shots', step:1}. Null means nothing
  // pressed yet, and Confirm stays disabled.
  var selected = null;
  // Player number pad state: a string of typed digits, or null once cleared
  // by "NO #". Applied to the next card or shootout-kick action only; a
  // stat action never carries a player number.
  var playerNumberDigits = null;
  var lastRenderedRevision = null, conflictTimer = null, autoPreviewTimer = null;

  var confirmButton = document.getElementById('confirm');
  var conflict = document.getElementById('conflict'), notice = document.getElementById('notice');

  function text(id, value) { document.getElementById(id).textContent = value == null ? '' : value; }
  function teamName(side) { return model && model.teams && model.teams[side] ? model.teams[side].name : String(side || '').toUpperCase(); }
  function fillTeamNames() {
    var nodes = document.querySelectorAll('[data-team-name]');
    for (var i = 0; i < nodes.length; i += 1) nodes[i].textContent = teamName(nodes[i].getAttribute('data-team-name'));
  }

  function currentPlayerNumber() {
    if (!playerNumberDigits) return null;
    var value = Number(playerNumberDigits);
    return isNaN(value) ? null : Math.min(99, value);
  }

  function updatePlayerReadout() {
    text('player-number-readout', currentPlayerNumber() === null ? '—' : String(currentPlayerNumber()));
  }

  // ---- request assembly (raw operator choices only; Python maps and
  // validates every one of these through host/soccer_field_assistant.py's
  // allow-list -- see map_assist_action). --------------------------------
  function buildAction() {
    if (!selected) return null;
    if (selected.kind === 'stat') {
      return { kind: 'stat', team: selected.team, stat: selected.stat, step: 1 };
    }
    if (selected.kind === 'card') {
      return { kind: 'card', team: selected.team, card: selected.card, player_number: currentPlayerNumber() };
    }
    if (selected.kind === 'shootout_kick') {
      return { kind: 'shootout_kick', team: selected.team, made: selected.made, kicker_number: currentPlayerNumber() };
    }
    if (selected.kind === 'first_kicker') {
      return { kind: 'first_kicker', team: selected.team };
    }
    return null;
  }

  // ---- rendering ---------------------------------------------------------
  function shootoutActive() { return Boolean(model && model.period === 'SHOOTOUT'); }

  function dots(made, total) {
    var out = '';
    for (var i = 0; i < total; i += 1) out += i < made ? '● ' : '○ ';
    return out.trim();
  }

  function renderShootout() {
    var panel = document.getElementById('shootout-panel');
    var active = shootoutActive();
    panel.hidden = !active;
    if (!active) return;
    var s = (model.soccer && model.soccer.shootout) || {};
    var nextTeam = s.next_team || null;
    text('shootout-status', 'ROUND ' + (s.round != null ? s.round : '—') + ' · ' + (nextTeam ? teamName(nextTeam) + ' TO KICK' : '—'));
    text('shootout-dots-home', dots(s.home_made || 0, 5));
    text('shootout-dots-away', dots(s.away_made || 0, 5));
    var buttons = document.querySelectorAll('#shootout-panel [data-action="shootout_kick"]');
    for (var i = 0; i < buttons.length; i += 1) {
      var button = buttons[i];
      button.disabled = Boolean(nextTeam) && button.getAttribute('data-team') !== nextTeam;
    }
    document.getElementById('shootout-first-kicker').hidden = Boolean(s.first_kicker);
  }

  function renderScoreboardNow() {
    var s = model.soccer || {};
    var home = s.home || {}, away = s.away || {};
    var homeCards = (home.cards && home.cards.display) || '';
    var awayCards = (away.cards && away.cards.display) || '';
    var parts = [
      teamName('home') + ' ' + ((model.teams && model.teams.home && model.teams.home.score) || 0),
      '·',
      teamName('away') + ' ' + ((model.teams && model.teams.away && model.teams.away.score) || 0),
      '· Shots ' + (home.shots || 0) + '–' + (away.shots || 0),
      '· Saves ' + (home.saves || 0) + '–' + (away.saves || 0),
      '· Corners ' + (home.corners || 0) + '–' + (away.corners || 0),
      '· Fouls ' + (home.fouls || 0) + '–' + (away.fouls || 0),
    ];
    if (homeCards || awayCards) parts.push('· ' + homeCards + ' / ' + awayCards);
    text('scoreboard-now', 'Scoreboard now: ' + parts.join(' '));
  }

  function render(next) {
    if (!next) return;
    model = next;
    // Live sync: whatever the scoreboard shows now is the base for the next
    // confirm. Python still rejects a genuine race at finalize time.
    baseRevision = model.revision;
    var revisionChanged = lastRenderedRevision !== null && lastRenderedRevision !== model.revision;
    lastRenderedRevision = model.revision;
    text('revision', 'REV ' + model.revision);
    var clocks = model.clocks || {};
    var game = clocks.game || {};
    text('clocks', 'GAME ' + (game.display || '—') + ' ' + (game.status || '') + ' · ' + (model.period_display || model.period || '—'));
    fillTeamNames();
    renderShootout();
    renderScoreboardNow();
    // Something changed elsewhere while a press is pending: re-ask Python so
    // the Confirm label describes the new state. Confirm stays enabled with
    // its previous label until the answer arrives.
    if (revisionChanged && selected && api && autoPreviewTimer === null) preview();
  }

  // ---- preview / confirm --------------------------------------------------
  function scheduleAutoPreview() {
    draft = null;
    confirmButton.disabled = true;
    if (autoPreviewTimer !== null) clearTimeout(autoPreviewTimer);
    if (!selected) { confirmButton.textContent = 'CONFIRM'; return; }
    if (!api) return;
    autoPreviewTimer = setTimeout(function () { autoPreviewTimer = null; preview(); }, 150);
  }

  function preview() {
    if (!api || !model || !selected) return;
    var request = buildAction();
    var pressed = selected;
    Promise.resolve(api.preview_assist(request)).then(function (result) {
      // The press this answer describes may be gone (Cancel, a commit, or a
      // different button) by the time Python answers -- drop a late one.
      if (selected !== pressed) return;
      if (!result || !result.ok) {
        confirmButton.textContent = 'CONFIRM';
        confirmButton.disabled = true;
        text('notice', (result && result.error) || 'That cannot be done from here.');
        return;
      }
      draft = request;
      confirmButton.textContent = result.label;
      confirmButton.disabled = false;
      text('notice', '');
    }).catch(function (error) { text('notice', 'Preview failed: ' + error); });
  }

  function isStale(result) { return Boolean(result && result.error && result.error.code === 'STALE_REVISION'); }

  function showConflict() {
    conflict.hidden = false;
    if (conflictTimer !== null) clearTimeout(conflictTimer);
    conflictTimer = setTimeout(function () { conflictTimer = null; conflict.hidden = true; }, 5000);
  }

  function clearDraft(message) {
    draft = null; selected = null; confirmButton.disabled = true;
    if (autoPreviewTimer !== null) { clearTimeout(autoPreviewTimer); autoPreviewTimer = null; }
    confirmButton.textContent = 'CONFIRM';
    if (message !== undefined) text('notice', message);
  }

  function select(action) {
    selected = action;
    scheduleAutoPreview();
  }

  // ---- player number pad ---------------------------------------------
  document.querySelectorAll('.pad-key[data-digit]').forEach(function (button) {
    button.addEventListener('click', function () {
      var digit = button.getAttribute('data-digit');
      playerNumberDigits = ((playerNumberDigits || '') + digit).slice(-2);
      updatePlayerReadout();
      if (selected) scheduleAutoPreview();
    });
  });
  document.getElementById('pad-backspace').addEventListener('click', function () {
    if (playerNumberDigits) playerNumberDigits = playerNumberDigits.slice(0, -1) || null;
    updatePlayerReadout();
    if (selected) scheduleAutoPreview();
  });
  document.getElementById('pad-no-number').addEventListener('click', function () {
    playerNumberDigits = null;
    updatePlayerReadout();
    if (selected) scheduleAutoPreview();
  });

  // ---- big-button wiring ------------------------------------------------
  document.querySelectorAll('[data-action="stat"]').forEach(function (button) {
    button.addEventListener('click', function () {
      select({ kind: 'stat', team: button.getAttribute('data-team'), stat: button.getAttribute('data-stat') });
    });
  });
  document.querySelectorAll('[data-action="card"]').forEach(function (button) {
    button.addEventListener('click', function () {
      select({ kind: 'card', team: button.getAttribute('data-team'), card: button.getAttribute('data-card') });
    });
  });
  document.querySelectorAll('[data-action="shootout_kick"]').forEach(function (button) {
    button.addEventListener('click', function () {
      if (button.disabled) return;
      select({ kind: 'shootout_kick', team: button.getAttribute('data-team'), made: button.getAttribute('data-made') === 'true' });
    });
  });
  document.querySelectorAll('[data-action="first_kicker"]').forEach(function (button) {
    button.addEventListener('click', function () {
      select({ kind: 'first_kicker', team: button.getAttribute('data-team') });
    });
  });

  // ---- resync / cancel / confirm -----------------------------------------
  function resync() {
    if (!api) return;
    Promise.resolve(api.get_snapshot()).then(function (next) {
      render(next);
      clearDraft('Draft discarded. Reading the scoreboard again.');
    }).catch(function (error) { text('notice', 'Could not reload: ' + error); });
  }
  document.getElementById('resync').addEventListener('click', resync);
  document.getElementById('cancel').addEventListener('click', function () { clearDraft('Cancelled. Nothing was changed.'); });

  confirmButton.addEventListener('click', function () {
    if (!draft || confirmButton.disabled) return;
    var committed = draft;
    Promise.resolve(api.finalize_assist(committed, baseRevision)).then(function (result) {
      if (result && result.view) render(result.view);
      if (!result || !result.accepted) {
        text('notice', (result && result.error && result.error.message) || 'The scoreboard did not accept that.');
        if (isStale(result)) { showConflict(); preview(); }
        return;
      }
      playerNumberDigits = null;
      updatePlayerReadout();
      clearDraft('Done.');
    }).catch(function (error) { text('notice', 'Field assistant action failed: ' + error); });
  });

  updatePlayerReadout();

  window.applyView = render;

  // pywebview dispatches `pywebviewready` on WINDOW, never on document
  // (mirrors views/field_assistant/field_assistant.js exactly -- see that
  // file's comment for the bug this avoids).
  function attachBridge() {
    api = window.pywebview.api;
    Promise.resolve(api.get_snapshot()).then(function (next) {
      render(next);
    }).catch(function (error) { text('notice', 'Could not read the scoreboard: ' + error); });
  }
  if (window.pywebview && window.pywebview.api) attachBridge();
  else window.addEventListener('pywebviewready', attachBridge);
}());
