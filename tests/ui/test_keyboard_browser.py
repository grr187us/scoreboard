import sys
import unittest

from tests.ui.browser_support import run_browser


class KeyboardBrowserTests(unittest.TestCase):
    def test_keyboard_to_real_bridge_and_input_safety(self):
        result = run_browser('keyboard.cjs', {'python': sys.executable})
        # 17 pre-cutscenes bindings (16 command/clock shortcuts plus Esc) plus
        # the six `host` bindings from .scratch/cutscenes-v3/spec.md 2.5
        # (five events -- D/T/O/F/L -- and Shift+C cancel), plus the eight
        # F13-F20 macro-pad clock bindings added with the field status work.
        # The September 8 control refresh changed what two of those bindings
        # do (score keys arm first, Ctrl+Z confirms first) but added none.
        # September 10, 2026: the button box remapped F15-F20, added the
        # rocker switch's F21 (game clock start) and F22 (game clock stop),
        # and dropped F13/F14 (the paddle), so the count is back to 31.
        self.assertEqual(result['shortcuts'], 31)
        self.assertGreaterEqual(result['editableFields'], 12)
