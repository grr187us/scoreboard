/* The soccer spectator page's boot script (mirrors
 * scoreboard.views.spectator.spectator.js, spec section 5). Builds the
 * "soccer" game board and the shared "event" pre-game/halftime board, and
 * wires the same host calls football's page does: get_snapshot, get_layout,
 * get_motion, get_cutscene. `screenForLifecycle` is football's, unchanged --
 * soccer's lifecycle values (PRE_GAME/HALFTIME/else) are the same strings.
 */
(function () {
  'use strict';
  var R = window.ScoreboardRender;
  var B = window.ScoreboardBoard;
  var canvas = document.getElementById('canvas');
  var gameBoard = document.getElementById('game-board');
  var eventBoard = document.getElementById('event-board');
  var closeButton = document.getElementById('close-display');

  // Captured once R.whenReady fires (bottom of this file) so the pointer/key
  // handlers below -- installed once, at load -- can still reach the bridge.
  var bridgeApi = null;

  // Guards a second Escape press or click while close_display's promise is
  // still in flight.
  var closeRequested = false;
  var revealTimer = null;

  function isPlainObject(value) {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  // The full layout document last accepted from the host (schema v3: the
  // soccer game screen at the top level, plus screens.pregame/halftime).
  // Starts as the built-in Soccer Grid default so both boards look right
  // before any host call returns.
  var currentLayout = B.SOCCER_DEFAULT_LAYOUT;

  // A cutscene's temporary layout override, or null when no cutscene is
  // playing. While it is set it wins over `currentLayout` on both boards.
  var overrideLayout = null;

  /** Whichever document the boards should currently be drawn from. */
  function activeLayout() {
    return overrideLayout || currentLayout;
  }

  /** Draw both boards from the active layout and record its name on #canvas.
   * The event board keeps whichever screen it last applied (its
   * `data-screen`), so a layout change never silently switches screens. */
  function applyBoards() {
    var layout = activeLayout();
    B.applyLayout(gameBoard, layout);
    B.applyLayout(eventBoard, B.screenDocument(layout, eventBoard.dataset.screen));
    canvas.dataset.layout = typeof layout.name === 'string' ? layout.name : '';
  }

  // Build both boards and place them at the built-in default immediately.
  B.build(gameBoard, 'soccer');
  B.build(eventBoard, 'event');
  eventBoard.dataset.screen = 'pregame';
  applyBoards();

  window.applyView = function (model) {
    try {
      var screenId = B.screenForLifecycle(model.lifecycle);
      var eventMode = screenId !== 'game';
      if (eventMode && eventBoard.dataset.screen !== screenId) {
        eventBoard.dataset.screen = screenId;
        B.applyLayout(eventBoard, B.screenDocument(activeLayout(), screenId));
      }
      R.show(gameBoard, !eventMode);
      R.show(eventBoard, eventMode);
      B.applyModel(gameBoard, model);
      B.applyModel(eventBoard, model);
      // Colour supplements, never replaces, the textual clock status shown to
      // the operator. Soccer has no play clock, so only the game clock flag.
      R.setFlag(gameBoard.querySelector('[data-widget="game_clock_value"]'), 'running-game', model.clocks.game.running);
      canvas.dataset.revision = model.revision;
    } catch (error) {
      // Keep the last usable board; no operator diagnostic appears on the LED.
      console.error('Spectator rendering failed', error);
    }
  };

  // New global the host calls whenever the active presentation layout
  // changes. A payload that is not a usable layout document is rejected here
  // -- before board.js ever sees it.
  window.applyLayout = function (layout) {
    try {
      if (!isPlainObject(layout) || !isPlainObject(layout.widgets)) {
        throw new Error('Layout payload is not a usable layout document');
      }
      currentLayout = layout;
      if (!overrideLayout) {
        applyBoards();
      }
    } catch (error) {
      console.error('Layout apply failed; keeping the previous layout', error);
    }
  };

  // The motion kill switch: a host preference, pushed by the host exactly
  // like a layout. It only adds or removes `data-motion="off"` on #canvas.
  window.applyMotion = function (enabled) {
    try {
      B.setMotion(canvas, enabled !== false);
    } catch (error) {
      console.error('Motion switch failed; keeping the current motion state', error);
    }
  };

  // The seam cutscene.js drives. Deliberately tiny: the player owns the
  // timeline and the stage, this owns the boards.
  window.ScoreboardSpectator = {
    /** Draw both boards from `layoutDoc` until it is cleared; pass null (or
     * nothing) to drop the override and return to the operator's layout.
     * Returns true when the boards were re-drawn. */
    setOverrideLayout: function (layoutDoc) {
      try {
        if (layoutDoc === null || layoutDoc === undefined) {
          overrideLayout = null;
          applyBoards();
          return true;
        }
        if (!isPlainObject(layoutDoc) || !isPlainObject(layoutDoc.widgets)) {
          throw new Error('Override layout is not a usable layout document');
        }
        overrideLayout = layoutDoc;
        applyBoards();
        return true;
      } catch (error) {
        console.error('Cutscene layout override failed; keeping the board as it is', error);
        return false;
      }
    },
    /** The operator's layout -- never the cutscene override. */
    currentLayout: function () { return currentLayout; },
    canvas: canvas
  };

  // Closing this window is the one action the spectator page can take: it
  // changes no game state (no score, no clock, no history row).
  /** Show the close button, then hide it again after 3 seconds of no
   * pointer movement. A wall with nothing plugged in never sees it. */
  function revealCloseButton() {
    if (!closeButton) {
      return;
    }
    closeButton.hidden = false;
    if (revealTimer) {
      clearTimeout(revealTimer);
    }
    revealTimer = setTimeout(function () {
      closeButton.hidden = true;
    }, 3000);
  }

  function requestClose() {
    if (closeRequested) {
      return;
    }
    try {
      if (bridgeApi && typeof bridgeApi.close_display === 'function') {
        closeRequested = true;
        Promise.resolve(bridgeApi.close_display()).catch(function (error) {
          console.error('Spectator close_display failed', error);
        });
      }
    } catch (error) {
      console.error('Spectator close_display failed', error);
    }
  }

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && !event.repeat) {
      requestClose();
    }
  });
  document.addEventListener('mousemove', revealCloseButton);
  document.addEventListener('pointermove', revealCloseButton);
  if (closeButton) {
    closeButton.addEventListener('click', requestClose);
  }

  R.whenReady(function (api) {
    bridgeApi = api;
    Promise.resolve(api.get_snapshot()).then(window.applyView).catch(function (error) {
      console.error('Spectator snapshot failed', error);
    });
    if (typeof api.get_layout === 'function') {
      Promise.resolve(api.get_layout()).then(window.applyLayout).catch(function (error) {
        console.error('Spectator layout fetch failed', error);
      });
    }
    if (typeof api.get_motion === 'function') {
      Promise.resolve(api.get_motion()).then(window.applyMotion).catch(function (error) {
        console.error('Spectator motion fetch failed', error);
      });
    }
    // A spectator window opened (or reopened) while a cutscene is already
    // playing joins it mid-flight.
    if (typeof api.get_cutscene === 'function') {
      Promise.resolve(api.get_cutscene()).then(function (program) {
        if (program && typeof window.applyCutscene === 'function') {
          window.applyCutscene(program);
        }
      }).catch(function (error) {
        console.error('Spectator cutscene fetch failed', error);
      });
    }
  });
})();
