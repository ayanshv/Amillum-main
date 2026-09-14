import unittest
from unittest.mock import Mock
from native.macos.detection_reader import DetectionReader,MAX_SAMPLE
from native.macos.region_reader import ReadBlocked

class SampleTests(unittest.TestCase):
    def setUp(self):
        self.api=Mock();self.reader=DetectionReader(self.api)
        self.reader.check_role=Mock(return_value='AXTextArea')
        self.reader.bounds=Mock(return_value=(0,0,100,100))
        self.reader.attribute=Mock(side_effect=lambda e,n:{'AXRole':'AXTextArea','AXVisibleCharacterRange':'visible'}.get(n))
        self.api.AXValueGetValue.return_value=(True,(10,5000))
        self.api.AXValueCreate.return_value='bounded'
        self.reader.parameter=Mock(return_value='The employee shall observe confidentiality under this agreement.')
        self.checked={'ranged':[((0,0,100,100),'element')]}
    def test_bounded_range_only(self):
        self.assertTrue(self.reader.sample(self.checked))
        self.api.AXValueCreate.assert_called_once_with(self.api.kAXValueCFRangeType,(10,MAX_SAMPLE))
        self.reader.parameter.assert_called_once_with('element','AXStringForRange','bounded')
        self.assertFalse(any(c.args[1]=='AXValue' for c in self.reader.attribute.call_args_list))
    def test_secure_or_changed_context_never_reads(self):
        self.reader.check_role.side_effect=ReadBlocked('Secure field')
        with self.assertRaises(ReadBlocked):self.reader.sample(self.checked)
        self.reader.parameter.assert_not_called();self.reader.attribute.assert_not_called()
        self.reader.check_role.side_effect=None
        with self.assertRaises(ReadBlocked):self.reader.sample(self.checked,lambda:False)
        self.reader.parameter.assert_not_called()
    def test_no_visible_range_does_not_read_whole_editable_document(self):
        self.reader.attribute.side_effect=lambda e,n:'AXTextArea' if n=='AXRole' else None
        self.assertIsNone(self.reader.sample(self.checked))
        self.reader.parameter.assert_not_called()
    def test_sensitive_sample_fails_closed(self):
        self.reader.parameter.return_value='password: synthetic-secret'
        with self.assertRaises(ReadBlocked):self.reader.sample(self.checked)
