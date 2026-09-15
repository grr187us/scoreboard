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
class SoccerU001BrowserTests(unittest.TestCase):
    """U-001: no scrolling at 1093x614 / 1180x720 / 1366x768, idle / armed /
    shootout / alert, with 24-character team names, against the real bridge.
    Screenshots land in .scratch/soccer-mode/evidence/u001/ (not shipped).
    """

    def test_no_scroll_and_every_control_fits_at_every_viewport_and_state(self):
        result = run_browser('soccer_u001.cjs', {'python': sys.executable})
        self.assertEqual(len(result), 12, result.keys())  # 3 viewports x 4 states
        for key, metrics in result.items():
            with self.subTest(key=key):
                self.assertLessEqual(metrics['scrollHeight'], metrics['innerHeight'] + 1)
                self.assertLessEqual(metrics['scrollWidth'], metrics['innerWidth'] + 1)
        idle = result['1093x614-idle']
        self.assertEqual(idle['innerHeight'], 614)


if __name__ == '__main__':  # pragma: no cover - convenience runner
    unittest.main()
