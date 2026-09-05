"""Display identity, matching, and change detection, with no window at all.

The development host has one display, so every second-display behaviour has to
be reachable without one. That is why the selection policy is a pure function
of a screen list and a remembered preference: a monitor is unplugged here by
returning a shorter list.

What these tests cannot do is prove that Windows reports what we assume it
reports. Two-display behaviour on real hardware is a manual checklist, in
`docs/DISPLAY_CHECKLIST.md`.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scoreboard.host.app import ScoreboardApplication, WindowHost
from scoreboard.host.displays import (
    MATCH_EXACT,
    MATCH_GEOMETRY,
    MATCH_NAME,
    MATCH_NONE,
    DisplayPreference,
    DisplayWatch,
    default_target,
    enumerate_displays,
    find_by_key,
    match_preference,
    preference_from_dict,
    selected_screen,
)
from scoreboard.infrastructure.diagnostics import NullDiagnostics
from scoreboard.infrastructure.paths import resolve_paths


class FakeScreen:
    def __init__(self, x: int, y: int, width: int, height: int, scale: float) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.scale = scale


#: The shape this project keeps assuming: the operator's laptop panel at the
#: origin, and the wall to its right.
LAPTOP = FakeScreen(0, 0, 1366, 768, 1.0)
WALL = FakeScreen(1366, 0, 1920, 1080, 1.0)


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

    def make_host(self) -> WindowHost:
        """A host with a real application but no window and no data of its own."""

        directory = tempfile.TemporaryDirectory(prefix="scoreboard-displays-")
        self.addCleanup(directory.cleanup)
        application = ScoreboardApplication(
            resolve_paths(Path(directory.name) / "Scoreboard"),
            diagnostics=NullDiagnostics(),
            acquire_lock=False,
        )
        self.addCleanup(application.stop_refresh)
        return WindowHost(application, initial_display_index=0)

    def test_closing_a_replaced_spectator_does_not_clear_the_new_window(self) -> None:
        host = self.make_host()
        replaced_window = object()
        current_window = object()
        host.spectator_window = current_window  # type: ignore[assignment]

        host._spectator_closed(replaced_window)  # type: ignore[arg-type]
        self.assertIs(host.spectator_window, current_window)

        host._spectator_closed(current_window)  # type: ignore[arg-type]
        self.assertIsNone(host.spectator_window)
        self.assertEqual(host.status, "DISPLAY CLOSED: Select a display and reopen it")


class DisplayIdentityTests(unittest.TestCase):
    """A display is recognised by name and geometry, never by list position."""

    def test_device_names_are_attached_in_enumeration_order(self) -> None:
        displays = enumerate_displays([LAPTOP, WALL], [r"\\.\DISPLAY1", r"\\.\DISPLAY2"])

        self.assertEqual(displays[0].name, r"\\.\DISPLAY1")
        self.assertEqual(displays[1].name, r"\\.\DISPLAY2")
        self.assertIn(r"\\.\DISPLAY2", displays[1].description)

    def test_a_missing_name_is_normal_and_leaves_geometry_as_the_identity(self) -> None:
        displays = enumerate_displays([LAPTOP, WALL])

        self.assertIsNone(displays[0].name)
        self.assertEqual(displays[1].key, "1920x1080+1366+0")

    def test_a_short_name_list_names_only_what_it_covers(self) -> None:
        displays = enumerate_displays([LAPTOP, WALL], [r"\\.\DISPLAY1"])

        self.assertEqual(displays[0].name, r"\\.\DISPLAY1")
        self.assertIsNone(displays[1].name)

    def test_the_primary_display_is_the_one_at_the_origin(self) -> None:
        displays = enumerate_displays([LAPTOP, WALL])

        self.assertTrue(displays[0].primary)
        self.assertFalse(displays[1].primary)

    def test_the_key_does_not_move_when_another_display_is_unplugged(self) -> None:
        both = enumerate_displays([LAPTOP, WALL])
        alone = enumerate_displays([WALL])

        # The index changed from 1 to 0; the identity did not.
        self.assertEqual(both[1].index, 1)
        self.assertEqual(alone[0].index, 0)
        self.assertEqual(both[1].key, alone[0].key)

    def test_find_by_key_resolves_a_choice_and_refuses_a_stale_one(self) -> None:
        displays = enumerate_displays([LAPTOP, WALL])

        self.assertIs(find_by_key("1920x1080+1366+0", displays), displays[1])
        self.assertIsNone(find_by_key("1920x1080+9999+0", displays))
        self.assertIsNone(find_by_key(None, displays))
        self.assertIsNone(find_by_key(1, displays))

    def test_a_target_round_trips_through_its_preference(self) -> None:
        target = enumerate_displays([WALL], [r"\\.\DISPLAY2"])[0]

        restored = preference_from_dict(target.as_preference().to_dict())

        self.assertEqual(restored, target.as_preference())
        self.assertEqual(match_preference(restored, [target]).how, MATCH_EXACT)


class StoredPreferenceTests(unittest.TestCase):
    """A preference that has gone bad reads as 'nothing saved', never as an error."""

    def valid(self) -> dict:
        return {
            "name": r"\\.\DISPLAY2",
            "x": 1366,
            "y": 0,
            "width": 1920,
            "height": 1080,
            "scale": 1.0,
        }

    def test_a_good_payload_is_read(self) -> None:
        self.assertIsNotNone(preference_from_dict(self.valid()))

    def test_a_name_is_optional(self) -> None:
        payload = self.valid()
        payload["name"] = None

        preference = preference_from_dict(payload)

        self.assertIsNotNone(preference)
        self.assertIsNone(preference.name)  # type: ignore[union-attr]

    def test_every_kind_of_damage_reads_as_nothing_saved(self) -> None:
        cases: dict[str, object] = {
            "not a dictionary": ["1920x1080"],
            "nothing at all": None,
            "a string where a number belongs": {**self.valid(), "x": "1366"},
            "a boolean where a number belongs": {**self.valid(), "y": True},
            "a missing field": {k: v for k, v in self.valid().items() if k != "height"},
            "a zero width": {**self.valid(), "width": 0},
            "a negative height": {**self.valid(), "height": -1080},
            "a zero scale": {**self.valid(), "scale": 0},
            "a name that is not text": {**self.valid(), "name": 2},
        }
        for description, payload in cases.items():
            with self.subTest(description):
                self.assertIsNone(preference_from_dict(payload))


class MatchingTests(unittest.TestCase):
    """Three tiers, and deliberately no fourth (D-002)."""

    def setUp(self) -> None:
        self.displays = enumerate_displays(
            [LAPTOP, WALL], [r"\\.\DISPLAY1", r"\\.\DISPLAY2"]
        )
        self.saved = self.displays[1].as_preference()

    def test_the_same_display_in_the_same_place_matches_exactly(self) -> None:
        match = match_preference(self.saved, self.displays)

        self.assertEqual(match.how, MATCH_EXACT)
        self.assertIs(match.target, self.displays[1])

    def test_the_same_device_at_a_new_resolution_still_matches(self) -> None:
        """What a stadium processor renegotiating HDMI looks like."""

        renegotiated = enumerate_displays(
            [LAPTOP, FakeScreen(1366, 0, 1280, 720, 1.0)],
            [r"\\.\DISPLAY1", r"\\.\DISPLAY2"],
        )

        match = match_preference(self.saved, renegotiated)

        self.assertEqual(match.how, MATCH_NAME)
        self.assertIs(match.target, renegotiated[1])
        self.assertIn("size or position changed", match.message)

    def test_a_scaling_change_alone_is_a_name_match_not_an_exact_one(self) -> None:
        rescaled = enumerate_displays(
            [LAPTOP, FakeScreen(1366, 0, 1920, 1080, 1.25)],
            [r"\\.\DISPLAY1", r"\\.\DISPLAY2"],
        )

        match = match_preference(self.saved, rescaled)

        self.assertEqual(match.how, MATCH_NAME)
        self.assertIs(match.target, rescaled[1])

    def test_a_renumbered_device_in_the_same_place_matches_by_geometry(self) -> None:
        """What Windows renumbering after a replug looks like."""

        renamed = enumerate_displays(
            [LAPTOP, WALL], [r"\\.\DISPLAY1", r"\\.\DISPLAY4"]
        )

        match = match_preference(self.saved, renamed)

        self.assertEqual(match.how, MATCH_GEOMETRY)
        self.assertIs(match.target, renamed[1])
        self.assertIn("same place", match.message)

    def test_an_unplugged_display_is_reported_and_never_substituted(self) -> None:
        match = match_preference(self.saved, enumerate_displays([LAPTOP]))

        self.assertFalse(match.found)
        self.assertIsNone(match.target)
        self.assertEqual(match.how, MATCH_NONE)
        self.assertIn("DISPLAY NOT FOUND", match.message)
        self.assertIn("still running and saving", match.message)

    def test_no_saved_preference_selects_nothing(self) -> None:
        match = match_preference(None, self.displays)

        self.assertIsNone(match.target)
        self.assertIn("No display has been saved", match.message)

    def test_an_empty_screen_list_is_reported_rather_than_indexed(self) -> None:
        match = match_preference(self.saved, [])

        self.assertIsNone(match.target)
        self.assertIn("not reporting any display", match.message)

    def test_a_name_match_wins_over_a_geometry_match_elsewhere(self) -> None:
        """The device identity is the stronger claim, and the message says which."""

        swapped = enumerate_displays(
            [FakeScreen(1366, 0, 1920, 1080, 1.0), FakeScreen(0, 0, 1366, 768, 1.0)],
            [r"\\.\DISPLAY9", r"\\.\DISPLAY2"],
        )

        match = match_preference(self.saved, swapped)

        self.assertEqual(match.how, MATCH_NAME)
        self.assertEqual(match.target.name, r"\\.\DISPLAY2")  # type: ignore[union-attr]

    def test_geometry_matching_works_when_no_name_was_ever_available(self) -> None:
        nameless = enumerate_displays([LAPTOP, WALL])
        saved = DisplayPreference(name=None, x=1366, y=0, width=1920, height=1080, scale=1.0)

        match = match_preference(saved, nameless)

        self.assertEqual(match.how, MATCH_GEOMETRY)
        self.assertIs(match.target, nameless[1])


class DefaultTargetTests(unittest.TestCase):
    """With nothing saved, never cover the screen the controls are on."""

    def test_the_first_non_primary_display_is_offered(self) -> None:
        displays = enumerate_displays([LAPTOP, WALL])

        self.assertIs(default_target(displays), displays[1])

    def test_a_single_display_yields_no_default_at_all(self) -> None:
        self.assertIsNone(default_target(enumerate_displays([LAPTOP])))

    def test_no_displays_yields_no_default(self) -> None:
        self.assertIsNone(default_target([]))


class DisplayWatchTests(unittest.TestCase):
    """Sampling is bounded, and the first look is never a 'change'."""

    def setUp(self) -> None:
        self.now = 100.0
        self.screens: list[FakeScreen] = [LAPTOP, WALL]
        self.reads = 0
        self.watch = DisplayWatch(
            self.read, monotonic=lambda: self.now, interval=2.0
        )

    def read(self):
        self.reads += 1
        return enumerate_displays(self.screens)

    def test_the_first_sample_establishes_the_baseline_silently(self) -> None:
        self.assertIsNone(self.watch.poll())
        self.assertEqual(len(self.watch.known), 2)

    def test_an_unchanged_list_reports_nothing(self) -> None:
        self.watch.poll()
        self.now += 5.0

        self.assertIsNone(self.watch.poll())

    def test_a_lost_display_is_reported_once(self) -> None:
        self.watch.poll()
        self.screens = [LAPTOP]
        self.now += 5.0

        changed = self.watch.poll()

        self.assertIsNotNone(changed)
        self.assertEqual(len(changed), 1)  # type: ignore[arg-type]

        self.now += 5.0
        self.assertIsNone(self.watch.poll())

    def test_a_returning_display_is_reported(self) -> None:
        self.watch.poll()
        self.screens = [LAPTOP]
        self.now += 5.0
        self.watch.poll()

        self.screens = [LAPTOP, WALL]
        self.now += 5.0

        self.assertIsNotNone(self.watch.poll())

    def test_windows_is_not_asked_more_often_than_the_interval(self) -> None:
        self.watch.poll()
        self.assertEqual(self.reads, 1)

        for _ in range(8):  # eight refresh ticks inside one interval
            self.now += 0.25
            self.watch.poll()

        self.assertEqual(self.reads, 2)

    def test_force_samples_regardless_of_the_interval(self) -> None:
        self.watch.poll()
        self.screens = [LAPTOP]

        self.assertIsNotNone(self.watch.poll(force=True))
