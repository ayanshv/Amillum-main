"""Own the native feature inside NiceGUI's existing PyWebView process."""

import logging
import os
import threading

import objc
import AppKit as AK

from native.macos.global_hotkey import GlobalHotkeys, Shortcut
from native.macos.overlay import Overlay
from native.macos.context_reader import ContextReader
from native.macos.application_context import ApplicationAwareness
from native.macos.context_panel import ContextPanel

LOG = logging.getLogger(__name__)
_runtime = None


class LifecycleObserver(AK.NSObject):
    def interrupted_(self, notification):
        self.runtime.overlay.cancel(restore_focus=False)
        if self.runtime.reader.busy:
            self.runtime.reader.cancel()

    def appearanceChanged_(self, notification):
        self.runtime.overlay.render()

    def windowClosed_(self, notification):
        if notification.object() == self.runtime.main_window:
            self.runtime.close()

    def terminating_(self, notification):
        self.runtime.close()


class Runtime:
    def __init__(self, main_window):
        self.main_window = main_window
        self.reader = ContextReader(self.open_review)
        self.overlay = Overlay(self.reader.start)
        self.panel = ContextPanel(self.open_review, lambda: self.open_page('/context?ask=true'))
        self.awareness = ApplicationAwareness(self.activate, self.panel.update)
        self.hotkeys = GlobalHotkeys(self.activate)
        self.observer = LifecycleObserver.alloc().init()
        self.observer.runtime = self
        self.centers = []
        self.closed = False
        self.alert = None
        self.desktop = None

    def start(self):
        from native.macos.lifecycle import DesktopLifecycle
        self.desktop = DesktopLifecycle(self.main_window)
        self.desktop.start()
        self.awareness.indicator.start(self.desktop.show, self.open_settings, self.desktop.quit)
        self.awareness.start()
        main = AK.NSNotificationCenter.defaultCenter()
        workspace = AK.NSWorkspace.sharedWorkspace().notificationCenter()
        self.centers = [main, workspace]
        for name, selector in (
            (AK.NSApplicationDidChangeScreenParametersNotification, 'interrupted:'),
            (AK.NSWindowWillCloseNotification, 'windowClosed:'),
            (AK.NSApplicationWillTerminateNotification, 'terminating:'),
        ):
            main.addObserver_selector_name_object_(self.observer, selector, name, None)
        for name in (AK.NSWorkspaceWillSleepNotification,
                     AK.NSWorkspaceSessionDidResignActiveNotification,
                     AK.NSWorkspaceDidActivateApplicationNotification,
                     AK.NSWorkspaceActiveSpaceDidChangeNotification):
            workspace.addObserver_selector_name_object_(self.observer, 'interrupted:', name, None)
        workspace.addObserver_selector_name_object_(self.observer, 'appearanceChanged:',
                                                     AK.NSWorkspaceAccessibilityDisplayOptionsDidChangeNotification, None)
        try:
            primary = Shortcut.parse(os.environ.get('AMILLUM_SHORTCUT', 'cmd+shift+a'))
            self.hotkeys.register(primary)
        except Exception as exc:
            self.hotkeys.close()
            self.show_error('Amillum’s shortcut is unavailable', str(exc) + '\n\nSet AMILLUM_SHORTCUT to another combination and restart Amillum. Document analysis is still available.')
            return
        if os.environ.get('AMILLUM_CONTROL_SHORTCUT', '1') == '1' and primary == Shortcut.parse('cmd+shift+a'):
            try:
                self.hotkeys.register(Shortcut.parse('ctrl+shift+a'))
            except Exception as exc:
                self.show_error('The alternate shortcut is unavailable', str(exc) + '\n\nUse ⌘⇧A to select an area.')
        LOG.info('Amillum native selection ready (%s)', primary.label)

    def activate(self):
        if self.closed or self.alert is not None or self.reader.busy:
            return
        try:
            self.overlay.activate()
        except Exception:
            LOG.exception('Amillum could not enter selection mode')
            self.show_error('Selection could not start', 'Nothing was captured. Please try again.')

    def open_settings(self):
        self.open_page('/settings')

    def open_review(self):
        self.open_page('/context')

    def open_page(self, path):
        import webview
        from urllib.parse import urlsplit
        if self.closed or not webview.windows:
            return
        window = webview.windows[0]
        url = urlsplit(window.real_url)  # get_current_url blocks waiting for Cocoa; never call it on this thread.
        window.load_url(f'{url.scheme}://{url.netloc}{path}')
        if self.desktop:
            self.desktop.show()

    def show_error(self, title, message):
        LOG.warning('%s: %s', title, message)
        if self.closed or self.alert is not None:
            return
        self.alert = AK.NSAlert.alloc().init()
        self.alert.setMessageText_(title)
        self.alert.setInformativeText_(message)
        self.alert.addButtonWithTitle_('OK')

        def dismissed(response):
            self.alert = None

        self.alert.beginSheetModalForWindow_completionHandler_(self.main_window, dismissed)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.reader.close()
        self.awareness.close()
        self.panel.close()
        self.overlay.cancel(restore_focus=False)
        self.hotkeys.close()
        for center in self.centers:
            center.removeObserver_(self.observer)
        self.centers.clear()
        if self.alert:
            self.main_window.endSheet_(self.alert.window())
            self.alert = None
        self.observer.runtime = None
        if self.desktop:
            self.desktop.close()


def install():
    global _runtime
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('Native selection must initialize on the Cocoa main thread.')
    if _runtime is not None:
        return
    import webview
    if not webview.windows:
        return  # The application was closed before the startup callback ran.
    runtime = Runtime(webview.windows[0].native)
    _runtime = runtime
    try:
        runtime.start()
    except Exception:
        runtime.close()
        LOG.exception('Native selection initialization failed; document UI remains available')
