"""References existing user-approved context without reading any new screen data."""
from services.auth import current
from services.supabase import PersistenceError
from core.context_awareness import get_state
from core.workspace import workspace
from core.privacy import require_safe_text

class ApprovedEmailContext:
    def __init__(self,account,kind):
        self.account=account;self.generation=account.generation;self.kind=kind
        state=get_state()
        if kind=='selection':
            snapshot=state.context.snapshot()
            self.revision=snapshot['revision'];self.source=snapshot['source']
            self.text=snapshot['text'] if snapshot['status']=='result' else ''
        elif kind=='document':
            with workspace.lock:
                self.revision=workspace.revision;self.source=''
                self.text=workspace.text if workspace.status=='ready' else ''
        else:raise PersistenceError('Choose an approved document or selection.')
        if not self.text or not self.valid():raise PersistenceError('An approved explanation is required. Resume Amillum and review your document or selection first.')

    def valid(self):
        state=get_state()
        if not current(self.account) or self.generation!=self.account.generation or state.paused or state.preferences.load_error:return False
        if self.source in state.policy()['excluded']:return False
        if self.kind=='selection':
            snapshot=state.context.snapshot()
            return snapshot['revision']==self.revision and snapshot['status']=='result'
        with workspace.lock:return workspace.revision==self.revision and workspace.status=='ready'

    def excerpt(self,text):
        if not self.valid():raise PersistenceError('The approved source changed. Review it again.')
        if not isinstance(text,str) or not text.strip() or len(text)>12000 or text not in self.text:
            raise PersistenceError('Choose an unchanged excerpt of up to 12,000 characters from the approved source.')
        require_safe_text(text)
        return text
