import unittest
from core.legal_context import ContextDetector
from core.proactive import AssistancePolicy,AssistanceConfig

class AssistanceTests(unittest.TestCase):
    def setUp(self):
        self.now=0
        self.detector=ContextDetector(clock=lambda:self.now)
        self.policy=AssistancePolicy(self.detector)
    def offer(self,score=.94,key=b'context',doc=b'doc'):
        return self.policy.evaluate({'confidence':score,'legal_context':score>=.82},key,doc)
    def test_confidence_tiers(self):
        self.assertIsNone(self.offer(.2))
        self.assertEqual(self.offer(.76)['assistance'],'indicator')
        self.assertEqual(self.offer()['assistance'],'suggestion')
        with self.assertRaises(ValueError):AssistanceConfig(.95,.8)
    def test_unchanged_offer_does_not_restart(self):
        self.assertEqual(self.offer()['assistance'],'suggestion')
        first=self.policy.last_offer
        self.now=10;self.offer()
        self.assertEqual(self.policy.last_offer,first)
        self.policy.hide()
        self.assertEqual(self.offer()['assistance'],'indicator')
        self.now=121
        self.assertEqual(self.offer()['assistance'],'suggestion')
    def test_dismissal_backoff_and_recovery(self):
        self.offer();self.policy.feedback(False)
        self.assertIsNone(self.offer())
        self.now=301;self.offer();self.policy.feedback(False)
        self.assertEqual(self.policy.memory[b'doc']['until'],901)
        self.now=500;self.assertIsNone(self.offer(key=b'new section'))
        self.now=902;self.assertEqual(self.offer()['assistance'],'suggestion')
    def test_accept_suppresses_same_context_but_allows_change(self):
        self.offer();self.assertTrue(self.policy.feedback(True))
        self.now=1000;self.assertIsNone(self.offer())
        self.assertEqual(self.offer(key=b'new section')['assistance'],'suggestion')
        self.assertEqual(self.offer(key=b'other document',doc=b'other')['assistance'],'indicator')
    def test_new_context_respects_global_interval(self):
        self.offer();self.policy.hide()
        self.now=20;self.assertEqual(self.offer(key=b'new')['assistance'],'indicator')
        self.now=31;self.assertEqual(self.offer(key=b'new')['assistance'],'suggestion')
    def test_timeout_does_not_count_as_dismissal(self):
        self.offer();self.policy.hide()
        self.assertFalse(self.policy.memory)
        self.assertFalse(self.policy.feedback(False))
    def test_reset_and_memory_bounds(self):
        for i in range(100):
            self.now+=4000;self.offer(key=str(i),doc=str(i));self.policy.feedback(False)
        self.assertLessEqual(len(self.policy.memory),64)
        self.assertLessEqual(len(self.detector.seen),64)
        self.policy.reset();self.assertFalse(self.policy.memory)
