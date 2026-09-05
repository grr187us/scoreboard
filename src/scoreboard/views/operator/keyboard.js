/* Focused-window input adapter; the binding table also produces shortcut help. */
(function (global) {
  'use strict';
  var bindings = [
    {key: ' ', label: 'Space', action: 'Game clock Start / Stop', clock: 'game'},
    {key: '2', label: '2', action: 'Load play clock 25 (stopped)', command: 'play_clock_preset', args: {seconds: 25}},
    {key: '4', label: '4', action: 'Load play clock 40 (stopped)', command: 'play_clock_preset', args: {seconds: 40}},
    {key: 'p', label: 'P', action: 'Start play clock', command: 'play_clock_start'},
    {key: 's', label: 'S', action: 'Stop play clock', command: 'play_clock_stop'},
    {key: 'q', label: 'Q', action: 'Quarter forward', command: 'quarter_forward'},
    {key: 'q', shift: true, label: 'Shift+Q', action: 'Quarter back', command: 'quarter_back'},
    {key: 'z', label: 'Z', action: 'Home +1', command: 'add_score', args: {team: 'home', points: 1}},
    {key: 'x', label: 'X', action: 'Home +2', command: 'add_score', args: {team: 'home', points: 2}},
    {key: 'c', label: 'C', action: 'Home +3', command: 'add_score', args: {team: 'home', points: 3}},
    {key: 'v', label: 'V', action: 'Home +6', command: 'add_score', args: {team: 'home', points: 6}},
    {key: 'n', label: 'N', action: 'Away +1', command: 'add_score', args: {team: 'away', points: 1}},
    {key: 'm', label: 'M', action: 'Away +2', command: 'add_score', args: {team: 'away', points: 2}},
    {key: ',', label: ',', action: 'Away +3', command: 'add_score', args: {team: 'away', points: 3}},
    {key: '.', label: '.', action: 'Away +6', command: 'add_score', args: {team: 'away', points: 6}},
    {key: 'z', ctrl: true, label: 'Ctrl+Z', action: 'Undo last reversible command', command: 'undo'},
    {key: 'escape', label: 'Esc', action: 'Close dialog / drawer', close: true}
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
