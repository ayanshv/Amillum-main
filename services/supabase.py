"""Central Supabase gateway; refresh credentials are protected by macOS Keychain."""
import base64
import json
import os
import threading
import time
from urllib.parse import urlsplit
import httpx


class PersistenceError(ValueError):
    pass


class SessionExpired(PersistenceError):
    pass


class Supabase:
    def __init__(self, url=None, key=None, transport=None):
        self.url = (url if url is not None else os.getenv('SUPABASE_URL', '')).rstrip('/')
        self.key = key if key is not None else os.getenv('SUPABASE_PUBLISHABLE_KEY', os.getenv('SUPABASE_ANON_KEY', ''))
        self.http = httpx.Client(timeout=12, follow_redirects=False, transport=transport)

    @property
    def configured(self):
        parsed = urlsplit(self.url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment or parsed.path:
            return False
        if self.key.startswith('sb_publishable_'):
            return True
        try:
            payload = self.key.split('.')[1]
            return json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4))).get('role') == 'anon'
        except (ValueError, IndexError, TypeError):
            return False

    def request(self, method, path, *, token=None, body=None, params=None):
        if not self.configured:
            raise PersistenceError('Workbench is not connected yet. Configure the Supabase project URL and publishable key, then apply the Workbench migration.')
        headers = {'apikey': self.key, 'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if path.startswith('/rest/'):
            headers['Prefer'] = 'return=representation'
        try:
            response = self.http.request(method, self.url + path, headers=headers, json=body, params=params)
        except httpx.HTTPError:
            raise PersistenceError('Workbench couldn’t reach the server. Your draft is still here. Check your connection and retry.') from None
        if response.status_code == 401 or (path.endswith('/token') and response.status_code == 400):
            raise SessionExpired('Your session or sign-in is invalid. Please sign in again.')
        if response.status_code == 403:
            raise PersistenceError('Your session expired or this item is unavailable to your account. Sign in again and retry.')
        if not 200 <= response.status_code < 300:
            if path.startswith('/auth/'):
                raise PersistenceError('Sign-in could not complete. Check your email and password, including email confirmation, and try again.')
            if response.status_code == 404:
                raise PersistenceError('Workbench is not ready on this server. Apply the Workbench database migration and retry.')
            raise PersistenceError('The change could not be confirmed. Your draft is still here; retry safely or refresh the list.')
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise PersistenceError('The server returned an unreadable response. Your draft is still here; try again.') from None


class Account:
    """Access tokens stay in memory; refresh tokens are stored in Keychain."""
    def __init__(self, gateway, store=None, cookie_id=None):
        self.gateway = gateway
        self.store = store
        self.cookie_id = cookie_id
        self.restored = False
        self.recovery = False
        self.created_at = None
        self.lock = threading.RLock()
        self.refresh_lock = threading.Lock()
        self.generation = 0
        self.user_id = None
        self.email = ''
        self._access = self._refresh = ''
        self._expires = 0

    def snapshot(self):
        with self.lock:
            return {'user_id': self.user_id, 'email': self.email, 'generation': self.generation, 'created_at': self.created_at, 'recovery': self.recovery}

    def sign_in(self, email, password):
        if not email.strip() or not password:
            raise PersistenceError('Enter your email and password to sign in.')
        generation = self.generation
        tokens = self.gateway.request('POST', '/auth/v1/token', params={'grant_type': 'password'},
                                      body={'email': email.strip(), 'password': password})
        # The Auth server verifies the token; no client-supplied user ID is trusted.
        user = self.gateway.request('GET', '/auth/v1/user', token=tokens['access_token'])
        with self.lock:
            if generation != self.generation:
                raise PersistenceError('The account changed. Please sign in again.')
            self._set_tokens(tokens)
            self.user_id, self.email = user['id'], user.get('email', '')
            self.created_at = user.get('created_at')
            self.recovery = False
            self.generation += 1
        activate_account(self)

    def _set_tokens(self, tokens):
        if self.store:
            try:
                self.store.write('session', {'refresh_token': tokens['refresh_token'], 'cookie_id': self.cookie_id})
            except RuntimeError as exc:
                raise PersistenceError(str(exc)) from None

        self._access, self._refresh = tokens['access_token'], tokens['refresh_token']
        self._expires = time.monotonic() + float(tokens.get('expires_in', 3600))

    def sign_out(self):
        if self.store:
            try:
                record=self.store.read('session')
                if record and record.get('cookie_id')==self.cookie_id:self.store.delete('session')
            except RuntimeError as exc:raise PersistenceError(str(exc)) from None
        with self.lock:
            token = self._access
            self.user_id = None
            self.email = self._access = self._refresh = ''
            self.generation += 1
        if active_account() is self:clear_application_state()
        if token:
            try:
                self.gateway.request('POST', '/auth/v1/logout', token=token, params={'scope': 'local'})
            except PersistenceError:
                pass  # Local credentials are already cleared, including when offline.

    def _authenticated(self, method, path, **kwargs):
        with self.refresh_lock:
            with self.lock:
                generation, identity = self.generation, self.user_id
                refresh, access, expires = self._refresh, self._access, self._expires
            if not identity:
                raise PersistenceError('Sign in to save and view your Workbench.')
            if time.monotonic() >= expires - 60:
                tokens = self.gateway.request('POST', '/auth/v1/token', params={'grant_type': 'refresh_token'}, body={'refresh_token': refresh})
                user = self.gateway.request('GET', '/auth/v1/user', token=tokens['access_token'])
                with self.lock:
                    if generation != self.generation or user['id'] != identity:
                        raise PersistenceError('The account changed. Sign in again before continuing.')
                    self._set_tokens(tokens)
                    access = self._access
        result = self.gateway.request(method, path, token=access, **kwargs)
        with self.lock:
            if generation != self.generation:
                raise PersistenceError('The account changed. Refresh your Workbench before continuing.')
        return result

    def authenticated(self, method, path, **kwargs):
        generation=self.generation
        try:
            return self._authenticated(method, path, **kwargs)
        except SessionExpired:
            if generation == self.generation:self.invalidate()
            raise

    def backend_operation(self,operation):
        """Use the centralized, refreshed session without exposing tokens to UI code."""
        self.authenticated('GET','/auth/v1/user')
        with self.lock:
            generation=self.generation
            token=self._access
        try:result=operation(token)
        except SessionExpired:
            if generation==self.generation:self.invalidate()
            raise
        with self.lock:
            if generation!=self.generation:raise PersistenceError('The account changed. The response was discarded.')
        return result

    def invalidate(self):
        with self.lock:
            self.user_id = None
            self.email = self._access = self._refresh = ''
            self.generation += 1
        if active_account() is self:clear_application_state()
        if self.store:
            try:
                record=self.store.read('session')
                if record and record.get('cookie_id')==self.cookie_id:self.store.delete('session')
            except RuntimeError:pass

    def restore(self):
        if self.restored:return bool(self.user_id)
        if not self.store:
            self.restored=True
            return False
        generation=self.generation
        try:
            record=self.store.read('session')
        except (RuntimeError,ValueError):
            raise PersistenceError('Unlock your Mac to restore your session, or sign in again.') from None
        if not record or record.get('cookie_id') != self.cookie_id:
            self.restored=True
            return False
        try:
            tokens=self.gateway.request('POST','/auth/v1/token',params={'grant_type':'refresh_token'},body={'refresh_token':record['refresh_token']})
            user=self.gateway.request('GET','/auth/v1/user',token=tokens['access_token'])
            with self.lock:
                if generation != self.generation:raise PersistenceError('The account changed. Sign in again.')
                self._set_tokens(tokens)
                self.user_id,self.email=user['id'],user.get('email','')
                self.created_at=user.get('created_at')
                self.generation+=1
                self.restored=True
            activate_account(self)
            return True
        except SessionExpired:
            self.invalidate();self.restored=True
            return False

    def sign_up(self,email,password):
        if not email.strip() or len(password)<12:
            raise PersistenceError('Enter your email and a password of at least 12 characters.')
        self.gateway.request('POST','/auth/v1/signup',body={'email':email.strip(),'password':password})
        # Email confirmation never bypasses normal login and verified identity.

    def request_recovery(self,email):
        if not email.strip():raise PersistenceError('Enter your account email.')
        self.gateway.request('POST','/auth/v1/recover',body={'email':email.strip()})

    def recover(self,email,code,password):
        if len(password)<12 or not code.strip():
            raise PersistenceError('Enter the recovery code and a new password of at least 12 characters.')
        tokens=self.gateway.request('POST','/auth/v1/verify',body={'email':email.strip(),'token':code.strip(),'type':'recovery'})
        # Recovery credentials only authorize the password update, not workspace access.
        self.gateway.request('PUT','/auth/v1/user',token=tokens['access_token'],body={'password':password})
        self.gateway.request('POST','/auth/v1/logout',token=tokens['access_token'],params={'scope':'global'})
        self.invalidate()

    def change_password(self,current,new):
        if len(new)<12:raise PersistenceError('Use at least 12 characters for your new password.')
        user_id=self.user_id
        tokens=self.gateway.request('POST','/auth/v1/token',params={'grant_type':'password'},body={'email':self.email,'password':current})
        user=self.gateway.request('GET','/auth/v1/user',token=tokens['access_token'])
        if user['id'] != user_id:raise PersistenceError('The account changed. Sign in again.')
        self.gateway.request('PUT','/auth/v1/user',token=tokens['access_token'],body={'password':new})
        self.gateway.request('POST','/auth/v1/logout',token=tokens['access_token'],params={'scope':'global'})
        self.sign_out()


_gateway = None
_accounts = {}
_registry_lock = threading.Lock()
_active_account = None
_activation_lock = threading.RLock()

def clear_application_state():
    from core.workspace import workspace
    from core.context_awareness import get_state
    workspace.clear()
    workspace.draft_language = None
    get_state().update(enabled=False,paused=True,accessibility_enabled=False,smart_enabled=False,clear=True)

def activate_account(account):
    with _activation_lock:
        global _active_account
        previous=_active_account
        if previous is not account:
            if previous:
                with previous.lock:
                    previous.user_id=None
                    previous._access=previous._refresh=''
                    previous.generation+=1
            clear_application_state()
            from pathlib import Path
            from uuid import UUID
            from core.privacy import PrivacyPreferences
            from core.context_awareness import get_state
            preferences=PrivacyPreferences(Path.home()/'Library/Application Support/Amillum/accounts'/str(UUID(account.user_id))/'privacy.json')
            get_state().preferences=preferences
            _active_account=account

def active_account():
    return _active_account

def session_store():
    import sys
    if sys.platform != 'darwin':return None
    from native.macos.session_store import SessionStore
    import hashlib
    return SessionStore('com.amillum.session.'+hashlib.sha256(os.getenv('SUPABASE_URL','').encode()).hexdigest()[:16])

def storage_secret():
    import secrets
    store=session_store()
    if store is None:return secrets.token_urlsafe(32)
    value=store.read('cookie_secret')
    if not value:
        value=secrets.token_urlsafe(32);store.write('cookie_secret',value)
    return value


def get_account():
    """Call during page construction, before the signed cookie is sent."""
    global _gateway
    from nicegui import app
    import secrets
    cookie = app.storage.browser
    if 'amillum_account' not in cookie:
        cookie['amillum_account'] = secrets.token_urlsafe(32)
    with _registry_lock:
        if _gateway is None:
            _gateway = Supabase()
        return _accounts.setdefault(cookie['amillum_account'], Account(_gateway,session_store(),cookie['amillum_account']))
