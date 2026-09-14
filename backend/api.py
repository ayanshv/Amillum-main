"""Deploy separately from the desktop. Provider secrets belong ONLY on this server."""
import os
import json
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



def authorize(token,feature):
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
            quota=client.post(url+'/rest/v1/rpc/consume_ai_allowance',headers=headers,json={'requested_feature':feature})
            if quota.status_code!=200:raise HTTPException(503,'Usage enforcement unavailable')
            decision=quota.json()
            if decision=='denied':raise HTTPException(403,'Feature unavailable')
            if decision=='limit':raise HTTPException(429,'Usage limit reached')
            if decision!='allowed':raise HTTPException(503,'Usage enforcement unavailable')
    except (httpx.HTTPError,ValueError):raise HTTPException(503,'Authorization unavailable') from None


def generate_authorized(token,data,engine=None,authorizer=None):
    if not isinstance(data,dict):raise HTTPException(422,'Invalid request')
    feature=data.get('feature');context=data.get('context')
    if feature not in ('document_analysis','email_drafting'):raise HTTPException(422,'Unsupported feature')
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
    (authorizer or authorize)(token,feature)
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
async def generate_endpoint(request:Request,authorization:str=Header(default='')):
    if not authorization.startswith('Bearer '):raise HTTPException(401,'Authentication required')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>4500000:raise HTTPException(413,'Request too large')
    try:data=json.loads(raw)
    except ValueError:raise HTTPException(422,'Invalid request') from None
    return await run_in_threadpool(generate_authorized,authorization[7:],data)
