"""Source contract for the spectator page's cutscene player and its scenes.

A browser-free mirror of ``tests/ui/test_cutscene_player_browser.py``, in the
style of ``test_spectator_layout_render.py``: it reads the page's own source
text and pins the things the host, the operator windows, and a real-runtime
harness all depend on -- the two globals the host calls through
``evaluate_js``, the DOM markers a harness reads back, the scene ids Python
names, and the house rules the spectator page has always kept (no network, no
game command, no operator control).

Three scene files now (``.scratch/cutscenes-v2/spec.md`` section 4.3 and
``.scratch/cutscenes-v3/spec.md`` section 2.6): ``cutscenes/builtin.js`` owns
the registry, the claw intro and the penalty flag; ``cutscenes/tigers.js``
owns the Tigers' own first-down, touchdown and turnover scenes;
``cutscenes/crowd.js`` owns the MAKE SOME NOISE crowd prompt. The Tigers and
crowd files both show the crest, and that page-relative image is the only
thing any scene may load. Every rule below that is about *what a scene may
do* is checked against all three of them, because the reason for each rule
-- no network, no operator text in markup, no brand hex, no viewport units
-- does not care which file the scene lives in.

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
TIGERS_JS = SPECTATOR / "cutscenes" / "tigers.js"
TIGERS_CSS = SPECTATOR / "cutscenes" / "tigers.css"
CROWD_JS = SPECTATOR / "cutscenes" / "crowd.js"
CROWD_CSS = SPECTATOR / "cutscenes" / "crowd.css"

#: Which scene file registers which id. Python's ``BUILTIN_SCENE_IDS`` and
#: ``INTRO_IDS`` name the same six strings, and Agent A's
#: ``tests/unit/test_cutscene_schema.py`` greps this folder for them from the
#: Python side; this end holds them too, so neither side can be changed alone.
SCENE_IDS = {
    BUILTIN_JS: ("claw_scratch", "penalty"),
    TIGERS_JS: ("first_down", "touchdown", "turnover"),
    CROWD_JS: ("make_some_noise",),
}

#: The scene files that show the crest (v3 section 2.6): both must name it.
CREST_FILES = (TIGERS_JS, CROWD_JS)

#: The only image any scene may name. It is a page-relative path so WebView2
#: loads it as an ordinary subresource of ``file:///.../spectator/index.html``;
#: an absolute URL or a `file://` URI would not be, and neither would a fetch.
LOGO_SRC = "cutscenes/tmsa-logo.png"

#: Nothing a scene file may contain, whichever scene file it is.
FORBIDDEN_IN_SCENES = ("fetch(", "XMLHttpRequest", "api.command", "pywebview",
                       "http://", "https://", "@import", "new Image(")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class SpectatorPageLoadsThePlayerTests(unittest.TestCase):
    """The page has a stage, and loads all three scene files before the player."""

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

    def test_the_page_loads_the_stylesheets_the_scene_files_and_the_player(self) -> None:
        for reference in ('href="cutscene.css"', 'href="cutscenes/tigers.css"',
                          'href="cutscenes/crowd.css"',
                          'src="cutscenes/builtin.js"', 'src="cutscenes/tigers.js"',
                          'src="cutscenes/crowd.js"', 'src="cutscene.js"'):
            self.assertIn(reference, self.html, f"{reference} is not loaded by the spectator page")

    def test_the_scene_files_load_before_the_player_and_after_spectator_js(self) -> None:
        # cutscene.js reads window.ScoreboardCutsceneScenes at load time and
        # window.ScoreboardSpectator on every cutscene; tigers.js and
        # crowd.js read the registry (and its helpers) that builtin.js
        # defines. So the order is not a matter of taste: spectator.js,
        # builtin.js, tigers.js, crowd.js, cutscene.js -- and the
        # stylesheets cutscene.css, tigers.css, crowd.css in that order too
        # (v3 section 2.6; registration order is what the browser test's
        # `ids()` assertion pins).
        order = [self.html.index(marker) for marker in (
            'src="spectator.js"', 'src="cutscenes/builtin.js"',
            'src="cutscenes/tigers.js"', 'src="cutscenes/crowd.js"',
            'src="cutscene.js"')]
        self.assertEqual(order, sorted(order), "the spectator page's script order is wrong")
        css_order = [self.html.index(marker) for marker in (
            'href="cutscene.css"', 'href="cutscenes/tigers.css"',
            'href="cutscenes/crowd.css"')]
        self.assertEqual(css_order, sorted(css_order), "the spectator page's stylesheet order is wrong")

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
        # the scene tests below pin that they come from `program.texts`.
        for key in ("play_id", "duration_ms", "outro_ms", "intro", "stage",
                    "layout", "scene", "theme", "elapsed_ms"):
            self.assertIn(key, self.source, f"the player never reads {key!r}")

    def test_it_publishes_the_penalty_flag_colour_with_the_rest_of_the_theme(self) -> None:
        # `flag` is the one theme key v2 added. It has to reach the stage as
        # --cs-flag or the penalty scene draws its flag in a fallback yellow
        # that Python never chose.
        names = re.search(r"var names = \[([^\]]*)\]", self.source, re.S)
        self.assertIsNotNone(names, "cutscene.js must list the theme names it publishes")
        for name in ("navy", "navy_elevated", "blue", "red", "blue_light",
                     "white", "mist", "ink", "gold", "flag"):
            self.assertIn(f"'{name}'", names.group(1), f"--cs-{name} is never published")
        self.assertIn("'--cs-'", self.source.replace('"', "'"))

    def test_the_morph_lands_inside_the_intro_where_the_tears_open(self) -> None:
        # The claw intro's gouges widen at 45 % of the intro (cs-gouge-widen in
        # cutscene.css) so the strike appears to open the board onto the bar.
        # The player's fraction is the other half of that one effect.
        fraction = re.search(r"MORPH_AT_FRACTION\s*=\s*([0-9.]+)", self.source)
        self.assertIsNotNone(fraction, "cutscene.js must define MORPH_AT_FRACTION")
        self.assertTrue(0.45 <= float(fraction.group(1)) <= 0.55,
                        f"the morph must land mid-intro, not at {fraction.group(1)}")
        self.assertIn("45%", _read(CUTSCENE_CSS),
                      "cs-gouge-widen must open the tears at the same fraction")

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


class SceneRegistryTests(unittest.TestCase):
    """builtin.js owns the registry, and lends its helpers to the other scene files."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = _read(BUILTIN_JS)

    def test_it_exposes_the_registry(self) -> None:
        self.assertRegex(self.source, r"global\.ScoreboardCutsceneScenes\s*=\s*\{")
        for member in ("register:", "create:", "ids:"):
            self.assertIn(member, self.source)

    def test_it_lends_its_four_helpers_to_the_other_scene_files(self) -> None:
        # tigers.js and crowd.js hard-code these four names off
        # `registry.helpers`, so renaming one here would break files this
        # one knows nothing about.
        self.assertIn("helpers:", self.source)
        for helper in ("sceneRoot", "addText", "textOf", "simpleScene"):
            self.assertRegex(self.source, helper + r"\s*:\s*" + helper,
                             f"ScoreboardCutsceneScenes.helpers must expose {helper}")


class SceneFileRulesTests(unittest.TestCase):
    """Every rule a scene file must keep, checked on all three scene files."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = {path: _read(path) for path in SCENE_IDS}

    def test_each_file_registers_its_scenes_with_literal_ids(self) -> None:
        # Literal calls on purpose: Agent A's schema test greps for exactly
        # these strings so the Python id constants cannot drift from the
        # scenes that answer to them.
        for path, ids in SCENE_IDS.items():
            for scene_id in ids:
                self.assertIn(f"register('{scene_id}'", self.sources[path],
                              f"{path.name} must contain a literal register('{scene_id}', ...) call")

    def test_no_scene_file_registers_a_scene_that_belongs_to_another(self) -> None:
        # The split is the point: builtin.js is team-agnostic, tigers.js is
        # the Tigers' branding, crowd.js is the crowd prompt. A stray
        # registration in the wrong file would still work and would quietly
        # undo that.
        for path, ids in SCENE_IDS.items():
            others = [other for group in SCENE_IDS.values() for other in group if other not in ids]
            for scene_id in others:
                self.assertNotIn(f"register('{scene_id}'", self.sources[path],
                                 f"{path.name} must not register {scene_id!r}")

    def test_every_scene_marks_its_root_with_its_id(self) -> None:
        # `data-scene="<id>"` is how the browser test, and a real-runtime
        # harness, sees which scene is on the wall.
        for path, source in self.sources.items():
            self.assertIn("data-scene", source, f"{path.name} marks no scene root")

    def test_scenes_take_their_words_and_colours_from_the_program(self) -> None:
        for path, source in self.sources.items():
            self.assertIn("textContent", source, f"{path.name} writes no text as a text node")
            # Colours arrive as the --cs-* custom properties the player copies
            # out of program.theme; no brand hex is written into a scene.
            self.assertNotRegex(source, r"#[0-9A-Fa-f]{6}\b",
                                f"a brand hex is written into {path.name}")

    def test_scenes_load_nothing_and_command_nothing(self) -> None:
        for path, source in self.sources.items():
            for forbidden in FORBIDDEN_IN_SCENES:
                self.assertNotIn(forbidden, source, f"{forbidden!r} found in {path.name}")

    def test_operator_text_never_reaches_innerhtml(self) -> None:
        # A team name is operator input. Every scene writes words through a
        # text node; the only innerHTML in any file is a *static* SVG
        # constant, which the naming rule below makes visible at a glance:
        # the right-hand side of an innerHTML assignment is always an
        # identifier ending in _MARKUP, so a template string carrying a team
        # name cannot be added without breaking this test.
        for path, source in self.sources.items():
            occurrences = source.count("innerHTML")
            assignments = re.findall(r"\.innerHTML\s*=\s*([A-Za-z_$][\w$]*)\s*;", source)
            self.assertEqual(occurrences, len(assignments),
                             f"every innerHTML in {path.name} must be a plain assignment")
            for name in assignments:
                self.assertTrue(name.endswith("_MARKUP"),
                                f"{path.name} assigns {name} to innerHTML; only *_MARKUP constants may be")

    def test_the_logo_is_the_only_thing_any_scene_loads(self) -> None:
        # A page-relative <img> src is exactly what WebView2 serves from the
        # spectator folder. Nothing else in any file may set a `src`. Since
        # v3 the crowd scene shows the crest as well as the Tigers scenes, so
        # both of those files must name it -- and every `.src =` anywhere
        # must name it and nothing else.
        for path in CREST_FILES:
            self.assertIn(f"'{LOGO_SRC}'", self.sources[path],
                          f"{path.name} must name the crest image by its page-relative path")
        for path, source in self.sources.items():
            for value in re.findall(r"\.src\s*=\s*([^;\n]+)", source):
                self.assertIn(f"'{LOGO_SRC}'", value,
                              f"{path.name} sets a src to {value.strip()!r}, which is not the crest")


class SceneCssTests(unittest.TestCase):
    """All three stylesheets size from the stage and load nothing."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = {path: _read(path) for path in (CUTSCENE_CSS, TIGERS_CSS, CROWD_CSS)}

    def test_cutscene_css_carries_the_morph_rule_for_board_geometry(self) -> None:
        # board.css is shared with the layout editor and knows nothing about
        # cutscenes; the morph is one rule here, on the classes board.js puts
        # on every widget and every free element.
        source = self.sources[CUTSCENE_CSS]
        self.assertIn("#canvas.morphing .widget", source)
        self.assertIn("#canvas.morphing .element", source)
        for prop in ("left", "top", "width", "height", "font-size"):
            self.assertIn(prop, source)

    def test_cutscene_css_styles_the_stage_and_the_intro_and_outro(self) -> None:
        source = self.sources[CUTSCENE_CSS]
        self.assertIn("#cutscene-stage", source)
        self.assertIn("#cutscene-stage.intro", source)
        self.assertIn("#cutscene-stage.outro", source)

    def test_scenes_size_themselves_from_the_stage_not_the_viewport(self) -> None:
        for path, source in self.sources.items():
            self.assertIn("--stage-w", source, f"{path.name} sizes nothing from the stage")
            self.assertIn("--stage-h", source, f"{path.name} sizes nothing from the stage")
            for forbidden in ("vw", "vh", "vmin", "vmax"):
                self.assertNotRegex(source, r"\b\d+(\.\d+)?" + forbidden + r"\b",
                                    f"a scene must not be sized in {forbidden} ({path.name})")

    def test_the_stylesheets_load_no_font_and_no_remote_asset(self) -> None:
        # A local `url(cutscenes/...)` is allowed -- that is the crest, served
        # from the spectator folder like any other page-relative subresource.
        for path, source in self.sources.items():
            for forbidden in ("@import", "url(http", "https://", "http://", "@font-face"):
                self.assertNotIn(forbidden, source, f"{forbidden!r} found in {path.name}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
