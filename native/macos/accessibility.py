"""Opt-in focused-element structure only; never requests AXValue or text.

The injected adapter makes permission denial and secure-field behavior testable
without granting system access or querying private content.
"""

import math
from native.macos.secure_field_filter import block_reason


class AccessibilityReader:
    def __init__(self, api=None):
        if api is None:
            import ApplicationServices as api
        self.api = api

    def attribute(self, element, name):
        error, value = self.api.AXUIElementCopyAttributeValue(element, name, None)
        return value if error == 0 else None

    def focused_metadata(self, pid):
        if not self.api.AXIsProcessTrusted():
            return {'status': 'permission_required'}
        app = self.api.AXUIElementCreateApplication(pid)
        self.api.AXUIElementSetMessagingTimeout(app, .15)
        element = self.attribute(app, 'AXFocusedUIElement')
        if element is None:
            return {'status': 'unavailable'}
        role = self.attribute(element, 'AXRole')
        subrole = self.attribute(element, 'AXSubrole')
        reason = block_reason(role, subrole)
        if reason:
            return {'status': 'blocked', 'reason': reason}
        result = {'status': 'metadata', 'role': role}
        position = self.attribute(element, 'AXPosition')
        size = self.attribute(element, 'AXSize')
        if position is not None and size is not None:
            ok_point, point = self.api.AXValueGetValue(position, self.api.kAXValueCGPointType, None)
            ok_size, dimensions = self.api.AXValueGetValue(size, self.api.kAXValueCGSizeType, None)
            if ok_point and ok_size:
                bounds = [float(point.x), float(point.y), float(dimensions.width), float(dimensions.height)]
                if all(math.isfinite(v) and abs(v) < 1_000_000 for v in bounds) and bounds[2] >= 0 and bounds[3] >= 0:
                    result['bounds'] = bounds  # AX coordinates: top-left screen origin, points.
        return result


class FocusObserver:
    """Subscribe to focus changes in one permitted application, never all apps."""
    def __init__(self, callback):
        self.callback = callback
        self.observer = None
        self.application = None
        self.source = None
        self.generation = 0
        self.pending = False
        self.pid = None
        import objc
        import ApplicationServices as AX
        @objc.callbackFor(AX.AXObserverCreate)
        def native_callback(observer, element, notification, refcon):
            self.changed(observer, element, notification, refcon)
        self.native_callback = native_callback

    def watch(self, pid):
        if self.pid == pid:
            return
        self.close()
        import ApplicationServices as AX
        import CoreFoundation as CF
        if not AX.AXIsProcessTrusted():
            return
        self.pid = pid
        self.application = AX.AXUIElementCreateApplication(pid)
        AX.AXUIElementSetMessagingTimeout(self.application, .15)
        error, observer = AX.AXObserverCreate(pid, self.native_callback, None)
        if error:
            self.close()
            return
        self.observer = observer
        error = AX.AXObserverAddNotification(observer, self.application, 'AXFocusedUIElementChanged', None)
        window_error = AX.AXObserverAddNotification(observer, self.application, 'AXFocusedWindowChanged', None)
        if error and window_error:
            self.close()
            return
        error, window = AX.AXUIElementCopyAttributeValue(self.application, 'AXFocusedWindow', None)
        if not error and window is not None:
            AX.AXObserverAddNotification(observer, window, 'AXTitleChanged', None)
        error, focused = AX.AXUIElementCopyAttributeValue(self.application, 'AXFocusedUIElement', None)
        if not error and focused is not None:
            error, role = AX.AXUIElementCopyAttributeValue(focused, 'AXRole', None)
            if not error and role in ('AXTextArea', 'AXStaticText'):
                AX.AXObserverAddNotification(observer, focused, 'AXSelectedTextChanged', None)
        self.source = AX.AXObserverGetRunLoopSource(observer)
        CF.CFRunLoopAddSource(CF.CFRunLoopGetMain(), self.source, CF.kCFRunLoopCommonModes)

    def changed(self, observer, element, notification, refcon):
        if not self.pending:
            from PyObjCTools import AppHelper
            self.pending = True
            generation = self.generation
            AppHelper.callLater(.75 if str(notification)=='AXSelectedTextChanged' else .2, self.deliver, generation)

    def deliver(self, generation):
        if generation != self.generation:
            return
        self.pending = False
        # Refresh the title observer when focus switches to another window.
        self.close()
        self.callback()

    def close(self):
        self.generation += 1
        self.pending = False
        if self.source is not None:
            import CoreFoundation as CF
            CF.CFRunLoopRemoveSource(CF.CFRunLoopGetMain(), self.source, CF.kCFRunLoopCommonModes)
        self.observer = self.application = self.source = self.pid = None
