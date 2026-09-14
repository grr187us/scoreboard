"""PL-1: the global button-box hook against a fake user32.

No real hotkey is registered here: the fake records every RegisterHotKey /
UnregisterHotKey call and feeds a scripted queue of window messages to the
hook's GetMessage loop, so the dispatch table, the failure path, the
no-repeat modifier, and the shutdown handshake are all proven without Win32.
"""

from __future__ import annotations

import threading
import unittest

from scoreboard.host.hotkeys import (
    BUTTON_BOX_SOURCE,
    HOTKEY_TABLE,
    MOD_NOREPEAT,
    WM_HOTKEY,
    WM_QUIT,
    ButtonBoxHook,
    HookStatus,
    command_for,
    hotkey_id,
)


class FakeUser32:
    """Records registrations; GetMessageW hands out a scripted message queue."""

    def __init__(self, *, refuse: set[int] | None = None) -> None:
        self.refuse = refuse or set()
        self.registered: list[tuple[int, int, int]] = []  # (id, modifiers, vk)
        self.unregistered: list[int] = []
        self.posted: list[tuple[int, int]] = []
        self.queue: list[tuple[int, int]] = []  # (message, wParam)
        self.ready = threading.Event()  # set when the loop first waits
        self.pushed = threading.Event()

    def RegisterHotKey(self, hwnd, identifier, modifiers, vk):  # noqa: N802 - Win32 name
        if vk in self.refuse:
            return 0
        self.registered.append((identifier, modifiers, vk))
        return 1

    def UnregisterHotKey(self, hwnd, identifier):  # noqa: N802
        self.unregistered.append(identifier)
        return 1

    def PostThreadMessageW(self, thread_id, message, wparam, lparam):  # noqa: N802
        self.posted.append((thread_id, message))
        self.queue.append((message, wparam))
        self.pushed.set()
        return 1

    def GetMessageW(self, message_ref, hwnd, first, last):  # noqa: N802
        self.ready.set()
        while not self.queue:
            self.pushed.wait(0.05)
            self.pushed.clear()
        message, wparam = self.queue.pop(0)
        if message == WM_QUIT:
            return 0
        msg = message_ref._obj
        msg.message = message
        msg.wParam = wparam
        return 1

    def push(self, message: int, wparam: int = 0) -> None:
        self.queue.append((message, wparam))
        self.pushed.set()


class Diagnostics:
    def __init__(self) -> None:
        self.notes: list[tuple[str, dict]] = []
        self.errors: list[tuple[str, str]] = []

    def note(self, event, **fields):
        self.notes.append((event, fields))

    def unhandled_error(self, *, context, error, **fields):
        self.errors.append((context, str(error)))


class DispatchTableTests(unittest.TestCase):
    def test_the_eight_box_keys_map_to_the_page_commands(self) -> None:
        expected = {
            0x7E: ("play_clock_preset_start", {"seconds": 25}),
            0x7F: ("play_clock_preset_start", {"seconds": 40}),
            0x80: ("play_clock_preset", {"seconds": 40}),
            0x81: ("play_clock_preset", {"seconds": 25}),
            0x82: ("play_clock_clear", {}),
            0x83: ("play_clock_start", {}),
            0x84: ("game_clock_start", {}),
            0x85: ("game_clock_stop", {}),
        }
        self.assertEqual([b.key for b in HOTKEY_TABLE], [f"F{n}" for n in range(15, 23)])
        for vk, (command, args) in expected.items():
            with self.subTest(vk=hex(vk)):
                binding = command_for(vk)
                self.assertIsNotNone(binding)
                self.assertEqual((binding.command, binding.args), (command, args))
        # F13/F14 (the old paddle) and anything else are not box keys.
        self.assertIsNone(command_for(0x7C))
        self.assertIsNone(command_for(0x7D))
        self.assertIsNone(command_for(0x41))
        self.assertEqual(BUTTON_BOX_SOURCE, "button-box")

    def test_status_fallback_means_some_key_still_needs_the_page(self) -> None:
        self.assertFalse(HookStatus(active=True, registered=("F15",)).fallback)
        self.assertTrue(HookStatus(active=True, registered=("F15",), failed=("F16",)).fallback)
        self.assertTrue(HookStatus(active=False, error="not Windows").fallback)
        self.assertEqual(
            HookStatus(active=True, registered=("F15",), failed=("F16",)).as_dict(),
            {"active": True, "registered": ["F15"], "failed": ["F16"], "fallback": True, "error": None},
        )


class HookLoopTests(unittest.TestCase):
    def start(self, user32: FakeUser32, dispatch=None, diagnostics=None) -> tuple[ButtonBoxHook, list]:
        seen: list = []
        hook = ButtonBoxHook(
            dispatch or seen.append,
            user32=user32,
            current_thread_id=lambda: 4242,
            diagnostics=diagnostics,
            on_status=lambda status: seen.append(("status", status)) if dispatch else None,
        )
        hook.start(timeout=2.0)
        self.assertTrue(user32.ready.wait(2.0), "the loop never reached GetMessage")
        return hook, seen

    def test_every_key_is_registered_with_no_repeat_and_dispatched_by_id(self) -> None:
        user32 = FakeUser32()
        hook, seen = self.start(user32)
        try:
            self.assertEqual(
                user32.registered,
                [(hotkey_id(i), MOD_NOREPEAT, b.vk) for i, b in enumerate(HOTKEY_TABLE)],
            )
            self.assertEqual(hook.status, HookStatus(active=True, registered=tuple(b.key for b in HOTKEY_TABLE)))
            # F21 (rocker on), F15 (Quick 25), an unknown id, then F22.
            user32.push(WM_HOTKEY, hotkey_id(6))
            user32.push(WM_HOTKEY, hotkey_id(0))
            user32.push(WM_HOTKEY, 0x0001)
            user32.push(0x0113, 0)  # WM_TIMER: not ours, ignored
            user32.push(WM_HOTKEY, hotkey_id(7))
            deadline = threading.Event()
            for _ in range(40):
                if len(seen) >= 3:
                    break
                deadline.wait(0.05)
            self.assertEqual([b.command for b in seen], ["game_clock_start", "play_clock_preset_start", "game_clock_stop"])
            self.assertEqual(seen[1].args, {"seconds": 25})
        finally:
            hook.stop()
        self.assertEqual(user32.posted, [(4242, WM_QUIT)])
        self.assertEqual(sorted(user32.unregistered), sorted(hotkey_id(i) for i in range(len(HOTKEY_TABLE))))
        self.assertFalse(hook.status.active)
        self.assertEqual(hook.status.error, "stopped")

    def test_a_key_another_program_owns_is_reported_and_the_rest_still_work(self) -> None:
        user32 = FakeUser32(refuse={0x82, 0x83})  # F19, F20 taken elsewhere
        diagnostics = Diagnostics()
        hook, seen = self.start(user32, dispatch=None, diagnostics=diagnostics)
        try:
            status = hook.status
            self.assertTrue(status.active)
            self.assertEqual(status.failed, ("F19", "F20"))
            self.assertEqual(status.registered, ("F15", "F16", "F17", "F18", "F21", "F22"))
            self.assertTrue(status.fallback)
            self.assertEqual(diagnostics.notes[0][0], "BUTTON_BOX_HOOK_STARTED")
            self.assertEqual(diagnostics.notes[0][1]["failed"], ["F19", "F20"])
            user32.push(WM_HOTKEY, hotkey_id(6))
            for _ in range(40):
                if seen:
                    break
                threading.Event().wait(0.05)
            self.assertEqual(seen[0].key, "F21")
        finally:
            hook.stop()
        # Only what was registered is unregistered.
        self.assertEqual(len(user32.unregistered), 6)
        self.assertEqual(diagnostics.notes[-1][0], "BUTTON_BOX_HOOK_STOPPED")

    def test_nothing_registered_is_an_inactive_hook_with_a_reason(self) -> None:
        user32 = FakeUser32(refuse={b.vk for b in HOTKEY_TABLE})
        diagnostics = Diagnostics()
        hook, _ = self.start(user32, diagnostics=diagnostics)
        try:
            self.assertEqual(hook.status.active, False)
            self.assertEqual(hook.status.error, "no key could be registered")
            self.assertEqual(hook.status.failed, tuple(b.key for b in HOTKEY_TABLE))
        finally:
            hook.stop()

    def test_a_failing_dispatch_is_logged_and_the_loop_keeps_going(self) -> None:
        user32 = FakeUser32()
        diagnostics = Diagnostics()
        calls: list[str] = []

        def dispatch(binding):
            calls.append(binding.key)
            if binding.key == "F15":
                raise RuntimeError("bridge exploded")

        hook, _ = self.start(user32, dispatch=dispatch, diagnostics=diagnostics)
        try:
            user32.push(WM_HOTKEY, hotkey_id(0))
            user32.push(WM_HOTKEY, hotkey_id(5))
            for _ in range(40):
                if len(calls) >= 2:
                    break
                threading.Event().wait(0.05)
            self.assertEqual(calls, ["F15", "F20"])
            self.assertEqual(diagnostics.errors, [("button_box_dispatch", "bridge exploded")])
        finally:
            hook.stop()

    def test_start_twice_and_stop_before_start_are_harmless(self) -> None:
        user32 = FakeUser32()
        hook = ButtonBoxHook(lambda b: None, user32=user32, current_thread_id=lambda: 1)
        hook.stop()  # never started: nothing to post
        self.assertEqual(user32.posted, [])
        hook.start(timeout=2.0)
        first = hook.status
        self.assertEqual(hook.start(timeout=0.1), first)
        hook.stop()
        self.assertEqual(len(user32.registered), len(HOTKEY_TABLE))
        self.assertEqual(user32.posted, [(1, WM_QUIT)])


if __name__ == "__main__":
    unittest.main()
