"""Desktop authentication presentation; all identity operations stay centralized."""
from nicegui import ui, run
from components.mascot import mascot
from services.supabase import get_account, PersistenceError
from services.auth import current


@ui.page('/auth')
def authentication():
    ui.colors(primary='#203d60', secondary='#64748b', accent='#203d60')
    account = get_account()
    state = {'mode': 'Sign in', 'busy': False}
    with ui.element('div').classes('auth-scene'):
        ui.element('div').classes('auth-backdrop').props('aria-hidden=true')
        with ui.element('div').classes('auth-orbits').props('aria-hidden=true'):
            for _ in range(3):
                ui.element('span')
        with ui.column().classes('auth-surface'):
            with ui.element('div').classes('auth-emblem'):
                mascot('idle', 54)
            ui.label('AMILLUM').classes('auth-wordmark')
            heading = ui.label('Welcome back').classes('auth-heading').props('role=heading aria-level=1')
            subtitle = ui.label('A little clarity. A place of your own.').classes('auth-subtitle')
            with ui.row().classes('auth-status').props('role=status aria-live=polite') as status:
                spinner = ui.spinner(size='18px')
                message = ui.label('Restoring your session…')
            with ui.column().classes('auth-form w-full') as form:
                email = ui.input('Email address').props('outlined type=email autocomplete=username').classes('w-full')
                code = ui.input('Recovery code').props('outlined autocomplete=one-time-code').classes('w-full')
                password = ui.input('Password', password=True, password_toggle_button=True).props('outlined autocomplete=current-password').classes('w-full')
                confirm = ui.input('Confirm password', password=True).props('outlined autocomplete=new-password').classes('w-full')
                password_hint = ui.label('Use at least 12 characters.').classes('auth-hint')
                forgot = ui.button('Forgot password?', on_click=lambda: switch_mode('Recover password')).props('flat no-caps type=button').classes('auth-text-button auth-forgot')
                recovery_button = ui.button('Send recovery code', on_click=lambda: send_recovery()).props('outline no-caps type=button').classes('auth-secondary w-full')
                button = ui.button('Sign in', on_click=lambda: submit()).props('unelevated no-caps type=button').classes('auth-submit w-full')
                with ui.row().classes('auth-switch'):
                    switch_label = ui.label('New to Amillum?')
                    switch_button = ui.button('Create an account', on_click=lambda: switch_mode('Create account' if state['mode'] == 'Sign in' else 'Sign in')).props('flat no-caps type=button').classes('auth-text-button')
            retry = ui.button('Try restoring again', on_click=lambda: restore()).props('flat no-caps').classes('auth-text-button')
            retry.set_visibility(False)
            with ui.row().classes('auth-security'):
                ui.icon('lock_outline', size='14px')
                ui.label('Session protected by macOS Keychain')

    controls = [email, code, password, confirm, forgot, recovery_button, button, switch_button, retry]

    def busy(value):
        state['busy'] = value
        for control in controls:
            control.set_enabled(not value)
        spinner.set_visibility(value)

    def feedback(text='', error=False):
        message.set_text(text)
        status.set_visibility(bool(text))
        status.classes('auth-status-error' if error else '', remove='' if error else 'auth-status-error')

    def switch_mode(mode):
        if state['busy']:
            return
        state['mode'] = mode
        recovery = mode == 'Recover password'
        signup = mode == 'Create account'
        heading.set_text('Find your way back' if recovery else 'Make yourself at home' if signup else 'Welcome back')
        subtitle.set_text('We’ll email a code to reset your password.' if recovery else 'Your documents. Your space. Your Amillum.' if signup else 'A little clarity. A place of your own.')
        code.set_visibility(recovery)
        confirm.set_visibility(mode != 'Sign in')
        password_hint.set_visibility(mode != 'Sign in')
        recovery_button.set_visibility(recovery)
        forgot.set_visibility(mode == 'Sign in')
        password.props('autocomplete=current-password' if mode == 'Sign in' else 'autocomplete=new-password')
        password.set_value(''); confirm.set_value(''); code.set_value('')
        button.set_text('Set new password' if recovery else mode)
        switch_label.set_text('New to Amillum?' if mode == 'Sign in' else 'Already have an account?' if signup else 'Remember your password?')
        switch_button.set_text('Create an account' if mode == 'Sign in' else 'Back to sign in')
        feedback()

    async def send_recovery():
        if state['busy']:
            return
        busy(True)
        feedback('Sending your recovery email…')
        try:
            await run.io_bound(account.request_recovery, email.value or '')
            feedback('If this email has an account, a recovery code is on its way. Enter it above with your new password.')
        except PersistenceError as exc:
            feedback(str(exc), error=True)
        finally:
            busy(False)

    async def submit():
        if state['busy']:
            return
        mode = state['mode']
        busy(True)
        feedback('Signing in…' if mode == 'Sign in' else 'Creating your account…' if mode == 'Create account' else 'Updating your password…')
        try:
            if mode == 'Sign in':
                await run.io_bound(account.sign_in, email.value or '', password.value or '')
                ui.navigate.to('/')
            else:
                if password.value != confirm.value:
                    raise PersistenceError('The passwords don’t match.')
                if mode == 'Create account':
                    await run.io_bound(account.sign_up, email.value or '', password.value or '')
                    success = 'Check your email to confirm your account, then sign in.'
                else:
                    await run.io_bound(account.recover, email.value or '', code.value or '', password.value or '')
                    success = 'Password updated. Sign in with your new password.'
                busy(False)
                switch_mode('Sign in')
                feedback(success)
        except PersistenceError as exc:
            feedback(str(exc), error=True)
        finally:
            password.set_value(''); confirm.set_value(''); code.set_value('')
            busy(False)

    async def restore():
        if state['busy']:
            return
        busy(True)
        feedback('Restoring your session…')
        retry.set_visibility(False)
        try:
            if current(account) or await run.io_bound(account.restore):
                ui.navigate.to('/')
                return
            feedback()
        except PersistenceError as exc:
            feedback(str(exc), error=True)
            retry.set_visibility(True)
        finally:
            busy(False)
            form.set_visibility(True)

    for field in (email, password, confirm, code):
        field.on('keydown.enter', submit)
    switch_mode('Sign in')
    form.set_visibility(False)
    ui.timer(.01, restore, once=True)
