"""One desktop session, in memory. Never saves documents or responses to disk."""
from threading import RLock
from uuid import uuid4


class Workspace:
    def __init__(self):
        self.lock = RLock()
        self.revision = 0
        self.language = None
        self.question = ''
        self.draft_question = ''
        self.draft_language = None
        self.clear()

    def clear(self):
        with self.lock:
            self.revision += 1
            self.question = ''
            self.draft_question = ''
            self.document_id = None
            self.filename = ''
            self.text = ''
            self.result = ''
            self.error = ''
            self.status = 'empty'

    def draft(self, question=None, language=None):
        with self.lock:
            if question is not None:
                self.draft_question = question
            if language is not None:
                self.draft_language = language

    def begin(self, filename, question, language):
        with self.lock:
            if self.status in ('extracting', 'analyzing'):
                raise ValueError('An analysis is already running. Wait for it or clear the current document.')
            self.clear()
            self.document_id = str(uuid4())
            self.filename = filename
            self.question = self.draft_question = question
            self.language = self.draft_language = language
            self.status = 'extracting'
            return self.revision

    def extracted(self, revision, text):
        with self.lock:
            if revision != self.revision or self.status != 'extracting':
                return False
            self.text = text
            self.status = 'analyzing'
            return True

    def ask(self, question):
        with self.lock:
            if self.status not in ('ready', 'error') or not self.text:
                raise ValueError('Analyze a document before asking a follow-up question.')
            if not question.strip():
                raise ValueError('Enter a question about the current document.')
            self.revision += 1
            self.question = self.draft_question = question
            self.status = 'analyzing'
            self.error = ''
            return self.revision, self.text, self.language

    def finish(self, revision, result='', error=''):
        with self.lock:
            if revision != self.revision:
                return False
            self.result = result
            self.error = error
            self.status = 'error' if error else 'ready'
            return True

    def snapshot(self):
        with self.lock:
            # UI snapshots never copy raw document text.
            return {key: getattr(self, key) for key in ('revision', 'document_id', 'filename', 'question', 'language', 'result', 'error', 'status', 'draft_question', 'draft_language')} | {'can_ask': bool(self.text) and self.status in ('ready', 'error')}


workspace = Workspace()
