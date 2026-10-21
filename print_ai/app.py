import io
import uuid
from flask import Flask, render_template, request, jsonify, make_response, send_file

from services.order_service import process_message, reset as reset_session
from db import init_db, load_orders, get_docx

app = Flask(__name__)


def _resp(data, sid: str, code: int = 200):
    r = make_response(jsonify(data), code)
    r.set_cookie('sid', sid, max_age=86400, samesite='Lax')
    return r


@app.route('/')
def index():
    sid = request.cookies.get('sid') or str(uuid.uuid4())
    r = make_response(render_template('index.html'))
    r.set_cookie('sid', sid, max_age=86400, samesite='Lax')
    return r


@app.route('/send', methods=['POST'])
def send():
    sid = request.cookies.get('sid') or str(uuid.uuid4())
    try:
        text = (request.json or {}).get('text', '').strip()
        if not text:
            return _resp({'status': 'error', 'message': 'Пустой запрос'}, sid)
        result = process_message(sid, text)
        return _resp(result, sid)
    except Exception as exc:
        return _resp({'status': 'error', 'message': str(exc)}, sid, 500)


@app.route('/reset', methods=['POST'])
def reset():
    sid = request.cookies.get('sid') or str(uuid.uuid4())
    reset_session(sid)
    return _resp({'status': 'ok'}, sid)


@app.route('/download/id/<int:order_id>')
def download_by_id(order_id):
    docx_bytes, docx_name = get_docx(order_id)
    if not docx_bytes:
        return 'Файл не найден', 404
    return send_file(
        io.BytesIO(docx_bytes),
        as_attachment=True,
        download_name=docx_name or f'order_{order_id}.docx',
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )


@app.route('/history')
def history():
    return jsonify(load_orders())


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
