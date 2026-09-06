/* Field Assistant is deliberately a draft UI. Python validates, calculates,
 * persists, and owns every football-rule result; this file only selects an
 * explicit final spot, collects which big button the operator pressed, and
 * asks the bridge for a preview or one composite finalization. The only
 * "calculations" performed here are presentation mappings that the
 * architecture explicitly allows: converting an absolute 0..100 coordinate to
 * a HOME/AWAY yard-line label, and mirroring on-screen placement by
 * `assistant.home_goal_side`. No football rule (down, distance, possession,
 * score) is ever derived in this file.
 *
 * The screen is built for a volunteer with five minutes of training. There
 * is exactly one visible panel at a time:
 *   direction  -- asked once per game: which end zone HOME scores in;
 *   start      -- nobody has the ball: press the team that does;
 *   play       -- click where the ball ended, press what happened;
 *   penalty / score / manual -- sub-panels reached from the buttons above.
 * Whatever is pressed is previewed by Python at once and the result becomes
 * the Confirm button's own label, so the operator reads what will happen
 * before it happens. */
(function () {
  'use strict';
  var api, model, baseRevision = null, draft = null, dragging = false;
  var draftAbsolute = 50, penaltyOption = 0, tryPoints = null, tryTeam = 'home', scoreRecorded = false;
  var manualTeam = 'home', manualDown = 1, manualDistance = 10;
  // The one action the operator has pressed and not yet confirmed, e.g.
  // {kind:'normal_play'} or {kind:'touchdown', team:'home'}. Null means
  // "nothing pressed yet" and Confirm stays disabled.
  var selected = null;
  // The sub-panel the operator opened, or null for the automatic top panel.
  var openPanel = null;
  // HOME's first-quarter direction chosen on this screen but not yet saved by
  // a confirmed series. Python persists it with the first committed action.
  var pendingDirection = null;
  // After a confirmed touchdown, the score panel opens on the try for the
  // scoring team so the next press is obvious.
  var lastCommittedTouchdownTeam = null;
  // The draft ball belongs to the operator while they are aiming it. It is
  // re-seeded from the authoritative spot ONLY when the window opens, when
  // Re-sync is pressed, and after a committed action -- never by the host's
  // 10 Hz refresh push, which used to drag the ball back to the persisted
  // spot (HOME 50 at the start of a game) between a click and the next
  // frame, so no nudge, drag, or yard selection could ever stick.
  var pendingReseed = true, lastMirrored = null, autoPreviewTimer = null;

  var field = document.getElementById('field'), ball = document.getElementById('ball');
  var stale = document.getElementById('stale'), notice = document.getElementById('notice');
  var confirmButton = document.getElementById('confirm'), lineToGain = document.getElementById('line-to-gain');

  // Yard numbers are placed at the same percentages as the painted lines, so
  // they stay on those lines at any width or font size.
  (function () {
    var labels = document.getElementById('yard-labels');
    for (var pct = 0; pct <= 100; pct += 10) {
      var span = document.createElement('span');
      span.style.left = pct + '%';
      span.textContent = String(pct <= 50 ? pct : 100 - pct);
      labels.appendChild(span);
    }
  }());
  for (var y = 0; y <= 50; y += 1) { var o = document.createElement('option'); o.value = String(y); o.textContent = String(y); document.getElementById('spot-yard').appendChild(o); }

  // ---- small presentation helpers -----------------------------------
  function text(id, value) { document.getElementById(id).textContent = value || ''; }
  function teamName(side) { return model && model.teams && model.teams[side] ? model.teams[side].name : String(side || '').toUpperCase(); }
  function otherTeam(side) { return side === 'home' ? 'away' : 'home'; }
  function fieldText(f) { if (!f) return 'Nobody has the ball.'; return (f.possession ? teamName(f.possession) + ' ball · ' : 'Nobody has the ball · ') + (f.down_distance_display || 'no down') + ' · at ' + (f.ball_on_display || '—'); }
  function ordinal(n) { return n === 1 ? '1st' : n === 2 ? '2nd' : n === 3 ? '3rd' : n + 'th'; }
  function setPressed(nodes, isPressed) {
    for (var i = 0; i < nodes.length; i += 1) nodes[i].setAttribute('aria-pressed', isPressed(nodes[i]) ? 'true' : 'false');
  }
  function fillTeamNames() {
    var nodes = document.querySelectorAll('[data-team-name]');
    for (var i = 0; i < nodes.length; i += 1) nodes[i].textContent = teamName(nodes[i].getAttribute('data-team-name'));
  }

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

  function establishedDirection() {
    var a = model && model.assistant;
    return a && a.first_quarter_home_direction !== null && a.first_quarter_home_direction !== undefined ? a.first_quarter_home_direction : null;
  }
  function effectiveDirection() { var d = establishedDirection(); return d !== null ? d : pendingDirection; }
  // Presentation-only mirroring (allowed). Python reports home_goal_side once
  // a direction is saved; before that, the operator's not-yet-saved choice
  // draws HOME's goal on the side they picked so the picture matches.
  function homeGoalSide() {
    var a = model && model.assistant;
    if (a && a.home_goal_side) return a.home_goal_side;
    if (pendingDirection !== null) return pendingDirection === 1 ? 'left' : 'right';
    return 'left';
  }
  function isMirrored() { return homeGoalSide() === 'right'; }
  function absoluteToScreen(absolute) { return isMirrored() ? 100 - absolute : absolute; }
  function screenToAbsolute(screenPct) { return isMirrored() ? 100 - screenPct : screenPct; }

  function updateDraftReadout() { text('draft-spot', spotLabel(draftAbsolute)); }

  // Draw the current draft ball. Kept separate from setDraftAbsolute so a
  // refresh that only mirrors the drawing can re-place the same spot on the
  // side the operator now sees, without changing the spot itself.
  function placeDraftBall() {
    ball.style.left = absoluteToScreen(draftAbsolute) + '%';
    ball.dataset.absolute = String(draftAbsolute);
    field.setAttribute('aria-valuenow', String(draftAbsolute));
    field.setAttribute('aria-valuetext', spotLabel(draftAbsolute));
  }

  function syncSelectsFromDraft() {
    var spot = labelToTeamYard(draftAbsolute);
    var teamSelect = document.getElementById('spot-team'), yardSelect = document.getElementById('spot-yard');
    // Write only on a real change: an open native <select> can collapse when
    // its value is reassigned, and these run on operator input.
    if (teamSelect.value !== spot.team) teamSelect.value = spot.team;
    if (yardSelect.value !== String(spot.yard_line)) yardSelect.value = String(spot.yard_line);
  }

  // `options.silent` moves the ball without asking for a new preview: used
  // while a drag is still in progress and when seeding from a snapshot.
  function setDraftAbsolute(value, options) {
    draftAbsolute = Math.max(0, Math.min(100, Math.round(value)));
    placeDraftBall();
    syncSelectsFromDraft();
    updateDraftReadout();
    if (!(options && options.silent)) scheduleAutoPreview();
  }

  // Auto-preview: any operator change re-asks Python for the proposed result
  // so the Confirm button always describes the ball actually on screen.
  // Confirm stays a separate, deliberate press, and is disabled the moment a
  // change makes the previously accepted draft no longer match the controls.
  function scheduleAutoPreview() {
    draft = null;
    confirmButton.disabled = true;
    if (autoPreviewTimer !== null) clearTimeout(autoPreviewTimer);
    if (!selected) { text('proposed-status', 'Press what happened.'); confirmButton.textContent = 'CONFIRM'; return; }
    if (!api) return;
    autoPreviewTimer = setTimeout(function () { autoPreviewTimer = null; preview(); }, 200);
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

  function updateEndzones() {
    var mirrored = isMirrored();
    document.getElementById('endzone-left').innerHTML = teamName(mirrored ? 'away' : 'home') + '<br><span>GOAL</span>';
    document.getElementById('endzone-right').innerHTML = teamName(mirrored ? 'home' : 'away') + '<br><span>GOAL</span>';
  }

  function updateDirection(football) {
    var el = document.getElementById('direction');
    var direction = effectiveDirection();
    if (direction === null) { el.textContent = 'STEP 1: PICK WHICH END ZONE ' + teamName('home') + ' SCORES IN (RIGHT PANEL)'; return; }
    var possession = football && football.possession;
    if (!possession) {
      // Before a series exists, show the picked direction for HOME so the
      // operator can sanity-check it against the real field.
      var homeScreen = isMirrored() ? -1 : 1;
      el.textContent = teamName('home') + ' ' + (homeScreen > 0 ? '▶' : '◀') + ' DRIVES THIS WAY' + (establishedDirection() === null ? ' (saved when you confirm the first series)' : '');
      return;
    }
    var ruleDirection = possession === 'home' ? 1 : -1;
    var screenDirection = isMirrored() ? -ruleDirection : ruleDirection;
    var arrow = screenDirection > 0 ? '▶' : '◀';
    el.textContent = teamName(possession) + ' ' + arrow + ' TOWARD ' + teamName(otherTeam(possession)) + ' GOAL';
  }

  // ---- panel visibility ---------------------------------------------------
  var PANELS = document.querySelectorAll('[data-panel]');
  function topPanel() {
    if (effectiveDirection() === null) return 'direction';
    var f = model && model.football;
    return f && f.possession ? 'play' : 'start';
  }
  function showPanel(name) {
    for (var i = 0; i < PANELS.length; i += 1) PANELS[i].hidden = PANELS[i].getAttribute('data-panel') !== name;
  }
  function updatePanels() {
    var f = (model && model.football) || {};
    var direction = effectiveDirection();
    // Sub-panels that need a live series fall back when the series is gone.
    if (openPanel === 'penalty' && !f.possession) openPanel = null;
    if (direction === null) openPanel = null;
    showPanel(openPanel || topPanel());
    setPressed(document.querySelectorAll('#home-direction button'), function (b) { return Number(b.getAttribute('data-direction')) === direction; });
    var turnover = document.getElementById('turnover-button');
    if (f.possession) turnover.firstChild.textContent = teamName(otherTeam(f.possession)) + ' BALL HERE';
    setPressed(document.querySelectorAll('[data-action]'), function (b) {
      if (!selected || b.getAttribute('data-action') !== selected.kind) return false;
      if (b.hasAttribute('data-team') && b.getAttribute('data-team') !== selected.team) return false;
      if (b.hasAttribute('data-points') && Number(b.getAttribute('data-points')) !== selected.points) return false;
      return true;
    });
    text('try-team-word', teamName(tryTeam));
    setPressed(document.querySelectorAll('.try-team-button'), function (b) { return b.getAttribute('data-try-team') === tryTeam; });
    setPressed(document.querySelectorAll('.manual-team'), function (b) { return b.getAttribute('data-manual-team') === manualTeam; });
    setPressed(document.querySelectorAll('.manual-down'), function (b) { return Number(b.getAttribute('data-down')) === manualDown; });
    setPressed(document.querySelectorAll('.manual-distance'), function (b) { return Number(b.getAttribute('data-distance')) === manualDistance; });
  }

  // ---- proposed-status rendering (from preview fields, not just summary)
  function renderProposed(p, kind) {
    var parts = [];
    if (p.possession) parts.push(teamName(p.possession) + ' ball');
    if (p.down) parts.push(ordinal(p.down) + ' & ' + (p.distance === 0 ? 'Goal' : p.distance));
    if (p.ball_on) parts.push('at ' + (p.ball_on.yard_line === 50 ? '50' : teamName(p.ball_on.team) + ' ' + p.ball_on.yard_line));
    else if (/^((touchdown)|(try)|(field_goal)|(safety))$/.test(kind)) parts.push('down & distance clear');
    var scoreParts = [];
    if (p.score_delta) {
      if (p.score_delta.home) scoreParts.push(teamName('home') + ' +' + p.score_delta.home);
      if (p.score_delta.away) scoreParts.push(teamName('away') + ' +' + p.score_delta.away);
    }
    var line = (p.summary ? p.summary : '') + (parts.length ? (p.summary ? ' — ' : '') + parts.join(' · ') : '');
    if (scoreParts.length) line += (line ? ' · ' : '') + 'SCORE ' + scoreParts.join(', ');
    return line || 'Ready.';
  }

  // ---- request assembly (raw operator choices only) -------------------
  // JavaScript never computes football rules. It only collects the
  // operator's explicit selections into the documented {kind, payload}
  // envelope; Python normalizes and calculates every result. The manual
  // panel's team/down/distance are copied straight from the buttons the
  // operator pressed; nothing here derives them.
  function buildAction() {
    var kind = selected.kind;
    var spot = { team: document.getElementById('spot-team').value, yard_line: Number(document.getElementById('spot-yard').value) };
    var payload = { ball_on: spot };
    if (kind === 'start_series') {
      payload.team = selected.team;
      payload.offense = selected.team;
      payload.first_quarter_home_direction = effectiveDirection();
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
      payload.team = selected.team;
      payload.new_offense = selected.team;
      payload.final_absolute = draftAbsolute;
    } else if (kind === 'touchdown' || kind === 'field_goal' || kind === 'safety') {
      payload.team = selected.team;
      payload.scoring_team = selected.team;
      payload.resolution = scoreRecorded ? 'score_already_recorded' : '';
      payload.add_score = payload.resolution !== 'score_already_recorded';
    } else if (kind === 'try') {
      // The try gets its own 0/1/2 choice; it must never reuse the penalty
      // yardage option, which Python rejects as invalid try points.
      payload.team = selected.team;
      payload.scoring_team = selected.team;
      payload.points = selected.points;
    } else if (kind === 'manual') {
      // Facts the operator pressed, copied verbatim; Python validates them
      // and derives only the line to gain.
      payload = { ball_on: spot, team: manualTeam, possession: manualTeam, down: manualDown, distance: manualDistance };
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
    fillTeamNames();
    text('current-status', fieldText(f));
    text('current-spot', f.ball_on_display || '—');
    text('current-down', f.down_distance_display || '');
    var assistant = model.assistant || {};
    if (establishedDirection() !== null) pendingDirection = null;
    updateEndzones();
    updateDirection(f);
    updateLineToGain(assistant.line_to_gain);
    if (pendingReseed) {
      pendingReseed = false;
      setDraftAbsolute(
        assistant.ball_absolute !== null && assistant.ball_absolute !== undefined ? assistant.ball_absolute : 50,
        { silent: true }
      );
    } else if (isMirrored() !== lastMirrored) {
      // A quarter boundary mirrored the drawing. Keep the operator's spot and
      // redraw it on the side they now see; never move the spot itself.
      placeDraftBall();
    }
    lastMirrored = isMirrored();
    updateDraftReadout();
    updatePanels();
    if (model.revision !== baseRevision) markStale();
  }

  function markStale() { stale.hidden = false; confirmButton.disabled = true; text('notice', 'The scoreboard changed while you were working. Press "Reload from scoreboard" and try again.'); }
  function clearDraft(message) {
    draft = null; selected = null; openPanel = null; tryPoints = null; baseRevision = model.revision; stale.hidden = true; confirmButton.disabled = true;
    if (autoPreviewTimer !== null) { clearTimeout(autoPreviewTimer); autoPreviewTimer = null; }
    confirmButton.textContent = 'CONFIRM';
    text('proposed-status', 'Press what happened.');
    var assistant = model.assistant || {};
    updateLineToGain(assistant.line_to_gain);
    updatePanels();
    if (message) text('notice', message);
  }

  function preview() {
    if (!api || !model || !selected) return;
    if (model.revision !== baseRevision) { markStale(); return; }
    var request = buildAction();
    Promise.resolve(api.preview_field_action(request)).then(function (result) {
      if (result.view) render(result.view);
      if (!result.accepted) {
        text('proposed-status', result.error ? result.error.message : 'That cannot be done from here.');
        confirmButton.textContent = 'CONFIRM';
        confirmButton.disabled = true;
        return;
      }
      var p = result.preview || {};
      var line = renderProposed(p, request.kind);
      if (p.requires_explicit_turnover) {
        // Python never flips possession on its own. Tell the volunteer which
        // button does it.
        draft = null;
        text('proposed-status', line + ' — 4th down failed. Press "' + teamName(otherTeam(p.possession || (model.football || {}).possession || 'home')) + ' BALL HERE" instead.');
        confirmButton.textContent = 'CONFIRM';
        confirmButton.disabled = true;
        return;
      }
      draft = request;
      text('proposed-status', line);
      if (p.line_to_gain !== null && p.line_to_gain !== undefined) updateLineToGain(p.line_to_gain);
      confirmButton.textContent = 'CONFIRM → ' + line;
      confirmButton.disabled = false;
      text('notice', p.follow_up || '');
    }).catch(function (error) { text('notice', 'Preview failed: ' + error); });
  }

  function resync() {
    if (!api) return;
    Promise.resolve(api.get_snapshot()).then(function (next) {
      pendingReseed = true;
      render(next);
      clearDraft('Reloaded from the scoreboard.');
    }).catch(function (error) { text('notice', 'Could not reload: ' + error); });
  }

  function select(action) {
    selected = action;
    updatePanels();
    scheduleAutoPreview();
  }

  // ---- input wiring -----------------------------------------------------
  field.addEventListener('pointerdown', function (e) { dragging = true; field.setPointerCapture(e.pointerId); setDraftAbsolute(screenToAbsolute(pointerScreenPct(e)), { silent: true }); });
  field.addEventListener('pointermove', function (e) { if (dragging) setDraftAbsolute(screenToAbsolute(pointerScreenPct(e)), { silent: true }); });
  field.addEventListener('pointerup', function (e) {
    dragging = false;
    try { field.releasePointerCapture(e.pointerId); } catch (_) {}
    // One preview for the whole drag, on the spot the operator let go on.
    setDraftAbsolute(draftAbsolute);
  });
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

  // One delegated click handler for every button in the right column.
  document.querySelector('.panels').addEventListener('click', function (e) {
    var button = e.target.closest('button');
    if (!button) return;
    if (button.hasAttribute('data-direction')) {
      if (establishedDirection() !== null) return; // saved for this game already
      pendingDirection = Number(button.getAttribute('data-direction'));
      lastMirrored = isMirrored();
      placeDraftBall();
      updateEndzones();
      updateDirection(model && model.football);
      updateLineToGain(model && model.assistant ? model.assistant.line_to_gain : null);
      updatePanels();
      text('notice', teamName('home') + ' drives toward the ' + (pendingDirection === 1 ? 'right' : 'left') + '. Now click where the ball is and press the team that has it.');
      return;
    }
    if (button.hasAttribute('data-open')) {
      openPanel = button.getAttribute('data-open');
      // The penalty panel previews its default "use the ball spot" enforcement
      // at once, so Confirm reads correctly before any yardage is pressed.
      selected = openPanel === 'penalty' ? { kind: 'penalty' } : null;
      updatePanels(); scheduleAutoPreview(); return;
    }
    if (button.hasAttribute('data-back')) { openPanel = null; selected = null; updatePanels(); scheduleAutoPreview(); return; }
    if (button.hasAttribute('data-try-team')) { tryTeam = button.getAttribute('data-try-team'); if (selected && selected.kind === 'try') selected.team = tryTeam; updatePanels(); scheduleAutoPreview(); return; }
    if (button.hasAttribute('data-manual-team')) { manualTeam = button.getAttribute('data-manual-team'); if (!selected || selected.kind !== 'manual') selected = { kind: 'manual' }; updatePanels(); scheduleAutoPreview(); return; }
    if (button.hasAttribute('data-down')) { manualDown = Number(button.getAttribute('data-down')); if (!selected || selected.kind !== 'manual') selected = { kind: 'manual' }; updatePanels(); scheduleAutoPreview(); return; }
    if (button.hasAttribute('data-distance')) { manualDistance = Number(button.getAttribute('data-distance')); document.getElementById('manual-distance-other').value = ''; if (!selected || selected.kind !== 'manual') selected = { kind: 'manual' }; updatePanels(); scheduleAutoPreview(); return; }
    if (button.classList.contains('penalty-yards')) {
      var yards = Number(button.getAttribute('data-yards'));
      penaltyOption = yards;
      setPressed(document.querySelectorAll('.penalty-yards'), function (b) { return Number(b.getAttribute('data-yards')) === yards; });
      text('penalty-selected-label', 'Selected: ' + (yards === 0 ? 'no yards — use the ball spot' : Math.abs(yards) + ' yards ' + (yards > 0 ? 'against the defense (offense gains)' : 'against the offense (offense loses)')) + '.');
      select({ kind: 'penalty' });
      return;
    }
    if (button.hasAttribute('data-action')) {
      var kind = button.getAttribute('data-action');
      var action = { kind: kind };
      if (kind === 'turnover') action.team = otherTeam((model && model.football && model.football.possession) || 'home');
      else if (button.hasAttribute('data-team')) action.team = button.getAttribute('data-team');
      if (kind === 'try') { action.team = tryTeam; action.points = Number(button.getAttribute('data-points')); tryPoints = action.points; }
      select(action);
    }
  });

  document.getElementById('manual-distance-other').addEventListener('input', function (e) {
    var value = Number(e.target.value);
    if (!e.target.value || isNaN(value)) return;
    manualDistance = Math.max(1, Math.min(99, Math.round(value)));
    if (!selected || selected.kind !== 'manual') selected = { kind: 'manual' };
    updatePanels();
    scheduleAutoPreview();
  });
  document.getElementById('resolution').addEventListener('change', function () { if (selected && selected.kind === 'penalty') scheduleAutoPreview(); });
  document.getElementById('score-recorded').addEventListener('change', function (e) { scoreRecorded = e.target.checked; scheduleAutoPreview(); });

  document.getElementById('resync').addEventListener('click', resync);
  document.getElementById('discard').addEventListener('click', function () { clearDraft('Cancelled. Nothing was changed.'); });
  confirmButton.addEventListener('click', function () {
    if (!draft || confirmButton.disabled || model.revision !== baseRevision) { markStale(); return; }
    var committed = draft;
    Promise.resolve(api.finalize_field_action(committed, baseRevision)).then(function (result) {
      // A committed action makes the authoritative spot the right next
      // starting point, so this is one of the three re-seed moments.
      if (result.accepted) pendingReseed = true;
      if (result.view) render(result.view);
      if (!result.accepted) {
        text('notice', result.error ? result.error.message : 'The scoreboard did not accept that.');
        if (result.error && result.error.code === 'STALE_REVISION') markStale();
        return;
      }
      baseRevision = result.view.revision;
      clearDraft('Done — the scoreboard now shows: ' + fieldText(model.football));
      if (committed.kind === 'touchdown') {
        // Lead straight into the try so the next press is obvious.
        lastCommittedTouchdownTeam = committed.payload.scoring_team;
        tryTeam = lastCommittedTouchdownTeam;
        openPanel = 'score';
        updatePanels();
        text('notice', 'Touchdown recorded. Now press the TRY / PAT result for ' + teamName(tryTeam) + ', or Back if the try is not happening.');
      }
    }).catch(function (error) { text('notice', 'Field action failed: ' + error); });
  });

  // Render usably even without a live bridge (e.g. opened directly in a
  // browser for a visual check): initialize the draft ball and the panel
  // visibility so nothing throws before pywebview attaches.
  setDraftAbsolute(50, { silent: true });
  showPanel('direction');

  window.applyView = render;

  // pywebview dispatches `pywebviewready` on WINDOW, never on document; a
  // document listener never fires, which left `api` null forever: every
  // preview silently bailed out and Confirm could never enable, while the
  // host's applyView pushes still made the page look alive. Attach exactly
  // the way shared/render.js does, and take the first snapshot either way.
  function attachBridge() {
    api = window.pywebview.api;
    Promise.resolve(api.get_snapshot()).then(function (next) {
      pendingReseed = true;
      render(next);
    }).catch(function (error) { text('notice', 'Could not read the field status: ' + error); });
  }
  if (window.pywebview && window.pywebview.api) attachBridge();
  else window.addEventListener('pywebviewready', attachBridge);
}());
