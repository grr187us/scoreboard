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

  // Build the widget board and place it at the built-in default immediately,
  // so the board looks right before any host call returns (or if the host
  // never sends a layout at all -- an older host still gets a usable board).
  B.build(gameBoard);
  B.applyLayout(canvas, B.DEFAULT_LAYOUT);
  canvas.dataset.layout = B.DEFAULT_LAYOUT.name;

  window.applyView = function (model) {
    try {
      B.applyModel(canvas, model);
      var eventMode = model.lifecycle === 'PRE_GAME' || model.lifecycle === 'HALFTIME';
      R.show(gameBoard, !eventMode);
      R.show(eventBoard, eventMode);
      R.bindFields(document, model);
      R.show(document.getElementById('event-phase'), model.lifecycle === 'HALFTIME');
      R.show(document.getElementById('warmup'), Boolean(model.clocks.event.warmup_follows));
      // Colour supplements, never replaces, the textual clock status shown to
      // the operator.
      R.setFlag(canvas.querySelector('[data-widget="game_clock_value"]'), 'running-game', model.clocks.game.running);
      R.setFlag(canvas.querySelector('[data-widget="play_clock_value"]'), 'running-play', model.clocks.play.running);
      canvas.dataset.revision = model.revision;
    } catch (error) {
      // Keep the last usable board; no operator diagnostic appears on the LED.
      console.error('Spectator rendering failed', error);
    }
  };

  // New global the host calls whenever the active presentation layout
  // changes. A payload that is not a usable layout document is rejected here
  // -- before board.js ever sees it -- so the board keeps showing whatever
  // layout last applied successfully, rather than a half-applied mix.
  window.applyLayout = function (layout) {
    try {
      if (!isPlainObject(layout) || !isPlainObject(layout.widgets)) {
        throw new Error('Layout payload is not a usable layout document');
      }
      B.applyLayout(canvas, layout);
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
