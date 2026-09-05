(function () {
  'use strict';
  var R = window.ScoreboardRender;
  window.applyView = function (model) {
    try {
      R.bindFields(document, model);
      var eventMode = model.lifecycle === 'PRE_GAME' || model.lifecycle === 'HALFTIME';
      R.show(document.getElementById('game-board'), !eventMode);
      R.show(document.getElementById('event-board'), eventMode);
      R.show(document.getElementById('event-phase'), model.lifecycle === 'HALFTIME');
      R.show(document.getElementById('warmup'), Boolean(model.clocks.event.warmup_follows));
      R.show(document.getElementById('play-label'), model.clocks.play.display !== '');
      document.getElementById('canvas').dataset.revision = model.revision;
    } catch (error) {
      // Keep the last usable board; no operator diagnostic appears on the LED.
      console.error('Spectator rendering failed', error);
    }
  };
  R.whenReady(function (api) {
    Promise.resolve(api.get_snapshot()).then(window.applyView).catch(function (error) {
      console.error('Spectator snapshot failed', error);
    });
  });
})();
