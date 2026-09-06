(function () {
  'use strict';
  var R = window.ScoreboardRender;
  var B = window.ScoreboardBoard;
  var canvas = document.getElementById('canvas');
  var gameBoard = document.getElementById('game-board');
  var eventBoard = document.getElementById('event-board');

  function isPlainObject(value) {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  // The full layout document last accepted from the host (schema v3: the
  // in-game screen at the top level, plus screens.pregame/screens.halftime).
  // Starts as the built-in default so both boards look right before any host
  // call returns (or if the host never sends one at all -- an older host
  // still gets a usable board).
  var currentLayout = B.DEFAULT_LAYOUT;

  // Build both boards and place them at the built-in default immediately.
  B.build(gameBoard, 'game');
  B.build(eventBoard, 'event');
  B.applyLayout(gameBoard, currentLayout);
  // eventBoard.dataset.screen remembers which event screen is currently
  // applied, so a later layout push (window.applyLayout) can re-apply the
  // same screen without needing the latest model's lifecycle.
  eventBoard.dataset.screen = 'pregame';
  B.applyLayout(eventBoard, B.screenDocument(currentLayout, eventBoard.dataset.screen));
  canvas.dataset.layout = currentLayout.name;

  window.applyView = function (model) {
    try {
      var screenId = B.screenForLifecycle(model.lifecycle);
      var eventMode = screenId !== 'game';
      if (eventMode && eventBoard.dataset.screen !== screenId) {
        eventBoard.dataset.screen = screenId;
        B.applyLayout(eventBoard, B.screenDocument(currentLayout, screenId));
      }
      B.applyModel(gameBoard, model);
      B.applyModel(eventBoard, model);
      R.show(gameBoard, !eventMode);
      R.show(eventBoard, eventMode);
      // Colour supplements, never replaces, the textual clock status shown to
      // the operator.
      R.setFlag(gameBoard.querySelector('[data-widget="game_clock_value"]'), 'running-game', model.clocks.game.running);
      R.setFlag(gameBoard.querySelector('[data-widget="play_clock_value"]'), 'running-play', model.clocks.play.running);
      canvas.dataset.revision = model.revision;
    } catch (error) {
      // Keep the last usable board; no operator diagnostic appears on the LED.
      console.error('Spectator rendering failed', error);
    }
  };

  // New global the host calls whenever the active presentation layout
  // changes. A payload that is not a usable layout document is rejected here
  // -- before board.js ever sees it -- so the boards keep showing whatever
  // layout last applied successfully, rather than a half-applied mix.
  window.applyLayout = function (layout) {
    try {
      if (!isPlainObject(layout) || !isPlainObject(layout.widgets)) {
        throw new Error('Layout payload is not a usable layout document');
      }
      currentLayout = layout;
      B.applyLayout(gameBoard, currentLayout);
      B.applyLayout(eventBoard, B.screenDocument(currentLayout, eventBoard.dataset.screen));
      canvas.dataset.layout = typeof layout.name === 'string' ? layout.name : '';
    } catch (error) {
      console.error('Layout apply failed; keeping the previous layout', error);
    }
  };

  R.whenReady(function (api) {
    Promise.resolve(api.get_snapshot()).then(window.applyView).catch(function (error) {
      console.error('Spectator snapshot failed', error);
    });
    // An older host may not expose get_layout at all; the default layout
    // already applied above keeps the board usable either way.
    if (typeof api.get_layout === 'function') {
      Promise.resolve(api.get_layout()).then(window.applyLayout).catch(function (error) {
        console.error('Spectator layout fetch failed', error);
      });
    }
  });
})();
