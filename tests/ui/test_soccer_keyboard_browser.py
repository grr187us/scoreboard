import sys
import unittest

try:
    from scoreboard.host.soccer_bridge import SoccerBridge  # noqa: F401
    from scoreboard.host.soccer_app import SoccerApplication  # noqa: F401
    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - depends on agent B's landing state
    _IMPORT_ERROR = exc

from tests.ui.browser_support import run_browser


@unittest.skipIf(
    _IMPORT_ERROR is not None,
    f"scoreboard.host.soccer_bridge / soccer_app not importable yet: {_IMPORT_ERROR}",
)
class SoccerKeyboardBrowserTests(unittest.TestCase):
    def test_soccer_keyboard_to_real_bridge(self):
        result = run_browser('soccer_keyboard.cjs', {'python': sys.executable})
        # views/soccer_operator/keyboard.js's table (spec 4.5): Space, G, H,
        # Q, Shift+Q, A S D F (+Shift), J K L ; (+Shift), Y Shift+Y R Shift+R,
        # I, E, W, X, Ctrl+Z, Esc, 1, Shift+1, Shift+C.
        self.assertEqual(result['shortcuts'], 34)


if __name__ == '__main__':  # pragma: no cover - convenience runner
    unittest.main()
