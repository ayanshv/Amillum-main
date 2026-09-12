"""The desktop's working surface: current document, result, and explicit actions."""
from nicegui import ui, run
from components.mascot import mascot
from components.shell import shell
from components.primitives import page_heading, empty_state, primary_button
from core.workspace import workspace
from core.context_awareness import get_state
from backend.analyze import analyze_document


@ui.page('/')
@ui.page('/home')
def home():
    previous = [None]

    async def ask():
        if not workspace.snapshot()['can_ask']:
            workspace.draft(question=question.value or '')
            ui.navigate.to('/analyze')
            return
        try:
            revision, text, language = workspace.ask(question.value or '')
        except ValueError as exc:
            ui.notify(str(exc), type='warning')
            return
        refresh()
        try:
            result = await run.io_bound(analyze_document, text, question.value, language)
            workspace.finish(revision, result=result or '', error='' if result else 'No explanation was returned. Please try again.')
        except Exception:
            workspace.finish(revision, error='The analysis service is unavailable. You can retry your question or open Documents.')

    def clear():
        workspace.clear()
        question.value = ''
        refresh()

    with shell('home'):
        with ui.element('main').classes('workspace-content'):
            with ui.row().classes('workspace-heading'):
                page_heading('Your workspace', 'One document. A clearer picture.')
                open_button = ui.button('Document options', icon='description', on_click=lambda: ui.navigate.to('/analyze')).props('flat')
            with ui.element('section').classes('workspace-document'):
                with ui.row().classes('document-toolbar') as toolbar:
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('description', size='18px')
                        filename = ui.label().classes('document-name')
                    status_badge = ui.label().classes('workspace-status').props('role="status"')
                @ui.refreshable
                def document():
                    snapshot = workspace.snapshot()
                    status = snapshot['status']
                    if status == 'empty':
                        with empty_state('description', 'Make room for understanding.',
                                'Open a document or review a selected passage. Amillum will help you make sense of it.'):
                            primary_button('Open a document', lambda: ui.navigate.to('/analyze'), 'add')
                            ui.link('Review a selection', '/context').classes('text-link')
                            ui.label('PDF or image · Up to 20 MB').classes('fine-print')
                    elif status in ('extracting', 'analyzing'):
                        with ui.column().classes('processing-surface'):
                            mascot('reading' if status == 'extracting' else 'analyzing',size=88)
                            ui.label('Reading your document…' if status == 'extracting' else 'Finding a little clarity…').classes('card-heading')
                            ui.label('You can keep working while Amillum prepares your explanation.').classes('body-copy')
                            ui.button('Clear current document', on_click=clear).props('flat')
                            ui.label('A request already sent may finish; its result will be discarded.').classes('fine-print')
                    elif status == 'error':
                        with empty_state('info_outline', 'Let’s try that again.', snapshot['error']):
                            ui.button('Open Documents', on_click=lambda: ui.navigate.to('/analyze')).props('outline')
                            ui.button('Clear document', on_click=clear).props('flat')
                    else:
                        with ui.column().classes('workspace-result'):
                            mascot('success',size=48,once=True)
                            with ui.row().classes('reading-heading'):
                                ui.label('Understanding your document').classes('section-label')
                                ui.label(snapshot['language']).classes('fine-print')
                            if snapshot['question']:
                                ui.label(snapshot['question']).classes('workspace-question')
                            ui.markdown(snapshot['result']).classes('amicus-markdown w-full')
                            ui.label('Informational guidance. Verify important details with a qualified professional.').classes('fine-print')
                            ui.button('Clear current document', on_click=clear).props('flat dense')
                document()
            @ui.refreshable
            def selected_passage():
                selection=get_state().context.snapshot()
                if selection['status'] not in ('preview','result','error'):
                    return
                with ui.element('section').classes('selection-summary'):
                    with ui.row().classes('reading-heading'):
                        ui.label('Your selected passage').classes('card-heading')
                        ui.link('Open selection →','/context').classes('text-link')
                    result=selection.get('structured')
                    if result and selection['status']=='result':
                        ui.label(result['summary']).classes('body-copy')
                        ui.label('Review priority · '+result['attention']).classes('workspace-status')
                        with ui.expansion('Questions & next steps').classes('w-full'):
                            for heading,key in [('Questions','questions'),('Next steps','next_steps')]:
                                ui.label(heading).classes('section-label')
                                for item in result[key]:ui.label('• '+item).classes('body-copy')
                    else:
                        ui.label('Ready for your review. Nothing has been shared.' if selection['status']=='preview' else selection['message']).classes('body-copy')
            selected_passage()
            with ui.element('section').classes('assistant-composer') as composer:
                with ui.row().classes('assistant-heading'):
                    mascot('curious',size=38)
                    ui.label('A question on your mind?').classes('assistant-section-title')
                question = ui.textarea(placeholder='Ask about this document…', value=workspace.snapshot()['draft_question'],
                    on_change=lambda e: workspace.draft(question=e.value)).props('outlined autogrow aria-label="Question about your document"').classes('w-full workspace-question-input')
                with ui.row().classes('composer-footer'):
                    question_note = ui.label().classes('fine-print')
                    ask_button = primary_button('Ask Amillum', ask, 'arrow_upward')
            with ui.row().classes('workspace-footer'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('lock_outline', size='14px')
                    ui.label('Current session only').classes('fine-print')
                ui.link('Privacy & permissions', '/settings').classes('text-link')

    def refresh():
        snapshot = workspace.snapshot()
        selection=get_state().context.snapshot()
        key = (snapshot['revision'], snapshot['status'],selection['revision'],selection['status'])
        if previous[0] != key:
            previous[0] = key
            document.refresh()
            selected_passage.refresh()
            filename.set_text(snapshot['filename'] or 'Current document')
            status_badge.set_text({'empty':'No document', 'extracting':'Reading', 'analyzing':'Analyzing', 'ready':'Ready', 'error':'Needs attention'}[snapshot['status']])
        busy = snapshot['status'] in ('extracting', 'analyzing')
        ask_button.set_enabled(not busy)
        ask_button.set_text('Analyzing…' if busy else ('Ask Amillum' if snapshot['can_ask'] else 'Choose document'))
        question_note.set_text('Sends your current document text and question to Gemini for analysis.' if snapshot['can_ask'] or busy else 'Prepare your question here, then choose a document and language.')
        composer.set_visibility(snapshot['can_ask'] or busy)
        toolbar.set_visibility(snapshot['status'] != 'empty')
        open_button.set_visibility(snapshot['status'] != 'empty')

    refresh()
    ui.timer(.5, refresh)
