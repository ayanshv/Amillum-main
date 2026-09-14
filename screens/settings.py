from services.auth import protected, current, checked_operation
"""Privacy controls for the current stage; no placeholder capability switches."""

from nicegui import ui
from components.mascot import mascot
from components.shell import shell
from components.primitives import page_heading
from core.context_awareness import get_state


@ui.page('/settings')
@protected
def settings():
    from services.supabase import get_account
    account=get_account()
    state = get_state()
    def change(**kwargs):
        if not current(account):return
        try:
            state.update(**kwargs)
        except ValueError as exc:
            ui.notify(str(exc), type='warning')
        refresh()

    def exclude(identifier, remove=False):
        if not current(account):return
        try:
            state.exclude(identifier.strip(), remove=remove)
            exclusions.refresh()
            identifier_input.value = ''
            refresh()
        except (ValueError, OSError) as exc:
            ui.notify(str(exc), type='warning')

    def exclude_domain(remove=False, value=None):
        if not current(account):return
        try:
            state.exclude_domain(value or domain_input.value or '', remove=remove)
            domain_input.value = ''
            domains.refresh()
        except (ValueError, OSError) as exc:
            ui.notify(str(exc), type='warning')

    with shell('settings'), ui.column().classes('am-privacy studio-content'):
        with ui.column().classes('w-full gap-6').style('max-width:880px'):
            mascot('asking',size=48)
            page_heading('Privacy & access', 'Choose what Amillum can access. You stay in control.')
            with ui.card().classes('w-full p-6 gap-4').classes('privacy-card'):
                awareness = ui.switch('Current-app awareness', value=state.enabled,
                                      on_change=lambda e: change(enabled=e.value)).props('color=primary')
                ui.label('When enabled, Amillum receives only the current application’s name and identifier. No window titles, typed text, selected text, or screenshots. Off at every launch.').style('font-size:14px;color:#667085;line-height:1.6')
                status_label = ui.label().style('font-weight:600')
                app_label = ui.label().style('color:#667085;font-size:13px')
                with ui.row().classes('gap-3'):
                    pause = ui.button('Pause', on_click=lambda: change(paused=not state.paused)).props('outline')
                    ui.button('Clear context', on_click=lambda: change(clear=True)).props('flat')
                ui.label('Clear removes current context until the next app or focus change. No activity history is kept.').style('font-size:12px;color:#71798a')
            with ui.expansion('Excluded applications', icon='block').classes('settings-section'):
                with ui.column().classes('privacy-card w-full'):
                    ui.label('Excluded apps are discarded before their name is processed. Password managers are always excluded.').style('color:#667085;font-size:13px')
                    with ui.row().classes('w-full items-center'):
                        identifier_input = ui.input(placeholder='Application identifier, e.g. com.apple.Safari').props('outlined aria-label="Application identifier"').classes('grow').style('color:#121827')
                        ui.button('Add application', icon='add', on_click=lambda: exclude(identifier_input.value or ''))

                    @ui.refreshable
                    def exclusions():
                        for identifier in state.snapshot()['excluded']:
                            with ui.row().classes('w-full items-center justify-between'):
                                ui.label(identifier).style('font-size:13px')
                                ui.button('Remove', on_click=lambda identifier=identifier: exclude(identifier, remove=True)).props('flat dense')
                        if not state.snapshot()['excluded']:
                            ui.label('No additional exclusions. Built-in password-manager exclusions are active.').style('color:#71798a;font-size:13px')

                    exclusions()
            with ui.expansion('Excluded websites', icon='block').classes('settings-section'):
                with ui.column().classes('privacy-card w-full'):
                    ui.label('Blocks a domain and its subdomains. If a browser cannot expose the page address, region reading is blocked.').classes('body-copy')
                    with ui.row().classes('w-full items-center'):
                        domain_input = ui.input(placeholder='example.com').props('outlined aria-label="Excluded domain"').classes('grow')
                        ui.button('Exclude domain', on_click=lambda: exclude_domain())
                    @ui.refreshable
                    def domains():
                        for domain in state.snapshot()['excluded_domains']:
                            with ui.row().classes('w-full justify-between'):
                                ui.label(domain)
                                ui.button('Remove', on_click=lambda domain=domain: exclude_domain(True, domain)).props('flat')
                    domains()
            with ui.expansion('Content access', icon='shield').classes('settings-section'):
                with ui.column().classes('privacy-card w-full'):
                    metadata_switch = ui.switch('Accessibility metadata', value=state.accessibility_enabled,
                        on_change=lambda e: change(accessibility_enabled=e.value))
                    ui.label('With current-app awareness on, reads only the focused element’s role and bounds. Secure and single-line input fields are blocked. No text is read. Off at each launch.').style('color:#667085;font-size:13px')
                    permission_label = ui.label()
                    ui.button('Set up macOS Accessibility access', on_click=state.request_accessibility_setup).props('outline')
                    metadata_label = ui.label().style('font-size:13px')
                    capture_label = ui.label()
                    ui.button('Set up region capture', on_click=state.request_capture_setup).props('outline')
                    ui.label('Used only after you click Read locally on a selected region and Accessibility text is unavailable. Local OCR reads that region; no recording stream or screenshot upload.').classes('body-copy')
                    ui.switch('Automatic legal detection · local metadata', value=state.smart_enabled,
                        on_change=lambda e: change(smart_enabled=e.value))
                    ui.label('Uses titles and up to 1,200 accessible characters from the active context after privacy checks, locally and transiently. No text is saved, uploaded, or analyzed by AI. Medium confidence shows a quiet beaver; high confidence may offer Take a look or Not now. Repeated dismissals make offers less frequent. Reading for explanation still requires approval. Generic words alone do not trigger it. Off at each launch.').classes('body-copy')
                    suggestion_label = ui.label()
                    ui.label('Ask before reading · Always on').style('font-weight:600')
                    ui.label('Select → Read locally → review text → Explain. Sending to AI always needs a separate click.').classes('body-copy')

    def refresh():
        snapshot = state.snapshot()
        labels = {'off': 'Awareness is off', 'paused': 'Amillum is paused', 'waiting': 'Waiting for the native connection',
                  'active': 'Current application', 'excluded': 'Current application is excluded',
                  'unavailable': 'Application identity unavailable', 'cleared': 'Context cleared',
                  'disconnected': 'Native connection unavailable — context cleared'}
        status_label.set_text(labels.get(snapshot['status'], 'Awareness is off'))
        capture_label.set_text('macOS region capture permission granted' if snapshot['capture_granted'] else 'macOS region capture permission not granted')
        suggestion_label.set_text('Possible context: ' + snapshot['suggestion']['label'] if snapshot['suggestion'] else 'No automatic suggestion right now')
        permission_label.set_text('macOS Accessibility permission granted' if snapshot['accessibility_granted'] else 'macOS Accessibility permission not granted')
        metadata = snapshot['metadata'] or {}
        metadata_label.set_text({'blocked': 'Focused field blocked; no content read.',
            'permission_required': 'Enable macOS Accessibility access to test metadata.',
            'unavailable': 'Focused element metadata unavailable.',
            'metadata': 'Focused element: ' + str(metadata.get('role', ''))}.get(metadata.get('status'), 'No focused-element metadata retained'))
        if metadata_switch.value != snapshot['accessibility_enabled']:
            metadata_switch.value = snapshot['accessibility_enabled']
        current = snapshot['current']
        app_label.set_text(f"{current['name']} · {current['bundle_id']}" if current else 'No application context retained')
        pause.set_text('Resume' if snapshot['paused'] else 'Pause')
        pause.set_enabled(snapshot['enabled'])
        # Assigning identical values does not trigger a change event.
        if awareness.value != snapshot['enabled']:
            awareness.value = snapshot['enabled']

    refresh()
    ui.timer(.5, refresh)
