"""Opt-in event-driven context; bounded local samples after privacy checks."""

import hashlib
import queue
import os
from concurrent.futures import ThreadPoolExecutor
import threading
import AppKit as AK
from PyObjCTools import AppHelper

from native.bridge import request
from native.macos.accessibility import AccessibilityReader, FocusObserver
from native.macos.permissions import accessibility_granted, request_accessibility, capture_granted, request_capture
from native.macos.indicator import ContextIndicator
from native.macos.detection_reader import DetectionReader as RegionReader
from core.legal_context import ContextDetector, classify_context
from core.proactive import AssistancePolicy
from native.macos.suggestion_panel import SuggestionPanel


class ApplicationObserver(AK.NSObject):
    def activated_(self, notification):
        self.owner.sample()


class ApplicationAwareness:
    def __init__(self, activate=lambda: None, panel_update=None):
        self.indicator = ContextIndicator(activate)
        self.panel_update=panel_update
        self.probes=ThreadPoolExecutor(max_workers=1,thread_name_prefix="amillum-metadata")
        self.probe_busy=False
        self.probe_generation=0
        self.policy = {'enabled': False, 'epoch': -1, 'excluded': []}
        self.observer = ApplicationObserver.alloc().init()
        self.observer.owner = self
        self.subscribed = False
        self.closed = False
        self.stop = threading.Event()
        self.pending = queue.Queue(maxsize=1)
        self.thread = None
        self.detector = ContextDetector()
        self.assistance = AssistancePolicy(self.detector)
        self.offer_panel = SuggestionPanel(self.respond_to_offer)
        self.activate_selection = activate
        self.source_identifier = None
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
        self.probe_generation += 1
        request_id = policy.get('permission_request', 0)
        if request_id > self.handled_permission_request:
            self.handled_permission_request = request_id
            request_accessibility()
        capture_id = policy.get('capture_request', 0)
        if capture_id > self.handled_capture_request:
            self.handled_capture_request = capture_id
            request_capture()
        self.indicator.clear()
        self.offer_panel.hide()
        self.assistance.hide()
        self.detector.clear_current()
        center = AK.NSWorkspace.sharedWorkspace().notificationCenter()
        if policy.get('enabled') and not self.subscribed:
            center.addObserver_selector_name_object_(self.observer, 'activated:',
                                                     AK.NSWorkspaceDidActivateApplicationNotification, None)
            self.subscribed = True
        elif not policy.get('enabled') and self.subscribed:
            center.removeObserver_(self.observer)
            self.subscribed = False
        if not policy.get('enabled'):
            self.detector.seen.clear()
            self.assistance.reset()
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
        self.probe_generation += 1
        generation=self.probe_generation
        application = AK.NSWorkspace.sharedWorkspace().frontmostApplication()
        identifier = application.bundleIdentifier() if application else None
        payload = {'epoch': self.policy['epoch']}
        if identifier != self.source_identifier:
            self.indicator.clear()
            self.offer_panel.hide()
            self.assistance.hide()
            self.detector.clear_current()
            self.source_identifier=identifier
        # Asking our own Accessibility server from Cocoa's thread can deadlock
        # until the AX timeout. Amillum never needs to inspect its own interface.
        if not identifier or application.processIdentifier() == os.getpid():
            self.focus.close()
            payload['status']='unavailable'
        elif identifier in self.policy['excluded']:
            self.focus.close()
            payload['status']='excluded'
        else:
            payload.update(bundle_id=str(identifier),name=str(application.localizedName() or 'Application'))
            if self.policy.get('accessibility_enabled') and self.policy.get('accessibility_granted'):
                pid=application.processIdentifier()
                self.focus.watch(pid)
                if not self.probe_busy:
                    self.probe_busy=True
                    self.probes.submit(self.inspect_context,pid,str(identifier),dict(self.policy),payload,generation)
                return  # Coalesce focus events; never queue an unbounded backlog.
            self.focus.close()
            if self.policy.get('accessibility_enabled'):
                payload['metadata']={'status':'permission_required'}
        self.clear_pending()
        self.pending.put_nowait(payload)

    def inspect_context(self,pid,identifier,policy,payload,generation):
        try:
            if self.closed or generation != self.probe_generation:return
            payload['metadata']=self.reader.focused_metadata(pid)
            if self.closed or generation != self.probe_generation:return
            if policy.get('smart_enabled') and payload['metadata'].get('status')=='metadata':
                reader=RegionReader()
                window=reader.window(pid)
                if self.closed or generation != self.probe_generation:return
                bounds=payload['metadata'].get('bounds') or reader.bounds(window)
                checked=reader.preflight(pid,identifier,bounds,policy.get('excluded_domains',[]))
                if self.closed or generation != self.probe_generation:return
                sample=reader.sample(checked,lambda: not self.closed and generation==self.probe_generation)
                if self.closed or generation != self.probe_generation:return
                title=reader.attribute(window,'AXTitle')
                payload['_detection']=classify_context(title,identifier,self.detector.config,sample)
                document=hashlib.sha256((identifier+'\0'+str(title)[:300]).encode()).digest()
                payload['_document']=document
                normalized=' '.join(sample.split()).lower() if isinstance(sample,str) else ''
                payload['_fingerprint']=hashlib.sha256(document+normalized.encode()).digest()
        except Exception:
            pass  # Incomplete metadata stays quiet and fails closed.
        finally:
            AppHelper.callAfter(self.deliver_probe,payload,generation)

    def deliver_probe(self,payload,generation):
        self.probe_busy=False
        if self.closed:return
        if generation != self.probe_generation:
            self.sample()  # Inspect only the latest app/focus after a coalesced event.
            return
        if not self.policy.get('enabled') or payload['epoch'] != self.policy['epoch']:
            return
        detection=payload.pop('_detection',None)
        fingerprint=payload.pop('_fingerprint',None)
        document=payload.pop('_document',fingerprint)
        if detection is not None:
            suggestion=self.assistance.evaluate(detection,fingerprint,document)
            if suggestion:payload['suggestion']=suggestion
        else:
            self.detector.clear_current()
            self.assistance.hide()
        self.clear_pending()
        self.pending.put_nowait(payload)
        self.indicator.update(payload.get('suggestion'))
        if payload.get('suggestion',{}).get('assistance')=='suggestion':
            self.offer_panel.show(fingerprint)
        else:self.offer_panel.hide()

    def respond_to_offer(self,accepted):
        # A click offers manual selection only; its existing approval gates remain authoritative.
        active=AK.NSWorkspace.sharedWorkspace().frontmostApplication()
        identifier=active.bundleIdentifier() if active else None
        try:policy=request('policy')
        except (OSError,ValueError,TypeError):policy={}
        permitted=(not self.closed and policy.get('enabled') and policy.get('smart_enabled')
                   and policy.get('accessibility_enabled') and accessibility_granted() and not policy.get('paused')
                   and policy.get('epoch')==self.policy.get('epoch')
                   and identifier==self.source_identifier and identifier not in policy.get('excluded',[]))
        if accepted is None:
            self.assistance.hide()
            remembered=False
        else:remembered=self.assistance.feedback(accepted and permitted)
        try:request('clear_suggestion')
        except (OSError,ValueError,TypeError):pass
        self.indicator.clear()
        if accepted and permitted and remembered:self.activate_selection()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.probe_generation += 1
        self.probes.shutdown(wait=False,cancel_futures=True)
        self.offer_panel.close()
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
