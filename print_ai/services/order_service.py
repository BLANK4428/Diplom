from json_utils import (
    empty_order, extract_json, deep_update, check_missing,
    _extract_product_fallback, _extract_materials_fallback,
    resolve_deadline_date, resolve_urgency,
)
from llm import ask_llm
from docx_generator import build_doc
from db import save_order, save_session, load_session, delete_session

# In-memory cache backed by DB
_sessions: dict = {}


def _get_state(sid: str) -> dict:
    if sid not in _sessions:
        dialogue, order = load_session(sid)
        if dialogue is not None:
            _sessions[sid] = {'order': order, 'dialogue': dialogue}
        else:
            _sessions[sid] = {'order': empty_order(), 'dialogue': []}
    return _sessions[sid]


def process_message(sid: str, text: str) -> dict:
    state = _get_state(sid)

    state['dialogue'].append({'role': 'user', 'text': text})
    save_session(sid, state['dialogue'], state['order'])

    recent = state['dialogue'][-10:]
    dialogue_text = '\n'.join(
        f"{'Клиент' if m['role'] == 'user' else 'Менеджер'}: {m['text']}"
        for m in recent
    )

    new_data = extract_json(dialogue_text, ask_llm, current=state['order'])
    deep_update(state['order'], new_data)

    full_text = '\n'.join(m['text'] for m in state['dialogue'])

    if not state['order'].get('product_type'):
        state['order']['product_type'] = _extract_product_fallback(full_text)
    if not state['order'].get('materials'):
        state['order']['materials'] = _extract_materials_fallback(full_text)

    deadline = state['order'].setdefault('deadline', {})
    resolved_date = resolve_deadline_date(full_text)
    if resolved_date:
        deadline['date'] = resolved_date
    resolved_urgency = resolve_urgency(full_text)
    if resolved_urgency:
        deadline['urgency'] = resolved_urgency

    missing = check_missing(state['order'])

    if missing:
        state['dialogue'].append({'role': 'bot', 'text': missing})
        save_session(sid, state['dialogue'], state['order'])
        return {'status': 'question', 'message': missing, 'order': state['order']}

    clean = {k: v for k, v in state['order'].items() if not k.startswith('_')}
    dialogue_snapshot = list(state['dialogue'])

    docx_bytes, docx_name = build_doc(clean)
    order_id = save_order(clean, dialogue_snapshot, docx_bytes, docx_name)

    delete_session(sid)
    _sessions[sid] = {'order': empty_order(), 'dialogue': []}

    return {'status': 'done', 'json': clean, 'order_id': order_id}


def reset(sid: str) -> None:
    delete_session(sid)
    _sessions[sid] = {'order': empty_order(), 'dialogue': []}
