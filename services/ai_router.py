"""Single desktop AI gateway. Provider credentials never enter this module."""
import os
import sys
from uuid import uuid4
from urllib.parse import urlsplit
import httpx
from services.supabase import PersistenceError,SessionExpired

_HTTP=httpx.Client(timeout=httpx.Timeout(65,connect=5),follow_redirects=False)


def endpoint_url():
    endpoint=os.getenv('AMILLUM_AI_BACKEND_URL','').rstrip('/')
    try:
        parsed=urlsplit(endpoint)
        parsed.port  # Reject malformed ports before any request.
        local_dev=(os.getenv('AMILLUM_ENV')=='development' and not getattr(sys,'frozen',False)
                   and parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1','::1'))
        valid=(parsed.scheme=='https' or local_dev) and parsed.hostname and not (
            parsed.username or parsed.password or parsed.query or parsed.fragment)
    except ValueError:
        valid=False
    if not valid:
        raise PersistenceError('AI generation is not configured. Deploy the Amillum backend and set AMILLUM_AI_BACKEND_URL. No context was sent.')
    return endpoint


def generate(account,payload):
    endpoint=endpoint_url()
    def request(token):
        try:
            response=_HTTP.post(endpoint+'/v1/generate',headers={'Authorization':'Bearer '+token,'X-Request-ID':str(uuid4())},json=payload)
        except httpx.HTTPError:raise PersistenceError('The AI backend could not be reached. Your current draft is preserved; retry when connected.') from None
        if response.status_code==401:raise SessionExpired('Your session expired. Sign in again.')
        if response.status_code==403:raise PersistenceError('This feature is not included in your plan. Compare plans on the Amillum website.')
        if response.status_code==429:raise PersistenceError('Your AI usage limit or short-term request limit has been reached. Your draft is preserved. See Plans & billing for usage, reset timing, and upgrade options.')
        if response.status_code!=200:raise PersistenceError('The AI service could not complete this request. Your draft is preserved; try again.')
        try:
            result=response.json()['text']
            if not isinstance(result,str) or not result or len(result)>100000:raise ValueError()
            return result
        except (ValueError,KeyError,TypeError):raise PersistenceError('The AI backend returned an invalid response.') from None
    return account.backend_operation(request)
