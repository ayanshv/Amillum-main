"""Server-only billing adapter. Stripe owns billing; Supabase owns access decisions."""
import hashlib,hmac,json,os,time
from datetime import datetime,timezone
from urllib.parse import urlsplit
from uuid import UUID
import httpx
from fastapi import HTTPException
from services.supabase import Supabase


def database(method,path,token=None,body=None,admin=False):
    key=os.getenv('SUPABASE_SERVICE_ROLE_KEY','') if admin else os.getenv('SUPABASE_PUBLISHABLE_KEY','')
    url=os.getenv('SUPABASE_URL','').rstrip('/')
    if not key or not url.startswith('https://'):raise HTTPException(503,'Account service is not configured')
    try:
        with httpx.Client(timeout=12,follow_redirects=False) as client:
            r=client.request(method,url+'/rest/v1/'+path,headers={'apikey':key,'Prefer':'return=representation',**({'Authorization':'Bearer '+(key if admin else token)} if admin or token else {})},json=body)
        if r.status_code>=400:raise HTTPException(503,'Account state could not be confirmed; retry later')
        return r.json() if r.content else None
    except (httpx.HTTPError,ValueError):raise HTTPException(503,'Account service unavailable') from None


def identity(token):
    if not token:raise HTTPException(401,'Sign in to continue')
    gateway=Supabase()
    try:
        data=gateway.request('GET','/auth/v1/user',token=token)
        return str(UUID(data['id']))
    except Exception:raise HTTPException(401,'Sign in again to continue') from None
    finally:gateway.http.close()


def catalog():
    rows=database('GET','billing_plans?select=config')
    result=sorted([r['config'] for r in rows],key=lambda p:p['rank'])
    if {p['id'] for p in result}!={'free','weekly','monthly','grand'}:raise HTTPException(503,'Plan configuration unavailable')
    return result


def entitlements(token):
    identity(token)
    return database('POST','rpc/get_entitlements',token,{})


def stripe(method,path,data=None,idempotency=None):
    key=os.getenv('STRIPE_SECRET_KEY','')
    if not key:raise HTTPException(503,'Billing is not configured')
    headers={'Authorization':'Bearer '+key,'Stripe-Version':'2025-03-31.basil'}
    if idempotency:headers['Idempotency-Key']=idempotency
    try:
        with httpx.Client(timeout=20,follow_redirects=False) as client:
            r=client.request(method,'https://api.stripe.com/v1/'+path,headers=headers,data=data)
        if r.status_code>=400:raise HTTPException(503,'Billing could not complete this action. Please retry later.')
        return r.json()
    except (httpx.HTTPError,ValueError):raise HTTPException(503,'Billing unavailable; no local subscription change was made') from None


def website_url(variable):
    value=os.getenv(variable,'');base=urlsplit(os.getenv('AMILLUM_WEBSITE_URL',''));url=urlsplit(value)
    local=os.getenv('AMILLUM_ENV')=='development' and url.hostname in ('127.0.0.1','localhost')
    if (url.scheme!='https' and not(local and url.scheme=='http')) or not url.hostname or url.netloc!=base.netloc or url.scheme!=base.scheme or url.username or url.fragment:
        raise HTTPException(503,'Website billing URLs are not configured')
    return value


def checkout(token,plan_id):
    user=identity(token)
    plan=next((p for p in catalog() if p['id']==plan_id and p['id']!='free'),None)
    if not plan:raise HTTPException(422,'Choose a paid plan')
    success=website_url('STRIPE_SUCCESS_URL');cancel=website_url('STRIPE_CANCEL_URL')
    price_id=os.getenv(plan['stripe_price_env'],'')
    if not price_id.startswith('price_'):raise HTTPException(503,'Plan price is not configured')
    price=stripe('GET','prices/'+price_id)
    if (price.get('unit_amount')!=plan['price'] or price.get('currency')!=plan['currency'] or
        price.get('recurring',{}).get('interval')!=plan['interval'] or price.get('recurring',{}).get('interval_count')!=1 or not price.get('active')):
        raise HTTPException(503,'Billing price does not match the published plan')
    rows=database('GET','subscriptions?user_id=eq.'+user+'&select=*',admin=True)
    if rows and rows[0].get('subscription_id') and rows[0]['status'] not in ('canceled','expired','incomplete_expired'):
        raise HTTPException(409,'You already have a subscription. Open Account → Manage subscription & billing to change plans.')
    customer=rows[0]['customer_id'] if rows else stripe('POST','customers',{'metadata[amillum_user_id]':user},'amillum-customer-'+user)['id']
    reservation=database('POST','rpc/reserve_checkout',body={'p_user':user,'p_customer':customer},admin=True)
    data={'mode':'subscription','customer':customer,'line_items[0][price]':price_id,'line_items[0][quantity]':'1','success_url':success,'cancel_url':cancel,'payment_method_collection':'always','expires_at':str(int(time.time())+1800),'subscription_data[metadata][amillum_user_id]':user}
    if reservation['trial']:data['subscription_data[trial_period_days]']=str(plan['trial_days'])
    session=stripe('POST','checkout/sessions',data,'amillum-checkout-'+reservation['key'])
    return {'url':session['url']}


def portal(token):
    user=identity(token)
    rows=database('GET','subscriptions?user_id=eq.'+user+'&select=customer_id',admin=True)
    if not rows:raise HTTPException(409,'Choose a plan before opening billing management')
    return {'url':stripe('POST','billing_portal/sessions',{'customer':rows[0]['customer_id'],'return_url':website_url('STRIPE_PORTAL_RETURN_URL')})['url']}


def verify_event(raw,signature,now=None):
    secret=os.getenv('STRIPE_WEBHOOK_SECRET','')
    if not secret:raise HTTPException(503,'Webhook is not configured')
    try:
        parts=[p.split('=',1) for p in signature.split(',')]
        timestamp=int(next(v for k,v in parts if k=='t'))
        expected=hmac.new(secret.encode(),str(timestamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
        if abs((time.time() if now is None else now)-timestamp)>300 or not any(k=='v1' and hmac.compare_digest(v,expected) for k,v in parts):raise ValueError()
        event=json.loads(raw)
        if not isinstance(event,dict):raise ValueError()
        if event.get('livemode') is not (os.getenv('STRIPE_MODE','test')=='live'):raise ValueError()
        return event
    except (ValueError,StopIteration,TypeError):raise HTTPException(400,'Invalid webhook signature or mode') from None


def webhook(raw,signature):
    event=verify_event(raw,signature)
    if event.get('type') not in ('customer.subscription.created','customer.subscription.updated','customer.subscription.deleted','invoice.paid','invoice.payment_failed','checkout.session.completed'):
        return {'received':True}
    obj=event.get('data',{}).get('object',{})
    sub_id=obj.get('id') if event['type'].startswith('customer.subscription.') else obj.get('subscription') or obj.get('parent',{}).get('subscription_details',{}).get('subscription')
    if not isinstance(sub_id,str) or not sub_id.startswith('sub_'):return {'received':True}
    # Fetch current state rather than trusting an out-of-order payload snapshot.
    sub=stripe('GET','subscriptions/'+sub_id)
    items=sub.get('items',{}).get('data',[])
    if len(items)!=1:raise HTTPException(503,'Unsupported subscription configuration')
    item=items[0];price=item['price']['id']
    plan=next((p for p in catalog() if p.get('stripe_price_env') and os.getenv(p['stripe_price_env'])==price),None)
    if not plan:raise HTTPException(503,'Unmapped subscription price')
    start=sub.get('trial_start') if sub['status']=='trialing' else item.get('current_period_start',sub.get('current_period_start'))
    end=sub.get('trial_end') if sub['status']=='trialing' else item.get('current_period_end',sub.get('current_period_end'))
    if not start or not end:raise HTTPException(503,'Subscription period unavailable')
    stamp=lambda t:datetime.fromtimestamp(t,timezone.utc).isoformat()
    database('POST','rpc/sync_subscription',admin=True,body={'p_customer':sub['customer'],'p_subscription':sub_id,'p_plan':plan['id'],'p_status':sub['status'],'p_start':stamp(start),'p_end':stamp(end),'p_cancel':bool(sub.get('cancel_at_period_end')),'p_event':event['created']})
    return {'received':True}
