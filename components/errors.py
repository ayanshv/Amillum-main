"""Calm recovery surfaces without exposing exception details or document content."""
from nicegui import app, ui, Client
from nicegui.page import page
from starlette.exceptions import HTTPException
from components.shell import shell
from components.primitives import empty_state


def error_page(status=500):
    title = 'This page isn’t here.' if status == 404 else 'Amillum couldn’t complete this request.'
    message = ('The address may have changed. Return to your workspace to continue.' if status == 404 else
               'Please return to your workspace and try again. If this continues, restart Amillum.')
    with shell('info'):
        with ui.element('main').classes('studio-content'):
            with empty_state('info_outline',title,message):
                ui.label(f'Error {status}').classes('fine-print')
                ui.button('Return to workspace',on_click=lambda:ui.navigate.to('/')).classes('primary-button')
                ui.link('Help & permissions','/info').classes('text-link')


async def http_error(request,exception):
    status=getattr(exception,'status_code',500)
    with Client(page(''),request=request) as client:
        error_page(status)
    return client.build_response(request,status)


def interaction_error(exception):
    # Event-handler failures have a client context; background failures may not.
    try:
        if not ui.context.client.has_socket_connection:
            return
        ui.notify('That action couldn’t finish. Please try again, or return to your workspace.',
                  type='warning',timeout=0,close_button='Dismiss',classes='am-notice')
    except RuntimeError:
        pass


def install_errors():
    app.add_exception_handler(404,http_error)
    app.add_exception_handler(HTTPException,http_error)
    app.add_exception_handler(Exception,http_error)
    app.on_exception(interaction_error)
