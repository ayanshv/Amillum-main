from nicegui import ui,run
from services.supabase import get_account,PersistenceError
from services.auth import current
from services.billing import refresh,website


def plan_status():
    account=get_account()
    label=ui.label('Checking plan…').classes('fine-print')
    url=website()
    if url:ui.link('Plans & billing ↗',url,new_tab=True).classes('fine-print')
    else:ui.label('Website billing link not configured').classes('fine-print')
    async def load():
        if not current(account):return
        try:
            state=await run.io_bound(refresh,account)
            if current(account):
                feature=state['features']['document_analysis']
                label.text=f"{state['plan'].title()} · {feature['remaining']} analyses left"
                label.tooltip('Allowance resets '+state['reset_at'])
        except PersistenceError:label.text='Plan status unavailable · retry shortly'
    ui.timer(.2,load,once=True);ui.timer(60,load)
