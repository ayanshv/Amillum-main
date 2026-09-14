import unittest,time
from unittest.mock import patch,Mock
import httpx
from services.supabase import Account,Supabase,PersistenceError,SessionExpired

UID='11111111-1111-4111-8111-111111111111'
class MemoryStore:
    def __init__(self):self.values={}
    def read(self,key):return self.values.get(key)
    def write(self,key,value):self.values[key]=value
    def delete(self,key):self.values.pop(key,None)

class AuthTests(unittest.TestCase):
    def setUp(self):
        self.calls=[];self.failure=None
        def handle(request):
            self.calls.append(request)
            if self.failure=='offline':raise httpx.ConnectError('secret',request=request)
            if self.failure=='invalid':return httpx.Response(401,json={})
            if request.url.path.endswith('/user'):return httpx.Response(200,json={'id':UID,'email':'a@example.test'})
            if request.url.path.endswith(('/token','/verify')):return httpx.Response(200,json={'access_token':'synthetic-access','refresh_token':'synthetic-refresh','expires_in':3600})
            return httpx.Response(200,json={})
        self.gateway=Supabase('https://example.supabase.co','sb_publishable_test',httpx.MockTransport(handle))
        self.store=MemoryStore();self.account=Account(self.gateway,self.store,'cookie-one')
        self.clear=patch('services.supabase.clear_application_state');self.clear.start();self.addCleanup(self.clear.stop)
    def tearDown(self):self.gateway.http.close()
    def test_signup_login_logout(self):
        self.account.sign_up('a@example.test','long-synthetic-password')
        self.assertIsNone(self.account.user_id)
        self.account.sign_in('a@example.test','long-synthetic-password')
        self.assertEqual(self.account.user_id,UID)
        self.assertNotIn('access_token',self.store.values['session'])
        self.account.sign_out();self.assertFalse(self.store.values);self.assertIsNone(self.account.user_id)
    def test_restart_restores_and_rotates_refresh_token(self):
        self.account.sign_in('a@example.test','password')
        restarted=Account(self.gateway,self.store,'cookie-one')
        self.assertTrue(restarted.restore());self.assertEqual(restarted.user_id,UID)
        wrong_browser=Account(self.gateway,self.store,'other-cookie')
        self.assertFalse(wrong_browser.restore())
    def test_expired_invalid_session_clears_credentials(self):
        self.account.sign_in('a@example.test','password');self.account._expires=0;self.failure='invalid'
        with self.assertRaises(SessionExpired):self.account.authenticated('GET','/rest/v1/workbench_items')
        self.assertIsNone(self.account.user_id);self.assertFalse(self.store.values)
    def test_network_failure_keeps_saved_session_for_retry(self):
        self.account.sign_in('a@example.test','password');self.failure='offline'
        restarted=Account(self.gateway,self.store,'cookie-one')
        with self.assertRaises(PersistenceError):restarted.restore()
        self.assertIn('session',self.store.values);self.assertFalse(restarted.restored)
        self.failure=None;self.assertTrue(restarted.restore())
    def test_incorrect_credentials_never_authenticate(self):
        self.failure='invalid'
        with self.assertRaises(SessionExpired):self.account.sign_in('a@example.test','incorrect')
        self.assertIsNone(self.account.user_id)
    def test_recovery_requires_code_and_does_not_open_workspace(self):
        self.account.request_recovery('a@example.test')
        with self.assertRaises(PersistenceError):self.account.recover('a@example.test','','long-new-password')
        self.account.recover('a@example.test','123456','long-new-password')
        self.assertIsNone(self.account.user_id)
        self.assertTrue(any(r.method=='PUT' and r.url.path.endswith('/user') for r in self.calls))
    def test_account_switch_invalidates_previous_account(self):
        self.account.sign_in('a@example.test','password')
        other=Account(self.gateway,MemoryStore(),'second-cookie');other.sign_in('b@example.test','password')
        self.assertIsNone(self.account.user_id);self.assertEqual(self.account._access,'')
    def test_password_change_reauthenticates_and_clears_session(self):
        self.account.sign_in('a@example.test','old-password')
        self.account.change_password('old-password','new-long-password')
        self.assertIsNone(self.account.user_id)
        self.assertNotIn('session',self.store.values)
        self.assertTrue(any(r.method=='PUT' and r.url.path.endswith('/user') for r in self.calls))
    def test_keychain_failure_does_not_authenticate(self):
        self.store.write=Mock(side_effect=RuntimeError('Keychain unavailable'))
        with self.assertRaises(PersistenceError):self.account.sign_in('a@example.test','password')
        self.assertIsNone(self.account.user_id)
    def test_protected_route_does_not_construct_private_page(self):
        from services.auth import protected
        page=Mock()
        with patch('services.auth.get_account',return_value=self.account),patch('services.auth.ui.navigate.to') as navigate:
            protected(page)()
            navigate.assert_called_once_with('/auth');page.assert_not_called()
