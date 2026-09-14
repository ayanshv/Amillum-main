import unittest
from unittest.mock import Mock,patch
from services.email_context import ApprovedEmailContext
from services.supabase import PersistenceError
from core.context_awareness import AwarenessState
from core.privacy import PrivacyPreferences
from core.workspace import Workspace

class ContextTests(unittest.TestCase):
    def setUp(self):
        self.state=AwarenessState(PrivacyPreferences('/nonexistent/amillum-test-privacy'))
        self.workspace=Workspace();self.account=Mock(generation=1)
        self.patches=[patch('services.email_context.get_state',return_value=self.state),patch('services.email_context.current',return_value=True),patch('services.email_context.workspace',self.workspace)]
        for p in self.patches:p.start();self.addCleanup(p.stop)
    def approved(self):
        context=self.state.context;ticket=context.begin('com.apple.TextEdit');context.finish(ticket,'Approved employment agreement.','', 'Accessibility')
        revision,text=context.approve_analysis(context.revision,context.text);context.finish_analysis(revision,'Explanation')
    def test_requires_approved_result_not_detection_or_preview(self):
        with self.assertRaises(PersistenceError):ApprovedEmailContext(self.account,'selection')
        ticket=self.state.context.begin('com.apple.TextEdit');self.state.context.finish(ticket,'Local preview')
        with self.assertRaises(PersistenceError):ApprovedEmailContext(self.account,'selection')
        self.approved();source=ApprovedEmailContext(self.account,'selection')
        self.assertEqual(source.excerpt('employment agreement.'),'employment agreement.')
        with self.assertRaises(PersistenceError):source.excerpt('unrelated screen text')
    def test_pause_exclusion_account_change_and_clear_revoke_source(self):
        self.approved();source=ApprovedEmailContext(self.account,'selection')
        self.state.paused=True;self.assertFalse(source.valid());self.state.paused=False
        self.state.preferences.excluded.add('com.apple.TextEdit');self.assertFalse(source.valid());self.state.preferences.excluded.clear()
        self.account.generation+=1;self.assertFalse(source.valid());self.account.generation-=1
        self.state.context.clear();self.assertFalse(source.valid())
    def test_document_source_uses_existing_approved_memory(self):
        revision=self.workspace.begin('document.pdf','','English');self.workspace.extracted(revision,'Approved document text');self.workspace.finish(revision,'Explanation')
        source=ApprovedEmailContext(self.account,'document');self.assertEqual(source.text,'Approved document text')
        self.workspace.clear();self.assertFalse(source.valid())
