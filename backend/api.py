"""Deploy separately from the desktop. Provider secrets belong ONLY on this server."""
import os
import json
from uuid import UUID,uuid4
import httpx
from fastapi import FastAPI,Header,HTTPException,Request
from fastapi.concurrency import run_in_threadpool
from core.privacy import require_safe_text
from services.supabase import Supabase
from services.email_drafting import draft_prompt,parse_draft

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

app=FastAPI(title='Amillum AI backend',docs_url=None,redoc_url=None,openapi_url=None)


def configured():
    # Reuse the existing public-key validation; never accept privileged keys.
    client=Supabase()
    try:
        return client.configured and bool(os.getenv('GEMINI_API_KEY','').strip())
    finally:
        client.http.close()


@app.get('/healthz')
def health():
    return {'status':'ok'}


@app.get('/readyz')
def readiness():
    if not configured():raise HTTPException(503,'Backend is not configured')
    return {'status':'configured'}



def authorize(token,feature,request_id=None):
    url=os.getenv('SUPABASE_URL','').rstrip('/')
    key=os.getenv('SUPABASE_PUBLISHABLE_KEY','')
    if not url.startswith('https://') or not key:raise HTTPException(503,'Backend is not configured')
    headers={'apikey':key,'Authorization':'Bearer '+token}
    try:
        with httpx.Client(timeout=8,follow_redirects=False) as client:
            user=client.get(url+'/auth/v1/user',headers=headers)
            if user.status_code in (400,401,403):raise HTTPException(401,'Authentication required')
            if user.status_code!=200:raise HTTPException(503,'Authentication unavailable')
            # Database derives user identity from the verified JWT; no client user_id.
            quota=client.post(url+'/rest/v1/rpc/consume_ai_allowance',headers=headers,json={'requested_feature':feature,**({'request_id':request_id} if request_id else {})})
            if quota.status_code!=200:raise HTTPException(503,'Usage enforcement unavailable')
            decision=quota.json()
            if decision=='denied':raise HTTPException(403,'Feature unavailable')
            if decision=='duplicate':raise HTTPException(409,'This request was already submitted. Start a new request explicitly.')
            if decision=='rate_limit':raise HTTPException(429,'Too many requests. Wait a minute before retrying.')
            if decision=='limit':raise HTTPException(429,'Usage limit reached')
            if decision!='allowed':raise HTTPException(503,'Usage enforcement unavailable')
    except (httpx.HTTPError,ValueError):raise HTTPException(503,'Authorization unavailable') from None


def generate_authorized(token,data,engine=None,authorizer=None,request_id=None):
    if not isinstance(data,dict):raise HTTPException(422,'Invalid request')
    feature=data.get('feature');context=data.get('context')
    if feature not in ('document_analysis','email_drafting','contextual_assistance','ai_questions'):raise HTTPException(422,'Unsupported feature')
    limit=12000 if feature=='email_drafting' else 1000000
    if not isinstance(context,str) or not context.strip() or len(context)>limit:raise HTTPException(422,'Invalid approved context')
    try:
        require_safe_text(context)
        if feature=='email_drafting':
            if set(data)-{'feature','context','tone','length','notes'}:raise ValueError()
            question=draft_prompt(data.get('tone','Professional'),data.get('length','Concise'),data.get('notes',''))
            language='English'
        else:
            if set(data)-{'feature','context','question','language'}:raise ValueError()
            question=data.get('question','');language=data.get('language','English')
            if not isinstance(question,str) or len(question)>12000 or not isinstance(language,str) or len(language)>80:raise ValueError()
            require_safe_text(question)
    except ValueError:raise HTTPException(422,'Invalid or sensitive content') from None
    if not token:raise HTTPException(401,'Authentication required')
    if engine is None and not configured():raise HTTPException(503,'Backend is not configured')
    if request_id is not None and authorizer is None:authorize(token,feature,request_id)
    else:(authorizer or authorize)(token,feature)
    if engine is None:
        from backend.provider_engine import analyze_document
        engine=analyze_document
    try:
        text=engine(context,question,language)
        if feature=='email_drafting':
            draft=parse_draft(text)
            text=json.dumps({'subject':draft.subject,'body':draft.body})
        if not isinstance(text,str) or not text or len(text)>100000:raise ValueError()
        return {'text':text}
    except Exception:raise HTTPException(502,'Generation unavailable; retry explicitly') from None


@app.post('/v1/generate')
async def generate_endpoint(request:Request,authorization:str=Header(default=''),x_request_id:str=Header(default='')):
    try:request_id=str(UUID(x_request_id)) if x_request_id else str(uuid4())
    except ValueError:raise HTTPException(422,'Invalid request ID') from None
    if not authorization.startswith('Bearer '):raise HTTPException(401,'Authentication required')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>4500000:raise HTTPException(413,'Request too large')
    try:data=json.loads(raw)
    except ValueError:raise HTTPException(422,'Invalid request') from None
    return await run_in_threadpool(generate_authorized,authorization[7:],data,request_id=request_id)


@app.get('/v1/plans')
def plans_endpoint():
    from backend.billing import catalog
    return catalog()


@app.get('/v1/entitlements')
def entitlements_endpoint(authorization:str=Header(default='')):
    from backend.billing import entitlements
    return entitlements(authorization[7:] if authorization.startswith('Bearer ') else '')


@app.post('/v1/billing/{action}')
async def billing_endpoint(action:str,request:Request,authorization:str=Header(default='')):
    from backend.billing import checkout,portal
    token=authorization[7:] if authorization.startswith('Bearer ') else ''
    if action=='portal':return await run_in_threadpool(portal,token)
    if action!='checkout':raise HTTPException(404,'Not found')
    data=await small_json(request)
    if set(data)!={'plan'}:raise HTTPException(422,'Choose a plan')
    return await run_in_threadpool(checkout,token,data['plan'])


async def small_json(request):
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>16000:raise HTTPException(413,'Request too large')
    try:
        value=json.loads(raw)
        if not isinstance(value,dict):raise ValueError()
        return value
    except ValueError:raise HTTPException(422,'Invalid request') from None


@app.post('/v1/stripe/webhook')
async def stripe_endpoint(request:Request,stripe_signature:str=Header(default='')):
    from backend.billing import webhook
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>1000000:raise HTTPException(413,'Event too large')
    return await run_in_threadpool(webhook,bytes(raw),stripe_signature)


@app.post('/v1/auth/{action}')
async def website_auth(action:str,request:Request):
    # The website reuses the same Supabase Auth service; no second identity store.
    from services.supabase import PersistenceError
    data=await small_json(request)
    allowed={'login':{'email','password'},'signup':{'email','password'},'refresh':{'refresh_token'},'recovery':{'email'},'logout':{'access_token'}}
    if action not in allowed or set(data)!=allowed[action] or any(not isinstance(v,str) or len(v)>4096 for v in data.values()):raise HTTPException(422,'Invalid account request')
    if action=='signup' and len(data['password'])<12:raise HTTPException(422,'Use a password of at least 12 characters')
    def perform():
        gateway=Supabase()
        try:
            if action=='login':return gateway.request('POST','/auth/v1/token',params={'grant_type':'password'},body=data)
            if action=='signup':return gateway.request('POST','/auth/v1/signup',body=data)
            if action=='refresh':return gateway.request('POST','/auth/v1/token',params={'grant_type':'refresh_token'},body=data)
            if action=='recovery':gateway.request('POST','/auth/v1/recover',body=data);return {'ok':True}
            gateway.request('POST','/auth/v1/logout',token=data['access_token']);return {'ok':True}
        except PersistenceError:raise HTTPException(400,'Account request could not be completed. Check your details or try again later.') from None
        finally:gateway.http.close()
    return await run_in_threadpool(perform)
