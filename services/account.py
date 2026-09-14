"""Account data operations through the existing authenticated gateway."""
from services.supabase import PersistenceError
from core.privacy import valid_bundle_id, normalize_domain


def profile(account):
    rows=account.authenticated('GET','/rest/v1/profiles',params={'select':'display_name,created_at','limit':'1'})
    return rows[0] if rows else {'display_name':''}


def save_profile(account,name):
    name=name.strip()
    if len(name)>120:raise PersistenceError('Use at most 120 characters for your display name.')
    existing=account.authenticated('GET','/rest/v1/profiles',params={'select':'user_id','limit':'1'})
    return account.authenticated('PATCH' if existing else 'POST','/rest/v1/profiles',body={'display_name':name},params={'user_id':'eq.'+account.user_id} if existing else None)


def save_privacy(account,state):
    data={'excluded':sorted(state.preferences.excluded),'domains':sorted(state.preferences.domains)}
    existing=account.authenticated('GET','/rest/v1/user_settings',params={'select':'user_id','limit':'1'})
    account.authenticated('PATCH' if existing else 'POST','/rest/v1/user_settings',body={'privacy':data},params={'user_id':'eq.'+account.user_id} if existing else None)


def restore_privacy(account,state):
    rows=account.authenticated('GET','/rest/v1/user_settings',params={'select':'privacy','limit':'1'})
    if not rows:return
    data=rows[0]['privacy']; excluded=data.get('excluded',[]); domains=data.get('domains',[])
    if not isinstance(excluded,list) or len(excluded)>64 or not all(valid_bundle_id(x) for x in excluded):raise PersistenceError('Saved exclusions are invalid. Awareness remains paused.')
    if not isinstance(domains,list) or len(domains)>64 or not all(isinstance(x,str) and normalize_domain(x)==x for x in domains):raise PersistenceError('Saved website exclusions are invalid.')
    state.update(enabled=False,paused=True,clear=True)
    state.preferences.save(set(excluded),set(domains))


def delete_account(account,password,confirmation):
    if confirmation!='DELETE MY ACCOUNT':raise PersistenceError('Type DELETE MY ACCOUNT to confirm.')
    identity=account.user_id; generation=account.generation
    tokens=account.gateway.request('POST','/auth/v1/token',params={'grant_type':'password'},body={'email':account.email,'password':password})
    user=account.gateway.request('GET','/auth/v1/user',token=tokens['access_token'])
    if not identity or user['id']!=identity or account.generation!=generation:raise PersistenceError('The account changed. Sign in again.')
    account.gateway.request('POST','/rest/v1/rpc/delete_own_account',token=tokens['access_token'],body={'confirmation':confirmation})
    # Remove only this account’s local exclusion cache after confirmed remote deletion.
    from pathlib import Path
    from uuid import UUID
    path=Path.home()/'Library/Application Support/Amillum/accounts'/str(UUID(identity))/'privacy.json'
    account.invalidate()
    try:path.unlink(missing_ok=True)
    except OSError:raise PersistenceError('Account deleted, but the local exclusion cache could not be removed. Remove it in Application Support/Amillum/accounts.') from None
