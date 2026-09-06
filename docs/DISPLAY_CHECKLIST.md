# Two-display checklist

**Status:** not executed. Every box below is open.
**Last updated:** September 6, 2026 (C5 moved display recovery into the dedicated Display drawer)

Task 10 built display selection, persisted display identity, close and reopen, and disconnect reporting. The *policy* is covered by 73 automated tests that inject a fake screen list, because the development host exposes exactly one display (5120x1440). None of that proves how Windows, WebView2, or the stadium's LED processor actually behave.

This checklist is the other half. Work it on a real two-display Windows machine, then again at the stadium once the Phase 0 HDMI test has been done. Record what happened, including anything that surprised you — a checklist with every box ticked and no notes is less useful than one with a note.

Nothing here may be marked complete on the strength of a passing test suite.

## Before you start

- A Windows laptop with a second display attached over HDMI.
- The scoreboard, either from a checkout or from the rebuilt package (`dist\Scoreboard\Scoreboard.exe`). If it is a package, confirm it was built **after** Task 10 — see `PACKAGING.md`.
- Use an isolated data folder so a rehearsal never touches a real game:

```powershell
$env:SCOREBOARD_DATA_DIR = "$env:TEMP\scoreboard-display-rehearsal"
```

- Have `%LOCALAPPDATA%\Scoreboard\logs\application.log` (or the isolated folder's `logs\`) open in a second window. `DISPLAY_SELECTED`, `DISPLAY_OPENED`, and `DISPLAY_CLOSED` lines are the evidence.

## 1. First run, nothing saved

- [ ] **Two displays, no saved preference.** Launch. The spectator board opens fullscreen on the **second** display, not on the one holding the controls. Record which physical monitor Windows calls Display 2.
- [ ] **Nothing was silently remembered.** Open **Display… → Available now**. It should say *No display saved yet*, even though the board is showing. A default is not a choice.
- [ ] **One display only.** Disconnect the second display and launch again. No spectator window appears over the controls, and the operator says so in plain language. This is the behaviour that protects the operator; confirm it before trusting anything else.
- [ ] **Deliberately choosing the only screen.** With one display, choose it from the panel. The board opens over the controls, because that is what was asked for. `Alt`+`Tab` back to the operator window and confirm the controls still work.

## 2. Choosing and remembering

- [ ] **Choose the second display.** Display… → Available now → click the second display. The board moves there immediately.
- [ ] **It was remembered.** The panel now shows `Saved: <geometry> (\\.\DISPLAYn)`. Confirm the device name is present; if it is blank, note it — matching then falls back to geometry alone.
- [ ] **`config.json` holds it.** Open `config.json` in the data folder and confirm the `display` section matches what the panel showed.
- [ ] **Restart.** Close and relaunch. The board returns to the same physical monitor with no operator action. Record how long from launch to a visible board.
- [ ] **Forget it.** Click **Forget saved display**. The board already on screen must **not** move or close. Relaunch and confirm it falls back to the default rather than the forgotten display.

## 3. Resolution, scaling, and identity

These are the cases where an index would have picked the wrong monitor.

- [ ] **Change the second display's resolution** in Windows display settings while the scoreboard runs. Note what happens to the board immediately, then reopen it and confirm it still lands on the same physical monitor. The panel should report the display was matched with its size changed.
- [ ] **Change Windows scaling** on the second display (100% → 125% → 150%). Same check. Record whether the spectator layout still fills the screen at each setting.
- [ ] **Swap which monitor Windows calls primary** and relaunch. The saved display should still be found — by name if the device name survived, by geometry otherwise. Record which.
- [ ] **Move the second display's arrangement** (left of primary rather than right) and relaunch. Record whether it was matched by name.

## 4. Close, disconnect, reconnect

The clocks must never be affected by any of this. Start the game clock before each one and confirm afterwards that it kept running and shows the time it should.

- [ ] **Close the spectator window by hand** (`Alt`+`F4` on it). Operator stays open, clocks keep running, health strip reads `DISPLAY CLOSED`, and **Reopen Display** brings it back on the same monitor in one click.
- [ ] **Reopen shows the current score.** Change the score *while the board is closed*, then reopen. The board must show the new score immediately, not the score it had when it closed.
- [ ] **Play-clock continuity (D-008).** Start the play clock, close the board, wait five seconds, reopen. The play clock must still be running and showing the correct remaining time. This board is the stadium's only play-clock display, so this one matters more than it looks.
- [ ] **Unplug the HDMI cable** with clocks running. Within a few seconds the health strip must read `DISPLAY NOT FOUND` and say the game is still running and saving. Confirm in the log and confirm the game clock never paused.
- [ ] **Plug it back in.** The scoreboard must **not** move the board on its own. The strip should report the display is back and that Reopen Display will use it. Then reopen and confirm it lands correctly.
- [ ] **Unplug during a running play clock** and reconnect. Note how long Windows took to re-enumerate, and whether the play clock was correct on reopen.
- [ ] **Sleep and wake the laptop** with the board open, then repeat.

## 5. Fullscreen and the spectator surface

- [ ] **No chrome.** Borderless, no title bar, no scrollbars, no cursor artefacts on the second display.
- [ ] **Nothing of the operator's leaks onto it.** No dialog, no alert line, no drawer (D-007).
- [ ] **A confirmation dialog on the operator window** does not appear on, or dim, the spectator display.
- [ ] **The board stays put** when the operator window is moved, maximised, and minimised.

## 6. At the stadium (after the Phase 0 HDMI test)

Do not attempt these until the personal-laptop HDMI test has been done and its result recorded.

- [ ] **Windows sees the processor as a display.** Record the reported name, resolution, refresh rate, scaling, and orientation, and whether a device name appears in the display panel.
- [ ] **Choose it and confirm the geometry.** Photograph the whole wall with the board on it. Record cropping, stretching, seams, offset, and unused pixels.
- [ ] **Safe margins.** Confirm nothing important lands in a cropped region. The 4% inset was chosen without this evidence and may need changing.
- [ ] **Legibility from the stands.** Photograph from the far side and from the near sideline. Note the play clock specifically.
- [ ] **Reselect the processor's HDMI input** away and back. Record whether Windows re-enumerated the display, what the health strip said, and whether the saved display was still matched afterwards.
- [ ] **Power-cycle the processor** if it is safe to do so, and record the same.
- [ ] **Record the match tier.** After each recovery, open the display panel and note whether it says the display was found exactly, by name, or by position. This is the single most useful piece of evidence for whether the identity model is right for this hardware.

## What to write down afterwards

Update, in this order:

1. This file — tick what passed, and write what actually happened next to anything that did not.
2. `PROJECT_ROADMAP.md` — the Test and Evidence Log, and the Task 10 evidence section's **Not claimed** list, which should shrink.
3. `docs/UX_AND_LAYOUT.md` section 9 if the stadium geometry contradicts the logical canvas.
4. `PACKAGING.md` — the **Second display** release check.

If a case fails, record it as a defect rather than adjusting the checklist to match the behaviour.
