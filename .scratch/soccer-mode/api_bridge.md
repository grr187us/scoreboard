# Soccer host/bridge API (agent B)

Status: authoritative for `host/soccer_app.SoccerApplication`, `host/soccer_bridge.SoccerBridge`,
`soccer_operator_view_model`, `soccer_spectator_view_model`. Built against `.scratch/soccer-mode/api_domain.md`
(agent A). Update this file if anything below changes.

## `SoccerBridge.command`

```python
def command(
    self, name: str, args: dict | None = None, expected_revision: int | None = None,
    *, source: str = "operator-mouse",
) -> dict: ...
```

The airlock is `domain.soccer.commands.build_soccer_command(name, args, expected_revision, source=...)`.
Unlike football's `build_command`, it does **not** tolerate an extra `"source"` key inside `args` --
`SoccerBridge.command` pulls `args["source"]` out (it wins over the `source=` keyword, so a
button-box-style caller that tags the source inline still works) and forwards the rest. `"confirmed"`
*is* an allowed key on every command and needs no special handling.

Command names/args (from `SOCCER_ALLOWED_ARGUMENTS`, see api_domain.md for the full table):
`set_team_name {team,name}`, `add_goal {team}`, `correct_goal {team, ...}`, `set_score {team,value}`,
`undo {}`, `period_forward {}` (confirmed), `period_back {}` (confirmed), `set_period {label}` (confirmed),
`new_game {}` (confirmed), `end_game {}`, `game_clock_start/stop/reset {}`, `game_clock_correct {seconds}`,
`add_stat {team,stat,step}`, `set_stat {team,stat,value}`, `add_card {team,kind,player}`,
`remove_card {team,index}`, `set_shootout_first_kicker {team}`, `shootout_kick {team,made,player}`,
`shootout_correct_kick {index,made}`, `shootout_remove_last {}`, `finish_shootout {winner}`,
`set_game_status {label,seconds}`, `clear_game_status {}`, `status_clock_start/stop {}`.

## `soccer_operator_view_model` example: idle 1st half, two cards each side

```json
{
  "schema_version": 1,
  "revision": 5,
  "teams": {
    "home": { "name": "HOME", "score": 1, "identity": null },
    "away": { "name": "AWAY", "score": 0, "identity": null }
  },
  "period": "1st",
  "period_display": "1st Half",
  "lifecycle": "IN_PROGRESS",
  "clocks": {
    "game": {
      "seconds": 2400.0, "running": false, "display": "40:00", "status": "STOPPED",
      "maximum_seconds": 2400.0, "full_display": "40:00", "label": "GAME CLOCK"
    },
    "event": {
      "seconds": 0.0, "running": false, "display": "0:00", "status": "STOPPED",
      "phase": "WARMUP", "title": "UNTIL SECOND HALF"
    }
  },
  "soccer": {
    "home": {
      "shots": 0, "shots_display": "S 0", "saves": 0, "saves_display": "SV 0",
      "corners": 0, "corners_display": "COR 0", "fouls": 0, "fouls_display": "F 0",
      "cards": {
        "yellow": 1, "red": 0, "display": "Y 1 · R 0", "yellow_display": "Y 1", "red_display": "",
        "rows": [
          { "team": "home", "kind": "yellow", "player_number": 10, "period": "1st",
            "clock_display": "40:00", "display": "#10 · 40:00 · 1ST" }
        ]
      }
    },
    "away": {
      "shots": 0, "shots_display": "S 0", "saves": 0, "saves_display": "SV 0",
      "corners": 0, "corners_display": "COR 0", "fouls": 0, "fouls_display": "F 0",
      "cards": {
        "yellow": 2, "red": 0, "display": "Y 2 · R 0", "yellow_display": "Y 2", "red_display": "",
        "rows": [
          { "team": "away", "kind": "yellow", "player_number": 4, "period": "1st",
            "clock_display": "40:00", "display": "#4 · 40:00 · 1ST" },
          { "team": "away", "kind": "yellow", "player_number": 7, "period": "1st",
            "clock_display": "40:00", "display": "#7 · 40:00 · 1ST" }
        ]
      }
    },
    "shootout": {
      "active": false, "first_kicker": null, "winner": null, "round": 1, "sudden_death": false,
      "next_team": null, "home_display": "", "away_display": "", "home_made": 0, "away_made": 0,
      "tally_display": "0-0"
    }
  },
  "status": {
    "label": null, "active": false, "display": "", "clock_display": "",
    "clock": { "seconds": 0.0, "running": false, "display": "", "status": "STOPPED" }
  },
  "board": { "hidden_widgets": [] },
  "mercy_reached": false,
  "period_labels": ["PRE", "1st", "HALF", "2nd", "OT1", "OT2", "SHOOTOUT", "FINAL"],
  "rules": { "...": "SoccerRules.to_dict(), see api_domain.md 8" },
  "rule_fields": [
    { "name": "half_seconds", "label": "Half length", "kind": "clock", "value": 2400.0,
      "minutes": 40, "seconds": 0, "display": "40:00" },
    "...",
    { "name": "late_sub_note", "label": "Stop the clock for a leading team's substitution in the last 5:00 (NFHS 7-4-3)",
      "kind": "note", "value": null, "display": "Stop the clock for a leading team's substitution in the last 5:00 (NFHS 7-4-3)" }
  ],
  "status_labels": ["INJURY", "DELAY", "WEATHER"],
  "status_clock_presets": [1800],
  "last_action": { "command": "add_card", "team": "away", "field": "cards", "old_value": 2, "new_value": 3,
                   "label": "Cards 2 → 3" },
  "can_undo": true,
  "undo_history": ["...same shape as last_action, newest first..."],
  "undo_depth": 4,
  "period_decision": { "pending": false, "period": "1st", "token": 0, "choices": [] },
  "setup": { "teams_pending": false, "home_pending": false, "away_pending": false },
  "health": {
    "revision": 5,
    "display": { "open": false, "label": "DISPLAY CLOSED", "target": null, "detail": "Not opened yet.",
                 "can_reopen": true, "needs_selection": false },
    "persistence": { "saved": true, "label": "SAVED", "message": "Game state saved.", "revision": 5,
                     "checkpoint_at": "2026-09-15T13:32:59Z", "using_backup": false, "last_error": null,
                     "pending_history_rows": 0 }
  },
  "cutscenes": { "available": true, "playing": null },
  "button_box": null
}
```

`rule_fields`: a `"note"` row (`late_sub_note`) carries no dataclass field -- its `value` is always
`null` and `display` repeats the `label` text. Every other `kind` (`clock`/`count`/`toggle`/`choice`)
follows football's `_rule_fields_view` pattern (`clock` also gets `minutes`/`seconds`).

`last_action`/`undo_history` labels are generic (`"{subject} {old} → {new}"`); the label for a card
count is `"Cards 2 → 3"` (the undo entry's `field` is the count, not the card itself) -- agents C/G
should not rely on richer wording here without checking `domain.soccer.commands.SoccerUndoEntry`'s
actual `field`/`old_value`/`new_value` for the command they care about.

## During `SHOOTOUT` (after `away` scores kick 1, `home` misses kick 2)

```json
{
  "period": "SHOOTOUT",
  "period_display": "Shootout",
  "board": { "hidden_widgets": ["clocks"] },
  "teams": {
    "home": { "name": "HOME", "score": 0, "identity": null },
    "away": { "name": "AWAY", "score": 0, "identity": null }
  },
  "soccer": {
    "shootout": {
      "active": true, "first_kicker": "away", "winner": null, "round": 2, "sudden_death": false,
      "next_team": "away", "home_display": "○", "away_display": "●",
      "home_made": 0, "away_made": 1, "tally_display": "0-1"
    }
  }
}
```

Notes:
- `board.hidden_widgets` contains `"clocks"` on `FINAL` **and** on `SHOOTOUT` (spec 4.3: the clock
  block is replaced by the shootout panel while `period == SHOOTOUT`; the spectator board hides its
  clock widgets the same way it hides them on FINAL). This is a soccer-only literal, not reused from
  football's `FINAL_HIDDEN_WIDGET_IDS`.
- The shootout score itself (`home wins 4-3, score becomes 2-1`) is only applied by `finish_shootout`
  (not yet exercised above); `shootout_credit_goal` in `rules` controls whether the winner is credited
  +1 goal.
- `next_team` is `null` once `winner` is set or before `set_shootout_first_kicker` has ever run.

## Host actions (mirroring `ScoreboardBridge`)

`get_snapshot()`, `rules()`, `save_rules(payload)`, `teams()`, `save_team(payload)`, `delete_team(name)`,
`displays()`, `select_display(key)`, `forget_display()`, `reopen_display()`, `close_display()`,
`open_test_window()`, `presentation_layout()`, `open_layout_editor()`, `choose_data_folder()`,
`use_default_folder()`, `data_folder()`, `open_logs_folder()`, `open_field_assistant()`,
`open_cutscenes()`, `trigger_cutscene(event, team=None)` (soccer's GOAL event needs `team` -- unlike
football's single-side trigger, there is no side the event alone implies), `cancel_cutscene()`,
`set_button_box_status(status)`, `tick(now=None)`, `shutdown()`, `spectator_snapshot()`,
`display_opened(target)`, `display_closed(detail, needs_selection=False)`.

`SoccerApplication` (`host/soccer_app.py`): same public surface as `ScoreboardApplication`
(`can_resume`, `recovery_payload`, `resume`, `start_new`, `tick`, `set_publisher`,
`set_field_assistant_active`, `set_cutscenes_active`, `set_display_watch`, `start_refresh`,
`stop_refresh`, `display`, `layouts`, `teams`, `rules`, `cutscenes`, `shutdown`, `reopen_spectator`,
`close_spectator`, `spectator_opened`/`closed`, `profile`). `paths` passed to the constructor is the
**root** `ScoreboardPaths`; `self.paths = root.for_sport("soccer")`, `self.root_paths = root` (used only
for the shared `teams.json`). `SOCCER_PROFILE = SportProfile("soccer", "soccer_operator",
"soccer_startup", "soccer_spectator", "soccer_field_assistant", "soccer_cutscenes",
SoccerFieldAssistantBridge, SoccerCutscenesBridge, SOCCER_HOTKEY_TABLE)`.

As of this writing, `presentation.soccer_layout` (agent D), `host.soccer_cutscenes` (agent F), and
`host.soccer_field_assistant` (agent G) all import successfully already -- `SoccerApplication` uses
them directly when they satisfy the expected shape, and only falls back (with a `# TODO(integrator)`
comment) when an import or an attribute is still missing, so the fallback paths are effectively already
dead code for two of the three (cutscenes, field assistant) and only trip for `soccer_layout` in a
build where `infrastructure/layouts.py`'s schema contract (`default_layout`/`validate_layout`/
`validate_layout_name`) is not yet fully implemented by that module.
