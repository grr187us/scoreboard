/* Focused-window input adapter; the binding table also produces shortcut help. */
(function (global) {
  'use strict';
  var bindings = [
    {key: ' ', label: 'Space', action: 'Game clock Start / Stop', clock: 'game'},
    {key: '2', label: '2', action: 'Load play clock 25 (stopped)', command: 'play_clock_preset', args: {seconds: 25}},
    {key: '4', label: '4', action: 'Load play clock 40 (stopped)', command: 'play_clock_preset', args: {seconds: 40}},
    {key: 'p', label: 'P', action: 'Start play clock', command: 'play_clock_start'},
    {key: 's', label: 'S', action: 'Stop play clock', command: 'play_clock_stop'},
    // Button box (hardware/scoreboard_button_box, September 10, 2026 pin map):
    // D4-D9 play clock buttons, and a D10 rocker that sends F21 when flipped
    // on and F22 when flipped off. F13/F14 (the old game clock paddle) are
    // deliberately unbound: the rocker is the only hardware game clock control.
    {key: 'f15', label: 'F15', action: 'Load play clock 40 and start (Quick 40)', command: 'play_clock_preset_start', args: {seconds: 40}},
    {key: 'f16', label: 'F16', action: 'Load play clock 25 and start (Quick 25)', command: 'play_clock_preset_start', args: {seconds: 25}},
    {key: 'f17', label: 'F17', action: 'Load play clock 40 (stopped)', command: 'play_clock_preset', args: {seconds: 40}},
    {key: 'f18', label: 'F18', action: 'Load play clock 25 (stopped)', command: 'play_clock_preset', args: {seconds: 25}},
    {key: 'f19', label: 'F19', action: 'Start play clock', command: 'play_clock_start'},
    {key: 'f20', label: 'F20', action: 'Clear play clock', command: 'play_clock_clear'},
    {key: 'f21', label: 'F21', action: 'Start game clock (rocker on)', command: 'game_clock_start'},
    {key: 'f22', label: 'F22', action: 'Stop game clock (rocker off)', command: 'game_clock_stop'},
    {key: 'q', label: 'Q', action: 'Quarter forward', command: 'quarter_forward'},
    {key: 'q', shift: true, label: 'Shift+Q', action: 'Quarter back', command: 'quarter_back'},
    // Scoring is two steps for the keyboard too (control refresh spec 2.8):
    // `arm` routes the key through `options.score`, which arms that team on
    // the first press and sends the command the binding already names on the
    // second. The command and args are unchanged, so the help table and the
    // bridge still see exactly the same eight scoring shortcuts.
    {key: 'z', label: 'Z', action: 'Home +1 (press once to arm, again to apply)', command: 'add_score', args: {team: 'home', points: 1}, arm: 'home'},
    {key: 'x', label: 'X', action: 'Home +2 (press once to arm, again to apply)', command: 'add_score', args: {team: 'home', points: 2}, arm: 'home'},
    {key: 'c', label: 'C', action: 'Home +3 (press once to arm, again to apply)', command: 'add_score', args: {team: 'home', points: 3}, arm: 'home'},
    {key: 'v', label: 'V', action: 'Home +6 (press once to arm, again to apply)', command: 'add_score', args: {team: 'home', points: 6}, arm: 'home'},
    {key: 'n', label: 'N', action: 'Away +1 (press once to arm, again to apply)', command: 'add_score', args: {team: 'away', points: 1}, arm: 'away'},
    {key: 'm', label: 'M', action: 'Away +2 (press once to arm, again to apply)', command: 'add_score', args: {team: 'away', points: 2}, arm: 'away'},
    {key: ',', label: ',', action: 'Away +3 (press once to arm, again to apply)', command: 'add_score', args: {team: 'away', points: 3}, arm: 'away'},
    {key: '.', label: '.', action: 'Away +6 (press once to arm, again to apply)', command: 'add_score', args: {team: 'away', points: 6}, arm: 'away'},
    // Undo names what it reverses before it sends anything (owner decision 3).
    {key: 'z', ctrl: true, label: 'Ctrl+Z', action: 'Undo last reversible command', command: 'undo', confirm: true, title: 'Undo the last action?'},
    {key: 'escape', label: 'Esc', action: 'Close dialog / drawer', close: true},
    // Cutscenes are a host concern, not a Command: these route through
    // `options.host(name, args)` instead of `options.submit`, but otherwise
    // pass through the exact same editable/repeat/held guards below. Each
    // key names an event only -- a cutscene is always the home team's (or,
    // for the penalty flag, nobody's), so there is no side to pick. `O` is
    // the turnover and `L` is "get Loud"; both were free letters (N/M are
    // away scores, P/S the play clock).
    {key: 'd', label: 'D', action: 'Cutscene: First down', host: 'trigger_cutscene', args: ['first_down']},
    {key: 't', label: 'T', action: 'Cutscene: Touchdown', host: 'trigger_cutscene', args: ['touchdown']},
    {key: 'o', label: 'O', action: 'Cutscene: Turnover', host: 'trigger_cutscene', args: ['turnover']},
    {key: 'f', label: 'F', action: 'Cutscene: Penalty flag', host: 'trigger_cutscene', args: ['penalty']},
    {key: 'l', label: 'L', action: 'Cutscene: Make some noise', host: 'trigger_cutscene', args: ['make_some_noise']},
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
      // Preserve native Enter accessibility, but never allow a held Enter to
      // repeatedly activate a focused score button.
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
      // Prevent a focused button's native Space click as well as repeated shortcuts.
      event.preventDefault();
      if (event.repeat || alreadyHeld || options.blocked()) return;
      var snapshot = options.snapshot();
      if (!snapshot) return;
      if (binding.host) {
        options.host(binding.host, binding.args || []);
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
