(function () {
  'use strict';
  // Mirrors views/startup/startup.js exactly (same StartupBridge, same three
  // methods, spec section 2.5/9 -- "own page" per open question J). Only the
  // summary text differs: Period instead of Quarter, and no play clock line
  // (soccer has none, spec 3.1/3.3).
  var R = window.ScoreboardRender;
  var api;
  var busy = false;
  var confirmation = document.getElementById('new-confirm');
  function choose(method) {
    if (busy) return;
    busy = true;
    Promise.resolve().then(function () { return api[method](); }).catch(function (error) {
      busy = false;
      R.setText(document.getElementById('error'), 'Could not open the game: ' + error);
    });
  }
  document.getElementById('resume').onclick = function () { choose('resume_recovered_game'); };
  document.getElementById('new').onclick = function () {
    confirmation.hidden = false;
    document.getElementById('cancel').focus();
  };
  document.getElementById('cancel').onclick = function () { confirmation.hidden = true; };
  document.getElementById('accept').onclick = function () { choose('start_new_game'); };
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') { event.preventDefault(); confirmation.hidden = true; }
  });
  R.whenReady(function (bridge) {
    api = bridge;
    Promise.resolve(api.get_recovery()).then(function (report) {
      R.setText(document.getElementById('message'), report.message);
      R.setText(document.getElementById('checkpoint'),
        'Source: ' + report.source + ' · Last saved: ' +
        (report.checkpoint_at_local || report.checkpoint_at || 'unavailable'));
      R.setText(document.getElementById('summary'), report.view ?
        report.view.teams.home.name + ' ' + report.view.teams.home.score + ' — ' +
        report.view.teams.away.name + ' ' + report.view.teams.away.score + '\n' +
        'Period: ' + (report.view.period_display || report.view.period) + '\n' +
        'Game: ' + report.view.clocks.game.display + '\n' +
        report.view.clocks.event.title + ': ' + report.view.clocks.event.display :
        report.preserved_paths.join('\n'));
      document.getElementById('resume').disabled = !report.can_resume;
      document.getElementById('new').disabled = false;
    }).catch(function (error) { R.setText(document.getElementById('error'), String(error)); });
  });
})();
