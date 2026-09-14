import base64
import json
import time
import unittest
from uuid import uuid4
import httpx
from services.supabase import Supabase, Account, PersistenceError
from services.workbench import Workbench, validate

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
ITEM='33333333-3333-4333-8333-333333333333'
SOURCE='44444444-4444-4444-8444-444444444444'


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.requests=[]
        self.reply=[]
        self.failure=False
        def transport(request):
            self.requests.append(request)
            if self.failure:raise httpx.ConnectError('PRIVATE CONTENT',request=request)
            return httpx.Response(200,json=self.reply)
        self.gateway=Supabase('https://example.supabase.co','sb_publishable_test',httpx.MockTransport(transport))
        self.account=Account(self.gateway)
        self.account.user_id=A;self.account._access='USER_JWT';self.account._refresh='REFRESH';self.account._expires=time.monotonic()+3600
        self.service=Workbench(self.account)
        self.values={'type':'task','title':'Give notice','description':'Review the notice clause','status':'open'}

    def tearDown(self):self.gateway.http.close()

    def test_create_sends_no_user_id_and_uses_session_token(self):
        self.reply=[{'id':ITEM}]
        self.service.save(self.values,item_id=ITEM)
        request=self.requests[-1]
        self.assertEqual(request.headers['authorization'],'Bearer USER_JWT')
        payload=json.loads(request.content)
        self.assertNotIn('user_id',payload['p_item'])
        self.assertEqual(payload['p_item']['id'],ITEM)
        with self.assertRaises(PersistenceError):self.service.save({**self.values,'user_id':B})
        self.assertEqual(len(self.requests),1)

    def test_filters_and_pagination(self):
        self.service.list('question','open',50)
        params=self.requests[-1].url.params
        self.assertEqual(params['type'],'eq.question');self.assertEqual(params['status'],'eq.open')
        self.assertEqual(params['offset'],'50');self.assertEqual(params['limit'],'50')
        self.assertIn('workbench_sources',params['select'])

    def test_update_complete_dismiss_delete(self):
        self.reply=[{'id':ITEM}]
        self.service.update(ITEM,self.values)
        self.assertEqual(self.requests[-1].method,'PATCH')
        self.service.set_status(ITEM,'completed')
        self.assertEqual(json.loads(self.requests[-1].content),{'status':'completed'})
        self.service.set_status(ITEM,'dismissed')
        self.service.delete(ITEM)
        self.assertEqual(self.requests[-1].method,'DELETE')
        self.assertEqual(self.requests[-1].url.params['id'],'eq.'+ITEM)

    def test_source_reference_is_minimal_and_matches_item(self):
        self.reply=[{'id':ITEM}]
        self.service.save({**self.values,'document_id':SOURCE},item_id=ITEM,
                          source={'id':SOURCE,'title':'Lease.pdf','kind':'document','body':'DO NOT SEND'})
        payload=json.loads(self.requests[-1].content)
        self.assertEqual(set(payload['p_source']),{'id','title','kind'})
        self.assertNotIn('DO NOT SEND',str(payload))
        with self.assertRaises(PersistenceError):
            self.service.save(self.values,source={'id':SOURCE,'title':'Lease.pdf','kind':'document'})

    def test_dates_need_exact_confirmation(self):
        self.assertIsNone(validate(self.values)['due_date'])
        for when,confirmed in [('30 days',True),('2026-02-30',True),('2026-10-01',False)]:
            with self.assertRaises(PersistenceError):validate({**self.values,'due_date':when,'date_confirmed':confirmed})
        self.assertEqual(validate({**self.values,'due_date':'2026-10-01','date_confirmed':True})['due_date'],'2026-10-01')

    def test_failed_save_keeps_input_and_retry_id(self):
        original=dict(self.values)
        self.failure=True
        with self.assertRaises(PersistenceError) as error:self.service.save(self.values,item_id=ITEM)
        self.assertNotIn('PRIVATE CONTENT',str(error.exception))
        self.assertEqual(self.values,original)
        self.failure=False;self.reply=[{'id':ITEM}]
        self.service.save(self.values,item_id=ITEM)
        self.assertEqual(json.loads(self.requests[0].content)['p_item']['id'],json.loads(self.requests[1].content)['p_item']['id'])

    def test_unauthenticated_operations_never_reach_database(self):
        self.account.user_id=None
        for operation in [lambda:self.service.list(),lambda:self.service.save(self.values),lambda:self.service.update(ITEM,self.values),lambda:self.service.delete(ITEM)]:
            with self.assertRaises(PersistenceError):operation()
        self.assertFalse(self.requests)

    def test_inaccessible_update_is_not_reported_successful(self):
        with self.assertRaises(PersistenceError):self.service.set_status(ITEM,'completed')

    def test_auth_uses_verified_identity_and_private_tokens(self):
        def transport(request):
            if request.url.path.endswith('/token'):
                return httpx.Response(200,json={'access_token':'TOKEN','refresh_token':'REFRESH','user':{'id':B},'expires_in':3600})
            return httpx.Response(200,json={'id':A,'email':'a@example.test'})
        gateway=Supabase('https://example.supabase.co','sb_publishable_test',httpx.MockTransport(transport))
        account=Account(gateway)
        account.sign_in('a@example.test','synthetic-password')
        self.assertEqual(account.snapshot()['user_id'],A)
        self.assertNotIn('TOKEN',str(account.snapshot()))
        account.sign_out();self.assertIsNone(account.snapshot()['user_id']);self.assertEqual(account._access,'')
        gateway.http.close()

    def test_refresh_and_account_change_discard_response(self):
        self.account._expires=0
        def transport(request):
            if request.url.path.endswith('/token'):
                return httpx.Response(200,json={'access_token':'NEW','refresh_token':'NEXT','expires_in':3600})
            if request.url.path.endswith('/user'):return httpx.Response(200,json={'id':A})
            self.assertEqual(request.headers['authorization'],'Bearer NEW')
            self.account.generation+=1
            return httpx.Response(200,json=[{'id':ITEM}])
        self.gateway.http.close();self.gateway.http=httpx.Client(transport=httpx.MockTransport(transport))
        with self.assertRaises(PersistenceError):self.service.list()

    def test_service_role_and_insecure_configuration_rejected(self):
        payload=base64.urlsafe_b64encode(json.dumps({'role':'service_role'}).encode()).decode().rstrip('=')
        for url,key in [('https://example.supabase.co','sb_secret_test'),('https://example.supabase.co','x.'+payload+'.x'),('http://example.supabase.co','sb_publishable_test')]:
            gateway=Supabase(url,key)
            self.assertFalse(gateway.configured)
            with self.assertRaises(PersistenceError):gateway.request('GET','/rest/v1/workbench_items')
            gateway.http.close()
