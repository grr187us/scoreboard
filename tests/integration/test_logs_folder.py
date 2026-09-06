"""The operator can find the diagnostics log without knowing the path.

After a bad game the most useful thing an operator can hand over is the
application log. It has always existed -- a bounded, rotating file recording
every accepted command, expiry, display event, and failure -- but nothing in
the window pointed at it. ``open_logs_folder`` is a host action that shows the
folder in Explorer and does nothing else: no game state, no revision, no
reading or sending of the file.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from scoreboard.host.bridge import DisplayLink, ScoreboardBridge
from scoreboard.infrastructure.diagnostics import Diagnostics, NullDiagnostics
from tests.integration.support import TemporaryDataDirectoryTest


class OpenLogsFolderTests(TemporaryDataDirectoryTest):
    def setUp(self) -> None:
        super().setUp()
        self.service, self.store = self.started_session()
        self.opened: list[Path] = []
        self.diagnostics = Diagnostics(self.paths, wall_clock=self.wall_clock)
        self.addCleanup(self.diagnostics.close)

    def make_bridge(self, **kwargs: Any) -> ScoreboardBridge:
        kwargs.setdefault("diagnostics", self.diagnostics)
        kwargs.setdefault("logs_opener", self.opened.append)
        return ScoreboardBridge(self.service, self.store, display=DisplayLink(), **kwargs)

    def test_it_opens_the_folder_that_holds_the_log(self) -> None:
        bridge = self.make_bridge()

        payload = bridge.open_logs_folder()

        self.assertTrue(payload["opened"])
        self.assertEqual(self.opened, [Path(self.diagnostics.log_file).parent])
        self.assertEqual(payload["path"], str(self.opened[0]))
        self.assertIn("Opened the logs folder", payload["message"])

    def test_it_advances_no_revision_and_touches_no_clock(self) -> None:
        bridge = self.make_bridge()
        bridge.command("game_clock_start", {}, self.service.revision)
        revision = self.service.revision

        payload = bridge.open_logs_folder()

        self.assertEqual(self.service.revision, revision)
        self.assertEqual(payload["view"]["revision"], revision)
        self.assertTrue(self.service.state.game_clock.running)

    def test_a_refusal_from_windows_is_reported_not_raised(self) -> None:
        def refuse(_: Path) -> None:
            raise OSError("Explorer is not available")

        bridge = self.make_bridge(logs_opener=refuse)

        payload = bridge.open_logs_folder()

        self.assertFalse(payload["opened"])
        self.assertIn("Could not open the logs folder", payload["message"])
        # The path is still told to the operator, so the log can be found by hand.
        self.assertIn(payload["path"], payload["message"])

    def test_without_a_log_file_it_says_so(self) -> None:
        bridge = self.make_bridge(diagnostics=NullDiagnostics())

        payload = bridge.open_logs_folder()

        self.assertFalse(payload["opened"])
        self.assertIsNone(payload["path"])
        self.assertEqual(self.opened, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
