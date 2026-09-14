"""Validated explicit Workbench operations; no AI calls or local database."""
from datetime import date
from uuid import UUID, uuid4
from services.supabase import PersistenceError

TYPES = ('task', 'obligation', 'deadline', 'question', 'attention', 'note')
STATUSES = ('open', 'completed', 'dismissed')
FIELDS = {'type', 'title', 'description', 'status', 'due_date', 'date_confirmed', 'source_context', 'document_id'}


def identifier(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise PersistenceError('This item reference is invalid.') from None


def validate(values):
    if not isinstance(values,dict) or set(values) - FIELDS:
        raise PersistenceError('Unsupported Workbench fields.')
    if any(not isinstance(values.get(key,''),str) for key in ('title','description','source_context')):
        raise PersistenceError('Title, details, and source excerpt must be text.')
    result = {'type': values.get('type', 'note'), 'title': values.get('title', '').strip(),
              'description': values.get('description', '').strip(), 'status': values.get('status', 'open'),
              'source_context': values.get('source_context', '').strip(),
              'document_id': identifier(values['document_id']) if values.get('document_id') else None,
              'due_date': values.get('due_date') or None, 'date_confirmed': values.get('date_confirmed') is True}
    if result['type'] not in TYPES or result['status'] not in STATUSES:
        raise PersistenceError('Choose a supported item type and status.')
    if not 1 <= len(result['title']) <= 200 or len(result['description']) > 4000 or len(result['source_context']) > 500:
        raise PersistenceError('Use a title of 1–200 characters, details up to 4,000 characters, and a source excerpt up to 500 characters.')
    if result['due_date']:
        try:
            parsed = date.fromisoformat(result['due_date'])
            if parsed.isoformat() != result['due_date']:
                raise ValueError()
        except (ValueError, TypeError):
            raise PersistenceError('Choose a valid date in YYYY-MM-DD format.') from None
        if not result['date_confirmed']:
            raise PersistenceError('Confirm the exact due date before saving. Relative dates are not converted automatically.')
    else:
        result['date_confirmed'] = False
    return result


class Workbench:
    def __init__(self, account):
        self.account = account

    def list(self, kind=None, status=None, offset=0):
        if kind and kind not in TYPES or status and status not in STATUSES:
            raise PersistenceError('Choose a supported filter.')
        params = {'select': '*,workbench_sources(title,kind)', 'order': 'created_at.desc,id.desc', 'limit': '50', 'offset': str(max(0, int(offset)))}
        if kind: params['type'] = 'eq.' + kind
        if status: params['status'] = 'eq.' + status
        return self.account.authenticated('GET', '/rest/v1/workbench_items', params=params)

    def save(self, values, *, item_id=None, source=None):
        item = validate(values)
        item['id'] = identifier(item_id) if item_id else str(uuid4())
        if source:
            if source.get('kind') not in ('document', 'selection') or not 1 <= len(source.get('title', '')) <= 240:
                raise PersistenceError('The source reference is invalid.')
            source = {key: source[key] for key in ('id', 'kind', 'title')}
            source['id'] = identifier(source['id'])
            if item['document_id'] != source['id']:
                raise PersistenceError('The item and source do not match.')
        result = self.account.authenticated('POST', '/rest/v1/rpc/save_workbench_item', body={'p_item': item, 'p_source': source})
        if not result:
            raise PersistenceError('The save could not be confirmed. Keep your draft and retry.')
        return result[0]

    def update(self, item_id, values):
        item = validate(values)
        result = self.account.authenticated('PATCH', '/rest/v1/workbench_items', params={'id': 'eq.' + identifier(item_id)}, body=item)
        if not result:
            raise PersistenceError('This item is no longer available. Refresh your Workbench.')
        return result[0]

    def set_status(self, item_id, status):
        if status not in STATUSES:
            raise PersistenceError('Choose a supported status.')
        result = self.account.authenticated('PATCH', '/rest/v1/workbench_items', params={'id': 'eq.' + identifier(item_id)}, body={'status': status})
        if not result:
            raise PersistenceError('This item is no longer available. Refresh your Workbench.')
        return result[0]

    def delete(self, item_id):
        self.account.authenticated('DELETE', '/rest/v1/workbench_items', params={'id': 'eq.' + identifier(item_id)})
