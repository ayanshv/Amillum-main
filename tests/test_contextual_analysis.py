import json
import unittest
from unittest.mock import Mock
from services.contextual_analysis import analyze_context
from core.context_session import ContextSession
from core.privacy import require_safe_text

RESULT={'summary':'Notice is required.','attention':'Moderate','reasons':['Check the notice period.'],'questions':['When does notice start?'],'next_steps':['Review the full agreement.']}

class ContextualAnalysisTests(unittest.TestCase):
    def test_shared_engine_receives_only_approved_passage(self):
        engine=Mock(return_value=json.dumps(RESULT))
        self.assertEqual(analyze_context('Approved passage','Explain notice','English',engine=engine),RESULT)
        self.assertEqual(engine.call_args.args[0],'Approved passage')
        self.assertEqual(engine.call_args.args[2],'English')

    def test_cancel_and_sensitive_content_prevent_dispatch(self):
        for text,valid in [('Approved passage',lambda:False),('password: synthetic-secret',lambda:True),('4111 1111 1111 1111',lambda:True)]:
            engine=Mock()
            with self.assertRaises(ValueError):analyze_context(text,'','English',valid,engine)
            engine.assert_not_called()

    def test_cancel_during_request_discards_response(self):
        state=[True]
        def engine(*args):state[0]=False;return json.dumps(RESULT)
        with self.assertRaises(ValueError):analyze_context('Approved passage','','English',lambda:state[0],engine)

    def test_invalid_response_can_retry_same_preview(self):
        session=ContextSession();token=session.begin('synthetic');session.finish(token,'Approved passage')
        revision,text=session.approve_analysis(session.revision,'Approved passage')
        with self.assertRaises(ValueError):analyze_context(text,'','English',engine=lambda *args:'not json')
        session.finish_analysis(revision,error='Try again')
        self.assertEqual(session.snapshot()['status'],'preview')
        self.assertEqual(session.snapshot()['text'],text)

    def test_sensitive_result_never_becomes_preview(self):
        session=ContextSession();token=session.begin('synthetic')
        session.finish(token,'-----BEGIN PRIVATE KEY-----')
        self.assertEqual(session.snapshot()['text'],'')
        self.assertEqual(session.snapshot()['status'],'error')

    def test_followup_is_explicit_and_clear_revokes_it(self):
        session=ContextSession();token=session.begin('synthetic');session.finish(token,'Approved passage')
        rev,_=session.approve_analysis(session.revision,'Approved passage')
        session.finish_analysis(rev,'result',structured=RESULT)
        rev2,text=session.approve_followup(rev)
        self.assertGreater(rev2,rev);self.assertEqual(text,'Approved passage')
        session.clear();self.assertFalse(session.finish_analysis(rev2,'late',structured=RESULT))

class LocalOCRTests(unittest.TestCase):
    def test_confidence_and_cleanup(self):
        import sys
        from unittest.mock import patch
        from services.ocr import recognize_region
        api=Mock()
        handler=api.VNImageRequestHandler.alloc.return_value.initWithCGImage_options_.return_value
        handler.performRequests_error_.return_value=(True,None)
        candidate=Mock();candidate.string.return_value=' Notice\x00 thirty days '
        observation=Mock();observation.topCandidates_.return_value=[candidate]
        api.VNRecognizeTextRequest.alloc.return_value.init.return_value.results.return_value=[observation]
        with patch.dict(sys.modules,{'Vision':api}):
            candidate.confidence.return_value=.6
            result=recognize_region(object(),details=True)
            self.assertEqual(result['text'],'Notice thirty days');self.assertTrue(result['needs_review'])
            candidate.confidence.return_value=.2
            with self.assertRaises(RuntimeError):recognize_region(object())
