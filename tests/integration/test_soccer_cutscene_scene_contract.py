"""Source-contract test for ``views/soccer_spectator/cutscenes/*.js``: the
same house rules the football scene files keep (``CONTEXT_FOR_AGENTS.md``,
``touchdown-tiger-takeover.md``), checked by scanning the files as text --
no browser, no JS interpreter.

- Exactly one scene id is registered: ``goal`` (never one of football's five).
- No ``http://`` (or ``https://``) anywhere -- nothing here is ever fetched.
- Every ``innerHTML`` assignment reads from a ``*_MARKUP``-named constant.
- No brand hex literal (``#RRGGBB``) appears outside a fallback inside a
  ``var(--cs-*, #......)`` call -- every real colour comes from a `--cs-*`
  custom property, never a literal painted directly onto the DOM.
- A delayed one-shot CSS animation ends ``forwards``, never ``both`` (the
  football-pass rule this agent's task explicitly restates: an entrance must
  not hold its 0% state before playback starts).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SCENES_DIR = (
    Path(__file__).resolve().parents[2]
    / "src" / "scoreboard" / "views" / "soccer_spectator" / "cutscenes"
)
# The player is football's ../spectator/cutscene.js, reused unchanged and
# covered by football's own contract tests; only the soccer scene files are
# scanned here.
CSS_FILES = sorted(SCENES_DIR.glob("*.css"))


def _js_files() -> list[Path]:
    return sorted(SCENES_DIR.glob("*.js"))


def _all_js_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in _js_files())


def _all_css_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in CSS_FILES)


class SceneRegistryTests(unittest.TestCase):
    def test_the_directory_exists(self) -> None:
        self.assertTrue(SCENES_DIR.is_dir())

    def test_exactly_goal_is_registered(self) -> None:
        text = _all_js_text()
        registrations = re.findall(r"register\('([a-z_]+)'", text)

        self.assertEqual(sorted(set(registrations)), ["goal"])

    def test_none_of_footballs_five_ids_appear_as_a_registration(self) -> None:
        text = _all_js_text()
        for football_id in ("first_down", "touchdown", "turnover", "penalty", "make_some_noise"):
            with self.subTest(football_id=football_id):
                self.assertNotIn(f"register('{football_id}'", text)


class NoNetworkTests(unittest.TestCase):
    def test_no_scene_file_contains_a_url_scheme(self) -> None:
        for path in _js_files():
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("http://", text)
                self.assertNotIn("https://", text)


class MarkupConstantTests(unittest.TestCase):
    """Every ``innerHTML`` assignment must come from a ``*_MARKUP`` constant
    or a call/property chain whose *last* identifier ends in ``_MARKUP`` or
    ``markup`` (matching football's own ``root.innerHTML = X_MARKUP`` and
    ``el.innerHTML = TOUCHDOWN_HIDE_MARKUP`` idiom).
    """

    _ASSIGNMENT = re.compile(r"\.innerHTML\s*=\s*([A-Za-z_][A-Za-z0-9_.]*)")

    def test_every_innerhtml_assignment_reads_a_markup_constant(self) -> None:
        for path in _js_files():
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                for match in self._ASSIGNMENT.finditer(text):
                    identifier = match.group(1)
                    self.assertTrue(
                        identifier.upper().endswith("MARKUP"),
                        f"{path.name}: innerHTML assigned from {identifier!r}, not a *_MARKUP constant",
                    )

    def test_the_goal_markup_constant_exists_and_is_used(self) -> None:
        text = (SCENES_DIR / "soccer.js").read_text(encoding="utf-8")
        self.assertIn("var GOAL_MARKUP", text)
        self.assertIn("GOAL_MARKUP", text.split("var GOAL_MARKUP", 1)[1])


class TextContentOnlyForWordsTests(unittest.TestCase):
    def test_team_name_and_headline_reach_the_dom_only_through_textcontent(self) -> None:
        text = (SCENES_DIR / "soccer.js").read_text(encoding="utf-8")
        # program.texts.* is only ever read through the textOf()/addText()
        # helpers, which set textContent -- never concatenated into a
        # template string that could reach innerHTML.
        self.assertIn("span.textContent = value", text)
        self.assertNotIn("innerHTML = ", text.replace("ripple.innerHTML = GOAL_MARKUP;", ""))


class NoBrandHexTests(unittest.TestCase):
    """No real colour is ever a literal hex in the soccer scene files: every
    ``var(--cs-*, #......)`` fallback is allowed (it only ever paints if
    Python's real theme failed to arrive), but a colour used directly
    (``background: #123456`` or similar) is not.
    """

    _HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
    _VAR_FALLBACK = re.compile(r"var\(--cs-[a-z-]+,\s*#[0-9A-Fa-f]{3,8}\)")

    def test_no_bare_hex_colour_outside_a_css_variable_fallback(self) -> None:
        for path in CSS_FILES:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                # Remove every allowed var(--cs-*, #hex) fallback occurrence,
                # then nothing hex-shaped should remain.
                stripped = self._VAR_FALLBACK.sub("", text)
                remaining = self._HEX.findall(stripped)
                self.assertEqual(remaining, [], f"{path.name} has bare hex colours: {remaining}")

    def test_the_scene_js_carries_no_hex_literal_at_all(self) -> None:
        text = (SCENES_DIR / "soccer.js").read_text(encoding="utf-8")
        self.assertEqual(self._HEX.findall(text), [])


class ForwardsNotBothTests(unittest.TestCase):
    """Every delayed one-shot animation (a non-zero explicit delay, and not
    ``infinite``) in the soccer scene CSS ends ``forwards``, matching the
    house rule this agent's task restates. An animation with no delay (it
    already starts at its 0% state, so holding that state early makes no
    difference) or an ``infinite`` loop (the embers) is not a "delayed
    one-shot" and is exempt.
    """

    _DECLARATION = re.compile(r"animation:\s*([^;]+);")
    _DURATION_TOKEN = re.compile(r"^[0-9.]+m?s$")

    def _declarations(self, text: str) -> list[str]:
        return self._DECLARATION.findall(text)

    def test_every_delayed_one_shot_animation_ends_forwards(self) -> None:
        text = _all_css_text()
        found_any = False
        for declaration in self._declarations(text):
            # Drop any function call's parenthesised arguments (e.g.
            # "cubic-bezier(.16, .8, .2, 1)") before tokenizing on
            # whitespace, so an easing function's internal commas/spaces
            # never get mistaken for extra tokens.
            flattened = re.sub(r"\([^)]*\)", "", declaration)
            tokens = flattened.split()
            if not tokens:
                continue
            name = tokens[0]
            fill = tokens[-1] if tokens[-1] in ("forwards", "both") else None
            if fill is None:
                continue  # infinite / none -- not a one-shot at all.
            durations = [t for t in tokens[1:] if self._DURATION_TOKEN.match(t)]
            if len(durations) < 2:
                continue  # no explicit delay -- starts at its own 0% state.
            delay = durations[1]
            if delay in ("0ms", "0s"):
                continue
            found_any = True
            with self.subTest(name=name, delay=delay):
                self.assertEqual(
                    fill, "forwards",
                    f"{name} has a non-zero delay ({delay}) but fills 'both', not 'forwards'",
                )
        self.assertTrue(found_any, "expected at least one delayed one-shot animation to check")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
