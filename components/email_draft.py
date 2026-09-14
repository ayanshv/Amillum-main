"""Draft, edit, review, then explicitly hand off to the user's mail client."""
from nicegui import ui,run
from components.mascot import mascot
from services.email_context import ApprovedEmailContext
from services.email_drafting import DraftSession,MailClientHandoff,generate_draft,TONES,LENGTHS
from services.supabase import PersistenceError


def email_draft_button(account,kind):
    async def begin():
        from services.billing import refresh,website
        button.disable()
        try:
            state=await run.io_bound(refresh,account)
            feature=state['features']['email_drafting']
            if not feature['enabled'] or feature['remaining']<=0:
                with ui.dialog() as gate,ui.card().classes('email-editor'):
                    ui.label('Email drafting' if not feature['enabled'] else 'Drafting allowance reached').classes('card-heading')
                    ui.label('Create an editable email from content you approve. Compare eligible plans on the Amillum website.' if not feature['enabled'] else 'Your draft stays yours. Your allowance resets '+state['reset_at']+'. Manage your plan on the website.')
                    if website():ui.link('Compare plans on Amillum ↗',website(),new_tab=True)
                    ui.button('Close',on_click=gate.close).props('flat')
                gate.open()
                return
            open_editor(account,kind)
        except PersistenceError as exc:ui.notify(str(exc),type='warning')
        finally:button.enable()
    button=ui.button('Draft an email',icon='mail_outline',on_click=begin).props('outline no-caps')


def open_editor(account,kind):
    try:source=ApprovedEmailContext(account,kind)
    except (PersistenceError,ValueError) as exc:
        ui.notify(str(exc),type='warning');return
    session=DraftSession(source.valid)
    state={'busy':False}
    def close():
        session.cancel();source.text=''
        dialog.close();dialog.delete();guard.deactivate()
    with ui.dialog().props('persistent') as dialog,ui.card().classes('email-editor'):
        with ui.row().classes('items-center justify-between w-full'):
            ui.label('Draft email').classes('card-heading');mascot('reading',size=38)
        error=ui.label().props('role=alert aria-live=polite').classes('am-error');error.set_visibility(False)
        recipient=ui.input('To',placeholder='recipient@example.com').props('outlined type=email maxlength=254').classes('w-full')
        subject=ui.input('Subject').props('outlined maxlength=180').classes('w-full')
        body=ui.textarea('Email body').props('outlined autogrow maxlength=6000').classes('w-full')
        with ui.row().classes('w-full'):
            tone=ui.select(list(TONES),value='Professional',label='Tone').props('outlined').classes('grow')
            length=ui.select(list(LENGTHS),value='Concise',label='Length').props('outlined').classes('grow')
        with ui.expansion('Approved source used for this draft').classes('w-full'):
            ui.label('Only the excerpt below is used for generation. Trim it to what matters; no new screen content is collected.').classes('fine-print')
            excerpt=ui.textarea('Approved excerpt',value=source.text[:4000]).props('outlined autogrow maxlength=12000').classes('w-full')
            ui.label('For longer sources, the first 4,000 characters are shown. You may paste another unchanged excerpt from the approved source.').classes('fine-print')
            notes=ui.textarea('Additional information you choose to include (optional)',placeholder='For example, a Workbench question you want to ask.').props('outlined maxlength=2000').classes('w-full')
        ui.label('Review every fact, name and date. This is communication assistance, not verified legal advice.').classes('fine-print')
        async def generate():
            if state['busy']:return
            state['busy']=True;generate_button.disable();use_button.disable();error.set_visibility(False)
            for field in (subject,body,tone,length,excerpt,notes):field.disable()
            try:
                session.check()
                selected=source.excerpt(excerpt.value)
                draft=await run.io_bound(generate_draft,account,selected,tone.value,length.value,notes.value or '',lambda:not session.cancelled and source.valid())
                session.check();subject.value=draft.subject;body.value=draft.body
                generate_button.set_text('Regenerate')
            except (PersistenceError,ValueError) as exc:
                if not session.cancelled:error.set_text(str(exc));error.set_visibility(True)
            finally:
                state['busy']=False
                if not session.cancelled:
                    generate_button.enable();use_button.enable()
                    for field in (subject,body,tone,length,excerpt,notes):field.enable()
        def review():
            try:
                session.use(recipient.value or '',subject.value or '',body.value or '')
                ticket=session.begin_review()
            except (PersistenceError,ValueError) as exc:error.set_text(str(exc));error.set_visibility(True);return
            with ui.dialog().props('persistent') as confirmation,ui.card().classes('email-editor'):
                ui.label('Review & send').classes('card-heading')
                ui.label('This opens an editable draft in your mail app. No email is sent by Amillum. You must press Send in your mail app to send this message.').classes('body-copy')
                ui.label('To: '+session.review.recipient)
                ui.label('Subject: '+session.review.subject)
                ui.label(session.review.body).classes('email-review-body')
                problem=ui.label().props('role=alert').classes('am-error');problem.set_visibility(False)
                def back():session.edit();review_guard.deactivate();confirmation.close();confirmation.delete()
                def handoff():
                    send_button.disable()
                    try:
                        session.handoff(ticket,True,MailClientHandoff())
                        review_guard.deactivate();confirmation.close();confirmation.delete();close()
                    except (PersistenceError,ValueError) as exc:
                        problem.set_text(str(exc)+' Return to the editor and review again before retrying.');problem.set_visibility(True)
                with ui.row().classes('w-full justify-end'):
                    ui.button('Cancel · return to editing',on_click=back).props('flat')
                    send_button=ui.button('Confirm · open mail app',on_click=handoff).props('unelevated')
                def protect_review():
                    if session.cancelled or not source.valid():confirmation.close();confirmation.delete();review_guard.deactivate()
                review_guard=ui.timer(.5,protect_review)
            confirmation.open()
        with ui.row().classes('w-full justify-end'):
            ui.button('Cancel',on_click=close).props('flat')
            generate_button=ui.button('Generate draft',on_click=generate).props('outline')
            use_button=ui.button('Use draft · review & send',on_click=review).props('unelevated')
    def protect():
        if not source.valid():close()
    guard=ui.timer(.5,protect)
    dialog.open()
