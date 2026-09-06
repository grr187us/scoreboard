"""Source contract for the spectator page's cutscene player (spec section 6).

A browser-free mirror of ``tests/ui/test_cutscene_player_browser.py``, in the
style of ``test_spectator_layout_render.py``: it reads the page's own source
text and pins the things the host, the operator windows, and a real-runtime
harness all depend on -- the two globals the host calls through
``evaluate_js``, the DOM markers a harness reads back, the scene ids Python
names, and the house rules the spectator page has always kept (no network, no
game command, no operator control).

These checks are deliberately cheap and deliberately literal. The owner will
iterate on how the cutscenes *look*; nothing in this file constrains that.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

VIEWS_ROOT = Path(__file__).resolve().parents[2] / "src" / "scoreboard" / "views"
SPECTATOR = VIEWS_ROOT / "spectator"
INDEX_HTML = SPECTATOR / "index.html"
SPECTATOR_JS = SPECTATOR / "spectator.js"
CUTSCENE_JS = SPECTATOR / "cutscene.js"
CUTSCENE_CSS = SPECTATOR / "cutscene.css"
BUILTIN_JS = SPECTATOR / "cutscenes" / "builtin.js"

#: The scene ids Python's ``BUILTIN_SCENE_IDS`` and ``INTRO_IDS`` name. Agent
#: A's ``tests/unit/test_cutscene_schema.py`` greps ``builtin.js`` for the same
#: literals from the Python side; this end holds them even before that module
#: exists, so neither side can be changed alone.
SCENE_IDS = ("claw_scratch", "first_down", "touchdown")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class SpectatorPageLoadsThePlayerTests(unittest.TestCase):
    """The page has a stage, and loads the registry before the player."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = _read(INDEX_HTML)

    def test_the_page_has_the_cutscene_stage(self) -> None:
        self.assertIn('id="cutscene-stage"', self.html)
        # Hidden until a cutscene plays, and never announced: it is decoration
        # over a board that already carries every value.
        stage = re.search(r"<section id=\"cutscene-stage\"[^>]*>", self.html)
        self.assertIsNotNone(stage, "the stage must be a <section> on the page")
        self.assertIn("hidden", stage.group(0))
        self.assertIn('aria-hidden="true"', stage.group(0))

    def test_the_page_loads_the_stylesheet_the_registry_and_the_player(self) -> None:
        for reference in ('href="cutscene.css"', 'src="cutscenes/builtin.js"', 'src="cutscene.js"'):
            self.assertIn(reference, self.html, f"{reference} is not loaded by the spectator page")

    def test_the_registry_loads_before_the_player_and_the_player_after_spectator_js(self) -> None:
        # cutscene.js reads window.ScoreboardCutsceneScenes at load time and
        # window.ScoreboardSpectator on every cutscene, so the order matters.
        self.assertLess(self.html.index('src="spectator.js"'), self.html.index('src="cutscenes/builtin.js"'))
        self.assertLess(self.html.index('src="cutscenes/builtin.js"'), self.html.index('src="cutscene.js"'))

    def test_the_page_still_has_no_operator_control(self) -> None:
        for forbidden in ("<button", "<input", "<dialog", "data-command", "data-action"):
            self.assertNotIn(forbidden, self.html)


class PlayerGlobalsTests(unittest.TestCase):
    """The two globals the host calls, and the one tests and harnesses read."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = _read(CUTSCENE_JS)

    def test_it_defines_the_two_host_globals(self) -> None:
        # WindowHost pushes with `window.applyCutscene(<json>)` and
        # `window.endCutscene(<int>)`; these names are the wire.
        self.assertIn("applyCutscene", self.source)
        self.assertIn("endCutscene", self.source)
        self.assertRegex(self.source, r"global\.applyCutscene\s*=\s*function")
        self.assertRegex(self.source, r"global\.endCutscene\s*=\s*function")

    def test_it_exposes_the_player_state_seam(self) -> None:
        self.assertRegex(self.source, r"global\.ScoreboardCutscenePlayer\s*=\s*\{")
        self.assertIn("state:", self.source)
        self.assertIn("scenes:", self.source)

    def test_it_drives_the_board_only_through_the_spectator_seam(self) -> None:
        # The player owns the stage; spectator.js owns the boards. The player
        # must never call board.js itself, or a restore could half-apply.
        self.assertIn("ScoreboardSpectator", self.source)
        self.assertIn("setOverrideLayout", self.source)
        self.assertNotIn("ScoreboardBoard", self.source)

    def test_it_reads_every_program_key_the_timeline_needs(self) -> None:
        # `texts` is deliberately absent: the words belong to the scenes, and
        # BuiltinScenesTests below pins that they come from `program.texts`.
        for key in ("play_id", "duration_ms", "outro_ms", "intro", "stage",
                    "layout", "scene", "theme", "elapsed_ms"):
            self.assertIn(key, self.source, f"the player never reads {key!r}")

    def test_it_fetches_nothing_and_commands_nothing(self) -> None:
        for forbidden in ("fetch(", "XMLHttpRequest", "api.command", "pywebview.api =",
                          "http://", "https://", "setInterval"):
            self.assertNotIn(forbidden, self.source, f"{forbidden!r} found in cutscene.js")

    def test_it_never_writes_to_the_python_bridge(self) -> None:
        # The spectator page has no path to a game command, and a cutscene does
        # not change that: the player only ever *receives*.
        self.assertNotIn("pywebview", self.source)


class SpectatorOverrideTests(unittest.TestCase):
    """spectator.js keeps the operator's layout while an override is up."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = _read(SPECTATOR_JS)

    def test_it_exposes_the_override_seam(self) -> None:
        self.assertRegex(self.source, r"window\.ScoreboardSpectator\s*=\s*\{")
        for member in ("setOverrideLayout", "currentLayout", "canvas"):
            self.assertIn(member, self.source)

    def test_a_host_layout_push_is_deferred_while_an_override_is_active(self) -> None:
        self.assertIn("overrideLayout", self.source)
        self.assertIn("if (!overrideLayout)", self.source)

    def test_it_resumes_a_cutscene_that_is_already_playing_on_load(self) -> None:
        self.assertIn("get_cutscene", self.source)
        self.assertIn("applyCutscene", self.source)

    def test_it_still_derives_no_displayed_value(self) -> None:
        for forbidden in ("Math.", "toFixed", "parseInt", "parseFloat", "setInterval",
                          "revision++", "api.command"):
            self.assertNotIn(forbidden, self.source, f"{forbidden!r} found in spectator.js")


class BuiltinScenesTests(unittest.TestCase):
    """The three code-authored scenes, and the registry contract."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = _read(BUILTIN_JS)

    def test_it_exposes_the_registry(self) -> None:
        self.assertRegex(self.source, r"global\.ScoreboardCutsceneScenes\s*=\s*\{")
        for member in ("register:", "create:", "ids:"):
            self.assertIn(member, self.source)

    def test_every_scene_is_registered_with_a_literal_id(self) -> None:
        # Literal calls on purpose: Agent A's schema test greps for exactly
        # these strings so the Python id constants cannot drift from the
        # scenes that answer to them.
        for scene_id in SCENE_IDS:
            self.assertIn(f"register('{scene_id}'", self.source,
                          f"builtin.js must contain a literal register('{scene_id}', ...) call")

    def test_every_scene_marks_its_root_with_its_id(self) -> None:
        # `data-scene="<id>"` is how the browser test, and a real-runtime
        # harness, sees which scene is on the wall.
        self.assertIn("data-scene", self.source)

    def test_scenes_take_their_words_and_colours_from_the_program(self) -> None:
        self.assertIn("program.texts", self.source)
        # Colours arrive as the --cs-* custom properties the player copies out
        # of program.theme; no brand hex is written into a scene.
        self.assertNotRegex(self.source, r"#[0-9A-Fa-f]{6}\b")

    def test_scenes_load_nothing_and_command_nothing(self) -> None:
        for forbidden in ("fetch(", "XMLHttpRequest", "api.command", "pywebview",
                          "http://", "https://", "@import", "new Image("):
            self.assertNotIn(forbidden, self.source, f"{forbidden!r} found in builtin.js")

    def test_operator_text_never_reaches_innerhtml(self) -> None:
        # A team name is operator input. Every scene writes text through a text
        # node; the only innerHTML in the file is the claw intro's static SVG.
        self.assertIn("textContent", self.source)
        self.assertEqual(self.source.count("innerHTML"), 1)
        self.assertIn("root.innerHTML = CLAW_MARKUP;", self.source)


class CutsceneCssTests(unittest.TestCase):
    """The morph rule, the stage, and the scene styling all live in one file."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = _read(CUTSCENE_CSS)

    def test_it_carries_the_morph_rule_for_board_geometry(self) -> None:
        # board.css is shared with the layout editor and knows nothing about
        # cutscenes; the morph is one rule here, on the classes board.js puts
        # on every widget and every free element.
        self.assertIn("#canvas.morphing .widget", self.source)
        self.assertIn("#canvas.morphing .element", self.source)
        for prop in ("left", "top", "width", "height", "font-size"):
            self.assertIn(prop, self.source)

    def test_it_styles_the_stage_and_the_intro_and_outro(self) -> None:
        self.assertIn("#cutscene-stage", self.source)
        self.assertIn("#cutscene-stage.intro", self.source)
        self.assertIn("#cutscene-stage.outro", self.source)

    def test_scenes_size_themselves_from_the_stage_not_the_viewport(self) -> None:
        self.assertIn("--stage-w", self.source)
        self.assertIn("--stage-h", self.source)
        for forbidden in ("vw", "vh", "vmin", "vmax"):
            self.assertNotRegex(self.source, r"\b\d+(\.\d+)?" + forbidden + r"\b",
                                f"a scene must not be sized in {forbidden}")

    def test_it_loads_no_font_and_no_remote_asset(self) -> None:
        for forbidden in ("@import", "url(http", "https://", "http://", "@font-face"):
            self.assertNotIn(forbidden, self.source, f"{forbidden!r} found in cutscene.css")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
