import unittest
from unittest.mock import Mock,patch
from services.account import profile,save_profile,save_privacy,restore_privacy,delete_account
from services.supabase import PersistenceError

class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.account=Mock(user_id='11111111-1111-4111-8111-111111111111',email='a@example.test',generation=1)
    def test_profile_create_read_update(self):
        self.account.authenticated.return_value=[{'display_name':'A'}]
        self.assertEqual(profile(self.account)['display_name'],'A')
        self.account.authenticated.side_effect=[[],[{'display_name':'New'}]]
        save_profile(self.account,' New ')
        self.assertEqual(self.account.authenticated.call_args.args[0],'POST')
        self.assertEqual(self.account.authenticated.call_args.kwargs['body'],{'display_name':'New'})
        self.account.authenticated.side_effect=[[{'user_id':'11111111-1111-4111-8111-111111111111'}],[]]
        save_profile(self.account,'Updated')
        self.assertEqual(self.account.authenticated.call_args.args[0],'PATCH')
        self.assertEqual(self.account.authenticated.call_args.kwargs['params'],{'user_id':'eq.'+self.account.user_id})
    def test_profile_failure_is_not_reported_saved(self):
        self.account.authenticated.side_effect=PersistenceError('offline')
        with self.assertRaises(PersistenceError):save_profile(self.account,'Draft')
    def test_privacy_round_trip_stays_paused(self):
        state=Mock();state.preferences.excluded={'com.test.app'};state.preferences.domains={'example.com'}
        self.account.authenticated.side_effect=[[],[]]
        save_privacy(self.account,state)
        payload=self.account.authenticated.call_args.kwargs['body']
        self.account.authenticated.side_effect=None;self.account.authenticated.return_value=[payload]
        restore_privacy(self.account,state)
        state.update.assert_called_once_with(enabled=False,paused=True,clear=True)
        state.preferences.save.assert_called_once_with({'com.test.app'},{'example.com'})
    def test_privacy_network_failure_preserves_local_state(self):
        state=Mock();self.account.authenticated.side_effect=PersistenceError('offline')
        with self.assertRaises(PersistenceError):restore_privacy(self.account,state)
        state.preferences.save.assert_not_called()
    def test_deletion_requires_confirmation_and_same_verified_user(self):
        with self.assertRaises(PersistenceError):delete_account(self.account,'password','yes')
        self.account.gateway.request.assert_not_called()
        self.account.gateway.request.side_effect=[{'access_token':'synthetic'},{'id':'22222222-2222-4222-8222-222222222222'}]
        with self.assertRaises(PersistenceError):delete_account(self.account,'password','DELETE MY ACCOUNT')
        self.account.invalidate.assert_not_called()
    def test_delete_clears_only_after_confirmed_rpc(self):
        self.account.gateway.request.side_effect=[{'access_token':'synthetic'},{'id':'11111111-1111-4111-8111-111111111111'},None]
        delete_account(self.account,'password','DELETE MY ACCOUNT')
        self.account.invalidate.assert_called_once()
    def test_delete_backend_failure_retains_session(self):
        self.account.gateway.request.side_effect=[{'access_token':'synthetic'},{'id':'11111111-1111-4111-8111-111111111111'},PersistenceError('migration required')]
        with self.assertRaises(PersistenceError):delete_account(self.account,'password','DELETE MY ACCOUNT')
        self.account.invalidate.assert_not_called()
