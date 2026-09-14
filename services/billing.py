"""Desktop display of server entitlements; payment actions stay on the website."""
import os,time,threading
from urllib.parse import urlsplit
import httpx
from services.supabase import PersistenceError,SessionExpired

_CACHE={}
_LOCK=threading.RLock()

def website():
    value=os.getenv('AMILLUM_WEBSITE_URL','').rstrip('/')
    parsed=urlsplit(value)
    local=os.getenv('AMILLUM_ENV')=='development' and parsed.hostname in ('127.0.0.1','localhost')
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or (parsed.scheme!='https' and not(local and parsed.scheme=='http')):return None
    return value+'/pricing'


def refresh(account):
    from services.ai_router import endpoint_url
    base=endpoint_url()
    generation=account.generation
    def fetch(token):
        try:
            with httpx.Client(timeout=10,follow_redirects=False) as client:r=client.get(base+'/v1/entitlements',headers={'Authorization':'Bearer '+token})
            if r.status_code==401:raise SessionExpired('Sign in again.')
            if r.status_code!=200:raise PersistenceError('Plan status is temporarily unavailable.')
            return r.json()
        except SessionExpired:raise
        except (httpx.HTTPError,ValueError):raise PersistenceError('Plan status is temporarily unavailable.') from None
    result=account.backend_operation(fetch)
    with _LOCK:_CACHE[(account.user_id,generation)]=(time.monotonic()+65,result)
    return result


def shortcut_allowed(account):
    with _LOCK:entry=_CACHE.get((account.user_id,account.generation))
    return bool(entry and entry[0]>time.monotonic() and entry[1]['features'].get('global_shortcut',{}).get('enabled'))
