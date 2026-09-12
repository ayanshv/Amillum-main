"""Review-only handoff from native selection. AI requires a separate button click."""
from nicegui import ui, run
from components.mascot import mascot
from components.shell import shell
from components.primitives import page_heading, empty_state
from core.context_awareness import get_state
from services.contextual_analysis import analyze_context, format_result
from core.privacy import require_safe_text
from screens.analysis import LANGUAGES


@ui.page('/context')
def context(ask: bool = False):
    state = get_state()
    rendered = [None]

    def discard():
        state.context.clear()
        refresh()

    async def explain(revision, editor, question, language, followup=False):
        user_question=question.value or ''
        chosen_language=language.value
        try:
            require_safe_text(user_question)
            with state.lock:
                if state.paused or state.preferences.load_error:
                    raise ValueError('Amillum is paused or privacy settings are unavailable. Resume in Settings first.')
                if followup:
                    revision,approved=state.context.approve_followup(revision)
                else:
                    revision,approved=state.context.approve_analysis(revision,editor.value)
        except ValueError as exc:
            ui.notify(str(exc),type='warning')
            return
        refresh()
        try:
            result=await run.io_bound(analyze_context,approved,user_question,chosen_language,
                                     lambda: state.analysis_valid(revision))
            state.context.finish_analysis(revision,result=format_result(result),structured=result)
        except Exception as exc:
            message=str(exc) if isinstance(exc,ValueError) else 'The analysis service is unavailable. Your local preview is still here; you can try again.'
            state.context.finish_analysis(revision,error=message)
        refresh()

    with shell('context'):
        with ui.element('main').classes('studio-content context-content'):
            page_heading('Your selection', 'Review locally. Share only what you choose.')

            @ui.refreshable
            def content():
                snapshot = state.context.snapshot()
                status = snapshot['status']
                rendered[0] = (snapshot['revision'], status, snapshot['message'])
                if status == 'empty':
                    with empty_state('crop_free', 'A closer look, on your terms.', 'Press ⌘⇧A in another application, drag around the text, then choose Read locally.'):
                        ui.link('Privacy & permissions →', '/settings').classes('text-link')
                    return
                if status in ('reading', 'analyzing'):
                    with ui.card().classes('privacy-card w-full'):
                        mascot('reading' if status == 'reading' else 'analyzing',size=80)
                        ui.label('Reading your approved region locally…' if status == 'reading' else 'Preparing your explanation…').classes('card-heading')
                        ui.button('Discard', on_click=discard).props('flat')
                    return
                if status == 'error':
                    with ui.card().classes('privacy-card w-full'):
                        mascot('confused',size=64)
                        ui.label('This selection needs another look.').classes('card-heading')
                        ui.label(snapshot['message']).classes('body-copy')
                        ui.link('Open privacy & permissions →', '/settings').classes('text-link')
                        ui.link('Upload the document instead →', '/analyze').classes('text-link')
                        ui.button('Discard', on_click=discard).props('flat')
                    return
                if status == 'result':
                    with ui.card().classes('privacy-card w-full'):
                        mascot('success',size=64)
                        ui.label('Amillum’s explanation').classes('card-heading')
                        ui.markdown(snapshot['result']).classes('amicus-markdown w-full')
                        ui.label('Information to help you understand, not legal advice. Verify important details.').classes('fine-print')
                        ui.button('Add to Workbench').props('outline disable').tooltip('Workbench is not available yet. Nothing has been saved.')
                        question=ui.input('Ask Amillum',placeholder='Your follow-up question').props('outlined stack-label maxlength=2000').classes('w-full')
                        language=ui.select(LANGUAGES,value='English',label='Explanation language').props('outlined').classes('w-full')
                        ui.label('A follow-up sends this approved passage and your new question to Gemini.').classes('fine-print')
                        ui.button('Ask Amillum',on_click=lambda: explain(snapshot['revision'],None,question,language,True)).props('unelevated')
                        if ask:
                            question.props('autofocus')
                        ui.button('Clear this explanation', on_click=discard).props('outline')
                    return
                with ui.card().classes('privacy-card w-full'):
                    mascot('asking',size=64)
                    ui.label('Selected content').classes('card-heading')
                    with ui.row().classes('context-metadata'):
                        ui.label(snapshot['source'] or 'Selected application').classes('workspace-status')
                        ui.label(snapshot['method']).classes('workspace-status')
                        ui.label('Local preview · not shared').classes('workspace-status')
                    extraction=snapshot.get('extraction') or {}
                    if snapshot['method']=='Local OCR':
                        confidence=extraction.get('confidence')
                        if isinstance(confidence,(int,float)):
                            ui.label(f'OCR confidence: {confidence:.0%}. Check names, numbers, and dates carefully.').classes('fine-print')
                        if extraction.get('needs_review'):
                            ui.label('Recognition is uncertain. Correct the text below before explaining it.').classes('body-copy')
                    editor = ui.textarea('Text to explain', value=snapshot['text']).props('outlined autogrow maxlength=12000').classes('w-full context-editor')
                    question = ui.input('Your question (optional)').props('outlined maxlength=2000').classes('w-full')
                    language = ui.select(LANGUAGES, value='English', label='Explanation language').props('outlined').classes('w-full')
                    ui.label('Explain sends the text above and your question to Gemini through Amillum’s existing analysis service. The screenshot is never uploaded.').classes('body-copy')
                    if snapshot['message']:
                        ui.label(snapshot['message']).classes('body-copy')
                    with ui.row().classes('items-center gap-3'):
                        ui.button('Explain this text', icon='arrow_forward', on_click=lambda: explain(snapshot['revision'], editor, question, language)).props('unelevated').classes('studio-primary')
                        ui.button('Cancel & discard', on_click=discard).props('flat')
            content()

    def refresh():
        state.snapshot()  # Discard pending context if the native connection has gone away.
        snapshot = state.context.snapshot()
        key = (snapshot['revision'], snapshot['status'], snapshot['message'])
        if key != rendered[0]:
            content.refresh()

    ui.timer(.5, refresh)
