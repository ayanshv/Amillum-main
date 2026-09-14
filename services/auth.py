"""Central desktop route and operation guards; no alternate Supabase client."""
from functools import wraps
from nicegui import ui
from services.supabase import get_account, active_account, PersistenceError


def current(account):
    return bool(account.user_id and active_account() is account)


def protected(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        account = get_account()
        if not current(account):
            ui.navigate.to('/auth')
            return
        generation = account.generation
        result = function(*args, **kwargs)
        client = ui.context.client
        def check():
            if not current(account) or account.generation != generation:
                guard.deactivate()
                client.content.clear()
                ui.navigate.to('/auth')
        guard=ui.timer(.5, check)
        return result
    return guarded


def checked_operation(account, operation, *args):
    if not current(account):raise PersistenceError('Sign in before continuing.')
    generation = account.generation
    account.authenticated('GET','/auth/v1/user')
    if not current(account) or generation != account.generation:raise PersistenceError('The session changed.')
    result = operation(*args)
    if not current(account) or generation != account.generation:raise PersistenceError('The session changed. The result was discarded.')
    return result
