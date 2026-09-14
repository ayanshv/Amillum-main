"""Minimal account controls, alongside the existing privacy screen."""
from nicegui import ui, run
from components.shell import shell
from services.auth import protected,current
from services.supabase import get_account,PersistenceError
from services.account import profile,save_profile,save_privacy,restore_privacy,delete_account
from core.context_awareness import get_state

@ui.page('/account')
@protected
def account_page():
    account=get_account()
    async def perform(operation,*args):
        if not current(account):return
        try:
            result=await run.io_bound(operation,account,*args)
            ui.notify('Done',type='positive')
            return result
        except (PersistenceError,OSError,ValueError) as exc:ui.notify(str(exc),type='negative')
    async def logout():
        await perform(lambda a:a.sign_out())
        if not current(account):ui.navigate.to('/auth')
    async def password_change():
        if new.value!=confirm.value:
            ui.notify('The new passwords do not match.',type='warning');return
        await perform(lambda a:a.change_password(old.value,new.value))
        old.value=new.value=confirm.value=''
        if not current(account):ui.navigate.to('/auth')
    async def delete():
        await perform(delete_account,delete_password.value,phrase.value)
        delete_password.value=''
        if not current(account):ui.navigate.to('/auth')
    with shell('account'),ui.column().classes('studio-content w-full gap-5').style('max-width:850px'):
        ui.label('Your account').classes('text-h4')
        ui.label(account.email)
        ui.label('Account created: '+str(account.created_at or 'Not available')[:10]).classes('fine-print')
        name=ui.input('Display name').classes('w-full').props('outlined maxlength=120')
        ui.button('Save profile',on_click=lambda:perform(save_profile,name.value or ''))
        ui.button('Log out',on_click=logout).props('outline')
        with ui.expansion('Password & security').classes('w-full'):
            old=ui.input('Current password',password=True,password_toggle_button=True)
            new=ui.input('New password · at least 12 characters',password=True)
            confirm=ui.input('Confirm new password',password=True)
            ui.button('Change password and sign out',on_click=password_change)
            ui.label('Forgot your password? Log out and choose Recover password on the sign-in screen.').classes('fine-print')
        with ui.expansion('Privacy & data').classes('w-full'):
            ui.link('Open existing privacy controls','/settings')
            ui.label('Exclusions are saved locally for your account. You can sync them below. Awareness remains off after login; reading and analysis always need your approval.').classes('body-copy')
            ui.button('Save exclusions to account',on_click=lambda:perform(save_privacy,get_state()))
            ui.button('Restore saved exclusions',on_click=lambda:perform(restore_privacy,get_state())).props('outline')
            ui.button('Clear approved context',on_click=lambda:get_state().update(clear=True) if current(account) else None).props('outline')
        with ui.expansion('Delete account').classes('w-full'):
            ui.label('Permanently removes your account, profile, saved settings and Workbench items. This cannot be undone. If stored files require backend removal, deletion will stop.').classes('body-copy')
            phrase=ui.input('Type DELETE MY ACCOUNT').props('autocomplete=off')
            delete_password=ui.input('Confirm current password',password=True)
            ui.button('Permanently delete my account',on_click=delete).props('outline color=negative')
        async def load():
            try:
                data=await run.io_bound(profile,account)
                if current(account):name.value=data['display_name']
            except PersistenceError as exc:ui.notify(str(exc),type='warning')
        ui.timer(.1,load,once=True)
