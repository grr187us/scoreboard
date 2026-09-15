/* Soccer operator controls.
 *
 * Mirrors src/scoreboard/views/operator/operator.js's shape (spec section 4):
 * this file holds no authoritative state. It stores five kinds of ephemeral
 * view state -- which drawer is open, which command a confirmation dialog is
 * waiting on, the text an operator has typed but not applied, which team's
 * scoring is armed, and which team/kind of card entry is armed -- and it
 * renders whatever view model Python returns.
 *
 * It never computes a score, a clock value, a period, or a revision. Every
 * control routes through bridge.command(), and the expected revision comes
 * from the rendered view model, so a control that is showing stale values is
 * rejected with STALE_REVISION rather than applied to a board that moved on.
 */

(function () {
  'use strict';

  var R = window.ScoreboardRender;
  var api = null;
  var model = null;
  var pending = null; // the command a confirmation dialog is waiting on
  var dismissedPeriodToken = null;
  var dismissedMercy = false;
  var lastDisplayLabel = null;
  var armedTeam = null; // 'home' / 'away' / null -- which team's score-controls block is armed
  var armedMode = null; // 'goal' / 'card' / null
  var armedCardKind = null; // 'yellow' / 'red' / null, only when armedMode === 'card'
  var armTimer = null;
  var promptedForTeams = false;
  var buttonBoxWarned = null;

  var ARM_SECONDS = 8;

  var alertLine = document.getElementById('alert');
  var dialog = document.getElementById('confirm-dialog');
  var dialogTitle = document.getElementById('confirm-title');
  var dialogDetail = document.getElementById('confirm-detail');
  var dialogChange = document.getElementById('confirm-change');
  var teamsPayload = null;
  var rulesPayload = null;

  // Setup drawer fields, by SoccerRules name (spec section 8). A two-id entry
  // is a minutes:seconds pair; a one-id 'toggle' is a checkbox; a one-id
  // 'choice' is a select; anything else one-id is a plain number.
  var RULE_INPUTS = {
    half_seconds: {kind: 'clock', ids: ['rule-half-minutes', 'rule-half-seconds']},
    halftime_seconds: {kind: 'clock', ids: ['rule-halftime-minutes', 'rule-halftime-seconds']},
    warmup_seconds: {kind: 'clock', ids: ['rule-warmup-minutes', 'rule-warmup-seconds']},
    pregame_seconds: {kind: 'clock', ids: ['rule-pregame-minutes', 'rule-pregame-seconds']},
    overtime_periods: {kind: 'number', ids: ['rule-overtime-periods']},
    overtime_seconds: {kind: 'clock', ids: ['rule-overtime-minutes', 'rule-overtime-seconds']},
    golden_goal: {kind: 'toggle', ids: ['rule-golden-goal']},
    shootout_enabled: {kind: 'toggle', ids: ['rule-shootout-enabled']},
    shootout_initial_kickers: {kind: 'number', ids: ['rule-shootout-kickers']},
    shootout_credit_goal: {kind: 'toggle', ids: ['rule-shootout-credit-goal']},
    mercy_differential: {kind: 'number', ids: ['rule-mercy-differential']},
    mercy_applies: {kind: 'choice', ids: ['rule-mercy-applies']},
    stop_clock_on_goal: {kind: 'toggle', ids: ['rule-stop-clock-on-goal']},
    clock_direction: {kind: 'choice', ids: ['rule-clock-direction']},
    weather_seconds: {kind: 'clock', ids: ['rule-weather-minutes', 'rule-weather-seconds']}
  };

  /* --- Rendering -------------------------------------------------------- */

  function render(next) {
    if (!next) {
      return;
    }
    model = next;
    R.bindFields(document, model);
    refreshPeriodDialog();
    refreshMercyDialog();
    renderButtonBox(model.button_box);

    var game = model.clocks.game;
    R.setText(document.getElementById('chip-game'), 'GAME ' + game.display + ' ' + game.status);
    R.setText(document.getElementById('chip-revision'), 'Rev ' + model.revision);

    R.setFlag(document.getElementById('game-display'), 'running-game', game.running);
    R.setFlag(document.getElementById('game-state'), 'running-game', game.running);
    markState('game-start', game.running);
    markState('game-stop', !game.running);

    var gameReset = document.querySelector('[data-command="game_clock_reset"]');
    if (gameReset) gameReset.dataset.confirmDetail =
      'The clock returns to ' + (game.full_display || '') + ' and stays stopped.';

    renderRules(model.rules);
    renderHealth(model.health);
    renderCrowdStatus(model);
    renderLastAction(model);
    renderCutsceneBadge(model.cutscenes);
    renderPeriodChoices(model.period_labels, model.period);
    renderShootout(model);
    renderCorrectionsCards(model);

    var homeIdentity = model.teams.home ? model.teams.home.identity : null;
    var awayIdentity = model.teams.away ? model.teams.away.identity : null;
    renderIdentityNow('home', homeIdentity || null);
    renderIdentityNow('away', awayIdentity || null);
    renderIdentityStripe('home', homeIdentity || null);
    renderIdentityStripe('away', awayIdentity || null);
    renderSetup(model);
  }

  /* --- Teams not chosen yet ------------------------------------------------ */

  function renderSetup(current) {
    var setup = current.setup || {};
    R.show(document.getElementById('home-pending'), Boolean(setup.home_pending));
    R.show(document.getElementById('away-pending'), Boolean(setup.away_pending));

    var prompt = document.getElementById('teams-prompt');
    if (prompt) {
      R.setText(prompt, setup.detail || '');
      R.show(prompt, Boolean(setup.teams_pending));
    }
    var teamsButton = document.getElementById('open-teams');
    if (teamsButton) {
      R.setFlag(teamsButton, 'is-attention', Boolean(setup.teams_pending));
      teamsButton.title = setup.teams_pending ? 'Choose the teams before kickoff.' : '';
    }
  }

  function renderRules(rules) {
    if (!rules) {
      return;
    }
    var weatherButton = document.getElementById('crowd-weather');
    if (weatherButton && rules.weather_seconds) {
      weatherButton.dataset.seconds = String(rules.weather_seconds);
    }
  }

  /* --- Armed scoring / card entry (spec 4.2) ------------------------------- */

  function armScore(team) {
    disarmScore();
    armedTeam = team;
    armedMode = 'goal';
    armTimer = window.setTimeout(disarmScore, ARM_SECONDS * 1000);
    renderArmed();
  }

  function armCard(team, kind) {
    disarmScore();
    armedTeam = team;
    armedMode = 'card';
    armedCardKind = kind;
    armTimer = window.setTimeout(disarmScore, ARM_SECONDS * 1000);
    renderArmed();
  }

  function disarmScore() {
    if (armTimer !== null) {
      window.clearTimeout(armTimer);
      armTimer = null;
    }
    armedTeam = null;
    armedMode = null;
    armedCardKind = null;
    renderArmed();
  }

  function clearCardNumber(selector) {
    var field = document.querySelector(selector);
    if (field) field.value = '';
  }

  /**
   * Swap the three groups inside the fixed-height .score-controls block. They
   * are toggled with `hidden`, never style.display, and all three stay
   * inside the same block, so the panel's height never changes (U-001).
   */
  function renderArmed() {
    ['home', 'away'].forEach(function (side) {
      var armed = armedTeam === side;
      var mode = armed ? armedMode : null;
      var controls = document.getElementById(side + '-score-controls');
      if (controls) {
        controls.dataset.armed = mode || 'idle';
      }
      R.setFlag(document.getElementById(side + '-panel'), 'is-armed', armed);
      R.show(document.getElementById(side + '-idle'), !armed);
      R.show(document.getElementById(side + '-goal-armed'), mode === 'goal');
      R.show(document.getElementById(side + '-card-armed'), mode === 'card');

      var flag = document.getElementById(side + '-armed-flag');
      if (flag) {
        R.setText(flag, mode === 'goal' ? ' · SCORING' : mode === 'card' ? ' · CARD' : '');
        R.show(flag, Boolean(mode));
      }

      if (mode === 'card') {
        var heading = document.getElementById(side + '-card-heading');
        R.setText(heading, armedCardKind.toUpperCase() + ' #');
        R.show(document.getElementById(side + '-card-confirm-yellow'), armedCardKind === 'yellow');
        R.show(document.getElementById(side + '-card-confirm-red'), armedCardKind === 'red');
      }
    });
  }

  window.addEventListener('blur', disarmScore);

  /* --- SHOOTOUT panel (spec 4.3) ------------------------------------------- */

  function renderShootout(current) {
    var isShootout = current.period === 'SHOOTOUT';
    R.show(document.getElementById('clock-block'), !isShootout);
    R.show(document.getElementById('shootout-block'), isShootout);
    if (!isShootout) {
      return;
    }
    var shootout = (current.soccer && current.soccer.shootout) || {};
    var nextTeam = shootout.next_team;
    // `round` and `next_team` are raw fields (spec 3.3); the literal words
    // around them are static vocabulary, the same way the health chip
    // already builds 'GAME ' + display + ' ' + status from raw fields.
    R.setText(document.getElementById('shootout-round'),
      'ROUND ' + (shootout.round === undefined || shootout.round === null ? '' : shootout.round));
    R.setText(document.getElementById('shootout-next-team'),
      nextTeam ? '· ' + nextTeam.toUpperCase() + ' TO KICK' : '');
    ['home', 'away'].forEach(function (side) {
      var made = document.getElementById('shootout-' + side + '-made');
      var missed = document.getElementById('shootout-' + side + '-missed');
      var enabled = nextTeam === side;
      if (made) made.disabled = !enabled;
      if (missed) missed.disabled = !enabled;
    });
    var beforeFirstKick = !shootout.first_kicker;
    R.show(document.getElementById('shootout-first-kicker-row'), beforeFirstKick);
    // FINISH SHOOTOUT is enabled only once Python says the kicks are
    // decided (`decided`); the winner it sends is Python's `derived_winner`.
    // Python still refuses a stale press (SHOOTOUT_NOT_DECIDED).
    var finish = document.getElementById('finish-shootout');
    if (finish) {
      finish.disabled = !shootout.decided || shootout.winner !== null;
      finish.dataset.winner = shootout.derived_winner || '';
    }
  }

  function renderCorrectionsCards(current) {
    ['home', 'away'].forEach(function (side) {
      var host = document.getElementById(side + '-card-list');
      if (!host) return;
      host.replaceChildren();
      var cards = current.soccer && current.soccer[side] && current.soccer[side].cards;
      var rows = (cards && cards.rows) || [];
      if (!rows.length) {
        var empty = document.createElement('span');
        empty.className = 'hint';
        empty.textContent = 'No cards yet.';
        host.appendChild(empty);
        return;
      }
      rows.forEach(function (row) {
        var line = document.createElement('span');
        line.className = 'card-row';
        var text = document.createElement('span');
        text.textContent = row.kind.toUpperCase() + ' ' + row.display;
        line.appendChild(text);
        var remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = 'Remove…';
        remove.dataset.command = 'remove_card';
        remove.dataset.team = row.team;
        remove.dataset.index = String(row.index);
        remove.dataset.confirm = 'local';
        remove.dataset.confirmTitle = 'Remove this ' + row.kind + ' card?';
        line.appendChild(remove);
        host.appendChild(line);
      });
    });
    renderCorrectionsKicks(current);
  }

  function renderCorrectionsKicks(current) {
    var host = document.getElementById('kick-list');
    if (!host) return;
    host.replaceChildren();
    var shootout = current.soccer && current.soccer.shootout;
    var kicks = (shootout && shootout.kicks) || [];
    if (!kicks.length) {
      var empty = document.createElement('span');
      empty.className = 'hint';
      empty.textContent = 'No kicks yet.';
      host.appendChild(empty);
      return;
    }
    kicks.forEach(function (kick) {
      var line = document.createElement('span');
      line.className = 'card-row';
      var text = document.createElement('span');
      text.textContent = kick.display;
      line.appendChild(text);
      var correct = document.createElement('button');
      correct.type = 'button';
      correct.textContent = (kick.made ? 'Mark missed' : 'Mark made') + '…';
      correct.dataset.command = 'shootout_correct_kick';
      correct.dataset.index = String(kick.index);
      correct.dataset.made = kick.made ? 'false' : 'true';
      correct.dataset.confirm = 'local';
      correct.dataset.confirmTitle = 'Correct kick ' + (kick.index + 1) + '?';
      line.appendChild(correct);
      host.appendChild(line);
    });
  }

  /* --- Team identity -------------------------------------------------------- */

  function swatchGradient(identity) {
    return 'linear-gradient(to right, ' + identity.primary + ' 50%, ' + identity.secondary + ' 50%)';
  }

  function renderIdentityNow(side, identity) {
    var swatch = document.getElementById(side + '-identity-swatch');
    var shortLabel = document.getElementById(side + '-identity-short');
    if (swatch) {
      swatch.style.background = identity ? swatchGradient(identity) : '';
      R.show(swatch, Boolean(identity));
    }
    R.setText(shortLabel, identity ? identity.short_name : '');
  }

  function inkOn(hex) {
    var match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(String(hex || ''));
    if (!match) {
      return '#12161c';
    }
    var channels = match.slice(1).map(function (part) {
      var value = parseInt(part, 16) / 255;
      return value <= 0.03928 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
    });
    var luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    return (1.05 / (luminance + 0.05)) >= ((luminance + 0.05) / 0.058) ? '#ffffff' : '#12161c';
  }

  function renderIdentityStripe(side, identity) {
    var stripe = document.getElementById(side + '-identity-stripe');
    if (!stripe) {
      return;
    }
    if (identity) {
      stripe.style.background = identity.primary;
      stripe.style.borderBottomColor = identity.secondary;
      stripe.style.color = inkOn(identity.primary);
      R.setText(stripe, identity.short_name);
    } else {
      stripe.style.background = '';
      stripe.style.borderBottomColor = '';
      stripe.style.color = '';
      R.setText(stripe, '');
    }
    R.show(stripe, Boolean(identity));
  }

  function markState(id, isCurrent) {
    var button = document.getElementById(id);
    if (button) {
      button.classList.toggle('is-current', Boolean(isCurrent));
      button.classList.toggle('is-active', !isCurrent);
    }
  }

  function renderHealth(health) {
    var displayChip = document.getElementById('chip-display');
    var displayDrawer = document.getElementById('display-drawer');
    if (health.display.label !== lastDisplayLabel) {
      lastDisplayLabel = health.display.label;
      if (displayDrawer && !displayDrawer.hidden) {
        refreshDisplays();
      }
    }
    R.setText(displayChip, health.display.label);
    R.setFlag(displayChip, 'bad', !health.display.open);
    R.setFlag(displayChip, 'good', health.display.open);
    R.show(document.getElementById('reopen-display'), health.display.can_reopen);

    var drawerChip = document.getElementById('drawer-display-chip');
    R.setText(drawerChip, health.display.label);
    R.setFlag(drawerChip, 'bad', !health.display.open);
    R.setFlag(drawerChip, 'good', health.display.open);
    R.setText(document.getElementById('display-detail'),
      health.display.detail || (health.display.open ? health.display.target : '') || '');
    R.show(document.getElementById('drawer-reopen-display'), health.display.can_reopen);
    R.show(document.getElementById('close-display'), health.display.open);

    var saveChip = document.getElementById('chip-save');
    R.setText(saveChip, health.persistence.label);
    R.setFlag(saveChip, 'bad', !health.persistence.saved);
    R.setFlag(saveChip, 'good', health.persistence.saved);
    saveChip.title = health.persistence.message;

    if (!health.persistence.saved) {
      showAlert(health.persistence.message);
    }
  }

  function renderLastAction(current) {
    R.setText(document.getElementById('last-action'),
      current.last_action ? current.last_action.label : 'nothing yet');
    Array.prototype.forEach.call(document.querySelectorAll('[data-command="undo"]'),
      function (button) { button.disabled = !current.can_undo; });

    var depth = typeof current.undo_depth === 'number' ? current.undo_depth : 0;
    var badge = document.getElementById('undo-depth');
    if (badge) {
      R.setText(badge, '×' + depth);
      badge.hidden = depth < 2;
    }
    renderHistory(current.undo_history || []);
  }

  function renderHistory(entries) {
    var host = document.getElementById('history-list');
    if (!host) {
      return;
    }
    host.replaceChildren();
    if (!entries.length) {
      var empty = document.createElement('li');
      empty.className = 'empty';
      empty.textContent = 'Nothing to undo.';
      host.appendChild(empty);
      return;
    }
    entries.forEach(function (entry, index) {
      var row = document.createElement('li');
      row.textContent = entry.label;
      if (index === 0) {
        row.classList.add('next');
        var mark = document.createElement('span');
        mark.className = 'next-mark';
        mark.textContent = ' — next Undo';
        row.appendChild(mark);
      }
      host.appendChild(row);
    });
  }

  function renderCutsceneBadge(cutscenes) {
    var badge = document.getElementById('cutscene-badge');
    if (!badge) {
      return;
    }
    var playing = cutscenes && cutscenes.playing;
    if (playing) {
      R.setText(badge, 'CUTSCENE: ' + String(playing.label || '').toUpperCase() +
        ' ' + playing.remaining_display);
    }
    R.show(badge, Boolean(playing));
  }

  /**
   * The crowd-facing message row (spec 4.1). Only three words: INJURY,
   * DELAY, WEATHER. CLEAR appears only while raised; the countdown group
   * with green START / red STOP appears only while the raised message
   * carries a countdown (WEATHER), both to the right of the message
   * buttons so appearing never moves a button the operator is reaching for.
   */
  function renderCrowdStatus(current) {
    var status = current.status;
    if (!status) {
      return;
    }
    var chip = document.getElementById('crowd-status');
    R.setText(chip, status.display || '—');
    R.setFlag(chip, 'active', !!status.active);

    ['INJURY', 'DELAY', 'WEATHER'].forEach(function (label) {
      var button = document.getElementById('crowd-' + label.toLowerCase());
      if (button) {
        button.classList.toggle('is-active', status.label === label);
      }
    });

    var hasCountdown = status.label === 'WEATHER' || Boolean(status.clock_display);
    R.show(document.getElementById('crowd-clear'), !!status.active || hasCountdown);
    R.show(document.getElementById('crowd-countdown'), hasCountdown);

    var running = !!(status.clock && status.clock.running);
    R.setFlag(document.getElementById('crowd-clock'), 'running-status', running);
    markState('crowd-start', running);
    markState('crowd-stop', !running);
  }

  function renderPeriodChoices(labels, currentLabel) {
    ['period-choices', 'display-choices-noop'].forEach(function () {});
    var host = document.getElementById('period-choices');
    if (!host || !labels) {
      return;
    }
    if (host.childElementCount === labels.length) {
      updatePeriodChoice(host, currentLabel);
      return;
    }
    host.replaceChildren();
    labels.forEach(function (label) {
      var button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.setAttribute('data-command', 'set_period');
      button.setAttribute('data-label', label);
      host.appendChild(button);
    });
    updatePeriodChoice(host, currentLabel);
  }

  function updatePeriodChoice(host, currentLabel) {
    if (!host) {
      return;
    }
    Array.prototype.forEach.call(host.children, function (button) {
      button.classList.toggle('is-current', button.getAttribute('data-label') === currentLabel);
    });
  }

  function showAlert(message) {
    R.setText(alertLine, message);
    alertLine.hidden = false;
  }

  function clearAlert() {
    alertLine.hidden = true;
  }

  /* --- Building a request from a control ----------------------------------- */

  function argumentsFor(button) {
    var args = {};
    if (button.dataset.team) {
      args.team = button.dataset.team;
    }
    if (button.dataset.label) {
      args.label = button.dataset.label;
    }
    if (button.dataset.seconds) {
      args.seconds = Number(button.dataset.seconds);
    }
    if (button.dataset.stat) {
      args.stat = button.dataset.stat;
    }
    if (button.dataset.step) {
      args.step = Number(button.dataset.step);
    }
    if (button.dataset.kind) {
      args.kind = button.dataset.kind;
    }
    if (button.dataset.made !== undefined) {
      args.made = button.dataset.made === 'true';
    }
    if (button.dataset.index !== undefined) {
      args.index = Number(button.dataset.index);
    }
    if (button.dataset.winner) {
      args.winner = button.dataset.winner;
    }
    if (button.dataset.command === 'finish_shootout' && model && model.soccer && model.soccer.shootout) {
      // spec 3.2: finish_shootout's `winner` must equal the derived winner;
      // the view model carries it as `derived_winner` once `decided`.
      args.winner = model.soccer.shootout.derived_winner || null;
    }
    if (button.dataset.clearValue === 'true') {
      args.value = null;
    } else if (button.dataset.value !== undefined) {
      args.value = Number(button.dataset.value);
    }
    if (button.dataset.argMinutes && button.dataset.argSeconds) {
      var minutes = Number(fieldValue(button.dataset.argMinutes));
      var seconds = Number(fieldValue(button.dataset.argSeconds));
      args[button.dataset.argName] = minutes * 60 + seconds;
    } else if (button.dataset.argSource) {
      var raw = fieldValue(button.dataset.argSource);
      if (button.dataset.argName === 'name') {
        args.name = raw;
      } else if (button.dataset.argName === 'player' || button.dataset.argName === 'kicker') {
        args[button.dataset.argName] = raw === '' ? null : Number(raw);
      } else if (button.dataset.argRelative) {
        // Corrections drawer's quick +1/-1 on the score field (spec 4.4):
        // the field holds the base value the operator is about to Apply, and
        // the button only adds or subtracts the step visible on its face.
        var base = raw === '' ? (model && button.dataset.team ? model.teams[button.dataset.team].score : 0) : Number(raw);
        var next = base + Number(button.dataset.argRelative);
        args[button.dataset.argName] = next;
        var field = document.querySelector(button.dataset.argSource);
        if (field) field.value = String(next);
      } else {
        args[button.dataset.argName] = raw === '' ? null : Number(raw);
      }
    }
    if (button.dataset.name !== undefined) {
      args.name = button.dataset.name;
    }
    return args;
  }

  function fieldValue(selector) {
    var field = document.querySelector(selector);
    return field ? field.value : '';
  }

  function describeUndo() {
    return 'Reverses: ' + (model && model.last_action ? model.last_action.label : '');
  }

  function describeChange(button, args) {
    if (button.dataset.command === 'undo') {
      return describeUndo();
    }
    if (args.value !== undefined && button.dataset.team && button.dataset.command === 'set_score') {
      var team = button.dataset.team;
      return team.toUpperCase() + ' score ' + model.teams[team].score + ' → ' + args.value;
    }
    if (args.name !== undefined && button.dataset.team) {
      return model.teams[button.dataset.team].name + ' → ' + args.name;
    }
    if (args.seconds !== undefined) {
      return String(args.seconds) + ' seconds';
    }
    return '';
  }

  /* --- Submitting ------------------------------------------------------- */

  function submit(name, args, options) {
    options = options || {};
    args = Object.assign({}, args, {source: options.source || args.source || 'operator-mouse'});
    if (!api) {
      showAlert('The control bridge is not connected. Restart the application.');
      return;
    }
    var expected = model ? model.revision : null;
    if (options.expectedRevision !== undefined) expected = options.expectedRevision;
    Promise.resolve(api.command(name, args, expected)).then(function (result) {
      handleResult(name, args, result, options || {});
    }).catch(function (error) {
      showAlert('That control could not be sent: ' + error);
    });
  }

  function handleResult(name, args, result, options) {
    render(result.view);
    if (result.accepted) {
      clearAlert();
      if (typeof options.then === 'function') {
        options.then(result);
      }
      if (name === 'add_goal' && api && typeof api.trigger_cutscene === 'function') {
        // Spec section 7: the operator's confirmed GOAL press triggers the
        // cutscene immediately after acceptance, with the scoring side as an
        // explicit argument (soccer's departure from football's home-only
        // trigger). The view model carries no auto-play switch to gate this
        // on yet; Shift+C / the Cutscenes window's Cancel remain the way to
        // skip a playing cutscene.
        Promise.resolve(api.trigger_cutscene('goal', args.team)).catch(function () {});
      }
      if (name === 'new_game') {
        promptedForTeams = true;
        openDrawer('teams-drawer');
        refreshTeams();
      }
      return;
    }
    if (result.confirmation_required) {
      openDialog({
        title: options.title || 'Confirm this change',
        detail: result.confirmation ? result.confirmation.detail : (result.error ? result.error.message : ''),
        change: '',
        acceptLabel: result.confirmation ? result.confirmation.accept_label : null,
        command: name,
        args: args,
        source: options.source || args.source,
        expectedRevision: result.view.revision
      });
      return;
    }
    if (result.error) {
      showAlert(result.error.message);
    }
  }

  /* --- Button box hook ---------------------------------------------------- */

  function renderButtonBox(box) {
    var chip = document.getElementById('chip-button-box');
    if (!chip) return;
    if (!box) {
      R.setText(chip, 'BOX —');
      chip.classList.remove('bad');
      chip.hidden = true;
      return;
    }
    var failed = box.failed || [];
    var label = !box.active ? 'BOX OFF' : failed.length ? 'BOX PARTIAL' : 'BOX ON';
    R.setText(chip, label);
    var bad = Boolean(box.fallback) && box.error !== 'not started' && box.error !== 'stopped';
    chip.classList.toggle('bad', bad);
    chip.hidden = !bad;
    var warning = null;
    if (box.active && failed.length) {
      warning = 'Button box: ' + failed.join(', ') + ' could not be registered with Windows (another program owns ' +
        (failed.length === 1 ? 'it' : 'them') + '). ' + (failed.length === 1 ? 'That key works' : 'Those keys work') +
        ' only while this window is focused.';
    } else if (!box.active && box.error && box.error !== 'not started' && box.error !== 'stopped') {
      warning = 'Button box hook is off (' + box.error + '): the box works only while this window is focused.';
    }
    if (warning && warning !== buttonBoxWarned) {
      buttonBoxWarned = warning;
      showAlert(warning);
    }
  }

  /* --- Period decision dialog (spec 3.2) ----------------------------------- */

  var periodDialog = document.getElementById('period-dialog');
  var periodButtonsHost = document.getElementById('period-choices-buttons');

  function refreshPeriodDialog() {
    var decision = model && model.period_decision;
    var show = Boolean(decision && decision.pending && decision.token !== dismissedPeriodToken);
    if (show && periodDialog.hidden) {
      disarmScore();
      R.setText(document.getElementById('period-quarter'), decision.period);
      R.setText(document.getElementById('period-keep-quarter'), decision.period);
      buildPeriodChoiceButtons(decision.choices || []);
      periodDialog.hidden = false;
      document.getElementById('period-keep').focus();
    } else if (!show && !periodDialog.hidden) {
      periodDialog.hidden = true;
    }
  }

  /**
   * Each choice from `service.period_decision()` already carries its own
   * `command`/`args` (a "Keep" choice carries `command: null`, since the
   * static #period-keep button already sends nothing) -- the page picks no
   * wording and computes no target period, it only wires up what Python
   * already decided the options are.
   */
  function buildPeriodChoiceButtons(choices) {
    if (!periodButtonsHost) return;
    Array.prototype.slice.call(periodButtonsHost.querySelectorAll('button:not(#period-keep)'))
      .forEach(function (button) { button.remove(); });
    choices.forEach(function (choice) {
      if (!choice.command) {
        return; // "Keep" -- the static button already in the dialog
      }
      var button = document.createElement('button');
      button.type = 'button';
      button.textContent = choice.label;
      if (choice.label === 'Final') {
        button.className = 'danger';
      }
      button.addEventListener('click', function () {
        dismissPeriodDialog();
        submit(choice.command, Object.assign({}, choice.args), {title: choice.label});
      });
      periodButtonsHost.appendChild(button);
    });
  }

  function dismissPeriodDialog() {
    if (model && model.period_decision) dismissedPeriodToken = model.period_decision.token;
    periodDialog.hidden = true;
  }

  /* --- Mercy banner (spec 3.2) ---------------------------------------------- */

  var mercyDialog = document.getElementById('mercy-dialog');

  function refreshMercyDialog() {
    var reached = Boolean(model && model.mercy_reached);
    if (reached && !dismissedMercy && mercyDialog.hidden) {
      disarmScore();
      mercyDialog.hidden = false;
    } else if ((!reached || dismissedMercy) && !mercyDialog.hidden) {
      mercyDialog.hidden = true;
    }
    if (!reached) {
      dismissedMercy = false;
    }
  }

  /* --- Confirmation dialog --------------------------------------------- */

  function openDialog(request) {
    disarmScore();
    request.restoreFocus = document.activeElement;
    request.expectedRevision = request.expectedRevision === undefined ? model.revision : request.expectedRevision;
    pending = request;
    R.setText(dialogTitle, request.title);
    R.setText(dialogDetail, request.detail || '');
    R.setText(dialogChange, request.change || '');
    R.setText(document.getElementById('confirm-accept'), request.acceptLabel || 'Confirm');
    dialogChange.hidden = !request.change;
    dialog.hidden = false;
    document.getElementById('confirm-cancel').focus();
  }

  function closeDialog() {
    var focus = pending && pending.restoreFocus;
    pending = null;
    dialog.hidden = true;
    if (focus && focus.isConnected) focus.focus();
  }

  document.getElementById('confirm-cancel').addEventListener('click', function () {
    closeDialog();
  });

  document.getElementById('confirm-accept').addEventListener('click', function () {
    if (!pending) {
      return;
    }
    var request = pending;
    closeDialog();
    if (request.perform) {
      request.perform();
      return;
    }
    var args = Object.assign({}, request.args, {confirmed: true});
    submit(request.command, args, {title: request.title, source: request.source,
      expectedRevision: request.expectedRevision});
  });

  /* --- Control wiring --------------------------------------------------- */

  document.addEventListener('click', function (clickEvent) {
    var button = clickEvent.target.closest('button');
    if (!button) {
      return;
    }
    if (button.dataset.action) {
      handleAction(button.dataset.action, button);
      return;
    }
    if (button.dataset.displayKey) {
      Promise.resolve(api.select_display(button.dataset.displayKey))
        .then(function (payload) {
          renderDisplays(payload);
          if (payload && payload.status && !payload.status.open) {
            showAlert(payload.status.detail || 'That display could not be opened.');
          } else {
            clearAlert();
          }
        }).catch(function (error) {
          showAlert('That display could not be opened: ' + error);
        });
      return;
    }
    if (!button.dataset.command) {
      return;
    }
    var name = button.dataset.command;
    var args = argumentsFor(button);
    var source = clickEvent.detail === 0 ? 'operator-keyboard' : 'operator-mouse';

    if (name === 'add_goal' || name === 'add_card') {
      disarmScore();
    }

    if (button.dataset.confirm === 'local') {
      openDialog({
        title: button.dataset.confirmTitle || 'Confirm this change',
        detail: button.dataset.confirmDetail || '',
        change: describeChange(button, args),
        command: name,
        source: source,
        args: args
      });
      return;
    }
    submit(name, args, {title: button.dataset.confirmTitle, source: source});
  });

  /* --- Which display the board is on ------------------------------------ */

  function refreshDisplays() {
    if (!api || !api.displays) {
      return;
    }
    Promise.resolve(api.displays()).then(renderDisplays).catch(function (error) {
      R.setText(document.getElementById('display-summary'), 'could not be read: ' + error);
    });
  }

  function renderDisplays(payload) {
    if (!payload) {
      return;
    }
    if (payload.view) {
      render(payload.view);
    }
    R.setText(document.getElementById('display-summary'),
      payload.saved_label ? 'Saved: ' + payload.saved_label : 'No display saved yet.');
    var note = document.getElementById('display-note');
    if (note && payload.match) {
      note.textContent = payload.error ? payload.error : payload.match.message;
    }

    var host = document.getElementById('display-choices');
    if (!host) {
      return;
    }
    host.replaceChildren();
    (payload.displays || []).forEach(function (display) {
      var button = document.createElement('button');
      button.type = 'button';
      button.textContent = display.description + (display.key === payload.current_key ? ' — in use' : '');
      button.setAttribute('data-display-key', display.key);
      button.classList.toggle('is-current', display.key === payload.current_key);
      host.appendChild(button);
    });
    if (!host.childElementCount) {
      var empty = document.createElement('span');
      empty.textContent = 'Windows is reporting no display.';
      host.appendChild(empty);
    }
  }

  /* --- Saved teams -------------------------------------------------------- */

  function refreshTeams() {
    if (!api || !api.teams) {
      renderTeamsUnavailable();
      return;
    }
    Promise.resolve(api.teams()).then(function (payload) {
      teamsPayload = payload;
      renderTeams(payload);
    }).catch(function () {
      renderTeamsUnavailable();
    });
  }

  function renderTeamsUnavailable() {
    var host = document.getElementById('team-list');
    if (host) {
      host.replaceChildren();
      var note = document.createElement('span');
      note.className = 'hint';
      note.textContent = 'Saved teams are unavailable in this build.';
      host.appendChild(note);
    }
    setTeamFormDisabled(true);
  }

  function setTeamFormDisabled(disabled) {
    ['team-name-input', 'team-short-input', 'team-primary-input', 'team-secondary-input']
      .forEach(function (id) {
        var field = document.getElementById(id);
        if (field) {
          field.disabled = disabled;
        }
      });
    var saveButton = document.querySelector('#team-form [data-action="save_team"]');
    if (saveButton) {
      saveButton.disabled = disabled;
    }
  }

  function renderTeams(payload) {
    var host = document.getElementById('team-list');
    if (host) {
      host.replaceChildren();
      var teams = (payload && payload.teams) || [];
      if (!teams.length) {
        var empty = document.createElement('span');
        empty.className = 'hint';
        empty.textContent = 'No saved teams yet. Save the names below.';
        host.appendChild(empty);
      } else {
        teams.forEach(function (team) {
          host.appendChild(buildTeamRow(team));
        });
      }
    }
    setTeamFormDisabled(false);
    if (payload && payload.current) {
      renderIdentityNow('home', payload.current.home || null);
      renderIdentityNow('away', payload.current.away || null);
    }
  }

  function buildTeamRow(team) {
    var row = document.createElement('div');
    row.className = 'team-row';

    var swatch = document.createElement('span');
    swatch.className = 'swatch';
    swatch.style.background = swatchGradient(team);
    row.appendChild(swatch);

    var nameCell = document.createElement('span');
    nameCell.className = 'team-name-cell';
    nameCell.appendChild(document.createTextNode(team.name + ' '));
    var short = document.createElement('small');
    short.textContent = '(' + team.short_name + ')';
    nameCell.appendChild(short);
    row.appendChild(nameCell);

    ['home', 'away'].forEach(function (side) {
      var button = document.createElement('button');
      button.type = 'button';
      button.textContent = 'Use for ' + side.toUpperCase();
      button.setAttribute('data-command', 'set_team_name');
      button.setAttribute('data-team', side);
      button.setAttribute('data-name', team.name);
      button.setAttribute('data-confirm', 'local');
      button.setAttribute('data-confirm-title', 'Change the ' + side.toUpperCase() + ' team name?');
      row.appendChild(button);
    });

    var editButton = document.createElement('button');
    editButton.type = 'button';
    editButton.textContent = 'Edit';
    editButton.setAttribute('data-action', 'edit_team');
    editButton.setAttribute('data-name', team.name);
    row.appendChild(editButton);

    var deleteButton = document.createElement('button');
    deleteButton.type = 'button';
    deleteButton.textContent = 'Delete…';
    deleteButton.setAttribute('data-action', 'delete_team');
    deleteButton.setAttribute('data-name', team.name);
    row.appendChild(deleteButton);

    return row;
  }

  /* --- Where the game is saved ------------------------------------------ */

  function refreshDataFolder() {
    if (!api || !api.data_folder) {
      return;
    }
    Promise.resolve(api.data_folder()).then(function (location) {
      R.setText(document.getElementById('data-folder-path'), location.root);
      var note = document.getElementById('data-folder-note');
      if (note) {
        note.textContent = location.explanation +
          ' The game running now keeps saving where it is; a new folder is' +
          ' used the next time the scoreboard starts.';
      }
    }).catch(function (error) {
      R.setText(document.getElementById('data-folder-path'), 'could not be read: ' + error);
    });
  }

  function applyFolderChoice(result) {
    if (!result) {
      return;
    }
    showAlert(result.message);
    if (result.view) {
      render(result.view);
    }
    refreshDataFolder();
  }

  function handleAction(action, button) {
    if (action === 'period_keep') {
      dismissPeriodDialog();
      return;
    }
    if (action === 'mercy_keep') {
      dismissedMercy = true;
      mercyDialog.hidden = true;
      return;
    }
    if (action === 'mercy_end') {
      dismissedMercy = true;
      mercyDialog.hidden = true;
      openDrawer('game-drawer');
      return;
    }
    if (action === 'arm_score') {
      armScore(button && button.dataset.team);
      return;
    }
    if (action === 'arm_card') {
      armCard(button && button.dataset.team, button && button.dataset.kind);
      return;
    }
    if (action === 'disarm_score') {
      disarmScore();
      return;
    }
    if (action === 'clear_card_number') {
      clearCardNumber(button && button.dataset.target);
      return;
    }
    if (action === 'second_yellow_to_red') {
      // Corrections drawer only (spec 4.2): a shortcut that sends yellow
      // then red, never an automatic escalation on the board itself.
      var team = button && button.dataset.team;
      if (!team) return;
      submit('add_card', {team: team, kind: 'yellow'}, {
        then: function () { submit('add_card', {team: team, kind: 'red'}, {}); }
      });
      return;
    }
    if (action === 'close_display') {
      if (!api || typeof api.close_display !== 'function') {
        showAlert('This build cannot close the display window from here.');
        return;
      }
      Promise.resolve(api.close_display()).then(function (payload) {
        renderDisplays(payload);
        if (payload && payload.status) {
          showAlert(payload.status.detail || '');
        }
      }).catch(function (error) {
        showAlert('The display could not be closed: ' + error);
      });
      return;
    }
    if (action === 'edit_team') {
      var editName = button && button.dataset.name;
      var editTeam = teamsPayload && teamsPayload.teams &&
        teamsPayload.teams.find(function (team) { return team.name === editName; });
      if (editTeam) {
        document.getElementById('team-name-input').value = editTeam.name;
        document.getElementById('team-short-input').value = editTeam.short_name;
        document.getElementById('team-primary-input').value = editTeam.primary;
        document.getElementById('team-secondary-input').value = editTeam.secondary;
      }
      return;
    }
    if (action === 'delete_team') {
      var deleteName = button && button.dataset.name;
      if (!deleteName) {
        return;
      }
      openDialog({
        title: 'Delete team ' + deleteName + '?',
        detail: 'This removes it from the saved list. It does not change the board.',
        perform: function () {
          if (!api || !api.delete_team) {
            showAlert('Saved teams are unavailable in this build.');
            return;
          }
          Promise.resolve(api.delete_team(deleteName)).then(function (result) {
            teamsPayload = result;
            renderTeams(result);
            showAlert(result.message);
          }).catch(function (error) {
            showAlert('That team could not be deleted: ' + error);
          });
        }
      });
      return;
    }
    if (action === 'prefill_team') {
      var side = button && button.dataset.team;
      if (side && model && model.teams && model.teams[side]) {
        document.getElementById('team-name-input').value = model.teams[side].name;
      }
      return;
    }
    if (action === 'save_team') {
      if (!api || !api.save_team) {
        showAlert('Saved teams are unavailable in this build.');
        return;
      }
      var payload = {
        name: fieldValue('#team-name-input'),
        short_name: fieldValue('#team-short-input'),
        primary: fieldValue('#team-primary-input'),
        secondary: fieldValue('#team-secondary-input')
      };
      Promise.resolve(api.save_team(payload)).then(function (result) {
        teamsPayload = result;
        renderTeams(result);
        showAlert(result.message);
      }).catch(function (error) {
        showAlert('That team could not be saved: ' + error);
      });
      return;
    }
    if (action === 'choose_data_folder') {
      Promise.resolve(api.choose_data_folder()).then(applyFolderChoice)
        .catch(function (error) {
          showAlert('The folder picker could not be opened: ' + error);
        });
      return;
    }
    if (action === 'use_default_folder') {
      Promise.resolve(api.use_default_folder()).then(applyFolderChoice)
        .catch(function (error) {
          showAlert('The standard folder could not be restored: ' + error);
        });
      return;
    }
    if (action === 'forget_display') {
      Promise.resolve(api.forget_display()).then(function (payload) {
        renderDisplays(payload);
        showAlert('The saved display was forgotten. The board on screen is unchanged.');
      }).catch(function (error) {
        showAlert('The saved display could not be cleared: ' + error);
      });
      return;
    }
    if (action === 'open_logs_folder') {
      Promise.resolve(api.open_logs_folder()).then(function (result) {
        showAlert((result && result.message) || 'Opened the logs folder.');
      }).catch(function (error) {
        showAlert('The logs folder could not be opened: ' + error);
      });
      return;
    }
    if (action === 'open_layout_editor') {
      Promise.resolve(api.open_layout_editor()).then(function (result) {
        showAlert((result && result.message) || 'Presentation layout editor opened.');
      }).catch(function (error) {
        showAlert('The presentation layout editor could not be opened: ' + error);
      });
      return;
    }
    if (action === 'open_test_window') {
      Promise.resolve(api.open_test_window()).then(function (result) {
        showAlert((result && result.message) || 'Test spectator window opened.');
      }).catch(function (error) {
        showAlert('The test spectator window could not be opened: ' + error);
      });
      return;
    }
    if (action === 'open_field_assistant') {
      Promise.resolve(api.open_field_assistant()).then(function (result) {
        showAlert((result && result.message) || 'Field Assistant opened.');
      }).catch(function (error) {
        showAlert('The Field Assistant could not be opened: ' + error);
      });
      return;
    }
    if (action === 'open_cutscenes') {
      Promise.resolve(api.open_cutscenes()).then(function (result) {
        showAlert((result && result.message) || 'Cutscenes opened.');
      }).catch(function (error) {
        showAlert('The Cutscenes window could not be opened: ' + error);
      });
      return;
    }
    if (action === 'open_teams') {
      openDrawer('teams-drawer');
      refreshTeams();
    } else if (action === 'open_corrections') {
      openDrawer('corrections');
      refreshDataFolder();
    } else if (action === 'open_display') {
      openDrawer('display-drawer');
      refreshDisplays();
    } else if (action === 'open_setup') {
      openDrawer('setup-drawer');
      refreshRules();
    } else if (action === 'save_rules') {
      saveRules();
    } else if (action === 'restore_default_rules') {
      if (rulesPayload && rulesPayload.default_fields) {
        fillRules(rulesPayload.default_fields);
        setRulesNote('Defaults filled in. Press Save rules to apply them.');
      }
    } else if (action === 'open_game') {
      openDrawer('game-drawer');
    } else if (action === 'open_history') {
      openDrawer('history-drawer');
    } else if (action === 'open_help') {
      openDrawer('shortcut-help');
    } else if (action === 'open_advanced') {
      openDrawer('advanced-drawer');
    } else if (action === 'close_drawer') {
      closeDrawers();
    } else if (action === 'reopen_display') {
      Promise.resolve(api.reopen_display()).then(function (view) {
        render(view);
        if (view && view.health && view.health.display.needs_selection) {
          showAlert(view.health.display.detail || 'Choose a display.');
          openDrawer('display-drawer');
          refreshDisplays();
        }
      });
    }
  }

  function openDrawer(id) {
    disarmScore();
    closeDrawers();
    var drawer = document.getElementById(id);
    if (drawer) {
      drawer.hidden = false;
    }
  }

  function closeDrawers() {
    ['corrections', 'display-drawer', 'teams-drawer', 'setup-drawer', 'game-drawer',
      'history-drawer', 'shortcut-help', 'advanced-drawer'].forEach(function (id) {
      var drawer = document.getElementById(id);
      if (drawer) {
        drawer.hidden = true;
      }
    });
  }

  /* --- Setup drawer (SoccerRules, spec section 8) -------------------------- */

  function refreshRules() {
    if (!api || typeof api.rules !== 'function') {
      setRulesNote('Rules are not available in this build.');
      return;
    }
    Promise.resolve(api.rules()).then(function (payload) {
      rulesPayload = payload;
      fillRules(payload.fields);
      setRulesNote('');
    }).catch(function (error) {
      setRulesNote('The rules could not be read: ' + error);
    });
  }

  function fillRules(fields) {
    (fields || []).forEach(function (entry) {
      var spec = RULE_INPUTS[entry.name];
      if (!spec) return;
      if (spec.kind === 'clock') {
        var minutes = document.getElementById(spec.ids[0]);
        var seconds = document.getElementById(spec.ids[1]);
        if (minutes) minutes.value = String(entry.minutes);
        if (seconds) seconds.value = String(entry.seconds);
      } else if (spec.kind === 'toggle') {
        var checkbox = document.getElementById(spec.ids[0]);
        if (checkbox) checkbox.checked = Boolean(entry.value);
      } else if (spec.kind === 'choice') {
        var select = document.getElementById(spec.ids[0]);
        if (select) select.value = entry.value;
      } else {
        var field = document.getElementById(spec.ids[0]);
        if (field) field.value = String(entry.value);
      }
    });
  }

  function readRules() {
    var payload = {};
    Object.keys(RULE_INPUTS).forEach(function (name) {
      var spec = RULE_INPUTS[name];
      if (spec.kind === 'clock') {
        payload[name] = Number(fieldValue('#' + spec.ids[0])) * 60 + Number(fieldValue('#' + spec.ids[1]));
      } else if (spec.kind === 'toggle') {
        var checkbox = document.getElementById(spec.ids[0]);
        payload[name] = Boolean(checkbox && checkbox.checked);
      } else if (spec.kind === 'choice') {
        payload[name] = fieldValue('#' + spec.ids[0]);
      } else {
        payload[name] = Number(fieldValue('#' + spec.ids[0]));
      }
    });
    return payload;
  }

  function saveRules() {
    if (!api || typeof api.save_rules !== 'function') {
      setRulesNote('Rules cannot be saved in this build.');
      return;
    }
    Promise.resolve(api.save_rules(readRules())).then(function (result) {
      if (result && result.fields) {
        rulesPayload = result;
        fillRules(result.fields);
      }
      setRulesNote(result ? result.message : '');
      if (result && !result.ok) {
        showAlert(result.message);
      } else {
        clearAlert();
      }
    }).catch(function (error) {
      setRulesNote('The rules could not be saved: ' + error);
    });
  }

  function setRulesNote(message) {
    var note = document.getElementById('rules-note');
    if (!note) return;
    R.setText(note, message || '');
    note.hidden = !message;
  }

  function callHost(name, args) {
    if (!api || typeof api[name] !== 'function') {
      showAlert('The control bridge is not connected. Restart the application.');
      return;
    }
    Promise.resolve(api[name].apply(api, args || [])).then(function (result) {
      if (result && result.view) render(result.view);
      showAlert((result && result.message) || '');
    }).catch(function (error) {
      showAlert('That control could not be sent: ' + error);
    });
  }

  window.ScoreboardKeyboard.install({
    snapshot: function () { return model; },
    blocked: function () { return !api || !dialog.hidden || !document.getElementById('shortcut-help').hidden; },
    submit: submit,
    host: callHost,
    score: function (binding) {
      if (armedTeam === binding.arm && armedMode === 'goal') {
        disarmScore();
        submit(binding.command, Object.assign({}, binding.args), {source: 'operator-keyboard'});
        return;
      }
      armScore(binding.arm);
    },
    /**
     * Y/R arm the card panel (spec 4.5); the operator types a number (or
     * leaves it blank) and confirms with the mouse or Enter, exactly like
     * the on-screen CONFIRM button.
     */
    card: function (request) {
      if (armedTeam === request.team && armedMode === 'card' && armedCardKind === request.kind) {
        return;
      }
      armCard(request.team, request.kind);
    },
    confirm: function (name, args, options) {
      openDialog({
        title: (options && options.title) || 'Confirm this change',
        detail: '',
        change: name === 'undo' ? describeUndo() : '',
        command: name,
        args: args,
        source: 'operator-keyboard'
      });
    },
    close: function () {
      if (!dialog.hidden) closeDialog();
      else if (!periodDialog.hidden) dismissPeriodDialog();
      else if (!mercyDialog.hidden) { dismissedMercy = true; mercyDialog.hidden = true; }
      else if (armedTeam) disarmScore();
      else closeDrawers();
    }
  });

  dialog.addEventListener('keydown', function (event) {
    if (event.key !== 'Tab') return;
    var cancel = document.getElementById('confirm-cancel');
    var accept = document.getElementById('confirm-accept');
    if (event.shiftKey && document.activeElement === cancel) {
      event.preventDefault(); accept.focus();
    } else if (!event.shiftKey && document.activeElement === accept) {
      event.preventDefault(); cancel.focus();
    }
  });

  /* --- Refresh ---------------------------------------------------------- */

  window.applyView = render;

  R.whenReady(function (bridge) {
    api = bridge;
    Promise.resolve(api.get_snapshot()).then(function (view) {
      render(view);
      if (!promptedForTeams && view && view.setup && view.setup.teams_pending) {
        promptedForTeams = true;
        openDrawer('teams-drawer');
        refreshTeams();
      }
    });
    refreshTeams();
  });
})();
