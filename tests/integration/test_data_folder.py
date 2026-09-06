"""Choosing where the game and its logs are saved.

The default per-user location is correct but buried, and an operator who wants
the game data on a USB stick or somewhere they can find after a game should not
have to edit an environment variable. These tests cover the choice end to end:
the pointer that remembers it, the resolution order that honours it, and the
operator-facing behaviour when the answer is a cancel, an unusable folder, or a
dialog that will not open at all.

No dialog is ever shown here. The picker is injected, because a test that opens
a real folder dialog would wait for a human forever.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from scoreboard.host import folders
from scoreboard.host.bridge import DisplayLink, ScoreboardBridge
from scoreboard.infrastructure import paths as paths_module
from scoreboard.infrastructure.paths import (
    DATA_DIRECTORY_ENVIRONMENT_VARIABLE,
    PathResolutionError,
    clear_chosen_root,
    describe_resolution,
    read_chosen_root,
    resolve_paths,
    validate_root,
    write_chosen_root,
)

from tests.integration.support import TemporaryDataDirectoryTest


class IsolatedDefaultRootTest(unittest.TestCase):
    """Every test gets its own 'platform default', so none touches the real one."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="scoreboard-folder-")
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name)
        self.default = self.home / "Default"
        self.default.mkdir()

        patcher = mock.patch.object(
            paths_module, "default_root", return_value=self.default
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        # The environment variable outranks a chosen folder, so it must be
        # absent for these tests to exercise the choice at all.
        removed = mock.patch.dict(
            os.environ, {}, clear=False
        )
        removed.start()
        self.addCleanup(removed.stop)
        os.environ.pop(DATA_DIRECTORY_ENVIRONMENT_VARIABLE, None)


class LocationPointerTests(IsolatedDefaultRootTest):
    """The pointer lives in the default root, never in the folder it names."""

    def test_no_choice_resolves_to_the_platform_default(self) -> None:
        self.assertIsNone(read_chosen_root())
        self.assertEqual(resolve_paths().root, self.default)

    def test_a_saved_choice_is_used_on_the_next_resolution(self) -> None:
        target = self.home / "Season 2026"

        saved = write_chosen_root(target)

        self.assertEqual(saved, target)
        self.assertEqual(read_chosen_root(), target)
        self.assertEqual(resolve_paths().root, target)

    def test_the_pointer_is_written_to_the_default_root(self) -> None:
        """A pointer inside the folder it points at could never be found."""

        target = self.home / "Elsewhere"
        write_chosen_root(target)

        pointer = self.default / "data-location.json"
        self.assertTrue(pointer.is_file())
        self.assertEqual(json.loads(pointer.read_text(encoding="utf-8"))["root"],
                         str(target))
        self.assertFalse((target / "data-location.json").exists())

    def test_clearing_the_choice_returns_to_the_default(self) -> None:
        write_chosen_root(self.home / "Somewhere")

        clear_chosen_root()

        self.assertIsNone(read_chosen_root())
        self.assertEqual(resolve_paths().root, self.default)

    def test_clearing_when_nothing_was_chosen_is_not_an_error(self) -> None:
        clear_chosen_root()
        clear_chosen_root()

        self.assertIsNone(read_chosen_root())

    def test_an_explicit_override_still_wins(self) -> None:
        """Every test in this repository passes an override; it must outrank all."""

        write_chosen_root(self.home / "Chosen")
        override = self.home / "Override"

        self.assertEqual(resolve_paths(override).root, override)

    def test_the_environment_variable_outranks_a_chosen_folder(self) -> None:
        """A rehearsal must never be able to write into the real game folder."""

        write_chosen_root(self.home / "Chosen")
        rehearsal = self.home / "Rehearsal"

        with mock.patch.dict(
            os.environ, {DATA_DIRECTORY_ENVIRONMENT_VARIABLE: str(rehearsal)}
        ):
            self.assertEqual(resolve_paths().root, rehearsal)
            self.assertEqual(describe_resolution()["source"], "environment")


class StalePointerTests(IsolatedDefaultRootTest):
    """A saved preference that went bad must never stop the scoreboard."""

    def write_pointer(self, text: str) -> None:
        (self.default / "data-location.json").write_text(text, encoding="utf-8")

    def test_a_corrupt_pointer_falls_back_to_the_default(self) -> None:
        self.write_pointer("{not json")

        self.assertIsNone(read_chosen_root())
        self.assertEqual(resolve_paths().root, self.default)

    def test_a_pointer_without_a_root_falls_back(self) -> None:
        self.write_pointer(json.dumps({"folder": "somewhere"}))

        self.assertIsNone(read_chosen_root())

    def test_a_relative_pointer_is_refused(self) -> None:
        self.write_pointer(json.dumps({"root": "data"}))

        self.assertIsNone(read_chosen_root())

    def test_an_unreachable_folder_falls_back_rather_than_failing(self) -> None:
        """The USB stick is not plugged in tonight. Start anyway."""

        self.write_pointer(json.dumps({"root": str(self.home / "gone" / "deeper")}))

        self.assertIsNone(read_chosen_root())
        self.assertEqual(resolve_paths().root, self.default)

    def test_reading_a_choice_creates_no_directory(self) -> None:
        """Resolving a path must not have side effects."""

        target = self.home / "NotYet"
        self.write_pointer(json.dumps({"root": str(target)}))

        self.assertEqual(read_chosen_root(), target)
        self.assertFalse(target.exists())


class ValidationTests(IsolatedDefaultRootTest):
    """An unusable folder is refused while the operator is still standing there."""

    def test_a_relative_folder_is_refused(self) -> None:
        with self.assertRaises(PathResolutionError):
            validate_root("data")

    def test_a_file_is_not_a_folder(self) -> None:
        target = self.home / "a-file.txt"
        target.write_text("", encoding="utf-8")

        with self.assertRaises(PathResolutionError):
            validate_root(target)

    def test_a_new_folder_is_created_and_written_to(self) -> None:
        target = self.home / "New" / "Nested"

        validated = validate_root(target)

        self.assertEqual(validated, target)
        self.assertTrue(target.is_dir())
        # The write probe must clean up after itself.
        self.assertEqual(list(target.iterdir()), [])


class ChoiceOutcomeTests(IsolatedDefaultRootTest):
    """What comes back from the picker, in the operator's terms."""

    def test_choosing_a_folder_saves_it_and_says_when_it_applies(self) -> None:
        target = self.home / "Chosen"

        with mock.patch.object(folders, "open_folder_dialog", return_value=str(target)):
            choice = folders.choose_data_folder()

        self.assertEqual(choice.outcome, "chosen")
        self.assertTrue(choice.changed)
        self.assertEqual(choice.root, str(target))
        self.assertIn("next time it starts", choice.message)
        self.assertEqual(read_chosen_root(), target)

    def test_cancelling_changes_nothing_and_says_so(self) -> None:
        write_chosen_root(self.home / "Original")

        with mock.patch.object(folders, "open_folder_dialog", return_value=None):
            choice = folders.choose_data_folder()

        self.assertEqual(choice.outcome, "cancelled")
        self.assertFalse(choice.changed)
        self.assertIn("still saving", choice.message)
        self.assertEqual(read_chosen_root(), self.home / "Original")

    def test_an_unusable_folder_is_rejected_without_losing_the_old_one(self) -> None:
        write_chosen_root(self.home / "Original")
        a_file = self.home / "not-a-folder.txt"
        a_file.write_text("", encoding="utf-8")

        with mock.patch.object(folders, "open_folder_dialog", return_value=str(a_file)):
            choice = folders.choose_data_folder()

        self.assertEqual(choice.outcome, "rejected")
        self.assertIn("Nothing was changed", choice.message)
        self.assertEqual(read_chosen_root(), self.home / "Original")

    def test_a_dialog_that_cannot_open_is_reported_not_raised(self) -> None:
        """This is reachable from a button during a game."""

        with mock.patch.object(
            folders, "open_folder_dialog", side_effect=RuntimeError("no shell")
        ):
            choice = folders.choose_data_folder()

        self.assertEqual(choice.outcome, "unavailable")
        self.assertIn("no shell", choice.message)
        self.assertIn(DATA_DIRECTORY_ENVIRONMENT_VARIABLE, choice.message)

    def test_returning_to_the_standard_folder(self) -> None:
        write_chosen_root(self.home / "Chosen")

        choice = folders.use_default_folder()

        self.assertEqual(choice.outcome, "chosen")
        self.assertEqual(choice.root, str(self.default))
        self.assertIsNone(read_chosen_root())

    def test_the_payload_is_json_compatible(self) -> None:
        with mock.patch.object(
            folders, "open_folder_dialog", return_value=str(self.home / "X")
        ):
            payload = folders.choose_data_folder().to_dict()

        json.dumps(payload)
        self.assertIn("location", payload)
        self.assertEqual(payload["location"]["source"], "chosen")


class BridgeFolderTests(TemporaryDataDirectoryTest):
    """The operator's path to the picker changes no game state."""

    def setUp(self) -> None:
        super().setUp()
        self.service, self.store = self.started_session()
        self.choice = folders.FolderChoice(
            outcome="chosen", message="Saved.", root=r"D:\Scoreboard"
        )
        self.bridge = ScoreboardBridge(
            self.service,
            self.store,
            display=DisplayLink(),
            folder_chooser=lambda: self.choice,
        )

    def test_the_open_picker_does_not_hold_up_the_game(self) -> None:
        """A game command submitted while the dialog is open must complete.

        The picker is modal and blocks until the operator answers. If it ran
        under the command lock, every score and clock command -- and the
        refresh tick -- would wait behind it, freezing the board for as long
        as the dialog stayed open. This test opens a "dialog" that, before it
        returns, submits a real command from another thread and waits for it.
        """

        outcome: dict[str, Any] = {}
        finished = threading.Event()

        def command_from_the_operator() -> None:
            outcome["result"] = self.bridge.command(
                "game_clock_start", {}, self.service.revision
            )
            finished.set()

        def blocking_picker() -> folders.FolderChoice:
            worker = threading.Thread(target=command_from_the_operator)
            worker.start()
            # Two seconds is far longer than a real command takes; the only way
            # to run out of time is to be waiting on the lock this thread holds.
            outcome["completed_while_open"] = finished.wait(timeout=2.0)
            worker.join(timeout=2.0)
            return self.choice

        self.bridge = ScoreboardBridge(
            self.service,
            self.store,
            display=DisplayLink(),
            folder_chooser=blocking_picker,
        )

        payload = self.bridge.choose_data_folder()

        self.assertTrue(outcome["completed_while_open"],
                        "a command waited behind the open folder dialog")
        self.assertTrue(outcome["result"]["accepted"], outcome["result"].get("error"))
        self.assertTrue(payload["changed"])
        self.assertTrue(self.service.state.game_clock.running)

    def test_choosing_a_folder_advances_no_revision(self) -> None:
        self.bridge.command("game_clock_start", {}, self.service.revision)
        revision = self.service.revision

        payload = self.bridge.choose_data_folder()

        self.assertEqual(self.service.revision, revision)
        self.assertEqual(payload["view"]["revision"], revision)
        self.assertTrue(payload["changed"])

    def test_a_running_clock_keeps_running(self) -> None:
        self.bridge.command("game_clock_start", {}, self.service.revision)
        self.monotonic.advance(2.0)

        payload = self.bridge.choose_data_folder()

        self.assertTrue(payload["view"]["clocks"]["game"]["running"])
        self.assertEqual(payload["view"]["clocks"]["game"]["display"], "29:58")

    def test_the_payload_carries_the_current_location(self) -> None:
        payload = self.bridge.choose_data_folder()

        self.assertIn("location", payload)
        self.assertIn("root", payload["location"])

    def test_reading_the_location_changes_nothing(self) -> None:
        revision = self.service.revision

        location = self.bridge.data_folder()

        self.assertEqual(self.service.revision, revision)
        self.assertIn("explanation", location)
        json.dumps(location)


class OperatorControlTests(unittest.TestCase):
    """The control exists, and it is not on the always-visible board (U-001)."""

    def setUp(self) -> None:
        views = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"
        self.html = (views / "operator" / "index.html").read_text(encoding="utf-8")
        self.script = (views / "operator" / "operator.js").read_text(encoding="utf-8")

    def test_the_page_offers_both_folder_actions(self) -> None:
        self.assertIn('data-action="choose_data_folder"', self.html)
        self.assertIn('data-action="use_default_folder"', self.html)

    def test_the_control_lives_inside_the_drawer(self) -> None:
        """The drawer scrolls inside itself, so no live control is displaced."""

        drawer = self.html.split('<div class="drawer" id="corrections"', 1)[1]
        drawer = drawer.split('<div class="drawer" id="event-drawer"', 1)[0]

        self.assertIn('data-action="choose_data_folder"', drawer)

    def test_the_folder_control_carries_no_command(self) -> None:
        """It is a host action, not a game command, and must not look like one."""

        row = self.html.split('id="data-folder-row"', 1)[1].split("</div>", 1)[0]

        self.assertNotIn("data-command", row)

    def test_the_script_reads_the_location_on_demand(self) -> None:
        """Not from the view model: resolving it touches the filesystem."""

        self.assertIn("api.data_folder()", self.script)
        self.assertIn("refreshDataFolder", self.script)


if __name__ == "__main__":
    unittest.main()
