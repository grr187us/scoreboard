/* Focused-window input adapter for the soccer operator page.
 *
 * A fresh table (spec 4.5), not a copy of football's `views/operator/
 * keyboard.js`: soccer has no play clock, no down/distance, and its own
 * scoring/card/crowd vocabulary. The binding-table structure (an array of
 * {key, label, action, ...} objects, `install(options)`, and the same
 * editable/repeat/held guards) is kept identical to football's so a
 * source-contract test can lift the table the same way
 * tests/integration/test_keyboard_source.py does for football.
 */
(function (global) {
  'use strict';
  var bindings = [
    {key: ' ', label: 'Space', action: 'Game clock Start / Stop', clock: 'game'},
    // Scoring is two steps for the keyboard too (spec 4.2): the first press
    // routes through `options.score`, which arms that team on the first
    // press and sends `add_goal` the binding already names on the second.
    {key: 'g', label: 'G', action: 'Home goal (press once to arm, again to apply)', command: 'add_goal', args: {team: 'home'}, arm: 'home'},
    {key: 'h', label: 'H', action: 'Away goal (press once to arm, again to apply)', command: 'add_goal', args: {team: 'away'}, arm: 'away'},
    {key: 'q', label: 'Q', action: 'Period forward', command: 'period_forward'},
    {key: 'q', shift: true, label: 'Shift+Q', action: 'Period back', command: 'period_back'},
    {key: 'a', label: 'A', action: 'Home shots +1', command: 'add_stat', args: {team: 'home', stat: 'shots', step: 1}},
    {key: 'a', shift: true, label: 'Shift+A', action: 'Home shots -1', command: 'add_stat', args: {team: 'home', stat: 'shots', step: -1}},
    {key: 's', label: 'S', action: 'Home saves +1', command: 'add_stat', args: {team: 'home', stat: 'saves', step: 1}},
    {key: 's', shift: true, label: 'Shift+S', action: 'Home saves -1', command: 'add_stat', args: {team: 'home', stat: 'saves', step: -1}},
    {key: 'd', label: 'D', action: 'Home corners +1', command: 'add_stat', args: {team: 'home', stat: 'corners', step: 1}},
    {key: 'd', shift: true, label: 'Shift+D', action: 'Home corners -1', command: 'add_stat', args: {team: 'home', stat: 'corners', step: -1}},
    {key: 'f', label: 'F', action: 'Home fouls +1', command: 'add_stat', args: {team: 'home', stat: 'fouls', step: 1}},
    {key: 'f', shift: true, label: 'Shift+F', action: 'Home fouls -1', command: 'add_stat', args: {team: 'home', stat: 'fouls', step: -1}},
    {key: 'j', label: 'J', action: 'Away shots +1', command: 'add_stat', args: {team: 'away', stat: 'shots', step: 1}},
    {key: 'j', shift: true, label: 'Shift+J', action: 'Away shots -1', command: 'add_stat', args: {team: 'away', stat: 'shots', step: -1}},
    {key: 'k', label: 'K', action: 'Away saves +1', command: 'add_stat', args: {team: 'away', stat: 'saves', step: 1}},
    {key: 'k', shift: true, label: 'Shift+K', action: 'Away saves -1', command: 'add_stat', args: {team: 'away', stat: 'saves', step: -1}},
    {key: 'l', label: 'L', action: 'Away corners +1', command: 'add_stat', args: {team: 'away', stat: 'corners', step: 1}},
    {key: 'l', shift: true, label: 'Shift+L', action: 'Away corners -1', command: 'add_stat', args: {team: 'away', stat: 'corners', step: -1}},
    {key: ';', label: ';', action: 'Away fouls +1', command: 'add_stat', args: {team: 'away', stat: 'fouls', step: 1}},
    {key: ';', shift: true, label: 'Shift+;', action: 'Away fouls -1', command: 'add_stat', args: {team: 'away', stat: 'fouls', step: -1}},
    // Card keys arm the card panel (spec 4.2); CONFIRM/Enter applies once the
    // operator has typed a number or pressed NO #. Neither key sends a
    // command by itself -- both route through `options.card`.
    {key: 'y', label: 'Y', action: 'Home yellow card (arms the card panel)', card: {team: 'home', kind: 'yellow'}},
    {key: 'y', shift: true, label: 'Shift+Y', action: 'Away yellow card (arms the card panel)', card: {team: 'away', kind: 'yellow'}},
    {key: 'r', label: 'R', action: 'Home red card (arms the card panel)', card: {team: 'home', kind: 'red'}},
    {key: 'r', shift: true, label: 'Shift+R', action: 'Away red card (arms the card panel)', card: {team: 'away', kind: 'red'}},
    {key: 'i', label: 'I', action: 'Crowd INJURY', command: 'set_game_status', args: {label: 'INJURY'}},
    {key: 'e', label: 'E', action: 'Crowd DELAY', command: 'set_game_status', args: {label: 'DELAY'}},
    {key: 'w', label: 'W', action: 'Crowd WEATHER', command: 'set_game_status', args: {label: 'WEATHER', seconds: 1800}},
    {key: 'x', label: 'X', action: 'Clear crowd message', command: 'clear_game_status'},
    // Undo names what it reverses before it sends anything (spec 3.2).
    {key: 'z', ctrl: true, label: 'Ctrl+Z', action: 'Undo last reversible command', command: 'undo', confirm: true, title: 'Undo the last action?'},
    {key: 'escape', label: 'Esc', action: 'Close dialog / drawer / disarm', close: true},
    // Cutscenes are a host concern, not a Command: they route through
    // `options.host(name, args)` instead of `options.submit`. Soccer has one
    // built-in cutscene (GOAL, spec section 7); the number row keeps the
    // letters above free of a collision (design draft section 3).
    {key: '1', label: '1', action: 'Replay GOAL cutscene (home)', host: 'trigger_cutscene', args: ['goal', 'home']},
    {key: '1', shift: true, label: 'Shift+1', action: 'Replay GOAL cutscene (away)', host: 'trigger_cutscene', args: ['goal', 'away']},
    {key: 'c', shift: true, label: 'Shift+C', action: 'Cancel cutscene', host: 'cancel_cutscene'}
  ];

  function editable(target) {
    return target && (target.isContentEditable ||
      (target.closest && target.closest('input, textarea, select, [contenteditable]')));
  }

  function install(options) {
    var held = new Set();
    document.addEventListener('keydown', function (event) {
      var identity = event.code || event.key;
      var alreadyHeld = held.has(identity);
      held.add(identity);
      if (event.isComposing || event.keyCode === 229 || event.altKey || event.metaKey) return;
      if (event.key === 'Enter' && event.target.closest && event.target.closest('button')) {
        if (event.repeat || alreadyHeld) event.preventDefault();
        return;
      }
      var binding = bindings.find(function (item) {
        return item.key === event.key.toLowerCase() && Boolean(item.ctrl) === event.ctrlKey &&
          Boolean(item.shift) === event.shiftKey;
      });
      if (!binding) return;
      if (binding.close) {
        event.preventDefault();
        if (!event.repeat && !alreadyHeld) options.close();
        return;
      }
      if (editable(event.target) || editable(document.activeElement)) return;
      event.preventDefault();
      if (event.repeat || alreadyHeld || options.blocked()) return;
      var snapshot = options.snapshot();
      if (!snapshot) return;
      if (binding.host) {
        options.host(binding.host, binding.args || []);
        return;
      }
      if (binding.card) {
        options.card(binding.card);
        return;
      }
      if (binding.arm) {
        options.score(binding);
        return;
      }
      if (binding.confirm) {
        options.confirm(binding.command, Object.assign({}, binding.args),
          {title: binding.title});
        return;
      }
      var command = binding.clock ?
        (snapshot.clocks.game.running ? 'game_clock_stop' : 'game_clock_start') : binding.command;
      options.submit(command, Object.assign({}, binding.args), {source: 'operator-keyboard'});
    });
    document.addEventListener('keyup', function (event) { held.delete(event.code || event.key); });
    global.addEventListener('blur', function () { held.clear(); });
    var help = document.getElementById('shortcut-list');
    bindings.forEach(function (binding) {
      var row = document.createElement('tr');
      var key = document.createElement('th');
      key.scope = 'row'; key.textContent = binding.label;
      var action = document.createElement('td'); action.textContent = binding.action;
      row.append(key, action); help.appendChild(row);
    });
  }
  global.ScoreboardKeyboard = {install: install};
})(window);
