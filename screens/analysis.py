from components.email_draft import email_draft_button
from services.auth import protected, current, checked_operation
from nicegui import ui, run
from services.supabase import get_account, PersistenceError
from components.workbench import analysis_save_button
from components.mascot import mascot
from components.shell import shell
from components.primitives import page_heading, primary_button
from core.workspace import workspace
import io

from backend.pdf_reader import extract_pdf
from backend.analyze import analyze_document
from backend.text_extract import extract_text_from_image


LANGUAGES = [
    "English", "Spanish (Español)", "French (Français)", "Chinese (中文)",
    "Arabic (العربية)", "Russian (Русский)", "Portuguese (Português)",
    "Hindi (हिन्दी)", "Bengali (বাংলা)", "Japanese (日本語)", "German (Deutsch)",
    "Korean (한국어)", "Italian (Italiano)", "Dutch (Nederlands)", "Turkish (Türkçe)",
    "Vietnamese (Tiếng Việt)", "Polish (Polski)", "Ukrainian (Українська)",
    "Romanian (Română)", "Greek (Ελληνικά)", "Czech (Čeština)", "Swedish (Svenska)",
    "Hungarian (Magyar)", "Finnish (Suomi)", "Dansk (Danish)", "Norwegian (Norsk)",
    "Catalan (Català)", "Indonesian (Bahasa Indonesia)", "Malay (Bahasa Melayu)",
    "Thai (ไทย)", "Hebrew (עברית)", "Bulgarian (Български)", "Croatian (Hrvatski)",
    "Estonian (Eesti)", "Gujarati (ગુજરાતી)", "Kannada (ಕನ್ನಡ)", "Latvian (Latviešu)",
    "Lithuanian (Lietuvių)", "Malayalam (മലയാളം)", "Marathi (मराठी)",
    "Slovak (Slovenčina)", "Slovenian (Slovenščina)", "Swahili (Kiswahili)",
    "Tamil (தமிழ்)", "Telugu (తెలుగు)", "Urdu (اردو)", "Serbian (Српски)",
    "Filipino (Filipino)", "Icelandic (Íslenska)", "Amharic (አማርኛ)",
    "Armenian (Հայերեն)", "Azerbaijani (Azərbaycan dili)", "Basque (Euskara)",
    "Galician (Galego)", "Georgian (ქართული)", "Kazakh (Қазақ тілі)",
    "Khmer (ខ្Khmer)", "Lao (ລາວ)", "Macedonian (Македонски)", "Mongolian (Монгол)",
    "Nepali (नेपाली)", "Sinhala (සිංහල)", "Albanian (Shqip)", "Bosnian (Bosanski)",
    "Uzbek (Oʻzbekcha)", "Zulu (isiZulu)", "Afrikaans (Afrikaans)"
]


@ui.page('/analyze')
@protected
def analyze():
    account = get_account()
    pending = {}

    def show_upload_error(message):
        upload_error.set_text(message)
        upload_error.set_visibility(True)

    async def process_file(e):
        if not current(account):return
        if workspace.snapshot()['status'] in ('extracting','analyzing'):
            show_upload_error('A document is already being analyzed. Wait for it to finish or clear the current document.')
            return
        try:
            pending.update(name=e.file.name, content=await e.file.read())
        except Exception:
            show_upload_error('Amillum couldn’t open this file. Choose it again, or try a different PDF or image.')
            return
        await continue_upload()

    async def continue_upload():
        if not current(account):return
        if not pending:
            return
        if not language_select.value:
            show_upload_error(f'“{pending["name"]}” is ready. Choose an explanation language above, then select Continue. Nothing has been sent for analysis.')
            continue_button.set_visibility(True)
            language_select.props('error error-message="Choose an explanation language to continue"')
            return
        language_select.props(remove='error error-message')
        upload_error.set_visibility(False)
        continue_button.set_visibility(False)
        question, language = question_input.value or '', language_select.value
        try:
            revision = workspace.begin(pending['name'], question, language)
        except ValueError as exc:
            ui.notify(str(exc), type='warning')
            return
        refresh()
        try:
            filename, file_content = pending['name'], pending['content']
            pending.clear()
            file_obj = io.BytesIO(file_content)
            if filename.lower().endswith('.pdf'):
                extracted_text = await run.io_bound(extract_pdf, file_obj)
            else:
                extracted_text = await run.io_bound(extract_text_from_image, file_obj)
            if not extracted_text or not extracted_text.strip():
                workspace.finish(revision, error='No readable text found. Try a clearer document or image.')
            elif workspace.extracted(revision, extracted_text):
                result = await run.io_bound(checked_operation, account, analyze_document, extracted_text, question, language)
                workspace.finish(revision, result=result or '', error='' if result else 'The analysis service returned no explanation. Please try again.')
        except PersistenceError as exc:
            workspace.finish(revision, error=str(exc))
        except Exception:
            workspace.finish(revision, error='We couldn’t analyze this document. Check your connection and analysis configuration, then try again.')
        # A client may have navigated back to Workspace. Its timer reads shared state.

    def reset_ui():
        if not current(account):return
        pending.clear()
        upload_error.set_visibility(False)
        continue_button.set_visibility(False)
        workspace.clear()
        question_input.value = ''
        uploader.reset()
        refresh()

    @ui.refreshable
    def document_beaver():
        status=workspace.snapshot()['status']
        mascot({'extracting':'reading','analyzing':'analyzing','error':'confused','ready':'success'}.get(status,'curious'),size=72)

    with shell('analysis'):
        with ui.element('main').classes('document-content'):
            heading, subtitle = page_heading('Open a document', 'A little clarity starts here.')
            with ui.element('section').classes('document-setup') as setup:
                ui.label('Before you open').classes('section-label')
                question_input = ui.input(
                    label='Your question', placeholder='Optional — what would you like to understand?',
                    value=workspace.snapshot()['draft_question'],
                    on_change=lambda e: workspace.draft(question=e.value)
                ).props('outlined stack-label').classes('w-full')
                language_select = ui.select(
                    options=LANGUAGES, value=workspace.snapshot()['draft_language'],
                    label='Explanation language', on_change=lambda e: workspace.draft(language=e.value)
                ).props('outlined').classes('w-full')
            upload_container = ui.column().classes('upload-surface w-full')
            with upload_container:
                mascot('curious',size=80)
                ui.label('Bring the complicated part.').classes('card-heading')
                ui.label('Choose a PDF or image, up to 20 MB.').classes('body-copy')
                uploader = ui.upload(on_upload=process_file, auto_upload=True,
                    max_file_size=20_000_000,
                    on_rejected=lambda: show_upload_error('This file couldn’t be opened. Choose a PDF or image smaller than 20 MB.')
                ).props('accept=".pdf, application/pdf, image/*" label="Choose a document"').classes('document-uploader')
                uploader.add_slot('header', '<q-btn unelevated no-caps label="Choose file" icon="folder_open" class="primary-button"><q-uploader-add-trigger /></q-btn>')
                upload_error = ui.label().classes('am-error w-full').props('role=alert aria-live=polite')
                upload_error.set_visibility(False)
                continue_button = ui.button('Continue',on_click=continue_upload).props('unelevated').classes('primary-button')
                continue_button.set_visibility(False)
                ui.label('Opening a file starts analysis. Extracted text and your question are sent to Gemini.').classes('fine-print upload-consent')
            loading_container = ui.column().classes('processing-surface').style('display:none;')
            with loading_container:
                document_beaver()
                progress_label = ui.label('Reading your document…').classes('card-heading')
                ui.label('Keep working. Your explanation will be here.').classes('body-copy')
                ui.button('Return to workspace', on_click=lambda: ui.navigate.to('/')).props('flat')
                ui.button('Clear document', on_click=reset_ui).props('flat')
            result_container = ui.column().classes('reading-surface w-full').style('display:none;')
            with result_container:
                document_beaver()
                result_heading = ui.label('Your explanation').classes('card-heading')
                result_markdown = ui.markdown().classes('amicus-markdown w-full')
                ui.label('Informational guidance. Verify important details with a qualified professional.').classes('fine-print')
                with ui.row().classes('result-actions'):
                    @ui.refreshable
                    def save_finding():
                        snapshot=workspace.snapshot()
                        if snapshot['status']=='ready':
                            email_draft_button(account,'document')
                            analysis_save_button(account,source={'id':snapshot['document_id'],'kind':'document','title':snapshot['filename'][:240]})
                    save_finding()
                    primary_button('Ask a follow-up', lambda: ui.navigate.to('/'), 'arrow_forward')
                    ui.button('Open another document', on_click=reset_ui).props('flat')

    last_render = [None]
    def refresh():
        snapshot = workspace.snapshot()
        key = (snapshot['revision'], snapshot['status'])
        if key == last_render[0]:
            return
        last_render[0] = key
        document_beaver.refresh()
        save_finding.refresh()
        busy = snapshot['status'] in ('extracting', 'analyzing')
        setup.set_visibility(snapshot['status'] == 'empty')
        heading.set_text('Open a document' if snapshot['status'] == 'empty' else (snapshot['filename'] or 'Your document'))
        subtitle.set_text('A little clarity starts here.' if snapshot['status'] == 'empty' else 'Your current document · ' + snapshot['language'])
        upload_container.set_visibility(snapshot['status'] == 'empty')
        loading_container.style('display:flex;' if busy else 'display:none;')
        result_container.style('display:flex;' if snapshot['status'] in ('ready', 'error') else 'display:none;')
        uploader.set_enabled(not busy)
        question_input.set_enabled(not busy)
        language_select.set_enabled(not busy)
        progress_label.set_text('Reading your document…' if snapshot['status'] == 'extracting' else 'Preparing your explanation…')
        result_heading.set_text('Let’s try that again.' if snapshot['status']=='error' else 'Your explanation')
        result_markdown.classes(add='am-error' if snapshot['status']=='error' else '', remove='am-error' if snapshot['status']!='error' else '')
        result_markdown.set_content(snapshot['result'] or snapshot['error'])

    refresh()
    ui.timer(.3, refresh)
