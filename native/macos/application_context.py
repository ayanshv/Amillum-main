"""Opt-in, event-driven application identity only. No Accessibility text APIs."""

import queue
import threading
import AppKit as AK
from PyObjCTools import AppHelper

from native.bridge import request
from native.macos.accessibility import AccessibilityReader, FocusObserver
from native.macos.permissions import accessibility_granted, request_accessibility, capture_granted, request_capture
from native.macos.indicator import ContextIndicator
from native.macos.region_reader import RegionReader
from core.legal_context import classify_title


class ApplicationObserver(AK.NSObject):
    def activated_(self, notification):
        self.owner.sample()


class ApplicationAwareness:
    def __init__(self, activate=lambda: None, panel_update=None):
        self.indicator = ContextIndicator(activate)
        self.panel_update=panel_update
        self.policy = {'enabled': False, 'epoch': -1, 'excluded': []}
        self.observer = ApplicationObserver.alloc().init()
        self.observer.owner = self
        self.subscribed = False
        self.closed = False
        self.stop = threading.Event()
        self.pending = queue.Queue(maxsize=1)
        self.thread = None
        self.reader = AccessibilityReader()
        self.focus = FocusObserver(self.sample)
        self.handled_permission_request = 0
        self.handled_capture_request = 0

    def start(self):
        self.thread = threading.Thread(target=self.sync, name='amillum-awareness-bridge', daemon=True)
        self.thread.start()

    def sync(self):
        previous = None
        while not self.stop.is_set():
            try:
                policy = request('policy')
                granted = accessibility_granted()
                request('permissions', {'accessibility': granted, 'capture': capture_granted()})
                policy['accessibility_granted'] = granted
                if self.panel_update:
                    AppHelper.callAfter(self.deliver_panel,request('panel_state'))
                if policy != previous:
                    previous = policy
                    AppHelper.callAfter(self.apply_policy, policy)
                try:
                    payload = self.pending.get_nowait()
                except queue.Empty:
                    payload = None
                if payload is not None:
                    request('publish', payload)
            except (OSError, ValueError, TypeError):
                previous = None
                if self.panel_update:
                    AppHelper.callAfter(self.deliver_panel,{})
                AppHelper.callAfter(self.apply_policy, {'enabled': False, 'epoch': -1, 'excluded': []})
            self.stop.wait(.5)  # Local control/liveness only; does not poll applications or screens.

    def deliver_panel(self,snapshot):
        if not self.closed and self.panel_update:
            self.panel_update(snapshot)

    def apply_policy(self, policy):
        if self.closed:
            return
        self.policy = policy
        request_id = policy.get('permission_request', 0)
        if request_id > self.handled_permission_request:
            self.handled_permission_request = request_id
            request_accessibility()
        capture_id = policy.get('capture_request', 0)
        if capture_id > self.handled_capture_request:
            self.handled_capture_request = capture_id
            request_capture()
        self.indicator.clear()
        center = AK.NSWorkspace.sharedWorkspace().notificationCenter()
        if policy.get('enabled') and not self.subscribed:
            center.addObserver_selector_name_object_(self.observer, 'activated:',
                                                     AK.NSWorkspaceDidActivateApplicationNotification, None)
            self.subscribed = True
        elif not policy.get('enabled') and self.subscribed:
            center.removeObserver_(self.observer)
            self.subscribed = False
        if not policy.get('enabled'):
            self.clear_pending()
            self.focus.close()
        elif policy.get('refresh'):
            self.sample()
        if not policy.get('accessibility_enabled') or not policy.get('accessibility_granted'):
            self.focus.close()

    def clear_pending(self):
        try:
            self.pending.get_nowait()
        except queue.Empty:
            pass

    def sample(self):
        if self.closed or not self.policy.get('enabled'):
            return
        self.indicator.clear()
        application = AK.NSWorkspace.sharedWorkspace().frontmostApplication()
        identifier = application.bundleIdentifier() if application else None
        payload = {'epoch': self.policy['epoch']}
        if not identifier:
            self.focus.close()
            payload['status'] = 'unavailable'
        elif identifier in self.policy['excluded']:
            self.focus.close()
            payload['status'] = 'excluded'
        else:
            payload.update(bundle_id=str(identifier), name=str(application.localizedName() or 'Application'))
            if self.policy.get('accessibility_enabled'):
                if self.policy.get('accessibility_granted'):
                    pid = application.processIdentifier()
                    self.focus.watch(pid)
                    payload['metadata'] = self.reader.focused_metadata(pid)
                    if self.policy.get('smart_enabled') and payload['metadata'].get('status') == 'metadata':
                        try:
                            reader = RegionReader()
                            window = reader.window(pid)
                            bounds = payload['metadata'].get('bounds') or reader.bounds(window)
                            # Domain and field checks precede title access. No body text is read.
                            reader.preflight(pid, identifier, bounds, self.policy.get('excluded_domains', []))
                            suggestion = classify_title(reader.attribute(window, 'AXTitle'))
                            if suggestion:
                                payload['suggestion'] = suggestion
                                self.indicator.update(suggestion)
                        except Exception:
                            pass  # Incomplete metadata stays quiet and fails closed.

                else:
                    self.focus.close()
                    payload['metadata'] = {'status': 'permission_required'}
        self.clear_pending()
        self.pending.put_nowait(payload)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.indicator.close()
        self.focus.close()
        self.stop.set()
        if self.subscribed:
            AK.NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(self.observer)
        self.subscribed = False
        self.clear_pending()
        self.policy = {'enabled': False, 'epoch': -1, 'excluded': []}
        self.observer.owner = None
        if self.thread:
            self.thread.join(timeout=1)
