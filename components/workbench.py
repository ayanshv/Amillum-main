"""Shared, explicit save editor for manual entries and existing analysis results."""
from uuid import uuid4
from nicegui import ui, run
from services.supabase import PersistenceError
from services.workbench import Workbench, TYPES, STATUSES


def sign_in_form(account, on_success):
    with ui.column().classes('w-full gap-3'):
        ui.label('Sign in to your Workbench').classes('card-heading')
        ui.label('Use your confirmed Supabase account. Your password is not saved. Session restoration uses macOS Keychain.').classes('fine-print')
        email = ui.input('Email').props('outlined type=email autocomplete=username').classes('w-full')
        password = ui.input('Password', password=True, password_toggle_button=True).props('outlined autocomplete=current-password').classes('w-full')
        message = ui.label().classes('am-error w-full').props('role=alert')
        message.set_visibility(False)

        async def sign_in():
            button.disable()
            try:
                await run.io_bound(account.sign_in, email.value or '', password.value or '')
                password.value = ''
                message.set_visibility(False)
                on_success()
            except PersistenceError as exc:
                message.set_text(str(exc)); message.set_visibility(True)
            finally:
                password.value = ''
                button.enable()
        button = ui.button('Sign in', on_click=sign_in).classes('primary-button')
        password.on('keydown.enter', sign_in)


def item_editor(account, *, initial=None, source=None, existing=None, on_saved=None):
    initial = initial or {}
    draft_id = existing['id'] if existing else str(uuid4())
    identity = account.snapshot()['user_id']
    def did_sign_in():
        nonlocal identity
        identity = account.snapshot()['user_id']
        auth_area.set_visibility(False)
    source_id = (source or {}).get('id') or initial.get('document_id')
    with ui.dialog().props('persistent') as dialog, ui.card().classes('workbench-editor'):
        ui.label('Edit item' if existing else 'Add to Workbench').classes('card-heading')
        ui.label('Save only what you want to keep. These are your working notes, not verified legal advice.').classes('fine-print')
        kind = ui.select(list(TYPES), value=initial.get('type', 'note'), label='Type').props('outlined').classes('w-full')
        title = ui.input('Title', value=initial.get('title', '')).props('outlined maxlength=200').classes('w-full')
        description = ui.textarea('Details', value=initial.get('description', '')).props('outlined autogrow maxlength=4000').classes('w-full')
        status = ui.select(list(STATUSES), value=initial.get('status', 'open'), label='Status').props('outlined').classes('w-full')
        due = ui.input('Due date (optional)', value=initial.get('due_date') or '').props('outlined type=date').classes('w-full')
        confirmed = ui.checkbox('I have checked and confirm this exact date.', value=bool(initial.get('due_date') and initial.get('date_confirmed')))
        due.on_value_change(lambda: confirmed.set_value(False))
        ui.label('No date is inferred from “30 days”, “next month”, or other ambiguous wording.').classes('fine-print')
        source_title = (source or {}).get('title') or (initial.get('workbench_sources') or {}).get('title')
        if source_title:
            ui.label('Source · ' + source_title).classes('workbench-source')
            ui.label('Only this source title/reference is saved. Reopen the original document to inspect it.').classes('fine-print')
        excerpt = ui.textarea('Source excerpt (optional)', value=initial.get('source_context', '')).props('outlined maxlength=500').classes('w-full')
        error = ui.label().classes('am-error w-full').props('role=alert')
        error.set_visibility(False)
        with ui.column().classes('w-full') as auth_area:
            if not identity:
                sign_in_form(account, did_sign_in)

        async def save():
            if identity and account.snapshot()['user_id'] != identity:
                error.set_text('The account changed. Close this editor and reopen it in your Workbench.'); error.set_visibility(True)
                return
            values = {'type': kind.value, 'title': title.value or '', 'description': description.value or '',
                      'status': status.value, 'due_date': due.value or None, 'date_confirmed': confirmed.value,
                      'source_context': excerpt.value or '', 'document_id': source_id}
            save_button.disable(); cancel_button.disable()
            try:
                service = Workbench(account)
                if existing:
                    await run.io_bound(service.update, draft_id, values)
                else:
                    await run.io_bound(service.save, values, item_id=draft_id, source=source)
                dialog.close()
                ui.notify('Saved to your Workbench.', type='positive')
                if on_saved:
                    await on_saved()
            except PersistenceError as exc:
                error.set_text(str(exc)); error.set_visibility(True)
            finally:
                save_button.enable(); cancel_button.enable()
        ui.label('Save sends these fields and the source reference to your Supabase Workbench. No AI request is made.').classes('fine-print')
        with ui.row().classes('gap-3'):
            save_button = ui.button('Save item', on_click=save).classes('primary-button')
            cancel_button = ui.button('Cancel', on_click=dialog.close).props('flat')
    def check_account():
        if identity and account.snapshot()['user_id'] != identity:
            dialog.close()
    with dialog:
        ui.timer(.5,check_account)
    dialog.on('hide',dialog.delete)
    dialog.open()
    return dialog


def analysis_save_button(account, *, source, structured=None):
    """Selection is explicit; the date always starts blank, even for AI suggestions."""
    def choose():
        if not structured:
            item_editor(account, source=source, initial={'document_id': source['id']})
            return
        with ui.dialog() as dialog, ui.card().classes('workbench-editor'):
            ui.label('What would you like to keep?').classes('card-heading')
            ui.label('Choose one finding, then review and edit it before saving.').classes('body-copy')
            for heading, key, kind in [('Attention items', 'reasons', 'attention'), ('Questions', 'questions', 'question'), ('Next steps', 'next_steps', 'task')]:
                ui.label(heading).classes('section-label')
                for text in structured.get(key, []):
                    with ui.row().classes('workbench-candidate'):
                        ui.label(text).classes('body-copy')
                        def pick(text=text, kind=kind):
                            dialog.close()
                            item_editor(account, source=source, initial={'type': kind, 'title': text[:200],
                                        'description': text if len(text)>200 else '', 'document_id': source['id']})
                        ui.button('Choose', on_click=pick).props('flat')
            ui.button('Write my own item', on_click=lambda: (dialog.close(), item_editor(account, source=source, initial={'document_id':source['id']}))).props('outline')
            ui.button('Cancel', on_click=dialog.close).props('flat')
        dialog.on('hide',dialog.delete)
        dialog.open()
    return ui.button('Add to Workbench', on_click=choose).props('outline')
