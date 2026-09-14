"""Field Assistant host lifecycle contract (FA-25 through FA-27).

These use pywebview-shaped fakes: no native window is claimed as evidence.
They prove the host containment policy -- an optional helper can disappear or
fail without reaching clocks, persistence, the primary operator, or spectator.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from scoreboard.host.app import ScoreboardApplication, WindowHost, view_url
from scoreboard.host.bridge import FieldAssistantBridge
from scoreboard.infrastructure.diagnostics import NullDiagnostics

from tests.integration.support import TemporaryDataDirectoryTest


class _Event:
    def __init__(self) -> None:
        self.handlers: list[Any] = []

    def __iadd__(self, handler: Any) -> "_Event":
        self.handlers.append(handler)
        return self

    def is_set(self) -> bool:
        return True


class _Events:
    def __init__(self) -> None:
        self.closed = _Event()
        self.closing = _Event()
        self.loaded = _Event()


class _Window:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.events = _Events()
        self.destroyed = False
        self.scripts: list[str] = []
        self.fail_push = False

    def destroy(self) -> None:
        self.destroyed = True

    def evaluate_js(self, script: str) -> None:
        if self.fail_push:
            raise RuntimeError("helper renderer stopped")
        self.scripts.append(script)


class FieldAssistantDraftOwnershipTests(unittest.TestCase):
    """The helper is pushed a complete snapshot ten times a second.

    A source-level contract, in the style of the layout-editor contract test.
    Live sync (PL-2, September 14, 2026): every push is adopted as the new
    base revision and Confirm is never disabled by a change made elsewhere.
    The draft ball follows the board until the operator moves it; from then
    on only a committed action or the explicit discard button gives it back.
    Re-seeding a touched ball on an ordinary refresh push pulled it back to
    the persisted spot between an operator's click and the next frame, so no
    nudge, drag, or yard selection could ever be finalized.
    """

    def setUp(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src" / "scoreboard" / "views" / "field_assistant" / "field_assistant.js"
        )
        self.source = path.read_text(encoding="utf-8")
        self.html = (path.parent / "index.html").read_text(encoding="utf-8")

    def test_every_push_is_adopted_and_never_disables_confirm(self) -> None:
        # The old gate: a push whose revision differed from the one captured
        # on open showed the red banner and disabled Confirm. It must not
        # come back in any of its four forms (render, preview, confirm, and
        # the STALE_REVISION rejection handler).
        self.assertNotIn("markStale", self.source)
        self.assertNotIn("model.revision !== baseRevision", self.source)
        self.assertNotIn("if (baseRevision === null) baseRevision = model.revision;", self.source)
        self.assertIn("baseRevision = model.revision;", self.source)
        self.assertNotIn('id="stale"', self.html)
        self.assertNotIn("RE-SYNC REQUIRED", self.html)
        # A pending press is re-previewed against the new state without
        # disabling Confirm (scheduleAutoPreview disables; preview() does not).
        self.assertIn("if (revisionChanged && selected && api && autoPreviewTimer === null) preview();", self.source)

    def test_a_refresh_push_reseeds_the_ball_only_while_it_is_untouched(self) -> None:
        self.assertNotIn("!dragging && !draft", self.source)
        self.assertNotIn("pendingReseed", self.source)
        self.assertIn("if (!ballTouched && live !== draftAbsolute) {", self.source)
        # Every operator way of moving the ball marks it touched: click/drag,
        # arrow keys and the nudge buttons (both through nudgeScreen), and
        # the typed yard line.
        self.assertEqual(self.source.count("touchBall();"), 3)
        self.assertIn("field.addEventListener('pointerdown', function (e) { dragging = true; touchBall();", self.source)
        nudge = self.source.split("function nudgeScreen")[1].split("}")[0]
        self.assertIn("touchBall();", nudge)
        selects = self.source.split("function syncDraftFromSelects")[1].split("}")[0]
        self.assertIn("touchBall();", selects)
        self.assertIn("nudgeScreen(e.key === 'ArrowRight' ? 1 : -1);", self.source)

    def test_only_a_commit_a_refused_race_and_discard_give_the_ball_back(self) -> None:
        # Three release sites and no fourth: an accepted commit or a refused
        # STALE_REVISION race, and the explicit "Discard draft & reload".
        self.assertEqual(self.source.count("ballTouched = false;"), 2)
        self.assertIn("if (result.accepted || isStale(result)) ballTouched = false;", self.source)
        resync = self.source.split("function resync()")[1].split("function select(")[0]
        self.assertIn("ballTouched = false;", resync)
        self.assertIn("Discard draft &amp; reload", self.html)

    def test_penalty_is_reachable_from_the_try_screen(self) -> None:
        # PL-6: the score panel (which stays open on the try after a touchdown)
        # offers PENALTY… and FIX MANUALLY…, and the penalty panel no longer
        # closes itself when nobody has the ball -- it explains instead.
        score_panel = self.html.split('data-panel="score"', 1)[1].split('data-panel="manual"', 1)[0]
        self.assertIn('data-open="penalty"', score_panel)
        self.assertIn('data-open="manual"', score_panel)
        self.assertIn('id="penalty-no-series"', self.html)
        self.assertNotIn("if (openPanel === 'penalty' && !f.possession) openPanel = null;", self.source)
        self.assertIn("document.getElementById('penalty-no-series').hidden = Boolean(f.possession);", self.source)

    def test_sides_can_be_swapped_after_the_direction_is_saved(self) -> None:
        # PL-7: the early return that froze the direction buttons is gone; a
        # different side after the save is a swap, with a press-again confirm,
        # and the Swap sides button under the field does the same.
        self.assertNotIn("if (establishedDirection() !== null) return; // saved for this game already", self.source)
        self.assertIn('id="swap-sides"', self.html)
        self.assertIn("api.set_assistant_direction(request, baseRevision)", self.source)
        self.assertIn("requestDirectionChange({ swap: true })", self.source)
        self.assertIn("requestDirectionChange({ value: wanted })", self.source)
        self.assertIn("swapButton.hidden = establishedDirection() === null;", self.source)
        # The page derives no direction of its own for the swap.
        self.assertNotIn("-establishedDirection()", self.source)

    def test_a_late_preview_for_a_press_that_is_gone_is_dropped(self) -> None:
        # PL-6 real run: a commit's own render re-previewed the just-committed
        # touchdown a moment before clearDraft cleared it, and the late answer
        # re-armed Confirm with a second +6. A preview answer is adopted only
        # while the press it describes is still the selected one.
        preview = self.source.split("function preview()", 1)[1].split("function resync()", 1)[0]
        self.assertIn("var pressed = selected;", preview)
        self.assertIn("if (selected !== pressed) return;", preview)
        self.assertLess(preview.index("if (selected !== pressed) return;"), preview.index("draft = request;"))

    def test_a_refused_race_is_a_toast_and_one_more_confirm(self) -> None:
        self.assertIn('id="conflict"', self.html)
        self.assertIn("if (isStale(result)) { showConflict(); preview(); }", self.source)
        self.assertIn("conflict.hidden = true; }, 5000);", self.source)

    def test_operator_changes_ask_python_for_a_fresh_preview(self) -> None:
        # Auto-preview keeps the Proposed panel describing the ball on screen,
        # and disables Confirm until Python has accepted the current draft.
        self.assertIn("function scheduleAutoPreview()", self.source)
        for control in ("kind", "team", "home-direction", "resolution"):
            with self.subTest(control=control):
                self.assertIn(control, self.source)
        self.assertIn("draft = null;\n    confirmButton.disabled = true;", self.source)

    def test_the_bridge_is_attached_on_the_window_ready_event(self) -> None:
        # pywebview dispatches `pywebviewready` on window, never on document. A
        # document listener never fired: `api` stayed null, every preview
        # bailed out silently, and Confirm could never enable -- while the
        # host's applyView pushes still made the page look alive.
        self.assertIn("window.addEventListener('pywebviewready'", self.source)
        self.assertNotIn("document.addEventListener('pywebviewready'", self.source)
        # Whether the API is already present or arrives later, the first
        # snapshot is read through the same path.
        self.assertEqual(self.source.count("attachBridge()"), 2)

    def test_the_draft_still_carries_no_calculated_football_values(self) -> None:
        # The envelope may name the operator's raw choices only. Any of these
        # would mean JavaScript had started deriving a rule Python owns.
        for forbidden in ("payload.down", "payload.distance", "payload.line_to_gain",
                          "payload.score_delta", "payload.possession"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)
        # The manual escape hatch is the one place down/distance travel in a
        # payload, and they must be the operator's pressed values verbatim.
        self.assertIn("down: manualDown, distance: manualDistance", self.source)
        build_action = self.source.split("function buildAction")[1].split("return { kind")[0]
        self.assertNotIn("line_to_gain", build_action)

    def test_the_volunteer_screen_shows_one_panel_at_a_time(self) -> None:
        # No workflow dropdown: the page picks direction -> start -> play from
        # the snapshot, and the sub-panels are reached from big buttons.
        for panel in ("direction", "start", "play", "penalty", "score", "manual"):
            with self.subTest(panel=panel):
                self.assertIn(f'data-panel="{panel}"', self.html)
        self.assertNotIn('id="kind"', self.html)
        self.assertIn("function topPanel()", self.source)
        # Confirm's label is the previewed result, so the operator reads what
        # will happen before it happens.
        self.assertIn("confirmButton.textContent = 'CONFIRM → ' + line;", self.source)


class FieldAssistantWindowTests(TemporaryDataDirectoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.windows: list[_Window] = []
        patcher = mock.patch(
            "scoreboard.host.app.webview.create_window", side_effect=self._create
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.application = ScoreboardApplication(
            self.paths,
            diagnostics=NullDiagnostics(),
            monotonic_clock=self.monotonic,
            acquire_lock=False,
        )
        self.addCleanup(self.application.shutdown)
        self.host = WindowHost(self.application, read_screens=lambda: [])
        self.bridge = self.application.start_new()
        self.bridge.set_field_assistant_opener(self.host.open_field_assistant)

    def _create(self, *args: Any, **kwargs: Any) -> _Window:
        window = _Window(**kwargs)
        self.windows.append(window)
        return window

    def test_open_is_deliberate_similarly_sized_and_reads_the_live_bridge(self) -> None:
        revision = self.bridge.get_snapshot()["revision"]
        result = self.host.open_field_assistant()

        self.assertIn("opened", result["message"].lower())
        window = self.host.field_assistant_window
        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual(window.kwargs["url"], view_url("field_assistant"))
        self.assertEqual((window.kwargs["width"], window.kwargs["height"]), (1180, 720))
        self.assertEqual(window.kwargs["min_size"], (1024, 600))
        self.assertIsInstance(window.kwargs["js_api"], FieldAssistantBridge)
        self.assertEqual(window.kwargs["js_api"].get_snapshot()["revision"], revision)

    def test_close_and_reopen_are_isolated_and_reopening_sees_latest_snapshot(self) -> None:
        self.host.open_field_assistant()
        first = self.host.field_assistant_window
        assert first is not None
        self.bridge.command("add_score", {"team": "home", "points": 6}, 0)
        for handler in first.events.closed.handlers:
            handler(first)
        self.assertIsNone(self.host.field_assistant_window)

        self.host.open_field_assistant()
        second = self.host.field_assistant_window
        assert second is not None
        self.assertEqual(second.kwargs["js_api"].get_snapshot()["teams"]["home"]["score"], 6)
        self.assertFalse(self.application.service is None)

    def test_helper_push_failure_destroys_only_the_helper(self) -> None:
        self.host.open_field_assistant()
        helper = self.host.field_assistant_window
        assert helper is not None
        helper.fail_push = True
        self.bridge.command("game_clock_start", {}, 0)

        self.assertTrue(self.application.service.game_clock.value.running)
        self.assertTrue(helper.destroyed)
        self.assertIsNone(self.host.field_assistant_window)
        self.assertTrue(self.bridge.get_snapshot()["health"]["persistence"]["saved"])

    def test_operator_shutdown_destroys_the_helper(self) -> None:
        self.host.open_field_assistant()
        helper = self.host.field_assistant_window
        assert helper is not None
        self.host._operator_closing()

        self.assertTrue(helper.destroyed)
        self.assertIsNone(self.host.field_assistant_window)

