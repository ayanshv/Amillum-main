import unittest
from unittest.mock import Mock,patch
from services.email_drafting import EmailDraft,DraftSession,generate_draft,parse_draft,MailClientHandoff
from services.supabase import PersistenceError

class EmailTests(unittest.TestCase):
    def setUp(self):
        self.account=Mock();self.valid=True
        self.session=DraftSession(lambda:self.valid)
        self.active=patch('services.auth.current',return_value=True);self.active.start();self.addCleanup(self.active.stop)
    def test_only_selected_context_and_explicit_notes_reach_engine(self):
        engine=Mock(return_value='{"subject":"Question about notice","body":"Based on the document, could you clarify the notice process?"}')
        authorize=Mock()
        draft=generate_draft(self.account,'approved excerpt','Professional','Concise','My selected question',engine=engine,authorize=authorize)
        self.assertEqual(draft.recipient,'');self.assertEqual(draft.subject,'Question about notice')
        self.assertIn('clarify',draft.body)
        authorize.assert_called_once_with(self.account,'email_drafting')
        self.assertEqual(engine.call_args.args[0],'approved excerpt')
        self.assertIn('My selected question',engine.call_args.args[1])
    def test_missing_context_auth_usage_and_backend_fail_closed(self):
        engine=Mock()
        with self.assertRaises(PersistenceError):generate_draft(self.account,'','Professional','Concise',engine=engine,authorize=Mock())
        with patch('services.auth.current',return_value=False):
            with self.assertRaises(PersistenceError):generate_draft(self.account,'approved','Professional','Concise',engine=engine,authorize=Mock())
        with self.assertRaises(PersistenceError):generate_draft(self.account,'approved','Professional','Concise',engine=engine,authorize=Mock(side_effect=PersistenceError('Usage limit reached')))
        with self.assertRaises(PersistenceError):generate_draft(self.account,'approved','Professional','Concise')
        engine.assert_not_called()
    def test_failure_does_not_expose_provider_content(self):
        with self.assertRaises(PersistenceError) as raised:
            generate_draft(self.account,'approved','Professional','Concise',engine=Mock(side_effect=RuntimeError('secret content')),authorize=Mock())
        self.assertNotIn('secret content',str(raised.exception))
    def test_model_cannot_choose_recipient(self):
        with self.assertRaises(PersistenceError):parse_draft('{"subject":"Hi","body":"Hello","recipient":"other@example.test"}')
        self.assertEqual(parse_draft('{"subject":"Hi","body":"Hello"}','chosen@example.test').recipient,'chosen@example.test')
    def test_edit_review_confirmation_and_single_handoff(self):
        transport=Mock()
        self.session.use('person@example.test','Edited subject','Edited body')
        transport.open_draft.assert_not_called()
        with self.assertRaises(PersistenceError):self.session.handoff(None,True,transport)
        ticket=self.session.begin_review()
        with self.assertRaises(PersistenceError):self.session.handoff(ticket,False,transport)
        transport.open_draft.assert_not_called()
        self.session.handoff(ticket,True,transport)
        transport.open_draft.assert_called_once_with(EmailDraft('person@example.test','Edited subject','Edited body'))
        with self.assertRaises(PersistenceError):self.session.handoff(ticket,True,transport)
    def test_edit_cancel_and_privacy_invalidate_confirmation(self):
        transport=Mock()
        self.session.use('person@example.test','Subject','Body');ticket=self.session.begin_review()
        self.session.edit()
        with self.assertRaises(PersistenceError):self.session.handoff(ticket,True,transport)
        ticket=self.session.begin_review();self.valid=False
        with self.assertRaises(PersistenceError):self.session.handoff(ticket,True,transport)
        transport.open_draft.assert_not_called()
        self.assertIsNone(self.session.draft)
    def test_failed_handoff_requires_new_review(self):
        self.session.use('person@example.test','Subject','Body');ticket=self.session.begin_review()
        transport=Mock();transport.open_draft.side_effect=PersistenceError('No mail client')
        with self.assertRaises(PersistenceError):self.session.handoff(ticket,True,transport)
        self.assertIsNotNone(self.session.draft)
        with self.assertRaises(PersistenceError):self.session.handoff(ticket,True,transport)
        self.assertNotEqual(self.session.begin_review(),ticket)
    def test_header_injection_and_multiple_recipients_rejected(self):
        for address in ['a@example.test\r\nBcc:x@example.test','a@example.test,b@example.test','.a@example.test','a@bad..test']:
            with self.assertRaises(PersistenceError):EmailDraft(address,'Subject','Body').validate()
        with self.assertRaises(PersistenceError):EmailDraft('a@example.test','Subject\r\nBcc:x','Body').validate()
    def test_regeneration_and_cancelled_response(self):
        engine=Mock(side_effect=['{"subject":"One","body":"First"}','{"subject":"Two","body":"Second"}'])
        self.assertEqual(generate_draft(self.account,'approved','Professional','Concise',engine=engine,authorize=Mock()).subject,'One')
        self.assertEqual(generate_draft(self.account,'approved','Professional','Detailed',engine=engine,authorize=Mock()).subject,'Two')
        engine=Mock(return_value='{"subject":"No","body":"Discard"}')
        checks=iter([True,True,False])
        with self.assertRaises(PersistenceError):generate_draft(self.account,'approved','Professional','Concise',valid=lambda:next(checks),engine=engine,authorize=Mock())
