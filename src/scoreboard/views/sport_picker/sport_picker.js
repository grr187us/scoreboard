(function () {
  'use strict';
  var R = window.ScoreboardRender;
  var api;
  var busy = false;

  function choose(sport) {
    if (busy) return;
    busy = true;
    Promise.resolve().then(function () { return api.choose_sport(sport); }).catch(function (error) {
      busy = false;
      R.setText(document.getElementById('error'), 'Could not open the scoreboard: ' + error);
    });
  }

  document.getElementById('football').onclick = function () { choose('football'); };
  document.getElementById('soccer').onclick = function () { choose('soccer'); };

  R.whenReady(function (bridge) {
    api = bridge;
    Promise.resolve(api.last_sport()).then(function (last) {
      var label = { football: 'Football', soccer: 'Soccer' }[last];
      R.setText(document.getElementById('last-sport'), label ? 'Last time: ' + label : '');
      // Pre-focus the remembered button. This never chooses on its own: a
      // click (or Enter/Space on the focused button) is still required.
      var button = document.getElementById(last === 'soccer' ? 'soccer' : 'football');
      if (last) { button.focus(); }
    }).catch(function (error) { R.setText(document.getElementById('error'), String(error)); });
  });
})();
