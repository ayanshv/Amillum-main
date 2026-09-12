"""Coordinates explicit region approval, local extraction, and the review page."""
import threading
import AppKit as AK
from PyObjCTools import AppHelper
from native.bridge import request
from native.macos.region_reader import RegionReader, ReadBlocked, screen_rect
from native.macos.screen_capture import capture_region
from services.ocr import recognize_region
from core.privacy import require_safe_text


class ContextReader:
    def __init__(self, open_review):
        self.open_review = open_review
        self.generation = 0
        self.busy = False
        self.closed = False

    def cancel(self):
        self.generation += 1
        self.busy = False

    def start(self, rect, application):
        if self.busy or self.closed or application is None:
            return
        self.generation += 1
        generation = self.generation
        pid = application.processIdentifier()
        identifier = str(application.bundleIdentifier() or '')
        primary_height = AK.NSScreen.screens()[0].frame().size.height
        region = screen_rect(rect, primary_height)
        self.busy = True
        threading.Thread(target=self.read, args=(generation, pid, identifier, region), daemon=True, name='amillum-approved-region').start()

    def read(self, generation, pid, identifier, region):
        ticket = None
        def valid():
            if self.closed or generation != self.generation:
                return False
            try:
                return bool(request('context_valid', ticket).get('valid'))
            except (OSError, ValueError):
                return False
        try:
            ticket = request('begin_context', {'bundle_id': identifier})
            if not valid():
                AppHelper.callAfter(self.done,generation)
                return
            policy = request('policy')
            reader = RegionReader()
            checked = reader.preflight(pid, identifier, region, policy.get('excluded_domains', []))
            if not valid():
                return
            text = reader.extract(checked)
            method = 'Accessibility'
            confidence = 1.0
            needs_review = False
            if not text.strip():
                # Recheck before capturing; never fall back past a sensitive-field failure.
                reader.preflight(pid, identifier, region, policy.get('excluded_domains', []))
                image = capture_region(pid, region, valid)
                if not valid():
                    return
                try:
                    ocr = recognize_region(image, details=True)
                    text = ocr['text']
                    confidence = ocr['confidence']
                    needs_review = ocr['needs_review']
                finally:
                    image = None
                method = 'Local OCR'
            if not text.strip():
                raise ReadBlocked('No readable text in this approved region. Try a larger text size or a tighter selection around the words. You can also upload the document.')
            require_safe_text(text)
            if not valid():
                return
            accepted = request('finish_context', {**ticket, 'text': text, 'method': method, 'extraction': {'bounds':list(region), 'application':identifier, 'window':{'bounds':list(checked['bounds'])}, 'confidence':confidence, 'needs_review':needs_review}}).get('accepted')
            if accepted:
                AppHelper.callAfter(self.done, generation)
        except Exception as exc:
            message = str(exc) if isinstance(exc, (ReadBlocked, RuntimeError, ValueError)) else 'Local reading could not complete. Check Privacy & control and try again.'
            if ticket is not None and valid():
                request('finish_context', {**ticket, 'message': message})
                AppHelper.callAfter(self.done, generation)
            else:
                AppHelper.callAfter(self.done, generation)
        finally:
            if ticket is not None and (self.closed or generation != self.generation):
                try:
                    request('cancel_context', ticket)
                except (OSError, ValueError):
                    pass
            if generation == self.generation:
                self.busy = False

    def done(self, generation):
        if not self.closed and generation == self.generation:
            self.busy = False
            self.open_review()

    def close(self):
        self.closed = True
        self.cancel()
