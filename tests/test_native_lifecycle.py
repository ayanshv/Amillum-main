import ctypes as C
import threading
import unittest

from native.macos.global_hotkey import GlobalHotkeys, HotKeyID, PRESSED, RELEASED, SIGNATURE, Shortcut


class FakeCarbon:
    def __init__(self):
        self.registration_status = 0
        self.kind = PRESSED
        self.identifier = 1
        self.signature = SIGNATURE
        self.removed = []

    def GetApplicationEventTarget(self):
        return 1

    def InstallEventHandler(self, target, callback, count, events, data, handler):
        C.cast(handler, C.POINTER(C.c_void_p))[0] = 100
        return 0

    def RegisterEventHotKey(self, key, modifiers, identifier, target, flags, reference):
        C.cast(reference, C.POINTER(C.c_void_p))[0] = 200 + identifier.identifier
        return self.registration_status

    def UnregisterEventHotKey(self, reference):
        self.removed.append(reference.value)

    def RemoveEventHandler(self, handler):
        self.removed.append(handler.value)

    def GetEventParameter(self, event, name, kind, actual_type, size, actual_size, output):
        C.cast(output, C.POINTER(HotKeyID))[0] = HotKeyID(self.signature, self.identifier)
        return 0

    def GetEventKind(self, event):
        return self.kind


class HotkeyTests(unittest.TestCase):
    def setUp(self):
        self.lib = FakeCarbon()
        self.calls = []
        self.hotkeys = GlobalHotkeys(lambda: self.calls.append('activate'), self.lib)

    def test_defaults_and_invalid_config(self):
        self.assertEqual(Shortcut.parse('Command + Shift + A').label, '⇧⌘A')
        self.assertEqual(Shortcut.parse('ctrl+shift+a').key_code, 0)
        for value in ('a', 'shift+a', 'cmd+cmd+a', 'cmd+f100', 'cmd++a'):
            with self.assertRaises(ValueError):
                Shortcut.parse(value)

    def test_configurable_key_positions(self):
        from native.macos.global_hotkey import KEY_CODES
        self.assertEqual(set(KEY_CODES), set('abcdefghijklmnopqrstuvwxyz0123456789'))
        self.assertEqual(Shortcut.parse('cmd+shift+t').key_code, 17)
        self.assertEqual(Shortcut.parse('cmd+shift+y').key_code, 16)
        self.assertEqual(Shortcut.parse('cmd+shift+6').key_code, 22)

    def test_repeat_suppression_and_release(self):
        self.hotkeys.register(Shortcut.parse('cmd+shift+a'))
        for _ in range(5):
            self.hotkeys._dispatch(None, None, None)
        self.assertEqual(self.calls, ['activate'])
        self.lib.kind = RELEASED
        self.hotkeys._dispatch(None, None, None)
        self.lib.kind = PRESSED
        self.hotkeys._dispatch(None, None, None)
        self.assertEqual(len(self.calls), 2)

    def test_foreign_events_cannot_start_selection(self):
        self.hotkeys.register(Shortcut.parse('cmd+shift+a'))
        self.lib.signature = 0
        self.assertNotEqual(self.hotkeys._dispatch(None, None, None), 0)
        self.assertFalse(self.calls)

    def test_conflict_and_idempotent_cleanup(self):
        self.hotkeys.register(Shortcut.parse('cmd+shift+a'))
        self.lib.registration_status = -9878
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            self.hotkeys.register(Shortcut.parse('ctrl+shift+a'))
        self.hotkeys.close()
        self.hotkeys.close()
        self.assertEqual(self.lib.removed, [201, 100])
        self.assertFalse(self.hotkeys.references)
        self.assertFalse(self.hotkeys.handler.value)

    def test_failed_first_registration_releases_handler(self):
        self.lib.registration_status = -9878
        with self.assertRaises(RuntimeError):
            self.hotkeys.register(Shortcut.parse('cmd+shift+a'))
        self.hotkeys.close()
        self.assertEqual(self.lib.removed, [100])

    def test_registration_rejected_off_main_thread(self):
        errors = []

        def register():
            try:
                self.hotkeys.register(Shortcut.parse('cmd+shift+a'))
            except RuntimeError as exc:
                errors.append(str(exc))

        thread = threading.Thread(target=register)
        thread.start()
        thread.join()
        self.assertEqual(len(errors), 1)
        self.assertFalse(self.hotkeys.handler.value)


if __name__ == '__main__':
    unittest.main()
