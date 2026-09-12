"""Register only named hotkeys. No event tap, keyboard monitor, or input recording.

Carbon's C interface is confined here; callbacks and registrations are retained
until close and all operations run on the Cocoa main thread.
"""

import ctypes as C
import logging
import threading
from dataclasses import dataclass

LOG = logging.getLogger(__name__)
KEYBOARD = int.from_bytes(b'keyb', 'big')
SIGNATURE = int.from_bytes(b'AMIL', 'big')
PRESSED, RELEASED = 5, 6
NOT_HANDLED = -9874
MODIFIERS = {'cmd': 1 << 8, 'shift': 1 << 9, 'option': 1 << 11, 'ctrl': 1 << 12}
# macOS virtual key positions (ANSI). No keystrokes are inspected to resolve these.
KEY_CODES = {'a': 0, 's': 1, 'd': 2, 'f': 3, 'h': 4, 'g': 5, 'z': 6, 'x': 7,
             'c': 8, 'v': 9, 'b': 11, 'q': 12, 'w': 13, 'e': 14, 'r': 15,
             'y': 16, 't': 17, '1': 18, '2': 19, '3': 20, '4': 21, '6': 22,
             '5': 23, '9': 25, '7': 26, '8': 28, '0': 29, 'o': 31, 'u': 32,
             'i': 34, 'p': 35, 'l': 37, 'j': 38, 'k': 40, 'n': 45, 'm': 46}


@dataclass(frozen=True)
class Shortcut:
    key_code: int
    modifiers: int
    label: str

    @classmethod
    def parse(cls, value):
        parts = value.lower().replace('command', 'cmd').replace('control', 'ctrl').replace('alt', 'option').split('+')
        parts = [part.strip() for part in parts]
        if (len(parts) < 2 or parts[-1] not in KEY_CODES
                or any(part not in MODIFIERS for part in parts[:-1])
                or len(set(parts[:-1])) != len(parts[:-1])
                or not set(parts[:-1]).intersection({'cmd', 'ctrl', 'option'})):
            raise ValueError('Use a shortcut such as cmd+shift+a or ctrl+option+a.')
        mask = sum(MODIFIERS[part] for part in parts[:-1])
        symbols = {'ctrl': '⌃', 'option': '⌥', 'shift': '⇧', 'cmd': '⌘'}
        label = ''.join(symbols[key] for key in symbols if key in parts[:-1]) + parts[-1].upper()
        return cls(KEY_CODES[parts[-1]], mask, label)


class EventType(C.Structure):
    _fields_ = [('eventClass', C.c_uint32), ('eventKind', C.c_uint32)]


class HotKeyID(C.Structure):
    _fields_ = [('signature', C.c_uint32), ('identifier', C.c_uint32)]


CALLBACK = C.CFUNCTYPE(C.c_int32, C.c_void_p, C.c_void_p, C.c_void_p)


def _load_carbon():
    lib = C.CDLL('/System/Library/Frameworks/Carbon.framework/Carbon')
    signatures = {
        'GetApplicationEventTarget': (C.c_void_p, []),
        'InstallEventHandler': (C.c_int32, [C.c_void_p, CALLBACK, C.c_uint32, C.POINTER(EventType), C.c_void_p, C.POINTER(C.c_void_p)]),
        'RemoveEventHandler': (C.c_int32, [C.c_void_p]),
        'RegisterEventHotKey': (C.c_int32, [C.c_uint32, C.c_uint32, HotKeyID, C.c_void_p, C.c_uint32, C.POINTER(C.c_void_p)]),
        'UnregisterEventHotKey': (C.c_int32, [C.c_void_p]),
        'GetEventKind': (C.c_uint32, [C.c_void_p]),
        'GetEventParameter': (C.c_int32, [C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p, C.c_uint32, C.c_void_p, C.c_void_p]),
    }
    for name, (result, args) in signatures.items():
        getattr(lib, name).restype = result
        getattr(lib, name).argtypes = args
    return lib


class GlobalHotkeys:
    def __init__(self, on_press, library=None):
        self.on_press = on_press
        self.lib = library
        self.handler = C.c_void_p()
        self.references = {}
        self.down = set()
        self.callback = CALLBACK(self._dispatch)

    @staticmethod
    def _assert_main():
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError('Register and dispose shortcuts on the main thread.')

    def register(self, shortcut):
        self._assert_main()
        if self.lib is None:
            self.lib = _load_carbon()
        target = self.lib.GetApplicationEventTarget()
        if not self.handler.value:
            events = (EventType * 2)(EventType(KEYBOARD, PRESSED), EventType(KEYBOARD, RELEASED))
            status = self.lib.InstallEventHandler(target, self.callback, 2, events, None, C.byref(self.handler))
            if status:
                raise RuntimeError('Could not install the shortcut handler (macOS %s).' % status)
        identifier = len(self.references) + 1
        reference = C.c_void_p()
        status = self.lib.RegisterEventHotKey(shortcut.key_code, shortcut.modifiers,
                                             HotKeyID(SIGNATURE, identifier), target, 1, C.byref(reference))
        if status:
            raise RuntimeError('%s is unavailable or already in use (macOS %s).' % (shortcut.label, status))
        self.references[identifier] = reference

    def _dispatch(self, handler, event, user_data):
        try:
            identifier = HotKeyID()
            status = self.lib.GetEventParameter(event, int.from_bytes(b'----', 'big'),
                                               int.from_bytes(b'hkid', 'big'), None,
                                               C.sizeof(identifier), None, C.byref(identifier))
            if status or identifier.signature != SIGNATURE or identifier.identifier not in self.references:
                return NOT_HANDLED
            key = identifier.identifier
            if self.lib.GetEventKind(event) == RELEASED:
                self.down.discard(key)
            elif self.lib.GetEventKind(event) == PRESSED and key not in self.down:
                self.down.add(key)
                self.on_press()
            return 0
        except Exception:
            LOG.exception('Amillum shortcut callback failed')
            return NOT_HANDLED

    def close(self):
        self._assert_main()
        if self.lib:
            for reference in self.references.values():
                self.lib.UnregisterEventHotKey(reference)
            if self.handler.value:
                self.lib.RemoveEventHandler(self.handler)
        self.references.clear()
        self.down.clear()
        self.handler = C.c_void_p()
