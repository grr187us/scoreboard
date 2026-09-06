import sys
import unittest

from tests.ui.browser_support import run_browser


class KeyboardBrowserTests(unittest.TestCase):
    def test_keyboard_to_real_bridge_and_input_safety(self):
        result = run_browser('keyboard.cjs', {'python': sys.executable})
        # 17 pre-cutscenes bindings (16 command/clock shortcuts plus Esc) plus
        # the six `host` bindings from .scratch/cutscenes-v3/spec.md 2.5
        # (five events -- D/T/O/F/L -- and Shift+C cancel).
        self.assertEqual(result['shortcuts'], 23)
        self.assertGreaterEqual(result['editableFields'], 12)
