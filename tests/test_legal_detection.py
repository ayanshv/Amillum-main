"""Detection calibration fixtures and privacy-boundary regressions."""
import tempfile
import unittest
from pathlib import Path
from core.legal_context import classify_context,ContextDetector,DetectionConfig
from core.context_awareness import AwarenessState
from core.privacy import PrivacyPreferences

class DetectionTests(unittest.TestCase):
    def test_legal_categories(self):
        fixtures={'Executed contract.pdf':'contract','Residential lease – Preview':'lease',
            'Employment agreement.docx':'employment','Notice to vacate.pdf':'legal_notice',
            'Insurance policy.pdf':'insurance','Power of attorney.pdf':'government_form',
            'Shareholder agreement.docx':'business_agreement','Non-disclosure agreement.pdf':'contract'}
        for title,kind in fixtures.items():
            with self.subTest(title=title):
                r=classify_context(title,'com.apple.Preview')
                self.assertTrue(r['legal_context']);self.assertEqual(r['context_type'],kind)
                self.assertNotIn(title,str(r));self.assertEqual(r['source_application'],'com.apple.Preview')
    def test_false_positive_corpus(self):
        for title in ['agreement','contract.pdf','terms','policy','Email — dinner plans',
                      'We are in agreement','Team policy discussion','How to write a lease agreement',
                      'Employment agreement template','Insurance policy news','contract.py — editor',
                      'Holiday photos.pdf','Recipe for bread','A normal web page','Terms of service examples']:
            with self.subTest(title=title):self.assertFalse(classify_context(title)['legal_context'])
        self.assertFalse(classify_context('Employment agreement.pdf','com.microsoft.VSCode')['legal_context'])
    def test_configured_threshold(self):
        self.assertFalse(classify_context('Employment agreement',config=DetectionConfig(.9))['legal_context'])
        self.assertTrue(classify_context('Employment agreement.pdf',config=DetectionConfig(.9))['legal_context'])
        for value in [float('nan'),.2,1.1]:
            with self.assertRaises(ValueError):DetectionConfig(value)
    def test_repeats_cooldown_and_bounded_memory(self):
        now=[0];d=ContextDetector(clock=lambda:now[0])
        first=d.detect('Employment agreement.pdf','viewer')
        self.assertIs(d.detect('Employment agreement.pdf','viewer'),first)
        d.detect('Vacation photos','viewer')
        self.assertIsNone(d.detect('Employment agreement.pdf','viewer'))
        now[0]=121;d.clear_current()
        self.assertIsNotNone(d.detect('Employment agreement.pdf','viewer'))
        for i in range(100):d.detect(f'Employment agreement {i}.pdf','viewer')
        self.assertLessEqual(len(d.seen),64)
        self.assertNotIn('Employment',repr(d.seen))
    def test_sensitive_title(self):
        self.assertFalse(classify_context('Employment agreement password: secret')['legal_context'])
    def test_server_privacy_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            state=AwarenessState(PrivacyPreferences(Path(folder)/'privacy.json'))
            state.update(enabled=True,accessibility_enabled=True,smart_enabled=True)
            state.report_permissions({'accessibility':True});state.heartbeat()
            def payload(status='metadata'):
                return {'epoch':state.epoch,'bundle_id':'com.apple.Preview','name':'Preview',
                    'metadata':{'status':status,'role':'AXStaticText'},
                    'suggestion':classify_context('Employment agreement.pdf','com.apple.Preview')}
            state.publish(payload());self.assertIsNotNone(state.suggestion)
            for status in ['blocked','permission_required','unavailable']:
                state.publish(payload(status));self.assertIsNone(state.suggestion)
            state.update(paused=True);state.publish(payload());self.assertIsNone(state.suggestion)
            state.update(paused=False,enabled=False);state.publish(payload());self.assertIsNone(state.suggestion)
            state.update(enabled=True);state.exclude('com.apple.Preview');state.publish(payload());self.assertIsNone(state.suggestion)
            self.assertEqual(state.context.snapshot()['status'],'empty')

    def test_accessible_text_refines_generic_contexts(self):
        legal='Employment agreement. The employer and employee agree that the employee shall maintain confidentiality. Termination requires notice. 1. Effective date: today.'
        for title,app in [('Untitled','com.apple.TextEdit'),('scan.pdf','com.apple.Preview'),('Document','com.google.Chrome'),('Inbox','com.apple.mail'),('Document1','com.microsoft.Word'),(None,'com.apple.TextEdit')]:
            with self.subTest(title=title):
                result=classify_context(title,app,accessible_text=legal)
                self.assertTrue(result['legal_context'])
                self.assertEqual(result['context_type'],'employment')
                self.assertNotIn(legal,str(result))
        email='Can we discuss the employment agreement? The employer must provide notice before termination.'
        self.assertTrue(classify_context('Inbox',accessible_text=email)['legal_context'])
        ordinary='We are meeting for coffee tomorrow. Please bring the photos from our holiday and choose a restaurant.'
        self.assertFalse(classify_context('Document1',accessible_text=ordinary)['legal_context'])
        self.assertFalse(classify_context('Employment agreement.pdf',accessible_text=ordinary)['legal_context'])
        self.assertFalse(classify_context('Employment agreement.pdf',accessible_text='password: secret')['legal_context'])

    def test_text_changes_reclassify_without_spam(self):
        d=ContextDetector()
        legal='The employment agreement requires the employee to maintain confidentiality. The employer shall provide notice before termination.'
        self.assertIsNone(d.detect('Untitled','viewer','Coffee tomorrow'))
        self.assertIsNotNone(d.detect('Untitled','viewer',legal))
        self.assertIsNone(d.detect('Untitled','viewer','Holiday photographs'))
        self.assertIsNone(d.detect('Untitled','viewer',legal))
