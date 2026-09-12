import unittest
from core.workspace import Workspace


class WorkspaceTests(unittest.TestCase):
    def test_clear_discards_content_and_rejects_late_completion(self):
        state = Workspace()
        revision = state.begin('lease.pdf', 'Notice period?', 'English')
        self.assertTrue(state.extracted(revision, 'Private document text'))
        state.clear()
        self.assertFalse(state.finish(revision, result='Late result'))
        self.assertEqual(state.text, '')
        self.assertEqual(state.snapshot()['status'], 'empty')
        self.assertEqual(state.snapshot()['question'], '')

    def test_clear_during_extraction_prevents_analysis(self):
        state = Workspace()
        revision = state.begin('lease.pdf', '', 'English')
        state.clear()
        self.assertFalse(state.extracted(revision, 'Stale text'))

    def test_drafts_do_not_change_approved_request_metadata(self):
        state = Workspace()
        revision = state.begin('lease.pdf', 'Approved question', 'English')
        state.draft(question='Next question', language='French')
        state.extracted(revision, 'Document')
        state.finish(revision, result='Explanation')
        snapshot = state.snapshot()
        self.assertEqual(snapshot['question'], 'Approved question')
        self.assertEqual(snapshot['language'], 'English')
        self.assertEqual(snapshot['draft_question'], 'Next question')
        self.assertNotIn('text', snapshot)

    def test_followup_uses_current_document_and_language(self):
        state = Workspace()
        revision = state.begin('notice.png', '', 'Spanish (Español)')
        state.extracted(revision, 'Approved document')
        state.finish(revision, result='Explanation')
        revision, text, language = state.ask('What is the deadline?')
        self.assertEqual(text, 'Approved document')
        self.assertEqual(language, 'Spanish (Español)')
        self.assertEqual(state.snapshot()['status'], 'analyzing')
        self.assertTrue(state.finish(revision, result='Follow-up answer'))
        self.assertEqual(state.snapshot()['result'], 'Follow-up answer')

    def test_overlapping_upload_is_rejected_and_errors_are_retryable(self):
        state = Workspace()
        revision = state.begin('first.pdf', '', 'English')
        with self.assertRaises(ValueError):
            state.begin('second.pdf', '', 'English')
        state.extracted(revision, 'Document')
        state.finish(revision, error='Service unavailable')
        self.assertTrue(state.snapshot()['can_ask'])
        with self.assertRaises(ValueError):
            state.ask('   ')
        state.ask('Try again')

    def test_empty_session_cannot_send_question(self):
        state = Workspace()
        with self.assertRaises(ValueError):
            state.ask('Question')
