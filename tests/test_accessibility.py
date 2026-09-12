"""Synthetic metadata only: tests never inspect another application's content."""
import unittest
from native.macos.accessibility import AccessibilityReader
from core.context_awareness import AwarenessState


class FakeAX:
    def __init__(self, role='AXTextArea', subrole=None, trusted=True):
        self.trusted = trusted
        self.calls = []
        self.values = {'AXFocusedUIElement': 'element', 'AXRole': role, 'AXSubrole': subrole}

    def AXIsProcessTrusted(self):
        return self.trusted

    def AXUIElementCreateApplication(self, pid):
        self.calls.append('create')
        return 'app'

    def AXUIElementSetMessagingTimeout(self, app, timeout):
        pass

    def AXUIElementCopyAttributeValue(self, element, name, out):
        self.calls.append(name)
        if name in ('AXValue', 'AXSelectedText', 'AXTitle', 'AXDescription'):
            raise AssertionError('Content must never be requested')
        return 0, self.values.get(name)


class MetadataTests(unittest.TestCase):
    def test_denied_permission_makes_no_queries(self):
        api = FakeAX(trusted=False)
        self.assertEqual(AccessibilityReader(api).focused_metadata(1)['status'], 'permission_required')
        self.assertEqual(api.calls, [])

    def test_sensitive_and_unknown_fields_stop_before_geometry(self):
        for role, subrole in [('AXTextField', None), ('AXComboBox', None),
                              ('AXTextArea', 'AXSecureTextField'), ('AXSecureTextField', None),
                              ('AXUnknown', None), (None, None)]:
            with self.subTest(role=role, subrole=subrole):
                api = FakeAX(role, subrole)
                self.assertEqual(AccessibilityReader(api).focused_metadata(1)['status'], 'blocked')
                self.assertNotIn('AXPosition', api.calls)
                self.assertNotIn('AXSize', api.calls)

    def test_allowed_metadata_does_not_read_content(self):
        api = FakeAX()
        self.assertEqual(AccessibilityReader(api).focused_metadata(1), {'status': 'metadata', 'role': 'AXTextArea'})
        self.assertEqual(api.calls, ['create', 'AXFocusedUIElement', 'AXRole', 'AXSubrole', 'AXPosition', 'AXSize'])

    def test_metadata_requires_optin_and_trust_and_is_cleared_on_revoke(self):
        state = AwarenessState()
        state.update(enabled=True)
        state.heartbeat()
        def publish():
            state.publish({'epoch': state.epoch, 'bundle_id': 'com.apple.TextEdit', 'name': 'TextEdit',
                           'metadata': {'status': 'metadata', 'role': 'AXTextArea', 'text': 'never retain', 'bounds': [1, 2, 3, 4]}})
        publish()
        self.assertIsNone(state.snapshot()['metadata'])
        state.update(accessibility_enabled=True)
        publish()
        self.assertIsNone(state.snapshot()['metadata'])
        state.report_permissions({'accessibility': True})
        publish()
        self.assertEqual(state.snapshot()['metadata'], {'status': 'metadata', 'role': 'AXTextArea'})
        state.report_permissions({'accessibility': False})
        self.assertIsNone(state.snapshot()['metadata'])
        state.update(paused=True)
        publish()
        self.assertIsNone(state.snapshot()['metadata'])


if __name__ == '__main__':
    unittest.main()
