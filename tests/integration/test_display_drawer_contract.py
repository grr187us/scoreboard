"""Audit item C5: a dedicated Display drawer and a 44px Reopen (source contract).

These assert against the operator source files rather than a browser, in the
same style as ``tests/integration/test_bridge.py`` and
``tests/integration/test_data_folder.py::OperatorControlTests``: they prove
the markup and script carry the right shape without needing a webview. The
one thing this file deliberately does not attempt is the U-001 visual fit at
the two supported viewports -- that is a Playwright check run by hand and
recorded in the implementation report, not something a source-text assertion
can prove.
"""

from __future__ import annotations

import unittest
from pathlib import Path

VIEWS = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"


class DisplayDrawerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.css = (VIEWS / "operator" / "operator.css").read_text(encoding="utf-8")
        self.js = (VIEWS / "operator" / "operator.js").read_text(encoding="utf-8")
        self.html = (VIEWS / "operator" / "index.html").read_text(encoding="utf-8")

    def test_the_reopen_button_meets_the_44px_floor(self) -> None:
        self.assertIn(".chip-button", self.css)
        chip_button_rule = self.css.split(".chip-button {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: var(--touch)", chip_button_rule)

    def test_no_32px_concession_remains(self) -> None:
        self.assertNotIn("32px", self.css)

    def test_close_drawers_names_the_display_drawer(self) -> None:
        close_drawers = self.js.split("function closeDrawers()", 1)[1].split(
            "}", 1
        )[0]
        self.assertIn("'display-drawer'", close_drawers)

    def test_reopen_display_opens_the_display_drawer_not_corrections(self) -> None:
        handler = self.js.split("reopen_display'", 1)[1]
        # The needs_selection branch is a short, self-contained block ending at
        # the callback's close; capturing up to the next top-level "} else"/
        # function boundary is enough to see which drawer it opens.
        handler = handler.split("function openDrawer", 1)[0]
        self.assertIn("openDrawer('display-drawer')", handler)
        self.assertNotIn("openDrawer('corrections')", handler)

    def test_the_display_drawer_holds_only_host_actions(self) -> None:
        drawer = self.html.split('<div class="drawer" id="display-drawer"', 1)[1]
        drawer = drawer.split('<div class="drawer" id="setup-drawer"', 1)[0]

        self.assertNotIn("data-command", drawer)
        self.assertNotIn("danger", drawer)
        # And it really is the drawer under test: the controls the audit item
        # names should all be here.
        self.assertIn('id="display-row"', drawer)
        self.assertIn('id="display-choices"', drawer)
        self.assertIn('data-action="forget_display"', drawer)
        self.assertIn('data-action="reopen_display"', drawer)


if __name__ == "__main__":
    unittest.main()
