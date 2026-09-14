import hashlib,hmac,json,os,unittest
from unittest.mock import patch,Mock
from fastapi import HTTPException
from backend.catalog import plans
from backend.billing import verify_event,checkout,portal,webhook

class MonetizationTests(unittest.TestCase):
    def test_canonical_catalog(self):
        p={v['id']:v for v in plans()}
        self.assertEqual(list(p),['free','weekly','monthly','grand'])
        self.assertEqual([v['price'] for v in p.values()],[0,500,2400,3500])
        self.assertEqual([v['interval'] for v in p.values()],[None,'week','month','week'])
        self.assertEqual([v['trial_days'] for v in p.values()],[0,7,7,7])
        self.assertTrue(p['monthly']['recommended'] and p['monthly']['best_value'])
        self.assertTrue(p['grand']['premium'])
        self.assertFalse(p['free']['features']['email_drafting']['enabled'])
        self.assertTrue(p['monthly']['features']['advanced_workbench']['enabled'])
        self.assertFalse(p['monthly']['features']['signature_workflow']['available'])
    def test_signature_and_replay_window(self):
        raw=b'{"livemode":false,"type":"example"}'
        signature='t=1000,v1='+hmac.new(b'synthetic',b'1000.'+raw,hashlib.sha256).hexdigest()
        with patch.dict(os.environ,{'STRIPE_WEBHOOK_SECRET':'synthetic','STRIPE_MODE':'test'}):
            self.assertEqual(verify_event(raw,signature,1001)['type'],'example')
            for data,sig,now in [(raw+b' ',signature,1001),(raw,'t=1000,v1=bad',1001),(raw,signature,1400)]:
                with self.assertRaises(HTTPException):verify_event(data,sig,now)
    def test_checkout_uses_trusted_customer_price_and_trial(self):
        calls=[]
        def db(method,path,**kwargs):
            if path.startswith('subscriptions'):return []
            calls.append(kwargs['body']);return {'key':'synthetic','trial':True}
        def stripe(method,path,data=None,*args):
            if path.startswith('prices/'):return {'unit_amount':2400,'currency':'usd','recurring':{'interval':'month','interval_count':1},'active':True}
            if path=='customers':return {'id':'cus_synthetic'}
            calls.append(data);return {'url':'https://checkout.stripe.com/test'}
        env={'STRIPE_PRICE_MONTHLY':'price_synthetic','AMILLUM_WEBSITE_URL':'https://amillum.example','STRIPE_SUCCESS_URL':'https://amillum.example/account','STRIPE_CANCEL_URL':'https://amillum.example/pricing'}
        with patch.dict(os.environ,env),patch('backend.billing.identity',return_value='user-a'),patch('backend.billing.catalog',return_value=plans()),patch('backend.billing.database',side_effect=db),patch('backend.billing.stripe',side_effect=stripe):
            self.assertIn('url',checkout('token','monthly'))
            self.assertEqual(calls[-1]['subscription_data[trial_period_days]'],'7')
            self.assertEqual(calls[-1]['customer'],'cus_synthetic')
            with self.assertRaises(HTTPException):checkout('token','invented')
    def test_price_mismatch_fails_before_checkout(self):
        with patch.dict(os.environ,{'STRIPE_PRICE_MONTHLY':'price_test'}),patch('backend.billing.identity',return_value='user'),patch('backend.billing.catalog',return_value=plans()),patch('backend.billing.website_url',return_value='https://example.test'),patch('backend.billing.stripe',return_value={}),patch('backend.billing.database') as db:
            with self.assertRaises(HTTPException):checkout('token','monthly')
            db.assert_not_called()
    def test_portal_uses_owned_mapping(self):
        with patch('backend.billing.identity',return_value='user-a'),patch('backend.billing.database',return_value=[{'customer_id':'cus_a'}]) as db,patch('backend.billing.website_url',return_value='https://example.test/account'),patch('backend.billing.stripe',return_value={'url':'https://billing.stripe.com/test'}) as stripe:
            portal('token')
            self.assertIn('user_id=eq.user-a',db.call_args.args[1])
            self.assertEqual(stripe.call_args.args[2]['customer'],'cus_a')
    def test_webhook_fetches_current_subscription(self):
        event={'type':'customer.subscription.updated','created':2000,'data':{'object':{'id':'sub_a','status':'active'}}}
        sub={'id':'sub_a','customer':'cus_a','status':'past_due','items':{'data':[{'price':{'id':'price_monthly'},'current_period_start':1000,'current_period_end':3000}]}}
        with patch.dict(os.environ,{'STRIPE_PRICE_MONTHLY':'price_monthly'}),patch('backend.billing.verify_event',return_value=event),patch('backend.billing.stripe',return_value=sub),patch('backend.billing.catalog',return_value=plans()),patch('backend.billing.database') as db:
            webhook(b'', '')
            self.assertEqual(db.call_args.kwargs['body']['p_status'],'past_due')
            self.assertEqual(db.call_args.kwargs['body']['p_plan'],'monthly')

    def test_billing_endpoints_reject_client_state_and_missing_auth(self):
        from fastapi.testclient import TestClient
        from backend.api import app
        client=TestClient(app)
        self.assertEqual(client.post('/v1/billing/checkout',json={'plan':'grand','user_id':'forged'}).status_code,422)
        with patch('backend.billing.identity',side_effect=HTTPException(401,'Sign in')):
            self.assertEqual(client.post('/v1/billing/checkout',json={'plan':'grand'}).status_code,401)
            self.assertEqual(client.post('/v1/billing/portal').status_code,401)
    def test_unentitled_features_cannot_reach_ai(self):
        from backend.api import generate_authorized
        for feature in ('advanced_analysis','document_comparison','signature_workflow','future_utilities'):
            engine=Mock()
            with self.assertRaises(HTTPException):generate_authorized('token',{'feature':feature,'context':'test'},engine,Mock())
            engine.assert_not_called()
    def test_request_id_reaches_atomic_allowance_check(self):
        from fastapi.testclient import TestClient
        from backend.api import app
        identifier='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        with patch('backend.api.configured',return_value=True),patch('backend.api.authorize',side_effect=HTTPException(409,'Duplicate')) as check:
            result=TestClient(app).post('/v1/generate',headers={'Authorization':'Bearer synthetic','X-Request-ID':identifier},json={'feature':'email_drafting','context':'Approved'})
            self.assertEqual(result.status_code,409)
            check.assert_called_once_with('synthetic','email_drafting',identifier)
