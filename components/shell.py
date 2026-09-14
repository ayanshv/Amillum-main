"""Shared desktop chrome. Navigation stays separate from document actions."""
from contextlib import contextmanager
from nicegui import ui
from components.mascot import mascot
from core.workspace import workspace
from core.context_awareness import get_state


@contextmanager
def shell(active):
    ui.colors(primary='#203d60', secondary='#64748b', accent='#203d60')
    with ui.element('div').classes('studio'):
        with ui.element('aside').classes('studio-rail'):
            with ui.link(target='/').classes('studio-brand').props('aria-label="Amillum workspace"'):
                mascot('idle',size=30)
                ui.label('Amillum').classes('studio-wordmark')
            with ui.element('nav').classes('studio-nav').props('aria-label="Main navigation"'):
                for title, icon, path, key in [('Workspace', 'window', '/', 'home'),
                    ('Documents', 'description', '/analyze', 'analysis'),
                    ('Workbench', 'checklist', '/workbench', 'workbench'),
                    ('Selection review', 'crop_free', '/context', 'context')]:
                    with ui.link(target=path).classes('studio-nav-item' + (' is-active' if active == key else '')).props(f'aria-label="{title}" ' + ('aria-current="page"' if active == key else '')):
                        ui.icon(icon, size='18px')
                        ui.label(title)
            with ui.column().classes('rail-bottom'):
                from components.plan_status import plan_status
                plan_status()
                @ui.refreshable
                def companion():
                    privacy=get_state().snapshot()
                    document=workspace.snapshot()
                    state=('sleep' if privacy['paused'] else 'found' if privacy['suggestion'] else
                           {'extracting':'reading','analyzing':'thinking','ready':'happy','error':'confused'}.get(document['status'],'blink'))
                    with ui.column().classes('rail-companion'):
                        mascot(state,size=54)
                        ui.label('Resting here' if privacy['paused'] else 'A passage to review' if privacy['suggestion'] else 'Here when you need me').classes('fine-print')
                    return state
                companion()
                previous=[None]
                def update_companion():
                    privacy=get_state().snapshot(); document=workspace.snapshot()
                    key=(privacy['paused'],bool(privacy['suggestion']),document['status'])
                    if key != previous[0]:
                        previous[0]=key; companion.refresh()
                ui.timer(.75,update_companion)
                with ui.row().classes('rail-shortcut'):
                    ui.icon('crop_free', size='15px')
                    ui.label('Select a region')
                    ui.label('⌘⇧A').classes('shortcut-keys')
                with ui.link(target='/settings').classes('studio-nav-item' + (' is-active' if active == 'settings' else '')).props('aria-label="Settings"'):
                    ui.icon('tune', size='18px')
                    ui.label('Settings')
        with ui.element('div').classes('studio-body'):
            with ui.element('header').classes('studio-topbar'):
                ui.label({'account':'Account', 'home':'Workspace', 'analysis':'Documents', 'settings':'Settings', 'info':'Help', 'context':'Selection review', 'workbench':'Workbench'}[active])
                with ui.row().classes('toolbar-actions'):
                    ui.link('Account', '/account').classes('toolbar-help')
                    ui.link('Help', '/info').classes('toolbar-help')
                    with ui.link(target='/settings').classes('toolbar-help').props('aria-label=Settings'):
                        ui.icon('tune',size='17px')
            yield
