from services.auth import protected, current, checked_operation
"""User-owned persisted legal notes, obligations, questions and next steps."""
from nicegui import ui, run
from components.shell import shell
from components.primitives import page_heading, empty_state
from components.workbench import item_editor, sign_in_form
from services.supabase import get_account, PersistenceError
from services.workbench import Workbench, TYPES, STATUSES


@ui.page('/workbench')
@protected
def workbench_page():
    client = ui.context.client
    account = get_account()
    service = Workbench(account)
    rows, offset = [], [0]
    busy, version = [False], [0]
    successful_offset = [0]
    loaded_generation = [account.snapshot()['generation']]

    def signed_in():
        rows.clear(); offset[0] = 0
        loaded_generation[0] = account.snapshot()['generation']
        content.refresh()
        with client:
            ui.timer(.01, reload, once=True)

    async def sign_out():
        rows.clear(); version[0] += 1
        await run.io_bound(account.sign_out)
        content.refresh()

    async def reload(reset=False):
        if busy[0]: return
        if reset: offset[0] = 0
        busy[0] = True
        request_version = version[0] = version[0] + 1
        generation = account.snapshot()['generation']
        reload_button.disable()
        type_filter.disable(); status_filter.disable()
        message.set_text('Loading your Workbench…'); message.set_visibility(True)
        try:
            result = await run.io_bound(service.list, type_filter.value or None, status_filter.value or None, offset[0])
            if request_version != version[0] or generation != account.snapshot()['generation']: return
            rows[:] = result
            successful_offset[0] = offset[0]
            message.set_visibility(False)
            listing.refresh()
            next_button.set_enabled(len(rows) == 50)
            previous_button.set_enabled(offset[0] > 0)
            page_label.set_text(f'Page {offset[0]//50+1}')
        except PersistenceError as exc:
            offset[0] = successful_offset[0]
            message.set_text(str(exc)); message.set_visibility(True)
        finally:
            busy[0] = False
            reload_button.enable()
            type_filter.enable(); status_filter.enable()

    async def change_status(item, status):
        try:
            await run.io_bound(service.set_status, item['id'], status)
            await reload()
        except PersistenceError as exc:
            ui.notify(str(exc), type='warning', timeout=0, close_button='Dismiss')

    def delete(item):
        with ui.dialog().props('persistent') as dialog, ui.card().classes('workbench-editor'):
            ui.label('Delete this Workbench item?').classes('card-heading')
            ui.label(item['title']).classes('body-copy')
            ui.label('This permanently removes the saved item. The source document is not changed.').classes('fine-print')
            error = ui.label().props('role=alert').classes('am-error'); error.set_visibility(False)
            async def confirm():
                confirm_button.disable()
                try:
                    await run.io_bound(service.delete, item['id'])
                    dialog.close(); await reload()
                except PersistenceError as exc:
                    error.set_text(str(exc)); error.set_visibility(True)
                finally: confirm_button.enable()
            with ui.row():
                confirm_button = ui.button('Delete item', on_click=confirm).props('outline')
                ui.button('Keep item', on_click=dialog.close).props('flat')
        dialog.on('hide',dialog.delete)
        dialog.open()

    def open_item(item):
        item_editor(account, initial=item, existing=item, on_saved=reload)

    with shell('workbench'):
        with ui.element('main').classes('studio-content workbench-content'):
            page_heading('Your legal workbench', 'What to do, remember, and figure out.')
            @ui.refreshable
            def content():
                nonlocal type_filter, status_filter, message, reload_button, listing, next_button, previous_button, page_label
                if not account.gateway.configured:
                    with empty_state('info_outline', 'Connect your Workbench.', 'Supabase setup is required before you can sign in and save items. Your existing document and selection tools remain available.'):
                        ui.label('Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY, then apply the Workbench migration.').classes('fine-print')
                    return
                if not account.snapshot()['user_id']:
                    with ui.column().classes('workbench-signin'):
                        sign_in_form(account, signed_in)
                    return
                with ui.row().classes('reading-heading'):
                    ui.label(account.snapshot()['email']).classes('fine-print')
                    ui.button('Sign out', on_click=sign_out).props('flat')
                with ui.row().classes('workbench-tools'):
                    type_filter = ui.select({'': 'All types', **{v: v.title() for v in TYPES}}, value='', label='Type').props('outlined dense')
                    status_filter = ui.select({'': 'All statuses', **{v: v.title() for v in STATUSES}}, value='open', label='Status').props('outlined dense')
                    reload_button = ui.button('Refresh', on_click=lambda: reload(True)).props('flat')
                    ui.button('Add item', icon='add', on_click=lambda: item_editor(account, on_saved=reload)).classes('primary-button')
                type_filter.on_value_change(lambda: reload(True))
                status_filter.on_value_change(lambda: reload(True))
                message = ui.label().classes('workbench-message').props('role=status aria-live=polite')
                message.set_visibility(False)
                @ui.refreshable
                def listing():
                    if not rows:
                        with empty_state('description', 'Room for what matters.', 'Add a task, question, or note—or save a finding from an explanation.'):
                            ui.label('Only information you choose to save appears here.').classes('fine-print')
                        return
                    for item in rows:
                        with ui.element('section').classes('workbench-row'):
                            with ui.column().classes('workbench-row-body'):
                                ui.button(item['title'], on_click=lambda item=item: open_item(item)).props('flat no-caps align=left').classes('workbench-item-title')
                                with ui.row().classes('context-metadata'):
                                    ui.label(item['type'].title()).classes('workspace-status')
                                    ui.label(item['status'].title()).classes('fine-print')
                                    if item.get('due_date'): ui.label('Due '+item['due_date']).classes('workbench-due')
                                source = item.get('workbench_sources')
                                if source: ui.label('Source · '+source['title']).classes('workbench-source')
                            with ui.row().classes('workbench-row-actions'):
                                if item['status']=='open':
                                    ui.button('Complete', on_click=lambda item=item: change_status(item,'completed')).props('flat dense')
                                    ui.button('Dismiss', on_click=lambda item=item: change_status(item,'dismissed')).props('flat dense')
                                else:
                                    ui.button('Reopen', on_click=lambda item=item: change_status(item,'open')).props('flat dense')
                                ui.button('Delete', on_click=lambda item=item: delete(item)).props('flat dense')
                listing()
                async def page(delta):
                    if busy[0]: return
                    offset[0] = max(0,offset[0]+delta)
                    await reload()
                with ui.row().classes('reading-heading'):
                    previous_button = ui.button('Previous', on_click=lambda: page(-50)).props('flat'); previous_button.disable()
                    page_label = ui.label('Page 1').classes('fine-print')
                    next_button = ui.button('Next', on_click=lambda: page(50)).props('flat'); next_button.disable()
                ui.label('Your selected information—not verified legal advice. Stored in your account; never sent to AI by this view.').classes('fine-print')
            type_filter = status_filter = message = reload_button = listing = next_button = previous_button = page_label = None
            content()
    if account.snapshot()['user_id'] and account.gateway.configured:
        ui.timer(.01, reload, once=True)

    def account_changed():
        generation = account.snapshot()['generation']
        if generation != loaded_generation[0]:
            loaded_generation[0] = generation
            rows.clear(); version[0] += 1; content.refresh()
    ui.timer(1, account_changed)
