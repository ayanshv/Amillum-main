"""An in-memory, one-shot approval transaction. No automatic cloud transmission."""
import secrets
import threading
import time
import copy
from core.privacy import require_safe_text

MAX_TEXT = 12000


class ContextSession:
    def __init__(self, clock=time.monotonic):
        self.lock = threading.RLock()
        self.clock = clock
        self.revision = 0
        self.clear()

    def clear(self):
        with self.lock:
            self.revision += 1
            self.token = None
            self.started = 0
            self.source = ''
            self.text = ''
            self.result = ''
            self.message = ''
            self.method = ''
            self.status = 'empty'
            self.extraction = {}
            self.structured = None

    def begin(self, source):
        with self.lock:
            self.clear()
            self.token = secrets.token_hex(24)
            self.started = self.clock()
            self.source = source
            self.status = 'reading'
            return self.token

    def valid(self, token):
        with self.lock:
            return token is not None and token == self.token and self.status == 'reading' and self.clock() - self.started < 30

    def finish(self, token, text='', error='', method='', extraction=None):
        with self.lock:
            if not self.valid(token):
                return False
            self.token = None
            try:
                require_safe_text(text)
            except ValueError as exc:
                text=''; error=str(exc)
            self.extraction=copy.deepcopy(extraction or {})
            self.text = text[:MAX_TEXT] if isinstance(text, str) else ''
            self.method = method if method in ('Accessibility', 'Local OCR') else ''
            self.message = str(error)[:500]
            self.status = 'preview' if self.text.strip() and not error else 'error'
            if self.status == 'error':
                self.text = ''
            return True

    def approve_analysis(self, revision, text):
        with self.lock:
            if revision != self.revision or self.status != 'preview':
                raise ValueError('This preview has changed. Review the current selection again.')
            if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
                raise ValueError('Review up to 12,000 characters of text before continuing.')
            require_safe_text(text)
            self.text = text
            self.status = 'analyzing'
            return self.revision, text

    def approve_followup(self, revision):
        with self.lock:
            if revision != self.revision or self.status != 'result':
                raise ValueError('This result has changed. Review the current selection again.')
            require_safe_text(self.text)
            self.revision += 1
            self.status='analyzing'
            self.structured=None
            return self.revision,self.text

    def finish_analysis(self, revision, result='', error='', structured=None):
        with self.lock:
            if revision != self.revision or self.status != 'analyzing':
                return False
            self.result = result
            self.structured = copy.deepcopy(structured)
            self.message = error
            self.status = 'result' if not error else 'preview'
            return True

    def snapshot(self):
        with self.lock:
            if self.status == 'reading' and self.clock() - self.started >= 30:
                self.token = None
                self.status = 'error'
                self.message = 'Local reading timed out. Select a smaller region and try again.'
            return {key: copy.deepcopy(getattr(self, key)) for key in ('revision', 'source', 'text', 'result', 'message', 'method', 'status', 'extraction', 'structured')}
