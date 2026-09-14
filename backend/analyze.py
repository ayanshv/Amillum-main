"""Existing analysis entry point, routed through the authenticated AI backend."""
from dotenv import load_dotenv
load_dotenv()


def analyze_document(document_info,user_question,user_language):
    from services.supabase import active_account,PersistenceError
    from services.ai_router import generate
    account=active_account()
    if account is None:raise PersistenceError('Sign in before requesting analysis.')
    return generate(account,{'feature':'document_analysis','context':document_info,
                             'question':user_question,'language':user_language})
