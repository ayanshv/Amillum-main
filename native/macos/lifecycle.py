"""Keep PyWebView alive when its workspace closes; explicit Quit still terminates.

Subclass the installed Cocoa delegates so WebKit events and PyWebView's normal
termination checks remain intact. All calls run on the Cocoa main thread.
"""
import AppKit as AK
from webview.platforms.cocoa import BrowserView


class WorkspaceWindowDelegate(BrowserView.WindowDelegate):
    def windowShouldClose_(self, window):
        window.orderOut_(None)
        return False


class WorkspaceAppDelegate(BrowserView.AppDelegate):
    def applicationShouldHandleReopen_hasVisibleWindows_(self, application, visible):
        self.owner.show()
        return True


class DesktopLifecycle:
    def __init__(self, window):
        self.window = window
        self.previous_window_delegate = window.delegate()
        self.previous_app_delegate = AK.NSApp.delegate()
        self.window_delegate = WorkspaceWindowDelegate.alloc().init()
        self.app_delegate = WorkspaceAppDelegate.alloc().init()
        self.app_delegate.owner = self
        self.closed = False

    def start(self):
        self.window.setDelegate_(self.window_delegate)
        AK.NSApp.setDelegate_(self.app_delegate)

    def show(self):
        if self.closed:
            return
        if self.window.isMiniaturized():
            self.window.deminiaturize_(None)
        AK.NSApp.unhide_(None)
        self.window.makeKeyAndOrderFront_(None)
        AK.NSApp.activateIgnoringOtherApps_(True)

    def quit(self):
        if not self.closed:
            # Uses PyWebView's inherited applicationShouldTerminate: checks.
            AK.NSApp.terminate_(None)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.window.delegate() == self.window_delegate:
            self.window.setDelegate_(self.previous_window_delegate)
        if AK.NSApp.delegate() == self.app_delegate:
            AK.NSApp.setDelegate_(self.previous_app_delegate)
        self.app_delegate.owner = None
