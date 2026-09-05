import sys
import unittest

from tests.ui.browser_support import run_browser


class KeyboardBrowserTests(unittest.TestCase):
    def test_keyboard_to_real_bridge_and_input_safety(self):
        result = run_browser('keyboard.cjs', {'python': sys.executable})
        self.assertEqual(result['shortcuts'], 17)
        self.assertGreaterEqual(result['editableFields'], 12)
