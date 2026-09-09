"""Task 11 packaging contracts (W-002 to W-006).

Building the package takes minutes and needs PyInstaller, so these tests do not
build it. They assert the things that silently break a build and are invisible
until the operator double-clicks a shortcut at a stadium:

* the packaging metadata ships every file a window loads, not only the pages;
* the frozen build looks for those files where PyInstaller actually puts them;
* the version the executable is stamped with is the version the code reports;
* a missing WebView2 runtime is detected and explained rather than producing a
  window that never opens.

``tools/build_package.py`` performs the checks that need a real build.
"""

from __future__ import annotations

import fnmatch
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

from scoreboard.domain.state import APP_VERSION
from scoreboard.host import app as host_app
from scoreboard.host import preflight

ROOT = Path(__file__).resolve().parents[2]
VIEWS = ROOT / "src" / "scoreboard" / "views"
PYPROJECT = ROOT / "pyproject.toml"
SPEC = ROOT / "tools" / "scoreboard.spec"
BUILD_SCRIPT = ROOT / "tools" / "build_package.py"


class PackageDataTests(unittest.TestCase):
    """Every file a window loads must be declared as package data."""

    def package_data_patterns(self) -> list[str]:
        """The patterns declared for the ``scoreboard`` package, comments aside."""

        text = PYPROJECT.read_text(encoding="utf-8")
        section = text.split("[tool.setuptools.package-data]", 1)[1]
        declaration = re.search(r"^scoreboard\s*=\s*\[(.*?)\]", section, re.S | re.M)
        self.assertIsNotNone(declaration, "no scoreboard package-data declaration")
        return re.findall(r'"([^"]+)"', declaration.group(1))

    def view_files(self) -> list[Path]:
        return sorted(path for path in VIEWS.rglob("*") if path.is_file())

    def test_every_view_file_matches_a_declared_pattern(self) -> None:
        """A page shipped without its stylesheet is a blank LED wall."""

        patterns = self.package_data_patterns()
        self.assertTrue(patterns, "no package-data patterns were declared")

        unmatched = []
        for path in self.view_files():
            relative = path.relative_to(ROOT / "src" / "scoreboard").as_posix()
            if not any(fnmatch.fnmatch(relative, pattern) for pattern in patterns):
                unmatched.append(relative)

        self.assertEqual(unmatched, [], f"not declared as package data: {unmatched}")

    def test_the_build_script_requires_every_view_file(self) -> None:
        """The verified file list must not drift behind the pages themselves."""

        required = set(re.findall(r'"(_internal/[^"]+)"', BUILD_SCRIPT.read_text(encoding="utf-8")))
        expected = {
            f"_internal/scoreboard/views/{path.relative_to(VIEWS).as_posix()}"
            for path in self.view_files()
        }

        self.assertEqual(expected - required, set(), "a view file is never verified")


#: Every bundled asset the boards load offline (assets/README.md): the two
#: SIL OFL font families with their licence texts, and the crest an image
#: element names as ``asset:tigers-crest``.
BUNDLED_ASSETS = (
    "shared/fonts/Graduate-Regular.ttf",
    "shared/fonts/Graduate-OFL.txt",
    "shared/fonts/BarlowCondensed-Medium.ttf",
    "shared/fonts/BarlowCondensed-SemiBold.ttf",
    "shared/fonts/BarlowCondensed-Bold.ttf",
    "shared/fonts/Barlow-OFL.txt",
    "shared/img/tigers-crest.png",
)


class BundledAssetTests(PackageDataTests):
    """Fonts and images ship inside the package; nothing is fetched at game
    time (event-screens spec sections 1 and 2.10)."""

    def test_every_bundled_asset_is_on_disk_and_not_empty(self) -> None:
        for relative in BUNDLED_ASSETS:
            with self.subTest(asset=relative):
                path = VIEWS / relative
                self.assertTrue(path.is_file(), f"{relative} is missing from views/")
                self.assertGreater(path.stat().st_size, 0, relative)

    def test_every_bundled_asset_is_declared_as_package_data(self) -> None:
        patterns = self.package_data_patterns()
        self.assertIn("views/**/img/*.png", patterns)
        self.assertIn("views/**/fonts/*.ttf", patterns)
        self.assertIn("views/**/fonts/*.txt", patterns)
        for relative in BUNDLED_ASSETS:
            with self.subTest(asset=relative):
                declared = f"views/{relative}"
                self.assertTrue(any(fnmatch.fnmatch(declared, pattern) for pattern in patterns), declared)

    def test_every_bundled_asset_is_verified_by_the_build_script(self) -> None:
        required = set(re.findall(r'"(_internal/[^"]+)"', BUILD_SCRIPT.read_text(encoding="utf-8")))
        for relative in BUNDLED_ASSETS:
            with self.subTest(asset=relative):
                self.assertIn(f"_internal/scoreboard/views/{relative}", required)

    def test_the_layout_schema_names_only_bundled_images_that_exist(self) -> None:
        from scoreboard.presentation.layout import BUNDLED_IMAGES

        for key, relative in BUNDLED_IMAGES.items():
            with self.subTest(key=key):
                self.assertTrue((VIEWS / relative).is_file(), relative)
                self.assertIn(relative, BUNDLED_ASSETS)

    def test_each_font_ships_with_its_licence_text(self) -> None:
        graduate = (VIEWS / "shared/fonts/Graduate-OFL.txt").read_text(encoding="utf-8")
        barlow = (VIEWS / "shared/fonts/Barlow-OFL.txt").read_text(encoding="utf-8")
        for licence in (graduate, barlow):
            self.assertIn("SIL Open Font License", licence)
        self.assertIn("Graduate", graduate)
        self.assertIn("Barlow", barlow)


class FrozenLayoutTests(unittest.TestCase):
    """The packaged build must look where PyInstaller puts the pages."""

    def test_a_checkout_resolves_views_beside_the_source(self) -> None:
        self.assertFalse(hasattr(sys, "_MEIPASS"), "this test run is not frozen")

        resolved = host_app._views_directory()

        self.assertEqual(resolved, VIEWS)
        self.assertTrue((resolved / "operator" / "index.html").is_file())

    def test_a_frozen_build_resolves_views_under_the_bundle(self) -> None:
        with mock.patch.object(sys, "_MEIPASS", create=True, new=r"C:\bundle"):
            resolved = host_app._views_directory()

        self.assertEqual(resolved, Path(r"C:\bundle") / "scoreboard" / "views")

    def test_the_spec_bundles_views_under_that_same_name(self) -> None:
        spec = SPEC.read_text(encoding="utf-8")

        self.assertIn('Path("scoreboard/views")', spec)
        self.assertIn("console=False", spec)
        self.assertIn("COLLECT(", spec)


class VersionStampTests(unittest.TestCase):
    """One version, reported everywhere the same (W-006)."""

    def test_the_packaging_metadata_reads_the_application_constant(self) -> None:
        text = PYPROJECT.read_text(encoding="utf-8")

        self.assertIn('dynamic = ["version"]', text)
        self.assertIn('version = {attr = "scoreboard.domain.state.APP_VERSION"}', text)
        self.assertNotIn(f'version = "{APP_VERSION}"', text)

    def test_the_spec_reads_the_same_constant_rather_than_repeating_it(self) -> None:
        spec = SPEC.read_text(encoding="utf-8")

        self.assertIn("APP_VERSION", spec)
        self.assertNotIn(f'"{APP_VERSION}"', spec)

    def test_the_application_version_is_a_real_release_number(self) -> None:
        """`0.0.0` was the pre-implementation placeholder."""

        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+$")
        self.assertNotEqual(APP_VERSION, "0.0.0")


class PrerequisiteTests(unittest.TestCase):
    """A missing runtime must be explained, not silently fatal (W-002)."""

    def test_a_missing_webview2_names_the_remedy(self) -> None:
        with mock.patch.object(preflight, "webview2_version", return_value=None):
            prerequisite = preflight.check_webview2()

        self.assertFalse(prerequisite.satisfied)
        message = prerequisite.message()
        self.assertIn("WebView2", message)
        self.assertIn("Install", message)
        self.assertIn("never needs one", message)

    def test_a_present_webview2_reports_its_version(self) -> None:
        with mock.patch.object(preflight, "webview2_version", return_value="152.0.4191.62"):
            prerequisite = preflight.check_webview2()

        self.assertTrue(prerequisite.satisfied)
        self.assertIn("152.0.4191.62", prerequisite.message())

    def test_the_detected_version_is_a_string_or_nothing(self) -> None:
        """Run against the real registry: it must never raise, whatever it finds."""

        version = preflight.webview2_version()

        self.assertTrue(version is None or isinstance(version, str))
        if version is not None:
            self.assertTrue(version.strip())

    def test_check_prerequisites_reports_webview2(self) -> None:
        names = [item.name for item in preflight.check_prerequisites()]

        self.assertIn("Microsoft Edge WebView2 Runtime", names)

    def test_a_checkout_prints_rather_than_opening_a_dialog(self) -> None:
        """A modal dialog in a terminal or a build script would hang it."""

        with mock.patch.object(preflight, "has_console", return_value=True), \
                mock.patch("builtins.print") as printed:
            preflight.report("Title", "Body")

        printed.assert_called_once_with("Body")

    def test_a_frozen_build_is_never_treated_as_having_a_console(self) -> None:
        with mock.patch.object(preflight, "frozen", return_value=True):
            self.assertFalse(preflight.has_console())


if __name__ == "__main__":
    unittest.main()
