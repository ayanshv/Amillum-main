"""Small, shared presentation primitives for the desktop surfaces."""
from nicegui import ui
from components.mascot import mascot


def page_heading(title, subtitle):
    with ui.column().classes('page-intro'):
        heading = ui.label(title).classes('page-heading')
        description = ui.label(subtitle).classes('body-copy')
    return heading, description


def empty_state(icon, title, description):
    with ui.column().classes('empty-state') as surface:
        mascot('confused' if icon == 'info_outline' else ('asking' if icon == 'crop_free' else 'idle'), size=88)
        ui.label(title).classes('card-heading')
        ui.label(description).classes('body-copy')
    return surface


def primary_button(label, on_click, icon=None):
    return ui.button(label, icon=icon, on_click=on_click).props('unelevated no-caps').classes('primary-button')
