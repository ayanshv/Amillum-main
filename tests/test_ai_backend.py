import unittest
from unittest.mock import Mock,patch
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.api import app,generate_authorized
from services.ai_router import generate
from services.supabase import PersistenceError

class BackendTests(unittest.TestCase):
    def setUp(self):
        self.data={'feature':'email_drafting','context':'Approved text','tone':'Professional','length':'Concise'}
        self.engine=Mock(return_value='{"subject":"A question","body":"Could you clarify this point?"}')
    def test_generation_uses_shared_engine_after_authorization(self):
        authorize=Mock();result=generate_authorized('token',self.data,self.engine,authorize)
        authorize.assert_called_once_with('token','email_drafting')
        self.assertEqual(self.engine.call_args.args[0],'Approved text')
        self.assertIn('A question',result['text'])
    def test_denial_or_quota_prevents_provider(self):
        for status in [401,403,429,503]:
            with self.assertRaises(HTTPException):generate_authorized('token',self.data,self.engine,Mock(side_effect=HTTPException(status)))
        self.engine.assert_not_called()
    def test_model_failure_has_no_content_in_error(self):
        self.engine.side_effect=RuntimeError('sensitive-source-or-provider-key')
        with self.assertRaises(HTTPException) as error:generate_authorized('token',self.data,self.engine,Mock())
        self.assertEqual(error.exception.status_code,502)
        self.assertNotIn('sensitive',error.exception.detail)
    def test_no_caller_identity_or_recipient_injection(self):
        for extra in ['user_id','recipient','provider_key']:
            with self.assertRaises(HTTPException):generate_authorized('token',dict(self.data,**{extra:'injected'}),self.engine,Mock())
        self.engine.assert_not_called()
    def test_http_requires_authentication(self):
        response=TestClient(app).post('/v1/generate',json=self.data)
        self.assertEqual(response.status_code,401)
    def test_router_maps_limits_without_fallback(self):
        account=Mock();account.backend_operation.side_effect=lambda f:f('synthetic')
        with patch.dict('os.environ',{'AMILLUM_AI_BACKEND_URL':'https://backend.example.test'}):
            with patch('services.ai_router._HTTP',httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(429)))):
                with self.assertRaises(PersistenceError) as error:generate(account,self.data)
                self.assertIn('usage limit',str(error.exception))
    def test_unconfigured_router_sends_nothing(self):
        with patch.dict('os.environ',{'AMILLUM_AI_BACKEND_URL':''}):
            account=Mock()
            with self.assertRaises(PersistenceError):generate(account,self.data)
            account.backend_operation.assert_not_called()

class ProductionConnectionTests(unittest.TestCase):
    def test_health_and_missing_config_fail_closed_without_charging(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':''}), patch('backend.api.authorize') as auth:
            client=TestClient(app)
            self.assertEqual(client.get('/healthz').status_code,200)
            self.assertEqual(client.get('/readyz').status_code,503)
            response=client.post('/v1/generate',headers={'Authorization':'Bearer synthetic'},json={'feature':'email_drafting','context':'Approved excerpt'})
            self.assertEqual(response.status_code,503)
            auth.assert_not_called()
    def test_router_localhost_requires_source_development_opt_in(self):
        account=Mock();account.backend_operation.side_effect=lambda f:f('synthetic')
        transport=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'text':'Draft'})))
        with patch('services.ai_router._HTTP',transport):
            for mode,frozen,url,allowed in [('production',False,'http://127.0.0.1:8080',False),('development',False,'http://127.0.0.1:8080',True),('development',True,'http://127.0.0.1:8080',False),('development',False,'http://external.example',False),('production',True,'https://backend.example',True),('production',False,'https://backend.example:bad',False)]:
                with self.subTest(mode=mode,frozen=frozen,url=url), patch.dict('os.environ',{'AMILLUM_ENV':mode,'AMILLUM_AI_BACKEND_URL':url}), patch('sys.frozen',frozen,create=True):
                    if allowed:self.assertEqual(generate(account,{}),'Draft')
                    else:
                        with self.assertRaises(PersistenceError):generate(account,{})
    def test_identity_and_allowance_http_sequence(self):
        from backend.api import authorize
        for decision,status in [('allowed',None),('denied',403),('limit',429)]:
            calls=[]
            def handler(request):
                calls.append(request)
                return httpx.Response(200,json={'id':'synthetic-user'} if request.method=='GET' else decision)
            client=httpx.Client(transport=httpx.MockTransport(handler))
            with patch.dict('os.environ',{'SUPABASE_URL':'https://project.example','SUPABASE_PUBLISHABLE_KEY':'sb_publishable_test'}),patch('backend.api.httpx.Client',return_value=client):
                if status:
                    with self.assertRaises(HTTPException) as error:authorize('synthetic','email_drafting')
                    self.assertEqual(error.exception.status_code,status)
                else:authorize('synthetic','email_drafting')
            self.assertEqual([r.url.path for r in calls],['/auth/v1/user','/rest/v1/rpc/consume_ai_allowance'])
            self.assertEqual(calls[1].headers['Authorization'],'Bearer synthetic')
            self.assertNotIn(b'user_id',calls[1].content)
    def test_invalid_identity_never_consumes_allowance(self):
        from backend.api import authorize
        calls=[]
        def handler(request):
            calls.append(request);return httpx.Response(401)
        client=httpx.Client(transport=httpx.MockTransport(handler))
        with patch.dict('os.environ',{'SUPABASE_URL':'https://project.example','SUPABASE_PUBLISHABLE_KEY':'sb_publishable_test'}),patch('backend.api.httpx.Client',return_value=client):
            with self.assertRaises(HTTPException) as error:authorize('synthetic','email_drafting')
            self.assertEqual(error.exception.status_code,401)
        self.assertEqual(len(calls),1)
    def test_existing_document_analysis_route(self):
        engine=Mock(return_value='Existing explanation')
        self.assertEqual(generate_authorized('synthetic',{'feature':'document_analysis','context':'Approved document','question':'Explain','language':'English'},engine,Mock()),{'text':'Existing explanation'})
        engine.assert_called_once_with('Approved document','Explain','English')
