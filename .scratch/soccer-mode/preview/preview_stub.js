/* Static preview stub for the soccer operator page (agent C).
 *
 * NOT SHIPPED. This is a fake window.pywebview.api good enough to open the
 * real page from a static file server and take screenshots at each of four
 * states (idle / armed / shootout / alert), chosen with a `?state=` query
 * parameter. It is intentionally dumb: `command()` mutates a small amount of
 * local state so the arm/disarm and +/- controls are visually exercised, but
 * it is not a rules engine and must never be mistaken for one. Real
 * correctness is proven against the actual bridge in tests/ui/.
 */
(function () {
  'use strict';

  function clockValue(display, running, seconds, maximum, label, status) {
    return {display: display, status: status || (running ? 'RUNNING' : 'STOPPED'),
      running: running, seconds: seconds, maximum_seconds: maximum,
      full_display: display, label: label};
  }

  function identity(primary, secondary, shortName) {
    return {primary: primary, secondary: secondary, short_name: shortName};
  }

  function statBlock(shots, saves, corners, fouls, yellow, red) {
    return {
      shots: shots, saves: saves, corners: corners, fouls: fouls,
      shots_display: 'S ' + shots, saves_display: 'SV ' + saves,
      corners_display: 'COR ' + corners, fouls_display: 'F ' + fouls,
      shots_saves_display: 'S ' + shots + '·SV ' + saves,
      cards: {
        yellow: yellow, red: red,
        display: (yellow || red) ? ('Y ' + yellow + ' · R ' + red) : '',
        rows: []
      }
    };
  }

  var RULE_FIELDS = [
    {name: 'half_seconds', kind: 'clock', minutes: 40, seconds: 0, display: '40:00'},
    {name: 'halftime_seconds', kind: 'clock', minutes: 10, seconds: 0, display: '10:00'},
    {name: 'warmup_seconds', kind: 'clock', minutes: 3, seconds: 0, display: '3:00'},
    {name: 'pregame_seconds', kind: 'clock', minutes: 30, seconds: 0, display: '30:00'},
    {name: 'overtime_periods', kind: 'number', value: 2, display: '2'},
    {name: 'overtime_seconds', kind: 'clock', minutes: 10, seconds: 0, display: '10:00'},
    {name: 'golden_goal', kind: 'toggle', value: false, display: 'Off'},
    {name: 'shootout_enabled', kind: 'toggle', value: false, display: 'Off'},
    {name: 'shootout_initial_kickers', kind: 'number', value: 5, display: '5'},
    {name: 'shootout_credit_goal', kind: 'toggle', value: true, display: 'On'},
    {name: 'mercy_differential', kind: 'number', value: 9, display: '9'},
    {name: 'mercy_applies', kind: 'choice', value: 'halftime_and_second_half', display: 'Halftime and second half'},
    {name: 'stop_clock_on_goal', kind: 'toggle', value: true, display: 'On'},
    {name: 'clock_direction', kind: 'choice', value: 'down', display: 'Down'},
    {name: 'weather_seconds', kind: 'clock', minutes: 30, seconds: 0, display: '30:00'}
  ];

  function baseView(overrides) {
    var homeName = 'EAGLES OF THE EASTERN CONFERENCE'; // 24+ chars to exercise ellipsis
    var awayName = 'TIGERS ATHLETIC ASSOCIATION';
    var view = {
      revision: 12,
      teams: {
        home: {name: homeName.slice(0, 24), score: 1, identity: identity('#08439A', '#F5AE08', 'EAGL')},
        away: {name: awayName.slice(0, 24), score: 0, identity: identity('#A50021', '#0A0A0A', 'TIGR')}
      },
      period: '1st',
      period_display: '1st Half',
      period_next_display: 'next: ▶ HALFTIME 10:00',
      lifecycle: 'IN_PROGRESS',
      clocks: {
        game: clockValue('40:00', false, 2400, 2400, 'GAME CLOCK'),
        event: {display: '', status: '', running: false, warmup_follows: ''}
      },
      soccer: {
        home: statBlock(4, 2, 3, 1, 0, 0),
        away: statBlock(6, 3, 5, 2, 1, 0),
        shootout: {
          active: false, first_kicker: null, winner: null, round: 1, round_display: 'ROUND 1',
          sudden_death: false, next_team: 'home', next_team_display: '· HOME TO KICK',
          home_display: '', away_display: '', tally_display: '', home_made: 0, away_made: 0,
          decided: false
        }
      },
      status: {display: '—', active: false, label: null, clock_display: '', clock: {running: false}},
      board: {hidden_widgets: []},
      mercy_reached: false,
      period_decision: {pending: false, period: null, token: 0, choices: []},
      rules: {half_seconds: 2400, weather_seconds: 1800},
      rule_fields: RULE_FIELDS,
      status_labels: ['INJURY', 'DELAY', 'WEATHER'],
      last_action: {label: 'HOME shots +1 → 4'},
      can_undo: true,
      undo_history: [{label: 'HOME shots +1 → 4'}, {label: 'AWAY saves +1 → 3'}],
      undo_depth: 2,
      setup: {teams_pending: false, home_pending: false, away_pending: false, detail: ''},
      health: {
        display: {label: 'DISPLAY OPEN', open: true, can_reopen: true, detail: '', target: ''},
        persistence: {label: 'SAVED', saved: true, message: ''}
      },
      cutscenes: {playing: null, auto_goal: true},
      button_box: {active: true, failed: [], fallback: false, error: null},
      period_labels: ['PRE', '1st', 'HALF', '2nd', 'OT1', 'OT2', 'SHOOTOUT', 'FINAL']
    };
    return Object.assign(view, overrides || {});
  }

  function armedView() {
    var view = baseView({last_action: {label: 'nothing yet'}});
    return view; // armed state is exercised by clicking SCORE in the browser
  }

  function shootoutView() {
    return baseView({
      period: 'SHOOTOUT',
      period_display: 'Shootout',
      teams: {
        home: {name: 'EAGLES', score: 1, identity: identity('#08439A', '#F5AE08', 'EAGL')},
        away: {name: 'TIGERS', score: 1, identity: identity('#A50021', '#0A0A0A', 'TIGR')}
      },
      soccer: {
        home: statBlock(4, 2, 3, 1, 0, 0),
        away: statBlock(6, 3, 5, 2, 1, 0),
        shootout: {
          active: true, first_kicker: 'home', winner: null, round: 3, round_display: 'ROUND 3',
          sudden_death: false, next_team: 'away', next_team_display: '· AWAY TO KICK',
          home_display: '● ● ○', away_display: '● ○', tally_display: '2-1',
          home_made: 2, away_made: 1, decided: false
        }
      }
    });
  }

  function alertView() {
    var view = baseView({
      mercy_reached: false,
      status: {display: 'WEATHER', active: true, label: 'WEATHER', clock_display: '29:42', clock: {running: true}}
    });
    view.health.persistence = {label: 'NOT SAVED', saved: false, message: 'The last save failed: disk full.'};
    return view;
  }

  var state = new URLSearchParams(window.location.search).get('state') || 'idle';
  var current = state === 'armed' ? armedView() : state === 'shootout' ? shootoutView() :
    state === 'alert' ? alertView() : baseView();

  function resolved(value) {
    return Promise.resolve(value);
  }

  window.pywebview = {
    api: {
      get_snapshot: function () { return resolved(current); },
      command: function (name, args, expectedRevision) {
        // A tiny, deliberately inexact mutation so the preview reflects a
        // press without pretending to be a rules engine.
        current = Object.assign({}, current, {revision: current.revision + 1,
          last_action: {label: name + ' (preview)'}});
        return resolved({accepted: true, view: current});
      },
      rules: function () { return resolved({rules: current.rules, fields: RULE_FIELDS, default_fields: RULE_FIELDS}); },
      save_rules: function (payload) { return resolved({ok: true, saved: true, message: 'Saved (preview only).', fields: RULE_FIELDS}); },
      teams: function () { return resolved({teams: [], current: {home: current.teams.home.identity, away: current.teams.away.identity}}); },
      displays: function () { return resolved({displays: [], current_key: null, saved_label: null}); },
      data_folder: function () { return resolved({root: '(preview)', explanation: 'Preview only.'}); },
      trigger_cutscene: function () { return resolved({message: 'Cutscene triggered (preview).'}); },
      cancel_cutscene: function () { return resolved({message: 'Cutscene cancelled (preview).'}); },
      open_field_assistant: function () { return resolved({message: 'Field Assistant opened (preview).'}); },
      open_cutscenes: function () { return resolved({message: 'Cutscenes opened (preview).'}); },
      open_test_window: function () { return resolved({message: 'Test window opened (preview).'}); },
      open_layout_editor: function () { return resolved({message: 'Layout editor opened (preview).'}); },
      open_logs_folder: function () { return resolved({message: 'Logs folder opened (preview).'}); },
      reopen_display: function () { return resolved(current); },
      close_display: function () { return resolved({status: {detail: 'Closed (preview).'}}); },
      choose_data_folder: function () { return resolved({message: 'Preview only.'}); },
      use_default_folder: function () { return resolved({message: 'Preview only.'}); },
      forget_display: function () { return resolved({}); },
      select_display: function () { return resolved({}); },
      save_team: function () { return resolved({teams: [], message: 'Saved (preview only).'}); },
      delete_team: function () { return resolved({teams: [], message: 'Deleted (preview only).'}); }
    }
  };
})();
