import json
import os
import psycopg2
import psycopg2.extras

from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS


os.environ.setdefault('PGCLIENTENCODING', 'UTF8')

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    id           SERIAL PRIMARY KEY,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    product_type TEXT,
    quantity     INTEGER,
    order_json   JSONB NOT NULL DEFAULT '{}',
    dialogue     JSONB NOT NULL DEFAULT '[]',
    docx_data    BYTEA,
    docx_name    TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    sid          TEXT PRIMARY KEY,
    dialogue     JSONB NOT NULL DEFAULT '[]',
    order_json   JSONB NOT NULL DEFAULT '{}',
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
"""


def _conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS,
        client_encoding='utf8',
    )


def init_db() -> None:
    with _conn() as con, con.cursor() as cur:
        cur.execute(_CREATE_SQL)


def save_order(order: dict, dialogue: list, docx_bytes: bytes, docx_name: str) -> int:
    """Save completed order to DB. Returns new row id."""

    product_type = order.get('product_type')
    quantity = order.get('quantity')
    try:
        quantity = int(quantity) if quantity is not None else None
    except (ValueError, TypeError):
        quantity = None

    with _conn() as con, con.cursor() as cur:
        cur.execute(
            """
            INSERT INTO orders (product_type, quantity, order_json, dialogue, docx_data, docx_name)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                product_type,
                quantity,
                json.dumps(order, ensure_ascii=False),
                json.dumps(dialogue, ensure_ascii=False),
                psycopg2.Binary(docx_bytes),
                docx_name,
            ),
        )
        row_id = cur.fetchone()[0]
    return row_id


def load_orders(limit: int = 50) -> list:
    """Return orders newest-first. dialogue included."""
    with _conn() as con, con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, created_at, product_type, quantity, order_json, dialogue, docx_name
            FROM orders
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()

    result = []
    for r in rows:
        entry = dict(r['order_json'])
        entry['id'] = r['id']
        entry['created_at'] = r['created_at'].isoformat(timespec='seconds')
        entry['product_type'] = r['product_type']
        entry['quantity'] = r['quantity']
        entry['docx_name'] = r['docx_name']
        entry['dialogue'] = list(r['dialogue'])
        result.append(entry)
    return result


def save_session(sid: str, dialogue: list, order: dict) -> None:
    """Upsert active session state so it survives server restarts."""
    with _conn() as con, con.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sessions (sid, dialogue, order_json, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (sid) DO UPDATE
                SET dialogue   = EXCLUDED.dialogue,
                    order_json = EXCLUDED.order_json,
                    updated_at = NOW()
            """,
            (
                sid,
                json.dumps(dialogue, ensure_ascii=False),
                json.dumps(order, ensure_ascii=False),
            ),
        )


def load_session(sid: str):
    """Return (dialogue, order) for an active session, or (None, None)."""
    with _conn() as con, con.cursor() as cur:
        cur.execute(
            "SELECT dialogue, order_json FROM sessions WHERE sid = %s",
            (sid,),
        )
        row = cur.fetchone()
    if not row:
        return None, None
    return list(row[0]), dict(row[1])


def delete_session(sid: str) -> None:
    with _conn() as con, con.cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE sid = %s", (sid,))


def get_docx(order_id: int):
    """Return (docx_bytes, docx_name) or (None, None) if not found."""
    with _conn() as con, con.cursor() as cur:
        cur.execute(
            "SELECT docx_data, docx_name FROM orders WHERE id = %s",
            (order_id,),
        )
        row = cur.fetchone()
    if not row or not row[0]:
        return None, None
    return bytes(row[0]), row[1]
