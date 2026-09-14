"""Stage 1: one current application, explicit opt-in, no activity history."""

import threading
import time

from core.context_session import ContextSession

from core.privacy import PrivacyPreferences, PROTECTED_APPLICATIONS, valid_bundle_id


class AwarenessState:
    def __init__(self, preferences=None, clock=time.monotonic):
        self.preferences = preferences or PrivacyPreferences()
        self.clock = clock
        self.lock = threading.RLock()
        self.enabled = False  # Opt in again each launch; no remembered content access.
        self.paused = False
        self.epoch = 0
        self.refresh = False
        self.current = None
        self.native_seen = None
        self.status = 'off'
        self.context = ContextSession()
        self.smart_enabled = False
        self.suggestion = None
        self.capture_request = 0
        self.capture_granted = False
        self.accessibility_enabled = False
        self.permission_request = 0
        self.accessibility_granted = False
        self.metadata = None

    def policy(self):
        with self.lock:
            return {'enabled': self.enabled and not self.paused and not self.preferences.load_error,
                    'epoch': self.epoch, 'refresh': self.refresh,
                    'accessibility_enabled': self.accessibility_enabled,
                    'smart_enabled': self.smart_enabled, 'paused': self.paused,
                    'capture_request': self.capture_request,
                    'excluded_domains': sorted(self.preferences.domains),
                    'permission_request': self.permission_request,
                    'excluded': sorted(self.preferences.excluded | PROTECTED_APPLICATIONS)}

    def update(self, *, enabled=None, paused=None, clear=False, accessibility_enabled=None, smart_enabled=None):
        with self.lock:
            if enabled and self.preferences.load_error:
                raise ValueError('Privacy preferences could not be read. Awareness remains off to preserve your exclusions.')
            if enabled is not None:
                self.enabled = bool(enabled)
            if paused is not None:
                self.paused = bool(paused)
            if accessibility_enabled is not None:
                self.accessibility_enabled = bool(accessibility_enabled)
            if smart_enabled is not None:
                self.smart_enabled = bool(smart_enabled)
            self.context.clear()
            self.suggestion = None
            self.epoch += 1
            self.current = None
            self.metadata = None
            self.refresh = not clear
            self.status = 'cleared' if clear else ('paused' if self.paused else ('waiting' if self.enabled else 'off'))

    def exclude(self, identifier, remove=False):
        if not valid_bundle_id(identifier):
            raise ValueError('Enter a valid application bundle identifier, such as com.apple.Safari.')
        if identifier in PROTECTED_APPLICATIONS:
            raise ValueError('This application is always excluded.')
        with self.lock:
            updated = set(self.preferences.excluded)
            updated.discard(identifier) if remove else updated.add(identifier)
            self.preferences.save(updated)
            self.update()

    def exclude_domain(self, domain, remove=False):
        from core.privacy import normalize_domain
        domain = normalize_domain(domain)
        with self.lock:
            updated = set(self.preferences.domains)
            updated.discard(domain) if remove else updated.add(domain)
            self.preferences.save(self.preferences.excluded, domains=updated)
            self.update()

    def begin_context(self, payload):
        with self.lock:
            identifier = payload.get('bundle_id')
            if self.paused or self.preferences.load_error or not valid_bundle_id(identifier) or identifier in self.policy()['excluded']:
                token = self.context.begin('')
                self.context.finish(token, error='This application is excluded or Amillum is paused. Nothing was read or captured.')
                return {'error': 'Application excluded or Amillum paused.'}
            return {'ticket': self.context.begin(identifier), 'epoch': self.epoch}

    def finish_context(self, payload):
        with self.lock:
            if payload.get('epoch') != self.epoch:
                return False
            return self.context.finish(payload.get('ticket'), payload.get('text', ''), payload.get('message', ''), payload.get('method', ''), payload.get('extraction'))

    def context_valid(self, payload):
        with self.lock:
            return payload.get('epoch') == self.epoch and not self.paused and self.context.valid(payload.get('ticket'))

    def cancel_context(self, payload):
        with self.lock:
            if self.context_valid(payload):
                self.context.clear()
                return True
            return False

    def analysis_valid(self, revision):
        with self.lock:
            snapshot=self.context.snapshot()
            return (not self.paused and not self.preferences.load_error
                    and snapshot['source'] not in self.policy()['excluded']
                    and snapshot['revision']==revision and snapshot['status']=='analyzing')

    def panel_state(self):
        with self.lock:
            snapshot=self.context.snapshot()
            return {'revision':snapshot['revision'], 'status':snapshot['status'],
                    'result':snapshot['structured'] if not self.paused and not self.preferences.load_error and snapshot['status']=='result' else None}

    def request_capture_setup(self):
        with self.lock:
            self.capture_request += 1

    def heartbeat(self):
        with self.lock:
            self.native_seen = self.clock()
            return self.policy()

    def request_accessibility_setup(self):
        with self.lock:
            self.permission_request += 1

    def report_permissions(self, payload):
        with self.lock:
            previously_granted = self.accessibility_granted
            previously_capturable = self.capture_granted
            self.accessibility_granted = payload.get('accessibility') is True
            self.capture_granted = payload.get('capture') is True
            if not self.accessibility_granted:
                self.metadata = None
                self.suggestion = None
            if (previously_granted and not self.accessibility_granted) or (previously_capturable and not self.capture_granted):
                self.context.clear()

    def publish(self, payload):
        with self.lock:
            if payload.get('epoch') != self.epoch or not self.policy()['enabled']:
                return False
            self.suggestion = None
            identifier, name = payload.get('bundle_id'), payload.get('name')
            if payload.get('status') in ('excluded', 'unavailable'):
                self.current = None
                self.metadata = None
                self.status = payload['status']
                return True
            if not valid_bundle_id(identifier) or identifier in self.policy()['excluded']:
                self.current = None
                self.metadata = None
                self.status = 'excluded'
                return False
            if not isinstance(name, str) or not 0 < len(name) <= 160 or any(ord(c) < 32 for c in name):
                return False
            # Accept only these two application-level values, never extra attributes.
            self.current = {'name': name, 'bundle_id': identifier}
            self.metadata = None
            metadata = payload.get('metadata')
            if self.accessibility_enabled and isinstance(metadata, dict):
                status = metadata.get('status')
                if status in {'blocked', 'permission_required', 'unavailable'}:
                    self.metadata = {'status': status}
                elif status == 'metadata' and self.accessibility_granted:
                    role = metadata.get('role')
                    if role in {'AXTextArea', 'AXStaticText', 'AXGroup', 'AXWebArea', 'AXButton',
                                'AXCheckBox', 'AXPopUpButton', 'AXRadioButton', 'AXTable',
                                'AXScrollArea', 'AXLink', 'AXImage', 'AXList'}:
                        # UI needs structural status only, not element handles or coordinates.
                        self.metadata = {'status': 'metadata', 'role': role}
            suggestion = payload.get('suggestion')
            if self.smart_enabled and self.accessibility_enabled and self.accessibility_granted and isinstance(suggestion, dict):
                from core.legal_context import SIGNALS, TYPES
                from core.proactive import AssistanceConfig
                score=suggestion.get('confidence')
                if (self.metadata and self.metadata.get('status')=='metadata'
                        and suggestion.get('label') in SIGNALS
                        and suggestion.get('source_application') == identifier
                        and isinstance(score,(int,float)) and AssistanceConfig.from_environment().indicator <= score <= 1):
                    label=suggestion['label']
                    self.suggestion = {'label':label, 'score':score, 'confidence':score,
                        'legal_context':bool(suggestion.get('legal_context')),'context_type':TYPES[label],
                        'reason':'Local legal-context signals','source_application':identifier}
            self.status = 'active'
            return True

    def clear_suggestion(self):
        with self.lock:self.suggestion=None

    def snapshot(self):
        with self.lock:
            connected = self.native_seen is not None and self.clock() - self.native_seen < 3
            if not connected:
                self.current = None
                self.metadata = None
                self.suggestion = None
                # Completed, approved previews survive transient bridge delays.
                # In-flight work is revoked after a sustained disconnect.
                if (self.context.snapshot()['status'] in ('reading','analyzing')
                        and (self.native_seen is None or self.clock()-self.native_seen >= 15)):
                    self.context.clear()
            return {'enabled': self.enabled, 'paused': self.paused,
                    'current': dict(self.current) if self.current else None,
                    'status': self.status if connected or not self.enabled else 'disconnected',
                    'connected': connected, 'excluded': sorted(self.preferences.excluded),
                    'protected': sorted(PROTECTED_APPLICATIONS), 'load_error': self.preferences.load_error,
                    'accessibility_enabled': self.accessibility_enabled,
                    'accessibility_granted': self.accessibility_granted if connected else False,
                    'metadata': dict(self.metadata) if self.metadata else None,
                    'smart_enabled': self.smart_enabled, 'suggestion': self.suggestion,
                    'capture_granted': self.capture_granted if connected else False,
                    'excluded_domains': sorted(self.preferences.domains)}


_state = None


def get_state():
    global _state
    if _state is None:
        _state = AwarenessState()
    return _state
