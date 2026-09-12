from pathlib import Path
import tempfile
import unittest

from core.context_awareness import AwarenessState
from core.privacy import PrivacyPreferences
from native.bridge import BridgeServer, request


class AwarenessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'privacy.json'
        self.time = 100.0
        self.state = AwarenessState(PrivacyPreferences(self.path), clock=lambda: self.time)

    def tearDown(self):
        self.temp.cleanup()

    def publish(self, **extra):
        return self.state.publish({'epoch': self.state.epoch, 'bundle_id': 'com.apple.TextEdit', 'name': 'TextEdit', **extra})

    def test_default_off_and_no_file_created(self):
        self.assertFalse(self.state.policy()['enabled'])
        self.assertFalse(self.publish())
        self.assertFalse(self.path.exists())

    def test_opt_in_accepts_only_app_identity(self):
        self.state.update(enabled=True)
        self.state.heartbeat()
        self.assertTrue(self.publish(text='This must not be retained', title='Document title'))
        self.assertEqual(self.state.snapshot()['current'], {'name': 'TextEdit', 'bundle_id': 'com.apple.TextEdit'})
        self.assertFalse(self.path.exists())

    def test_pause_and_old_generation_fail_closed(self):
        self.state.update(enabled=True)
        old_epoch = self.state.epoch
        self.state.heartbeat()
        self.publish()
        self.state.update(paused=True)
        self.assertFalse(self.state.policy()['enabled'])
        self.assertIsNone(self.state.snapshot()['current'])
        self.state.update(paused=False)
        self.assertFalse(self.publish(epoch=old_epoch))

    def test_clear_waits_for_next_app_event(self):
        self.state.update(enabled=True)
        self.state.update(clear=True)
        self.assertFalse(self.state.policy()['refresh'])
        self.assertIsNone(self.state.snapshot()['current'])

    def test_exclusions_persist_without_activity_or_enablement(self):
        self.state.update(enabled=True)
        self.state.exclude('com.apple.TextEdit')
        self.assertFalse(self.publish())
        restored = AwarenessState(PrivacyPreferences(self.path))
        self.assertIn('com.apple.TextEdit', restored.policy()['excluded'])
        self.assertFalse(restored.enabled)
        content = self.path.read_text()
        self.assertNotIn('current', content)
        self.assertNotIn('enabled', content)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_password_manager_cannot_be_unblocked(self):
        self.state.update(enabled=True)
        self.assertFalse(self.publish(bundle_id='com.apple.Passwords', name='Passwords'))
        with self.assertRaises(ValueError):
            self.state.exclude('com.apple.Passwords', remove=True)

    def test_disconnect_discards_context(self):
        self.state.update(enabled=True)
        self.state.heartbeat()
        self.publish()
        self.time += 4
        self.assertIsNone(self.state.snapshot()['current'])
        self.assertEqual(self.state.snapshot()['status'], 'disconnected')

    def test_corrupt_preferences_prevent_enablement(self):
        self.path.write_text('not json')
        state = AwarenessState(PrivacyPreferences(self.path))
        with self.assertRaises(ValueError):
            state.update(enabled=True)
        self.assertFalse(state.policy()['enabled'])

    def test_invalid_application_values_are_rejected(self):
        self.state.update(enabled=True)
        for value in ('file:///secret', 'com.app\nsecret', '', None):
            self.assertFalse(self.publish(bundle_id=value))
        self.assertFalse(self.publish(name='a\nb'))

    def test_authenticated_bridge_and_closed_cleanup(self):
        server = BridgeServer(self.state)
        server.start()
        try:
            self.assertFalse(request('policy', path=server.path, token=server.token)['enabled'])
            with self.assertRaises(ConnectionError):
                request('policy', path=server.path, token='wrong')
            with self.assertRaises(ConnectionError):
                request('enable', path=server.path, token=server.token)
            self.assertFalse(self.state.enabled)
            self.assertEqual(Path(server.path).stat().st_mode & 0o777, 0o600)
            self.assertEqual(server.directory.stat().st_mode & 0o777, 0o700)
        finally:
            server.close()
        self.assertFalse(server.directory.exists())
        self.assertFalse(server.thread.is_alive())


if __name__ == '__main__':
    unittest.main()
