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

    R.setFlag(document.getElementById('game-state'), 'running', game.running);
    R.setFlag(document.getElementById('play-state'), 'running', play.running);

    // The action that is already true is de-emphasised, never removed, so the
    // operator can always see both Start and Stop (U-002).
    markState('game-start', game.running);
    markState('game-stop', !game.running);
    markState('play-start', play.running);
    markState('play-stop', !play.running);
    markState('event-start', event.running);
    markState('event-stop', !event.running);

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
    if (!api) {
      showAlert('The control bridge is not connected. Restart the application.');
      return;
    }
    // The expected revision comes from what is on screen, so a control the
    // operator saw before someone else changed the board is refused.
    var expected = model ? model.revision : null;
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
        detail: result.error ? result.error.message : '',
        change: '',
        command: name,
        args: args
      });
      return;
    }
    if (result.error) {
      showAlert(result.error.message);
    }
  }

  /* --- Confirmation dialog --------------------------------------------- */

  function openDialog(request) {
    pending = request;
    R.setText(dialogTitle, request.title);
    R.setText(dialogDetail, request.detail || '');
    R.setText(dialogChange, request.change || '');
    dialogChange.hidden = !request.change;
    dialog.hidden = false;
    document.getElementById('confirm-cancel').focus();
  }

  function closeDialog() {
    pending = null;
    dialog.hidden = true;
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
    submit(request.command, args, { title: request.title });
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
    if (!button.dataset.command) {
      return;
    }
    var name = button.dataset.command;
    var args = argumentsFor(button);

    if (button.dataset.confirm === 'local') {
      // A direct correction shows old and new values before anything is sent.
      openDialog({
        title: button.dataset.confirmTitle || 'Confirm this change',
        detail: button.dataset.confirmDetail || '',
        change: describeChange(button, args),
        command: name,
        args: args
      });
      return;
    }
    submit(name, args, { title: button.dataset.confirmTitle });
  });

  function handleAction(action) {
    if (action === 'open_corrections') {
      openDrawer('corrections');
    } else if (action === 'open_event') {
      openDrawer('event-drawer');
    } else if (action === 'close_drawer') {
      closeDrawers();
    } else if (action === 'reopen_display') {
      Promise.resolve(api.reopen_display()).then(render);
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
    ['corrections', 'event-drawer'].forEach(function (id) {
      var drawer = document.getElementById(id);
      if (drawer) {
        drawer.hidden = true;
      }
    });
  }

  document.addEventListener('keydown', function (keyEvent) {
    // Escape closes a dialog or drawer. It never closes the spectator window
    // or the application.
    if (keyEvent.key !== 'Escape') {
      return;
    }
    if (!dialog.hidden) {
      closeDialog();
    } else {
      closeDrawers();
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
