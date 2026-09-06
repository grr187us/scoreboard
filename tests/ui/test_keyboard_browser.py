import sys
import unittest

from tests.ui.browser_support import run_browser


class KeyboardBrowserTests(unittest.TestCase):
    def test_keyboard_to_real_bridge_and_input_safety(self):
        result = run_browser('keyboard.cjs', {'python': sys.executable})
        # 17 pre-cutscenes bindings (16 command/clock shortcuts plus Esc) plus
        # the four `host` bindings from .scratch/cutscenes/spec.md 7.2.
        self.assertEqual(result['shortcuts'], 21)
        self.assertGreaterEqual(result['editableFields'], 12)
