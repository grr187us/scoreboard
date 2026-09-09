/* Operator controls.
 *
 * This file holds no authoritative state. It stores exactly four kinds of
 * ephemeral view state -- which drawer is open, which command a confirmation
 * dialog is waiting on, the text an operator has typed but not applied, and
 * which team's scoring is armed -- and it renders whatever view model Python
 * returns.
 *
 * It never computes a score, a clock value, a phase, or a revision. Every
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
  var lastDisplayLabel = null; // last rendered display health, to avoid re-reads
  var armedTeam = null; // which team's scoring is armed ('home'/'away'/null)
  var armTimer = null; // the auto-disarm timeout; see armScore()
  var promptedForTeams = false; // the soft prompt has had its one free opening

  // Long enough to reach the right point button, short enough that an armed
  // panel is never left waiting through the next play (owner decision 2).
  var ARM_SECONDS = 8;

  var alertLine = document.getElementById('alert');
  var dialog = document.getElementById('confirm-dialog');
  var dialogTitle = document.getElementById('confirm-title');
  var dialogDetail = document.getElementById('confirm-detail');
  var dialogChange = document.getElementById('confirm-change');
  var teamsPayload = null; // last api.teams() result, used to prefill Edit
  var rulesPayload = null; // last api.rules() result, for Restore defaults

  // The Setup drawer's fields, by rule name. A two-id entry is a
  // minutes:seconds pair; a one-id entry is a plain number. The names are
  // Python's (domain/rules.py); the page only moves values in and out.
  var RULE_INPUTS = {
    quarter_seconds: ['rule-quarter-minutes', 'rule-quarter-seconds'],
    overtime_seconds: ['rule-overtime-minutes', 'rule-overtime-seconds'],
    pregame_seconds: ['rule-pregame-minutes', 'rule-pregame-seconds'],
    halftime_seconds: ['rule-halftime-minutes', 'rule-halftime-seconds'],
    warmup_seconds: ['rule-warmup-minutes', 'rule-warmup-seconds'],
    timeout_seconds: ['rule-timeout-seconds'],
    timeouts_per_half: ['rule-timeouts-per-half']
  };

  /* --- Rendering -------------------------------------------------------- */

  function render(next) {
    if (!next) {
      return;
    }
    model = next;
    R.bindFields(document, model);

    var game = model.clocks.game;
    var play = model.clocks.play;

    R.setText(document.getElementById('chip-game'),
      'GAME ' + game.display + ' ' + game.status);
    R.setText(document.getElementById('chip-play'),
      'PLAY ' + (play.display === '' ? '—' : play.display) + ' ' + play.status);
    R.setText(document.getElementById('play-display'),
      play.display === '' ? '—' : play.display);
    R.setText(document.getElementById('chip-revision'), 'Rev ' + model.revision);

    // Colour is a rapid visual cue; the RUNNING/STOPPED text remains the
    // accessible, non-colour-only source of truth.
    R.setFlag(document.getElementById('game-display'), 'running-game', game.running);
    R.setFlag(document.getElementById('play-display'), 'running-play', play.running);
    R.setFlag(document.getElementById('game-state'), 'running-game', game.running);
    R.setFlag(document.getElementById('play-state'), 'running-play', play.running);

    // The action that is already true is de-emphasised, never removed, so the
    // operator can always see both Start and Stop (U-002).
    markState('game-start', game.running);
    markState('game-stop', !game.running);
    markState('play-start', play.running);
    markState('play-stop', !play.running);

    // The same correction controls serve the kickoff and halftime countdowns:
    // one game-clock engine for every quarter label. JavaScript only adjusts
    // form affordances from the period length Python reports; Python
    // validates and owns time.
    var maximumSeconds = Number(game.maximum_seconds) || 720;
    var gameMinutes = document.getElementById('game-minutes');
    if (gameMinutes) gameMinutes.max = String(Math.ceil(maximumSeconds / 60));
    var gameReset = document.querySelector('[data-command="game_clock_reset"]');
    if (gameReset) gameReset.dataset.confirmDetail =
      'The clock returns to ' + (game.full_display || '12:00') + ' and stays stopped.';
    renderRules(model.rules);

    renderHealth(model.health);
    renderCrowdStatus(model);
    renderLastAction(model);
    renderCutsceneBadge(model.cutscenes);
    renderQuarterChoices(model.quarter_labels, model.quarter);
    renderPossession(model.football.possession);

    // Team identity (F4) is carried in every view once the bridge is wired,
    // but this must never throw against an older view model that does not
    // have it yet -- both helpers tolerate a missing/undefined identity.
    var homeIdentity = model.teams.home ? model.teams.home.identity : null;
    var awayIdentity = model.teams.away ? model.teams.away.identity : null;
    renderIdentityNow('home', homeIdentity || null);
    renderIdentityNow('away', awayIdentity || null);
    renderIdentityStripe('home', homeIdentity || null);
    renderIdentityStripe('away', awayIdentity || null);
    renderSetup(model);
    renderTimeoutButtons(model);
  }

  /* --- Teams not chosen yet (owner decision 1) --------------------------- */

  /**
   * The soft prompt's three surfaces: NOT CHOSEN on the panel, the sentence
   * at the top of the Teams drawer, and a warm border on the Teams button.
   * Every word here is Python's (`setup.detail`); an older view model with no
   * `setup` block is treated as "nothing pending" rather than throwing, the
   * same way a missing `undo_history` is.
   */
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
      // Text plus a border, never colour alone (U-002): the drawer's sentence
      // and the panel's NOT CHOSEN carry the meaning; this only draws the eye.
      R.setFlag(teamsButton, 'is-attention', Boolean(setup.teams_pending));
      teamsButton.title = setup.teams_pending ? 'Choose the teams before kickoff.' : '';
    }
  }

  /**
   * A team with no timeouts left cannot spend one. This is a render-time
   * affordance only -- Python still refuses the command below zero -- and it
   * computes nothing: the count comes straight from the view model.
   */
  /**
   * The crowd TIMEOUT button loads the configured timeout length (Setup).
   * The length is copied from the view model into the button's data-seconds
   * at render time, so the command it sends is exactly what Python holds.
   */
  function renderRules(rules) {
    if (!rules) {
      return; // an older view model with no rules block; the HTML default stands
    }
    var timeoutButton = document.getElementById('crowd-timeout');
    if (timeoutButton && rules.timeout_seconds) {
      timeoutButton.dataset.seconds = String(rules.timeout_seconds);
    }
  }

  function renderTimeoutButtons(current) {
    var timeouts = current.football ? current.football.timeouts : null;
    ['home', 'away'].forEach(function (side) {
      var button = document.getElementById(side + '-timeout');
      if (button && timeouts) {
        button.disabled = timeouts[side] <= 0;
      }
    });
  }

  /* --- Armed scoring (owner decision 2) ---------------------------------- */

  /**
   * Arm one team's point buttons. Only one team can be armed at a time, so
   * this disarms whatever was armed first. The timeout it starts is the only
   * timer this file owns; it computes no game value, it just takes the point
   * buttons away again when nobody presses one.
   */
  function armScore(team) {
    disarmScore();
    armedTeam = team;
    armTimer = window.setTimeout(disarmScore, ARM_SECONDS * 1000);
    renderArmed();
  }

  function disarmScore() {
    if (armTimer !== null) {
      window.clearTimeout(armTimer);
      armTimer = null;
    }
    armedTeam = null;
    renderArmed();
  }

  /**
   * Swap the two groups inside the fixed-height .score-controls block. They
   * are toggled with `hidden`, never style.display, and both stay inside the
   * same block, so the panel's height never changes and nothing on the page
   * can be pushed off a 1093x614 screen (U-001).
   */
  function renderArmed() {
    ['home', 'away'].forEach(function (side) {
      var armed = armedTeam === side;
      var controls = document.getElementById(side + '-score-controls');
      if (controls) {
        controls.dataset.armed = armed ? 'true' : 'false';
      }
      R.setFlag(document.getElementById(side + '-panel'), 'is-armed', armed);
      R.show(document.getElementById(side + '-idle'), !armed);
      R.show(document.getElementById(side + '-armed'), armed);
      // The word SCORING in the heading, not the accent border alone (U-002).
      R.show(document.getElementById(side + '-armed-flag'), armed);
    });
  }

  // An armed panel must never survive the operator's attention moving away.
  window.addEventListener('blur', disarmScore);

  /* --- Team identity (F4) ------------------------------------------------ */

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

  function renderIdentityStripe(side, identity) {
    var stripe = document.getElementById(side + '-identity-stripe');
    if (!stripe) {
      return;
    }
    if (identity) {
      stripe.style.background = identity.primary;
      stripe.style.borderBottomColor = identity.secondary;
      R.setText(stripe, identity.short_name);
    } else {
      stripe.style.background = '';
      stripe.style.borderBottomColor = '';
      R.setText(stripe, '');
    }
    R.show(stripe, Boolean(identity));
  }

  function renderPossession(possession) {
    // Text, not colour alone (U-002's principle applied to a new field): the
    // flag is a visible word next to the team name, not only a CSS class.
    R.setText(document.getElementById('home-possession'), possession === 'home' ? ' ◀ BALL' : '');
    R.setText(document.getElementById('away-possession'), possession === 'away' ? ' BALL ▶' : '');
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
    // Re-read the display list only when the health strip actually changed and
    // the drawer is on screen. Enumerating monitors is a Windows call and this
    // function runs four times a second.
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

    // The drawer's own status row mirrors the strip exactly, so the display
    // panel never disagrees with what the health strip already said.
    var drawerChip = document.getElementById('drawer-display-chip');
    R.setText(drawerChip, health.display.label);
    R.setFlag(drawerChip, 'bad', !health.display.open);
    R.setFlag(drawerChip, 'good', health.display.open);
    R.setText(document.getElementById('display-detail'),
      health.display.detail || (health.display.open ? health.display.target : '') || '');
    R.show(document.getElementById('drawer-reopen-display'), health.display.can_reopen);
    // Closing is only offered while there is something to close (owner
    // request 6); Reopen is the mirror of it and already renders that way.
    R.show(document.getElementById('close-display'), health.display.open);

    var saveChip = document.getElementById('chip-save');
    R.setText(saveChip, health.persistence.label);
    R.setFlag(saveChip, 'bad', !health.persistence.saved);
    R.setFlag(saveChip, 'good', health.persistence.saved);
    saveChip.title = health.persistence.message;

    // A failed save must stay visible on its own, not only as a small chip.
    if (!health.persistence.saved) {
      showAlert(health.persistence.message);
    }
  }

  function renderLastAction(current) {
    R.setText(document.getElementById('last-action'),
      current.last_action ? current.last_action.label : 'nothing yet');
    Array.prototype.forEach.call(document.querySelectorAll('[data-command="undo"]'),
      function (button) { button.disabled = !current.can_undo; });

    // How many further Undos are waiting behind the one named in the strip
    // (I4). An older view model with no undo_history is treated as depth 0
    // rather than throwing, exactly like the team-identity fields above.
    var depth = typeof current.undo_depth === 'number' ? current.undo_depth : 0;
    var badge = document.getElementById('undo-depth');
    if (badge) {
      R.setText(badge, '×' + depth);
      // At 0 and 1 the badge says nothing the strip has not already said.
      badge.hidden = depth < 2;
    }
    renderHistory(current.undo_history || []);
  }

  /**
   * The undo-history list (I4). Every row is a label Python already rendered;
   * this function chooses no wording and reverses no value. The first row is
   * the one the next Undo reverses, which is the whole reason the list exists
   * -- an operator can see what a second Undo would give up before spending
   * the first (U-009).
   */
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

  /**
   * The cutscenes status badge. Like the crowd row, this renders exactly
   * what Python sent -- `label` and `remaining_display` -- and computes no
   * countdown of its own; when nothing is playing (`cutscenes` absent, or
   * `playing` null for an older view model, or no director at all) the
   * badge stays hidden rather than showing a stale or empty word.
   */
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
   * The crowd-facing message row (F3). Like every other control on this page
   * it renders what Python sent and computes nothing: the chip text is
   * `status.display`, the countdown is `status.clock_display`, and which
   * button is lit comes from `status.label`.
   */
  function renderCrowdStatus(current) {
    var status = current.status;
    if (!status) {
      return; // an older view model with no status block; nothing to draw
    }
    var chip = document.getElementById('crowd-status');
    R.setText(chip, status.display || '—');
    R.setFlag(chip, 'active', !!status.active);

    // The raised message is marked the way an already-true clock action is:
    // de-emphasised, never hidden, so every message stays one press away.
    ['FLAG', 'TIMEOUT', 'INJURY', 'DELAY'].forEach(function (label) {
      var button = document.getElementById('crowd-' + label.toLowerCase());
      if (button) {
        button.classList.toggle('is-active', status.label === label);
      }
    });

    var running = !!(status.clock && status.clock.running);
    R.setFlag(document.getElementById('crowd-clock'), 'running-status', running);
    markState('crowd-start', running);
    markState('crowd-stop', !running);
  }

  function renderQuarterChoices(labels, currentLabel) {
    var host = document.getElementById('quarter-choices');
    if (!host || host.childElementCount === labels.length) {
      updateQuarterChoice(host, currentLabel);
      return;
    }
    host.replaceChildren();
    labels.forEach(function (label) {
      var button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.setAttribute('data-command', 'set_quarter');
      button.setAttribute('data-label', label);
      host.appendChild(button);
    });
    updateQuarterChoice(host, currentLabel);
  }

  function updateQuarterChoice(host, currentLabel) {
    if (!host) {
      return;
    }
    Array.prototype.forEach.call(host.children, function (button) {
      button.classList.toggle('is-current',
        button.getAttribute('data-label') === currentLabel);
    });
  }

  function showAlert(message) {
    R.setText(alertLine, message);
    alertLine.hidden = false;
  }

  function clearAlert() {
    alertLine.hidden = true;
  }

  /* --- Building a request from a control -------------------------------- */

  /**
   * Read a control's arguments. Text fields are read here, at click time, so
   * typing alone can never reach the bridge (F-016).
   */
  function argumentsFor(button) {
    var args = {};
    if (button.dataset.clearTeam === 'true') {
      // An explicit "clear this" control (for example, clearing possession),
      // not a missing field: only a few commands accept team: null at all,
      // and Python's airlock still refuses it from anything else (F-016).
      args.team = null;
    } else if (button.dataset.team) {
      args.team = button.dataset.team;
    }
    if (button.dataset.points) {
      args.points = Number(button.dataset.points);
    }
    if (button.dataset.label) {
      args.label = button.dataset.label;
    }
    if (button.dataset.seconds) {
      args.seconds = Number(button.dataset.seconds);
    }
    if (button.dataset.clearValue === 'true') {
      args.value = null;
    } else if (button.dataset.value !== undefined) {
      args.value = Number(button.dataset.value);
    }
    if (button.dataset.name !== undefined) {
      // A generated "Use for HOME/AWAY" preset button (F4): the name is a
      // literal from the saved-team library, never computed from anything
      // else, so it reaches the same validated set_team_name path as typing
      // it by hand.
      args.name = button.dataset.name;
    }
    if (button.dataset.argMinutes && button.dataset.argSeconds) {
      var minutes = Number(fieldValue(button.dataset.argMinutes));
      var seconds = Number(fieldValue(button.dataset.argSeconds));
      args[button.dataset.argName] = minutes * 60 + seconds;
    } else if (button.dataset.argSide) {
      // Ball position needs a side plus a yard line together (they are one
      // compound state field); the side comes from the local toggle group's
      // selection, read here at click time exactly like a text field's value.
      var sideGroup = document.querySelector(button.dataset.argSide);
      args.team = sideGroup ? sideGroup.dataset.selected : null;
      var yardLine = fieldValue(button.dataset.argSource);
      args[button.dataset.argName] = yardLine === '' ? null : Number(yardLine);
    } else if (button.dataset.argSource) {
      var raw = fieldValue(button.dataset.argSource);
      if (button.dataset.argName === 'name') {
        args.name = raw;
      } else {
        args[button.dataset.argName] = raw === '' ? null : Number(raw);
      }
    }
    return args;
  }

  function fieldValue(selector) {
    var field = document.querySelector(selector);
    return field ? field.value : '';
  }

  /**
   * What Undo will reverse, in Python's own words. This page adds the two-word
   * prefix and nothing else: `last_action.label` is the same string the LAST
   * strip and the history drawer already show, so the dialog cannot disagree
   * with them about what is about to be given up (U-009).
   */
  function describeUndo() {
    return 'Reverses: ' + (model && model.last_action ? model.last_action.label : '');
  }

  function describeChange(button, args) {
    if (button.dataset.command === 'undo') {
      return describeUndo();
    }
    if (args.value !== undefined && button.dataset.team) {
      var team = button.dataset.team;
      return team.toUpperCase() + ' score ' + model.teams[team].score +
        ' → ' + args.value;
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
    args = Object.assign({}, args, {source: options.source || args.source || "operator-mouse"});
    if (!api) {
      showAlert('The control bridge is not connected. Restart the application.');
      return;
    }
    // The expected revision comes from what is on screen, so a control the
    // operator saw before someone else changed the board is refused.
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
      if (name === 'new_game') {
        // The soft prompt (owner decision 1): a new game arrives with the
        // default names, so the drawer that fixes that opens by itself. It
        // can be dismissed; nothing is locked, and this is one of only two
        // places the page opens a drawer on its own.
        promptedForTeams = true;
        openDrawer('teams-drawer');
        refreshTeams();
      }
      return;
    }
    if (result.confirmation_required) {
      // Nothing changed. The service is asking; the same command is resubmitted
      // with confirmed=true only if the operator confirms.
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

  /* --- Confirmation dialog --------------------------------------------- */

  function openDialog(request) {
    // A dialog takes the operator's attention; an armed panel waiting behind
    // it would apply a point on the next stray press (owner decision 2).
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
    // Cancel does nothing at all: no command is sent and no value changes.
    closeDialog();
  });

  document.getElementById('confirm-accept').addEventListener('click', function () {
    if (!pending) {
      return;
    }
    var request = pending;
    closeDialog();
    if (request.perform) {
      // A host-action confirmation (for example, Delete team): there is no
      // command, revision, or history row -- just a callback to run now that
      // the operator has confirmed. Cancel already did nothing at all.
      request.perform();
      return;
    }
    var args = Object.assign({}, request.args, { confirmed: true });
    submit(request.command, args, { title: request.title, source: request.source,
      expectedRevision: request.expectedRevision });
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
    if (button.dataset.side) {
      // A side toggle only changes which team a later "Set" reads (F-016's
      // "typing changes nothing before Apply" applies here too); it sends no
      // command and touches no game state on its own.
      var group = button.closest('.side-toggle');
      if (group) {
        group.dataset.selected = button.dataset.side;
        Array.prototype.forEach.call(group.querySelectorAll('[data-side]'), function (toggle) {
          toggle.classList.toggle('is-current', toggle.dataset.side === button.dataset.side);
        });
      }
      return;
    }
    if (button.dataset.displayKey) {
      // Choosing a display is a host action, not a game command: no revision
      // is sent and nothing about the game changes.
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

    if (name === 'add_score') {
      // One point press applies and disarms, accepted or rejected: the panel
      // is armed for a single decision, never for a run of them.
      disarmScore();
    }

    if (button.dataset.confirm === 'local') {
      // A direct correction shows old and new values before anything is sent.
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
    submit(name, args, { title: button.dataset.confirmTitle, source: source });
  });

  /* --- Which display the board is on ------------------------------------ */

  /**
   * Render the display panel. Like the data folder, this is read on demand
   * rather than carried in the view model: enumerating monitors is a Windows
   * call and the view model is rebuilt four times a second.
   */
  function refreshDisplays() {
    if (!api || !api.displays) {
      return;
    }
    Promise.resolve(api.displays()).then(renderDisplays).catch(function (error) {
      R.setText(document.getElementById('display-summary'),
        'could not be read: ' + error);
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
      button.textContent = display.description +
        (display.key === payload.current_key ? ' — in use' : '');
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

  /* --- Saved teams (F4) --------------------------------------------------- */

  /**
   * The saved-team library is a laptop preference, not game state, so it is
   * read on demand like the display list and the data folder rather than
   * carried in the four-times-a-second view model. `api.teams` may not exist
   * in every build; the drawer must say so plainly and never throw.
   */
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

  /** One saved-team row: swatch, name/short, apply/edit/delete controls. */
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
      // An ordinary command control (F4): the existing local-confirm path,
      // source detection, and revision check all apply unchanged. The name
      // is the preset's own name, never computed from anything else.
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

  /**
   * Show the current data folder. Read on demand, never from the view model:
   * resolving it touches the filesystem, and the view model is rebuilt four
   * times a second.
   */
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
      R.setText(document.getElementById('data-folder-path'),
        'could not be read: ' + error);
    });
  }

  function applyFolderChoice(result) {
    if (!result) {
      return;
    }
    // Cancelling is not an error and must say so plainly, so an operator is
    // never left wondering whether they changed something.
    showAlert(result.message);
    if (result.view) {
      render(result.view);
    }
    refreshDataFolder();
  }

  function handleAction(action, button) {
    if (action === 'arm_score') {
      // No bridge call and no game value: arming only reveals the four point
      // buttons that were always the real data-command controls (K-001).
      armScore(button && button.dataset.team);
      return;
    }
    if (action === 'disarm_score') {
      disarmScore();
      return;
    }
    if (action === 'close_display') {
      // A host action in the Reopen family: it closes that one window and
      // changes no game state, advances no revision (D-005). Older hosts have
      // no such method, and must say so plainly rather than throw.
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
      // A host action: shows the diagnostics folder in Explorer so an operator
      // can send the log after a bad game. Reads nothing, changes nothing.
      Promise.resolve(api.open_logs_folder()).then(function (result) {
        showAlert((result && result.message) || 'Opened the logs folder.');
      }).catch(function (error) {
        showAlert('The logs folder could not be opened: ' + error);
      });
      return;
    }
    if (action === 'open_layout_editor') {
      // A host action, like the test window: it opens a presentation-only
      // window and cannot reach the game. Both outcomes are reported plainly
      // because this is a button an operator may press during a game.
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
        // The helper is deliberately optional: an unavailable window leaves
        // the existing Field drawer and every game control usable.
        showAlert('The Field Assistant could not be opened: ' + error);
      });
      return;
    }
    if (action === 'open_cutscenes') {
      // A host action, like the Field Assistant: it opens a small persistent
      // trigger window and cannot itself reach the game. Both outcomes are
      // reported plainly because this is a button an operator may press
      // during a game.
      Promise.resolve(api.open_cutscenes()).then(function (result) {
        showAlert((result && result.message) || 'Cutscenes opened.');
      }).catch(function (error) {
        // Optional surface: an unavailable window leaves every other control
        // usable, including triggering nothing (there is nothing to trigger
        // without this window open).
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
      // Draft only: the defaults land in the fields, and nothing reaches
      // Python until Save (F-016).
      if (rulesPayload && rulesPayload.default_fields) {
        fillRules(rulesPayload.default_fields);
        setRulesNote('Defaults filled in. Press Save rules to apply them.');
      }
    } else if (action === 'open_field') {
      openDrawer('field-drawer');
    } else if (action === 'open_game') {
      // The separate danger area (owner request 5): every control inside asks
      // to be confirmed before it can lose a game.
      openDrawer('game-drawer');
    } else if (action === 'open_history') {
      // Read-only: the list is already in the rendered view model, so opening
      // it asks Python for nothing and changes nothing (I4).
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
        // One click reopens on the saved display whenever it is there. When it
        // is not, no window is opened over the controls; the operator is shown
        // the display drawer instead, because only they can say which screen
        // the board should go to (D-002, UX section 6.8).
        if (view && view.health && view.health.display.needs_selection) {
          showAlert(view.health.display.detail || 'Choose a display.');
          openDrawer('display-drawer');
          refreshDisplays();
        }
      });
    }
  }

  function openDrawer(id) {
    // An overlay hides the board, so an armed panel behind it would be a
    // surprise waiting for the drawer to close (owner decision 2).
    disarmScore();
    closeDrawers();
    var drawer = document.getElementById(id);
    if (drawer) {
      drawer.hidden = false;
    }
  }

  function closeDrawers() {
    ['corrections', 'display-drawer', 'teams-drawer', 'setup-drawer', 'field-drawer', 'game-drawer', 'history-drawer', 'shortcut-help', 'advanced-drawer'].forEach(function (id) {
      var drawer = document.getElementById(id);
      if (drawer) {
        drawer.hidden = true;
      }
    });
  }

  /* --- Setup drawer (game rules) ---------------------------------------- */

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

  /**
   * Fill the drawer from Python's per-field split (`fields`): a clock rule
   * arrives already divided into minutes and seconds, so nothing here does
   * arithmetic on a value it was given.
   */
  function fillRules(fields) {
    (fields || []).forEach(function (entry) {
      var ids = RULE_INPUTS[entry.name];
      if (!ids) return;
      if (ids.length === 2) {
        var minutes = document.getElementById(ids[0]);
        var seconds = document.getElementById(ids[1]);
        if (minutes) minutes.value = String(entry.minutes);
        if (seconds) seconds.value = String(entry.seconds);
      } else {
        var field = document.getElementById(ids[0]);
        if (field) field.value = String(entry.value);
      }
    });
  }

  /** Read every field at click time (F-016); Python validates the result. */
  function readRules() {
    var payload = {};
    Object.keys(RULE_INPUTS).forEach(function (name) {
      var ids = RULE_INPUTS[name];
      if (ids.length === 2) {
        payload[name] = Number(fieldValue('#' + ids[0])) * 60 + Number(fieldValue('#' + ids[1]));
      } else {
        payload[name] = Number(fieldValue('#' + ids[0]));
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

  /**
   * A `host` keyboard binding (cutscenes trigger/cancel) has no Command, no
   * revision, and no history row -- it calls the named host action on the
   * bridge directly, the same way the Cutscenes window's own buttons do, and
   * shows whatever plain-language message comes back.
   */
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
    /**
     * A score key is the same two steps as the SCORE button (2.8): the first
     * press only arms that team -- no bridge call, no game value -- and the
     * second sends the point the binding already named.
     */
    score: function (binding) {
      if (armedTeam === binding.arm) {
        disarmScore();
        submit(binding.command, Object.assign({}, binding.args),
          {source: 'operator-keyboard'});
        return;
      }
      armScore(binding.arm);
    },
    /**
     * A binding that must be confirmed first (Ctrl+Z). It opens the same
     * local dialog the button does, so both input adapters take the identical
     * round trip (owner decision 3).
     */
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
      // Escape with nothing open and a team armed just puts the point buttons
      // away; an armed panel can never be open at the same time as a drawer.
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

  /**
   * Python pushes a view model whenever a clock display changes. This function
   * is the entry point it calls; the page never derives a value on its own.
   */
  window.applyView = render;

  R.whenReady(function (bridge) {
    api = bridge;
    Promise.resolve(api.get_snapshot()).then(function (view) {
      render(view);
      // The second (and last) place the page opens a drawer by itself: a
      // fresh game at launch, or a recovered pregame board still carrying the
      // default names. It never re-opens from render(), so a prompt the
      // operator dismissed stays dismissed until the next New Game.
      if (!promptedForTeams && view && view.setup && view.setup.teams_pending) {
        promptedForTeams = true;
        openDrawer('teams-drawer');
        refreshTeams();
      }
    });
    // So the "Now" swatches are already right before the drawer is first
    // opened; identity also arrives in every view, so this is belt and
    // braces (F4).
    refreshTeams();
  });
})();
