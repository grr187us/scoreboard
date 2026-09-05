/* Operator controls.
 *
 * This file holds no authoritative state. It stores exactly three kinds of
 * ephemeral view state -- which drawer is open, which command a confirmation
 * dialog is waiting on, and the text an operator has typed but not applied --
 * and it renders whatever view model Python returns.
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

  var alertLine = document.getElementById('alert');
  var dialog = document.getElementById('confirm-dialog');
  var dialogTitle = document.getElementById('confirm-title');
  var dialogDetail = document.getElementById('confirm-detail');
  var dialogChange = document.getElementById('confirm-change');

  /* --- Rendering -------------------------------------------------------- */

  function render(next) {
    if (!next) {
      return;
    }
    model = next;
    R.bindFields(document, model);

    var game = model.clocks.game;
    var play = model.clocks.play;
    var event = model.clocks.event;

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
    markState('event-start', event.running);
    markState('event-stop', !event.running);

    // The same correction controls serve the authoritative pregame countdown.
    // JavaScript only adjusts form affordances; Python validates and owns time.
    var gameMinutes = document.getElementById('game-minutes');
    if (gameMinutes) gameMinutes.max = model.quarter === 'PRE' ? '30' : '12';
    var gameReset = document.querySelector('[data-command="game_clock_reset"]');
    if (gameReset) gameReset.dataset.confirmDetail = model.quarter === 'PRE' ?
      'The pregame countdown returns to 30:00 and stays stopped.' :
      'The game clock returns to 12:00 and stays stopped.';

    renderHealth(model.health);
    renderLastAction(model);
    renderQuarterChoices(model.quarter_labels, model.quarter);
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
    // Re-read the display list only when the health strip actually changed and
    // the panel is on screen. Enumerating monitors is a Windows call and this
    // function runs four times a second.
    if (health.display.label !== lastDisplayLabel) {
      lastDisplayLabel = health.display.label;
      if (!document.getElementById('corrections').hidden) {
        refreshDisplays();
      }
    }
    R.setText(displayChip, health.display.label);
    R.setFlag(displayChip, 'bad', !health.display.open);
    R.setFlag(displayChip, 'good', health.display.open);
    R.show(document.getElementById('reopen-display'), health.display.can_reopen);

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
    document.getElementById('undo').disabled = !current.can_undo;
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
    if (button.dataset.team) {
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
    if (button.dataset.argMinutes && button.dataset.argSeconds) {
      var minutes = Number(fieldValue(button.dataset.argMinutes));
      var seconds = Number(fieldValue(button.dataset.argSeconds));
      args[button.dataset.argName] = minutes * 60 + seconds;
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

  function describeChange(button, args) {
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
      handleAction(button.dataset.action);
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

  function handleAction(action) {
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
    if (action === 'open_test_window') {
      Promise.resolve(api.open_test_window()).then(function (result) {
        showAlert((result && result.message) || 'Test spectator window opened.');
      }).catch(function (error) {
        showAlert('The test spectator window could not be opened: ' + error);
      });
      return;
    }
    if (action === 'open_corrections') {
      openDrawer('corrections');
      refreshDataFolder();
      refreshDisplays();
    } else if (action === 'open_event') {
      openDrawer('event-drawer');
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
        // the display panel instead, because only they can say which screen
        // the board should go to (D-002, UX section 6.8).
        if (view && view.health && view.health.display.needs_selection) {
          showAlert(view.health.display.detail || 'Choose a display.');
          openDrawer('corrections');
          refreshDataFolder();
          refreshDisplays();
          var row = document.getElementById('display-row');
          if (row && row.scrollIntoView) {
            row.scrollIntoView({block: 'nearest'});
          }
        }
      });
    }
  }

  function openDrawer(id) {
    closeDrawers();
    var drawer = document.getElementById(id);
    if (drawer) {
      drawer.hidden = false;
    }
  }

  function closeDrawers() {
    ['corrections', 'event-drawer', 'shortcut-help', 'advanced-drawer'].forEach(function (id) {
      var drawer = document.getElementById(id);
      if (drawer) {
        drawer.hidden = true;
      }
    });
  }

  window.ScoreboardKeyboard.install({
    snapshot: function () { return model; },
    blocked: function () { return !api || !dialog.hidden || !document.getElementById('shortcut-help').hidden; },
    submit: submit,
    close: function () {
      if (!dialog.hidden) closeDialog();
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
    Promise.resolve(api.get_snapshot()).then(render);
  });
})();
