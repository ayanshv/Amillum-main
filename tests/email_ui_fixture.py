"""Opt-in UI smoke fixture: fictional source, fake generation, no mail handoff."""
if __name__=='__main__':
    import sys
    from pathlib import Path
    from unittest.mock import patch
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import services.supabase as auth
    account=auth.Account(auth.Supabase('https://fixture.invalid','sb_publishable_fixture'))
    account.user_id='11111111-1111-4111-8111-111111111111';account.email='fixture@example.test'
    auth.activate_account(account);auth.get_account=lambda:account
    from core.workspace import workspace
    from core.context_awareness import get_state
    get_state().update(paused=False)
    revision=workspace.begin('Fictional agreement.pdf','','English')
    workspace.extracted(revision,'The agreement asks the parties to discuss changes in writing.')
    workspace.finish(revision,'A fictional agreement for UI verification.')
    with patch('native.configure_desktop'):
        import app
    from services.email_drafting import EmailDraft
    import components.email_draft as editor
    editor.generate_draft=lambda *a,**kw:EmailDraft('','Question about the agreement','Could you clarify how proposed changes should be discussed?')
    editor.MailClientHandoff.open_draft=lambda *a:None  # Fixture never opens a mail application.
    from nicegui import ui
    ui.run(host='127.0.0.1',port=8012,native=False,show=False,reload=False,storage_secret='fixture-only',title='Amillum email UI test')
