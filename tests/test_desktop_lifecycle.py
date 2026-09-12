"""Lifecycle checks without screen access or background context collection."""
import unittest
from unittest.mock import Mock, patch

from native.macos.lifecycle import DesktopLifecycle, WorkspaceWindowDelegate, WorkspaceAppDelegate
from webview.platforms.cocoa import BrowserView


class DesktopLifecycleTests(unittest.TestCase):
    def test_close_hides_without_destroying_webview(self):
        window = Mock()
        delegate = WorkspaceWindowDelegate.alloc().init()
        for _ in range(3):
            self.assertFalse(delegate.windowShouldClose_(window))
        self.assertEqual(window.orderOut_.call_count, 3)
        window.close.assert_not_called()

    def test_reopen_preserves_window_and_restores_minimized_state(self):
        window = Mock()
        with patch('native.macos.lifecycle.AK.NSApp') as app:
            lifecycle = DesktopLifecycle(window)
            lifecycle.start()
            lifecycle.app_delegate.applicationShouldHandleReopen_hasVisibleWindows_(app, False)
            window.deminiaturize_.assert_called_once_with(None)
            window.makeKeyAndOrderFront_.assert_called_once_with(None)
            app.unhide_.assert_called_once_with(None)
            app.activateIgnoringOtherApps_.assert_called_once_with(True)
            lifecycle.close()
            lifecycle.close()
            lifecycle.show()
            self.assertEqual(window.makeKeyAndOrderFront_.call_count, 1)

    def test_quit_uses_normal_application_termination_not_window_hide(self):
        self.assertEqual(WorkspaceAppDelegate.applicationShouldTerminate_,
                         BrowserView.AppDelegate.applicationShouldTerminate_)
        with patch('native.macos.lifecycle.AK.NSApp') as app:
            lifecycle = DesktopLifecycle(Mock())
            lifecycle.quit()
            app.terminate_.assert_called_once_with(None)
            lifecycle.close()
            lifecycle.quit()
            app.terminate_.assert_called_once_with(None)
