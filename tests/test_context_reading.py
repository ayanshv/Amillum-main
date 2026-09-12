import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from core.context_session import ContextSession
from core.context_awareness import AwarenessState
from core.privacy import PrivacyPreferences, domain_excluded
from core.legal_context import classify_title
from native.macos.region_reader import RegionReader, ReadBlocked, screen_rect
from native.selection import Rect


class ContextSessionTests(unittest.TestCase):
    def test_clear_invalidates_inflight_read_and_analysis(self):
        session = ContextSession()
        old = session.begin('com.example.document')
        session.clear()
        self.assertFalse(session.finish(old, 'private'))
        token = session.begin('com.example.document')
        self.assertTrue(session.finish(token, 'approved text', method='Accessibility'))
        self.assertFalse(session.finish(token, 'replay'))
        revision, text = session.approve_analysis(session.revision, 'edited text')
        self.assertEqual(text, 'edited text')
        session.clear()
        self.assertFalse(session.finish_analysis(revision, 'stale result'))
        self.assertEqual(session.snapshot()['text'], '')

    def test_expired_ticket_does_not_publish(self):
        now = [0]
        session = ContextSession(clock=lambda: now[0])
        ticket = session.begin('com.example.document')
        now[0] = 31
        self.assertFalse(session.finish(ticket, 'late'))
        self.assertEqual(session.snapshot()['status'], 'error')

    def test_privacy_policy_change_revokes_approval(self):
        with tempfile.TemporaryDirectory() as d:
            state = AwarenessState(PrivacyPreferences(Path(d)/'privacy.json'))
            ticket = state.begin_context({'bundle_id': 'com.apple.TextEdit'})
            self.assertTrue(state.context_valid(ticket))
            state.update(paused=True)
            self.assertFalse(state.finish_context({**ticket, 'text': 'late'}))
            self.assertIn('error', state.begin_context({'bundle_id': 'com.apple.TextEdit'}))
            state.update(paused=False)
            self.assertIn('error', state.begin_context({'bundle_id': 'com.apple.Passwords'}))

    def test_domains_persist_and_match_subdomains_only(self):
        with tempfile.TemporaryDirectory() as d:
            prefs = PrivacyPreferences(Path(d)/'privacy.json')
            state = AwarenessState(prefs)
            state.exclude_domain('example.com')
            self.assertEqual(PrivacyPreferences(prefs.path).domains, {'example.com'})
            self.assertTrue(domain_excluded('https://secure.example.com/path', prefs.domains))
            self.assertFalse(domain_excluded('https://notexample.com', prefs.domains))
            self.assertFalse(domain_excluded('https://example.com.evil.test', prefs.domains))

    def test_classifier_is_selective_and_title_only(self):
        for title in ['Shopping list', 'Weather tomorrow', 'Weekly meeting notes', None]:
            self.assertIsNone(classify_title(title))
        self.assertEqual(classify_title('Employment Agreement.pdf')['label'], 'Employment agreement')
        self.assertEqual(classify_title('Residential lease – Preview')['label'], 'Lease or tenancy')

    def test_multiple_monitor_geometry_preserves_negative_origins(self):
        self.assertEqual(screen_rect(Rect(-500, 100, 250, 100), 900), (-500, 700, 250, 100))
        self.assertEqual(screen_rect(Rect(50, 950, 200, 80), 900), (50, -130, 200, 80))


class FakeAPI:
    def __init__(self, tree):
        self.tree = tree
        self.calls = []
    def AXIsProcessTrusted(self): return True
    def AXUIElementCreateApplication(self, pid): return 'app'
    def AXUIElementSetMessagingTimeout(self, app, timeout): pass
    def AXUIElementCopyAttributeValue(self, element, name, output):
        self.calls.append((element, name))
        return 0, self.tree.get(element, {}).get(name)


class RegionTests(unittest.TestCase):
    def setUp(self):
        self.tree = {
            'app': {'AXFocusedWindow': 'window', 'AXFocusedUIElement': 'text'},
            'window': {'AXRole': 'AXWindow', 'AXChildren': ['text']},
            'text': {'AXRole': 'AXStaticText', 'AXValue': 'Synthetic lease agreement'},
        }
        self.boxes = {'window': (0, 0, 800, 600), 'text': (100, 100, 300, 100)}
        self.api = FakeAPI(self.tree)
        self.reader = RegionReader(self.api)
        self.reader.bounds = lambda element: self.boxes.get(element)
        self.rect = (80, 80, 400, 160)

    def test_no_text_before_completed_preflight(self):
        checked = self.reader.preflight(1, 'com.apple.TextEdit', self.rect, [])
        self.assertFalse(any(name == 'AXValue' for _, name in self.api.calls))
        self.assertEqual(self.reader.extract(checked), 'Synthetic lease agreement')

    def test_protected_field_anywhere_in_region_prevents_read(self):
        self.tree['window']['AXChildren'].append('secure')
        self.tree['secure'] = {'AXRole': 'AXTextField', 'AXSubrole': 'AXSecureTextField', 'AXValue': 'never read'}
        self.boxes['secure'] = (150, 130, 100, 30)
        with self.assertRaises(ReadBlocked):
            self.reader.preflight(1, 'com.apple.TextEdit', self.rect, [])
        self.assertFalse(any(name == 'AXValue' for _, name in self.api.calls))

    def test_partial_text_never_reads_the_whole_element(self):
        checked = self.reader.preflight(1, 'com.apple.TextEdit', (120, 100, 200, 100), [])
        self.assertEqual(self.reader.extract(checked), '')
        self.assertFalse(any(name == 'AXValue' for _, name in self.api.calls))

    def test_changed_bounds_block_extraction(self):
        checked = self.reader.preflight(1, 'com.apple.TextEdit', self.rect, [])
        self.boxes['text'] = (120, 100, 300, 100)
        with self.assertRaises(ReadBlocked):
            self.reader.extract(checked)

    def test_domain_filter_precedes_text(self):
        self.tree['window']['AXDocument'] = 'https://bank.example.com/document'
        with self.assertRaises(ReadBlocked):
            self.reader.preflight(1, 'com.apple.Safari', self.rect, ['example.com'])
        self.assertFalse(any(name == 'AXValue' for _, name in self.api.calls))

    def test_missing_browser_address_blocks(self):
        with self.assertRaises(ReadBlocked):
            self.reader.preflight(1, 'com.apple.Safari', self.rect, [])

    def test_editable_text_never_uses_whole_value(self):
        self.tree['text']['AXRole'] = 'AXTextArea'
        checked = self.reader.preflight(1, 'com.apple.TextEdit', self.rect, [])
        self.assertEqual(self.reader.extract(checked), '')  # Adapter has no bounded-range support.
        self.assertFalse(any(name == 'AXValue' for _, name in self.api.calls))

    def test_unknown_metadata_blocks_without_capture(self):
        self.tree['text']['AXRole'] = 'AXUnknown'
        with self.assertRaises(ReadBlocked):
            self.reader.preflight(1, 'com.apple.TextEdit', self.rect, [])
        self.assertFalse(any(name == 'AXValue' for _, name in self.api.calls))


class NativeApprovalTests(unittest.TestCase):
    def setUp(self):
        cursor = patch("native.macos.overlay.AK.NSCursor")
        cursor.start()
        self.addCleanup(cursor.stop)

    def test_drag_does_not_read_and_approve_is_one_shot(self):
        from native.macos.overlay import Overlay
        from native.selection import Display, Point
        from unittest.mock import Mock
        callback = Mock()
        overlay = Overlay(callback)
        display = Display(1, Rect(0, 0, 800, 600), 2)
        overlay.selection.activate()
        overlay.begin(display, Point(20, 20))
        overlay.finish(Point(300, 200))
        callback.assert_not_called()
        overlay.approve()
        callback.assert_called_once()
        overlay.approve()
        callback.assert_called_once()

    def test_cancel_never_reads(self):
        from native.macos.overlay import Overlay
        from unittest.mock import Mock
        callback = Mock()
        overlay = Overlay(callback)
        overlay.selection.activate()
        overlay.cancel(restore_focus=False)
        overlay.approve()
        callback.assert_not_called()


if __name__ == '__main__':
    unittest.main()

class CaptureBoundaryTests(unittest.TestCase):
    def test_capture_uses_display_relative_approved_rectangle_and_one_window(self):
        from unittest.mock import Mock
        import Quartz as Q
        from native.macos.screen_capture import capture_region
        config = Mock()
        window = Mock()
        window.windowID.return_value = 42
        window.frame.return_value = Q.CGRectMake(100, 100, 800, 500)
        content = Mock()
        content.windows.return_value = [window]
        display = Mock()
        display.frame.return_value = Q.CGRectMake(100, 50, 1000, 800)
        content.displays.return_value = [display]
        api = Mock()
        api.SCStreamConfiguration.alloc.return_value.init.return_value = config
        api.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_.side_effect = lambda a,b,callback: callback(content, None)
        image = object()
        api.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_.side_effect = lambda f,c,callback: callback(image, None)
        info = {Q.kCGWindowLayer:0, Q.kCGWindowOwnerPID:7, Q.kCGWindowNumber:42,
                Q.kCGWindowBounds:{'X':100,'Y':100,'Width':800,'Height':500}}
        with patch.dict('sys.modules', {'ScreenCaptureKit':api}), patch.object(Q,'CGPreflightScreenCaptureAccess',return_value=True), patch.object(Q,'CGWindowListCopyWindowInfo',return_value=[info]):
            self.assertIs(capture_region(7,(120,150,400,30),lambda:True),image)
        actual = config.setSourceRect_.call_args[0][0]
        self.assertEqual((actual.origin.x,actual.origin.y,actual.size.width,actual.size.height),(20,100,400,30))
        config.setWidth_.assert_called_once_with(800)
        config.setHeight_.assert_called_once_with(60)
        api.SCContentFilter.alloc.return_value.initWithDisplay_includingWindows_.assert_called_once_with(display,[window])
        api.SCContentFilter.alloc.return_value.initWithDesktopIndependentWindow_.assert_not_called()

    def test_permission_denial_never_requests_capture(self):
        from unittest.mock import Mock
        import Quartz as Q
        from native.macos.screen_capture import capture_region
        api=Mock()
        with patch.dict('sys.modules', {'ScreenCaptureKit':api}), patch.object(Q,'CGPreflightScreenCaptureAccess',return_value=False):
            with self.assertRaises(ReadBlocked): capture_region(7,(1,1,100,100),lambda:True)
        api.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_.assert_not_called()


class ReviewNavigationTests(unittest.TestCase):
    def test_cocoa_handoff_avoids_blocking_url_query(self):
        from unittest.mock import Mock
        from native.macos.runtime import Runtime
        window = Mock(real_url='http://127.0.0.1:8000/')
        window.get_current_url.side_effect = AssertionError('Would deadlock Cocoa main thread')
        runtime = Runtime.__new__(Runtime)
        runtime.closed = False
        runtime.main_window = Mock()
        runtime.desktop = Mock()
        with patch('webview.windows', [window]), patch('native.macos.runtime.AK.NSApp'):
            runtime.open_review()
        window.load_url.assert_called_once_with('http://127.0.0.1:8000/context')
        runtime.desktop.show.assert_called_once_with()

class HandoffRegressionTests(unittest.TestCase):
    def test_completed_preview_survives_native_bridge_delay(self):
        with tempfile.TemporaryDirectory() as d:
            now=[0]
            state=AwarenessState(PrivacyPreferences(Path(d)/'privacy.json'),clock=lambda:now[0])
            state.heartbeat()
            ticket=state.begin_context({'bundle_id':'com.apple.TextEdit'})
            state.finish_context({**ticket,'text':'Approved text','method':'Accessibility'})
            now[0]=20
            self.assertFalse(state.snapshot()['connected'])
            self.assertEqual(state.context.snapshot()['text'],'Approved text')
            state.update(paused=True)
            self.assertEqual(state.context.snapshot()['text'],'')

    def test_focus_change_does_not_invalidate_completed_handoff(self):
        from unittest.mock import Mock
        from native.macos.runtime import LifecycleObserver
        observer=LifecycleObserver.alloc().init()
        observer.runtime=Mock()
        observer.runtime.reader.busy=False
        observer.interrupted_(None)
        observer.runtime.reader.cancel.assert_not_called()
        observer.runtime.reader.busy=True
        observer.interrupted_(None)
        observer.runtime.reader.cancel.assert_called_once()
