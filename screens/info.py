from services.auth import protected, current, checked_operation
from nicegui import ui
from components.shell import shell
from components.primitives import page_heading


@ui.page('/info')
@protected
def info():
    with shell('info'):
        with ui.element('main').classes('studio-content'):
            page_heading('A little help', 'A few things to know about working with Amillum.')
            for title, text in [('What can Amillum help with?', 'Upload a PDF or image and ask a question about it. Amillum uses AI to explain the extracted text in your chosen language. Responses can contain mistakes; verify important details with a qualified professional.'),
                ('What happens when I upload a document?', 'The document is processed for text extraction. Extracted content, your question, and your chosen language are sent to the existing Gemini analysis service. Upload only content you want analyzed.'),
                ('Does the Mac shortcut read my screen?', 'The shortcut draws a selection border. Read locally approves that region for Accessibility extraction or local OCR. You review the text before a separate Explain action sends it to AI. Escape cancels selection.'),
                ('How do I control contextual access?', 'Privacy & control contains separate opt-in controls for application awareness and Accessibility metadata, along with pause, clear, and application exclusions.')]:
                with ui.expansion(title).classes('guidance-faq w-full'):
                    ui.label(text).classes('body-copy p-4')
