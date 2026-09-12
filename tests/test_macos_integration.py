"""Opt-in real AppKit tests. Briefly shows selection panels, never captures pixels.

AMILLUM_NATIVE_TESTS=1 python -B -m unittest discover -s tests -p test_macos_integration.py -v
Run in a logged-in macOS GUI session. Ordinary test discovery skips this module.
"""

import os
import sys
import unittest
from unittest.mock import patch


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('AMILLUM_NATIVE_TESTS') == '1',
                     'opt-in macOS window-server tests')
class MacOSIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import AppKit as AK
        AK.NSApplication.sharedApplication()

    def setUp(self):
        from native.macos.overlay import Overlay
        self.overlay = Overlay()

    def tearDown(self):
        self.overlay.cancel(restore_focus=False)

    def test_context_panel_actions_dismiss_and_clear(self):
        from unittest.mock import Mock
        from native.macos.context_panel import ContextPanel
        from test_contextual_analysis import RESULT
        full,ask=Mock(),Mock()
        panel=ContextPanel(full,ask)
        try:
            panel.update({'revision':1,'result':RESULT})
            self.assertTrue(panel.window.isVisible())
            self.assertIn('ATTENTION · Moderate',panel.text.string())
            buttons={v.title():v for v in panel.window.contentView().subviews() if hasattr(v,'title')}
            self.assertFalse(buttons['Add to Workbench'].isEnabled())
            buttons['Open Full Analysis'].performClick_(None);full.assert_called_once()
            buttons['Ask Amillum'].performClick_(None);ask.assert_called_once()
            panel.window.performClose_(None)
            panel.update({'revision':1,'result':RESULT})
            self.assertFalse(panel.window.isVisible())
            panel.update({'revision':2,'result':RESULT})
            self.assertTrue(panel.window.isVisible())
            panel.update({})
            self.assertFalse(panel.window.isVisible())
            self.assertIsNone(panel.beaver.timer)
        finally:panel.close()

    def test_accessibility_observer_retains_a_native_callback(self):
        import ApplicationServices as AX
        from native.macos.accessibility import FocusObserver
        observer = FocusObserver(lambda: None)
        error, handle = AX.AXObserverCreate(os.getpid(), observer.native_callback, None)
        self.assertEqual(error, 0)
        self.assertIsNotNone(handle)
        observer.close()

    def test_real_panels_border_anchor_and_cancel_action(self):
        from native.selection import Phase, Point
        self.overlay.activate()
        panel = self.overlay.panels[0]
        view = panel.contentView()
        b = view.display.bounds
        self.assertFalse(panel.isOpaque())
        self.assertFalse(panel.hasShadow())
        self.assertTrue(panel.isVisible())
        self.assertEqual(panel.backgroundColor().alphaComponent(), 0)
        self.overlay.begin(view.display, Point(b.x + 100, b.y + 100))
        self.overlay.finish(Point(b.x + 400, b.y + 300))
        self.assertIsNotNone(view.border.path())
        self.assertEqual(self.overlay.anchor.position, Point(b.x + 250, b.y + 100))
        self.assertFalse(view.card.isHidden())
        # Invoke the real native button's action, not a parallel mock handler.
        view.cancel_button.performClick_(None)
        self.assertEqual(self.overlay.selection.phase, Phase.IDLE)
        self.assertIsNone(self.overlay.selection.rect)
        self.assertIsNone(self.overlay.anchor.position)
        self.assertFalse(panel.isVisible())
        self.assertFalse(view.border.animationKeys())

    def test_beaver_is_noninteractive_and_cancel_stops_animation(self):
        import AppKit as AK
        from native.selection import Point
        self.overlay.activate()
        view=self.overlay.panels[0].contentView()
        b=view.display.bounds
        self.overlay.begin(view.display,Point(b.x+100,b.y+100))
        self.overlay.finish(Point(b.x+400,b.y+300))
        beaver=view.beaver
        self.assertFalse(beaver.isHidden())
        self.assertEqual(beaver.state,'asking')
        self.assertIsNone(beaver.hitTest_(AK.NSMakePoint(10,10)))
        for button in (view.read_button,view.cancel_button):
            foreground=button.attributedTitle().attribute_atIndex_effectiveRange_(AK.NSForegroundColorAttributeName,0,None)[0]
            self.assertEqual(foreground,AK.NSColor.blackColor())
        with patch('native.macos.mascot.AK.NSWorkspace') as workspace:
            workspace.sharedWorkspace.return_value.accessibilityDisplayShouldReduceMotion.return_value=True
            beaver.show_state('asking')
            self.assertIsNone(beaver.timer)
        view.cancel_button.performClick_(None)
        self.assertIsNone(beaver.timer)
        self.assertFalse(self.overlay.panels)

    def test_repeated_sessions_and_escape_responder(self):
        for _ in range(20):
            self.overlay.activate()
            panels = list(self.overlay.panels)
            self.overlay.activate()
            self.assertEqual(self.overlay.panels, panels)
            panels[0].contentView().cancelOperation_(None)
            self.assertFalse(self.overlay.panels)
            self.assertTrue(all(not panel.isVisible() for panel in panels))

    def test_reduce_motion_stops_and_restarts_dash_animation(self):
        from native.selection import Point
        self.overlay.activate()
        view = self.overlay.panels[0].contentView()
        b = view.display.bounds
        self.overlay.begin(view.display, Point(b.x + 100, b.y + 100))
        self.overlay.finish(Point(b.x + 400, b.y + 300))
        # Exercise the real rendering path without changing the user's settings.
        with patch('native.macos.overlay.AK.NSWorkspace') as workspace:
            workspace.sharedWorkspace.return_value.accessibilityDisplayShouldReduceMotion.return_value = True
            view.render()
            self.assertFalse(view.border.animationKeys())
            workspace.sharedWorkspace.return_value.accessibilityDisplayShouldReduceMotion.return_value = False
            view.render()
            self.assertIn('amillum.dashes', view.border.animationKeys())

    def test_native_registration_conflict_and_release(self):
        from native.macos.global_hotkey import GlobalHotkeys, Shortcut
        # Avoid touching Amillum's active default registration in a separate app.
        shortcut = Shortcut.parse('cmd+ctrl+option+shift+9')
        first, second = GlobalHotkeys(lambda: None), GlobalHotkeys(lambda: None)
        try:
            first.register(shortcut)
            with self.assertRaises(RuntimeError):
                second.register(shortcut)
            first.close()
            second.register(shortcut)
        finally:
            first.close()
            second.close()

    def test_interruption_removes_selection_and_shutdown_is_idempotent(self):
        import AppKit as AK
        from native.macos.runtime import Runtime
        window = AK.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            AK.NSMakeRect(0, 0, 100, 100), AK.NSWindowStyleMaskTitled, AK.NSBackingStoreBuffered, False)
        window.setReleasedWhenClosed_(False)
        runtime = Runtime(window)
        try:
            runtime.overlay.activate()
            runtime.observer.interrupted_(None)
            self.assertFalse(runtime.overlay.panels)
            runtime.close()
            runtime.close()
            self.assertTrue(runtime.closed)
            self.assertIsNone(runtime.observer.runtime)
        finally:
            runtime.close()
            window.close()

    def test_background_window_and_persistent_menu(self):
        import AppKit as AK
        from unittest.mock import Mock
        from native.macos.lifecycle import DesktopLifecycle
        from native.macos.indicator import ContextIndicator
        window = AK.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            AK.NSMakeRect(0, 0, 100, 100),
            AK.NSWindowStyleMaskTitled | AK.NSWindowStyleMaskClosable,
            AK.NSBackingStoreBuffered, False)
        window.setReleasedWhenClosed_(False)
        lifecycle = DesktopLifecycle(window)
        indicator = ContextIndicator(Mock())
        open_settings, quit_app = Mock(), Mock()
        try:
            lifecycle.start()
            indicator.start(lifecycle.show, open_settings, quit_app)
            status_item = indicator.item
            self.assertIsNotNone(status_item)
            for _ in range(3):
                lifecycle.show()
                self.assertTrue(window.isVisible())
                window.performClose_(None)
                self.assertFalse(window.isVisible())
                # Clearing suggestions must never remove background access.
                indicator.update({'label': 'Contract'})
                indicator.clear()
                self.assertIs(indicator.item, status_item)
                indicator.target.open_(None)
                self.assertTrue(window.isVisible())
            titles = [item.title() for item in indicator.item.menu().itemArray()]
            self.assertIn('Open Amillum', titles)
            self.assertIn('Settings…', titles)
            self.assertIn('Quit Amillum', titles)
            indicator.target.settings_(None)
            open_settings.assert_called_once_with()
            indicator.target.quit_(None)
            quit_app.assert_called_once_with()
        finally:
            indicator.close()
            lifecycle.close()
            window.close()
        self.assertIsNone(indicator.item)

    def test_awareness_off_and_exclusions_precede_application_name(self):
        from native.macos.application_context import ApplicationAwareness
        tracker = ApplicationAwareness()
        try:
            with patch('native.macos.application_context.AK.NSWorkspace') as workspace:
                tracker.sample()
                workspace.sharedWorkspace.assert_not_called()
                app = workspace.sharedWorkspace.return_value.frontmostApplication.return_value
                app.bundleIdentifier.return_value = 'com.apple.Passwords'
                tracker.policy = {'enabled': True, 'epoch': 3, 'excluded': ['com.apple.Passwords']}
                tracker.sample()
                app.localizedName.assert_not_called()
                self.assertEqual(tracker.pending.get_nowait(), {'epoch': 3, 'status': 'excluded'})
        finally:
            tracker.close()


if __name__ == '__main__':
    unittest.main()
