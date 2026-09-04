from __future__ import annotations

import unittest

from scoreboard.host.displays import enumerate_displays, selected_screen
from scoreboard.host.app import WindowHost


class FakeScreen:
    def __init__(self, x: int, y: int, width: int, height: int, scale: float) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.scale = scale


class DisplaySelectionTests(unittest.TestCase):
    def test_enumeration_exposes_stable_operator_labels(self) -> None:
        displays = enumerate_displays(
            [FakeScreen(0, 0, 1920, 1080, 1.0), FakeScreen(1920, 0, 1280, 720, 1.25)]
        )

        self.assertEqual(displays[0].label, "Display 1: 1920x1080 at 0,0 (1x)")
        self.assertEqual(displays[1].label, "Display 2: 1280x720 at 1920,0 (1.25x)")

    def test_missing_selection_never_falls_back_to_primary(self) -> None:
        screens = [FakeScreen(0, 0, 1920, 1080, 1.0)]

        self.assertIsNone(selected_screen(screens, 1))
        self.assertIsNone(selected_screen(screens, -1))

    def test_selected_screen_keeps_the_requested_display_object(self) -> None:
        screens = [FakeScreen(0, 0, 1920, 1080, 1.0), FakeScreen(-1280, 0, 1280, 720, 1.0)]

        self.assertIs(selected_screen(screens, 1), screens[1])

    def test_closing_a_replaced_spectator_does_not_clear_the_new_window(self) -> None:
        host = WindowHost(initial_display_index=0)
        replaced_window = object()
        current_window = object()
        host.spectator_window = current_window  # type: ignore[assignment]

        host._spectator_closed(replaced_window)  # type: ignore[arg-type]
        self.assertIs(host.spectator_window, current_window)

        host._spectator_closed(current_window)  # type: ignore[arg-type]
        self.assertIsNone(host.spectator_window)
        self.assertEqual(host.status, "DISPLAY CLOSED: Select a display and reopen it")
