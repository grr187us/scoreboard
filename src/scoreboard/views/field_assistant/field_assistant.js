/* Field Assistant is deliberately a draft UI. Python validates, calculates,
 * persists, and owns every football-rule result; this file only selects an
 * explicit final spot and asks the bridge for a preview or one composite
 * finalization. The only "calculations" performed here are presentation
 * mappings that the architecture explicitly allows: converting an absolute
 * 0..100 coordinate to a HOME/AWAY yard-line label, and mirroring on-screen
 * placement by `assistant.home_goal_side`. No football rule (down, distance,
 * possession, score) is ever derived in this file. */
(function () {
  'use strict';
  var api, model, baseRevision = null, draft = null, dragging = false;
  var draftAbsolute = 50, penaltyOption = 0, tryPoints = 0, scoreRecorded = false;

  var field = document.getElementById('field'), ball = document.getElementById('ball');
  var stale = document.getElementById('stale'), notice = document.getElementById('notice');
  var confirmButton = document.getElementById('confirm'), lineToGain = document.getElementById('line-to-gain');
  var kindSelect = document.getElementById('kind');

  for (var y = 0; y <= 50; y += 1) { var o = document.createElement('option'); o.value = String(y); o.textContent = String(y); document.getElementById('spot-yard').appendChild(o); }

  // ---- small presentation helpers -----------------------------------
  function text(id, value) { document.getElementById(id).textContent = value || ''; }
  function teamName(side) { return model && model.teams && model.teams[side] ? model.teams[side].name : String(side || '').toUpperCase(); }
  function fieldText(f) { if (!f) return 'Not set — use Start / re-sync series.'; return (f.possession ? teamName(f.possession) + ' ball · ' : '') + (f.down_distance_display || 'No down/distance') + ' · ' + (f.ball_on_display || 'ball spot unavailable'); }
  function ordinal(n) { return n === 1 ? '1st' : n === 2 ? '2nd' : n === 3 ? '3rd' : n + 'th'; }

  // Presentation-only label mapping (allowed): 0 is the HOME goal line, 100
  // is the AWAY goal line, midfield (50) reads as plain "50".
  function spotLabel(absolute) {
    absolute = Math.max(0, Math.min(100, Math.round(absolute)));
    if (absolute === 50) return '50';
    if (absolute < 50) return teamName('home') + ' ' + absolute;
    return teamName('away') + ' ' + (100 - absolute);
  }
  function labelToTeamYard(absolute) {
    return absolute <= 50 ? { team: 'home', yard_line: absolute } : { team: 'away', yard_line: 100 - absolute };
  }

  function homeGoalSide() { return (model && model.assistant && model.assistant.home_goal_side) || 'left'; }
  function isMirrored() { return homeGoalSide() === 'right'; }
  // Presentation-only mirroring (allowed): screen position = absolute unless
  // the drawing is mirrored this quarter, in which case screen = 100 - absolute.
  function absoluteToScreen(absolute) { return isMirrored() ? 100 - absolute : absolute; }
  function screenToAbsolute(screenPct) { return isMirrored() ? 100 - screenPct : screenPct; }

  function updateDraftReadout() { text('draft-spot', spotLabel(draftAbsolute)); }

  function setDraftAbsolute(value) {
    draftAbsolute = Math.max(0, Math.min(100, Math.round(value)));
    ball.style.left = absoluteToScreen(draftAbsolute) + '%';
    ball.dataset.absolute = String(draftAbsolute);
    field.setAttribute('aria-valuenow', String(draftAbsolute));
    field.setAttribute('aria-valuetext', spotLabel(draftAbsolute));
    var spot = labelToTeamYard(draftAbsolute);
    document.getElementById('spot-team').value = spot.team;
    document.getElementById('spot-yard').value = String(spot.yard_line);
    updateDraftReadout();
  }

  function pointerScreenPct(e) {
    var rect = field.getBoundingClientRect();
    return Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
  }

  // Nudges/arrow keys move the ball in the SCREEN direction the operator
  // sees; the absolute change flips sign when the drawing is mirrored.
  function nudgeScreen(deltaScreenYards) {
    var deltaAbsolute = isMirrored() ? -deltaScreenYards : deltaScreenYards;
    setDraftAbsolute(draftAbsolute + deltaAbsolute);
  }

  function updateLineToGain(absoluteValue) {
    if (absoluteValue === null || absoluteValue === undefined) { lineToGain.hidden = true; return; }
    lineToGain.hidden = false;
    lineToGain.style.left = absoluteToScreen(absoluteValue) + '%';
  }

  function updateEndzones(assistant) {
    var mirrored = assistant && assistant.home_goal_side === 'right';
    document.getElementById('endzone-left').innerHTML = (mirrored ? 'AWAY' : 'HOME') + '<br><span>GOAL</span>';
    document.getElementById('endzone-right').innerHTML = (mirrored ? 'HOME' : 'AWAY') + '<br><span>GOAL</span>';
  }

  function updateDirection(assistant, football) {
    var el = document.getElementById('direction');
    if (!assistant || assistant.first_quarter_home_direction === null || assistant.first_quarter_home_direction === undefined) {
      el.textContent = 'SET 1ST-QUARTER DIRECTION BELOW TO BEGIN';
      return;
    }
    var possession = football && football.possession;
    if (!possession) { el.textContent = 'NO OFFENSE SET — START OR RE-SYNC A SERIES'; return; }
    var ruleDirection = possession === 'home' ? 1 : -1;
    var screenDirection = assistant.home_goal_side === 'right' ? -ruleDirection : ruleDirection;
    var arrow = screenDirection > 0 ? '▶' : '◀';
    var sideLabel = possession === 'home' ? 'HOME' : 'AWAY';
    var opponentLabel = possession === 'home' ? 'AWAY' : 'HOME';
    el.textContent = sideLabel + ' ' + arrow + ' TOWARD ' + opponentLabel + ' GOAL';
  }

  function updateHomeDirectionControl(assistant) {
    var select = document.getElementById('home-direction');
    var note = document.getElementById('direction-established-note');
    var established = assistant && assistant.first_quarter_home_direction !== null && assistant.first_quarter_home_direction !== undefined;
    note.hidden = !established;
    if (established) select.value = String(assistant.first_quarter_home_direction);
  }

  // ---- per-kind control visibility -----------------------------------
  var KIND_GROUPS = {
    start_series: ['offense', 'direction', 'spot'],
    normal_play: ['spot'],
    incomplete_pass: [],
    penalty: ['penalty'],
    turnover: ['offense', 'spot'],
    touchdown: ['offense', 'score-recorded'],
    try: ['offense', 'try-points'],
    field_goal: ['offense', 'score-recorded'],
    safety: ['offense', 'score-recorded'],
    kickoff: ['offense', 'spot'],
  };
  var TEAM_LABELS = {
    start_series: 'Offense',
    turnover: 'New offense',
    kickoff: 'Receiving team',
    touchdown: 'Scoring team',
    try: 'Scoring team',
    field_goal: 'Scoring team',
    safety: 'Scoring team',
  };
  var ALL_GROUPS = document.querySelectorAll('[data-group]');

  function updateGroups(kind) {
    var visible = KIND_GROUPS[kind] || [];
    for (var i = 0; i < ALL_GROUPS.length; i += 1) {
      var el = ALL_GROUPS[i];
      el.hidden = visible.indexOf(el.getAttribute('data-group')) === -1;
    }
    text('team-label-text', TEAM_LABELS[kind] || 'Team');
  }

  // ---- proposed-status rendering (from preview fields, not just summary)
  function renderProposed(p, kind) {
    var parts = [];
    if (p.possession) parts.push(teamName(p.possession) + ' ball');
    if (p.down) parts.push(ordinal(p.down) + ' & ' + (p.distance === 0 ? 'Goal' : p.distance));
    if (p.ball_on) parts.push(teamName(p.ball_on.team) + ' ' + p.ball_on.yard_line);
    else if (/^((touchdown)|(try)|(field_goal)|(safety))$/.test(kind)) parts.push('Ordinary field status will clear');
    var scoreParts = [];
    if (p.score_delta) {
      if (p.score_delta.home) scoreParts.push('HOME +' + p.score_delta.home);
      if (p.score_delta.away) scoreParts.push('AWAY +' + p.score_delta.away);
    }
    var line = (p.summary ? p.summary : '') + (parts.length ? (p.summary ? ' — ' : '') + parts.join(' · ') : '');
    if (scoreParts.length) line += (line ? ' · ' : '') + 'SCORE: ' + scoreParts.join(', ');
    if (p.requires_explicit_turnover) line += (line ? ' · ' : '') + 'TURNOVER ON DOWNS PROPOSED — CONFIRM NEW OFFENSE';
    text('proposed-status', line || 'Preview ready.');
  }

  // ---- request assembly (raw operator choices only) -------------------
  // JavaScript never computes football rules. It only collects the
  // operator's explicit selections into the documented {kind, payload}
  // envelope; Python normalizes and calculates every result.
  function buildAction() {
    var kind = kindSelect.value;
    var team = document.getElementById('team').value;
    var spot = { team: document.getElementById('spot-team').value, yard_line: Number(document.getElementById('spot-yard').value) };
    var payload = { ball_on: spot, team: team };
    if (kind === 'start_series') {
      payload.offense = team;
      payload.first_quarter_home_direction = Number(document.getElementById('home-direction').value);
    } else if (kind === 'normal_play') {
      payload.final_absolute = draftAbsolute;
    } else if (kind === 'incomplete_pass') {
      payload = {};
    } else if (kind === 'penalty') {
      payload.option = penaltyOption;
      payload.resolution = document.getElementById('resolution').value;
      // The underlying finished play remains a raw draft. Python calculates
      // it first, then applies the selected offense-relative enforcement.
      payload.underlying_action = { kind: 'normal_play', payload: { final_absolute: draftAbsolute } };
      if (penaltyOption === 0) payload.enforced_absolute = draftAbsolute;
    } else if (kind === 'turnover') {
      payload.new_offense = team;
      payload.final_absolute = draftAbsolute;
    } else if (kind === 'touchdown' || kind === 'field_goal' || kind === 'safety') {
      payload.scoring_team = team;
      payload.resolution = scoreRecorded ? 'score_already_recorded' : '';
      payload.add_score = payload.resolution !== 'score_already_recorded';
    } else if (kind === 'try') {
      // The try gets its own 0/1/2 choice; it must never reuse the penalty
      // yardage option, which Python rejects as invalid try points.
      payload.scoring_team = team;
      payload.points = tryPoints;
    } else if (kind === 'kickoff') {
      payload.receiving_team = team;
      payload.final_absolute = draftAbsolute;
    }
    return { kind: kind, payload: payload };
  }

  // ---- snapshot rendering ---------------------------------------------
  function render(next) {
    if (!next) return;
    model = next;
    if (baseRevision === null) baseRevision = model.revision;
    text('revision', 'REV ' + model.revision);
    text('clocks', 'GAME ' + model.clocks.game.display + ' ' + model.clocks.game.status + ' · PLAY ' + (model.clocks.play.display || '—') + ' ' + model.clocks.play.status);
    var f = model.football || {};
    text('current-status', fieldText(f));
    text('current-spot', f.ball_on_display || '—');
    text('current-down', f.down_distance_display || '');
    var assistant = model.assistant || {};
    updateEndzones(assistant);
    updateDirection(assistant, f);
    updateLineToGain(assistant.line_to_gain);
    updateHomeDirectionControl(assistant);
    if (!dragging && !draft) {
      setDraftAbsolute(assistant.ball_absolute !== null && assistant.ball_absolute !== undefined ? assistant.ball_absolute : 50);
    } else {
      updateDraftReadout();
    }
    if (model.revision !== baseRevision) markStale();
  }

  function markStale() { stale.hidden = false; confirmButton.disabled = true; text('notice', 'Your draft is based on an older revision. Re-sync or discard it before confirming.'); }
  function clearDraft(message) {
    draft = null; baseRevision = model.revision; stale.hidden = true; confirmButton.disabled = true;
    text('proposed-status', 'Choose an action to preview.');
    var assistant = model.assistant || {};
    updateLineToGain(assistant.line_to_gain);
    if (message) text('notice', message);
  }

  function preview() {
    if (!api) return;
    if (model.revision !== baseRevision) { markStale(); return; }
    var request = buildAction();
    Promise.resolve(api.preview_field_action(request)).then(function (result) {
      if (result.view) render(result.view);
      if (!result.accepted) { text('notice', result.error ? result.error.message : 'Preview could not be calculated.'); confirmButton.disabled = true; return; }
      draft = request;
      var p = result.preview || {};
      renderProposed(p, request.kind);
      if (p.line_to_gain !== null && p.line_to_gain !== undefined) updateLineToGain(p.line_to_gain);
      confirmButton.textContent = /^((touchdown)|(try)|(field_goal)|(safety)|(kickoff))$/.test(request.kind) ? 'Confirm Transition' : 'Confirm Play';
      confirmButton.disabled = false;
      text('notice', p.follow_up || 'Preview is ready. Confirm sends one atomic field action.');
    }).catch(function (error) { text('notice', 'Preview failed: ' + error); });
  }

  function resync() {
    if (!api) return;
    Promise.resolve(api.get_snapshot()).then(function (next) { render(next); clearDraft('Re-synced from the current authoritative field status.'); }).catch(function (error) { text('notice', 'Could not re-sync: ' + error); });
  }

  // ---- input wiring -----------------------------------------------------
  field.addEventListener('pointerdown', function (e) { dragging = true; field.setPointerCapture(e.pointerId); setDraftAbsolute(screenToAbsolute(pointerScreenPct(e))); });
  field.addEventListener('pointermove', function (e) { if (dragging) setDraftAbsolute(screenToAbsolute(pointerScreenPct(e))); });
  field.addEventListener('pointerup', function (e) { dragging = false; try { field.releasePointerCapture(e.pointerId); } catch (_) {} });
  field.addEventListener('keydown', function (e) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    nudgeScreen(e.key === 'ArrowRight' ? 1 : -1);
  });

  document.getElementById('nudge-left-1').addEventListener('click', function () { nudgeScreen(-1); });
  document.getElementById('nudge-right-1').addEventListener('click', function () { nudgeScreen(1); });
  document.getElementById('nudge-left-5').addEventListener('click', function () { nudgeScreen(-5); });
  document.getElementById('nudge-right-5').addEventListener('click', function () { nudgeScreen(5); });

  function syncDraftFromSelects() {
    var team = document.getElementById('spot-team').value;
    var yard = Number(document.getElementById('spot-yard').value);
    setDraftAbsolute(team === 'home' ? yard : 100 - yard);
  }
  document.getElementById('spot-team').addEventListener('change', syncDraftFromSelects);
  document.getElementById('spot-yard').addEventListener('change', syncDraftFromSelects);

  var penaltyButtons = document.querySelectorAll('.penalty-yards');
  function selectPenaltyOption(value, description) {
    penaltyOption = value;
    for (var i = 0; i < penaltyButtons.length; i += 1) {
      var pressed = Number(penaltyButtons[i].getAttribute('data-yards')) === value;
      penaltyButtons[i].setAttribute('aria-pressed', pressed ? 'true' : 'false');
    }
    text('penalty-selected-label', 'Selected: ' + description + '.');
  }
  for (var pIndex = 0; pIndex < penaltyButtons.length; pIndex += 1) {
    (function (button) {
      button.addEventListener('click', function () {
        var yards = Number(button.getAttribute('data-yards'));
        selectPenaltyOption(yards, yards === 0 ? 'no shortcut — use ball spot' : (Math.abs(yards) + ' yards, ' + (yards > 0 ? 'benefits offense' : 'benefits defense')));
      });
    }(penaltyButtons[pIndex]));
  }

  var tryButtons = document.querySelectorAll('.try-points');
  function selectTryPoints(value, description) {
    tryPoints = value;
    for (var i = 0; i < tryButtons.length; i += 1) {
      var pressed = Number(tryButtons[i].getAttribute('data-points')) === value;
      tryButtons[i].setAttribute('aria-pressed', pressed ? 'true' : 'false');
    }
    text('try-selected-label', 'Selected: ' + description + '.');
  }
  for (var tIndex = 0; tIndex < tryButtons.length; tIndex += 1) {
    (function (button) {
      button.addEventListener('click', function () {
        var points = Number(button.getAttribute('data-points'));
        selectTryPoints(points, points === 0 ? 'no score' : '+' + points);
      });
    }(tryButtons[tIndex]));
  }

  document.getElementById('score-recorded').addEventListener('change', function (e) { scoreRecorded = e.target.checked; });

  kindSelect.addEventListener('change', function () { updateGroups(kindSelect.value); });

  document.getElementById('preview').addEventListener('click', preview);
  document.getElementById('resync').addEventListener('click', resync);
  document.getElementById('discard').addEventListener('click', function () { clearDraft('Draft discarded. The main operator controls remain available.'); });
  confirmButton.addEventListener('click', function () {
    if (!draft || confirmButton.disabled || model.revision !== baseRevision) { markStale(); return; }
    Promise.resolve(api.finalize_field_action(draft, baseRevision)).then(function (result) {
      if (result.view) render(result.view);
      if (!result.accepted) {
        text('notice', result.error ? result.error.message : 'Field action was not accepted.');
        if (result.error && result.error.code === 'STALE_REVISION') markStale();
        return;
      }
      baseRevision = result.view.revision;
      clearDraft('Field action committed as one complete update.');
    }).catch(function (error) { text('notice', 'Field action failed: ' + error); });
  });

  // Render usably even without a live bridge (e.g. opened directly in a
  // browser for a visual check): initialize the draft ball and the
  // per-kind control visibility so nothing throws before pywebview attaches.
  updateGroups(kindSelect.value);
  setDraftAbsolute(50);

  window.applyView = render;
  if (window.pywebview && window.pywebview.api) { api = window.pywebview.api; }
  document.addEventListener('pywebviewready', function () {
    api = window.pywebview.api;
    Promise.resolve(api.get_snapshot()).then(function (next) {
      render(next);
      var assistant = next.assistant || {};
      setDraftAbsolute(assistant.ball_absolute !== null && assistant.ball_absolute !== undefined ? assistant.ball_absolute : 50);
    });
  });
}());
