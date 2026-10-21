import datetime
import json
import re


def empty_order() -> dict:
    return {
        'product_type': None,
        'dimensions': {'width_mm': None, 'height_mm': None, 'depth_mm': None},
        'quantity': None,
        'materials': [],
        'finishing': [],
        'print_details': {'colors': None, 'sides': None, 'notes': None},
        'deadline': {'date': None, 'urgency': 'normal'},
        'delivery': None,
        'notes': '',
        '_asked': [],   # tracks which optional questions have already been asked
    }


_PROMPT = """Извлеки параметры полиграфического заказа из диалога. Верни ТОЛЬКО JSON, без пояснений.
Форматы мм: А4=210x297 А5=148x210 А6=105x148 визитка=90x50.
Сегодня: {today}. Срок выполнения (deadline.date) записывай как ДД.ММ.ГГГГ — считай от сегодняшней даты.
Уже известные данные (не затирай их, дополняй новыми):
{current}
Шаблон (заполни из диалога, null если нет):
{{"product_type":null,"dimensions":{{"width_mm":null,"height_mm":null,"depth_mm":null}},"quantity":null,"materials":[],"finishing":[],"print_details":{{"colors":null,"sides":null,"notes":null}},"deadline":{{"date":null,"urgency":"normal"}},"delivery":null,"notes":""}}

Диалог:
{dialogue}
JSON:"""

_PRODUCT_KW = [
    ('визитк',      'визитки'),
    ('листовк',     'листовки'),
    ('флаер',       'листовки'),
    ('буклет',      'буклет'),
    ('брошюр',      'брошюра'),
    ('каталог',     'каталог'),
    ('плакат',      'плакат'),
    ('постер',      'постер'),
    ('баннер',      'баннер'),
    ('конверт',     'конверт'),
    ('блокнот',     'блокнот'),
    ('календар',    'календарь'),
    ('упаковк',     'упаковка'),
    ('этикетк',     'этикетка'),
    ('наклейк',     'наклейки'),
    ('коробка',     'коробки'),
    ('книга',     'книги'),
    ('обложка',     'обложки'),
]


def _extract_product_fallback(text: str) -> str | None:
    tl = text.lower()
    for kw, name in _PRODUCT_KW:
        if kw in tl:
            return name
    return None


def extract_json(dialogue: str, ask_llm, current: dict | None = None) -> dict:
    current_str = json.dumps(
        {k: v for k, v in (current or {}).items() if not k.startswith('_')},
        ensure_ascii=False
    )
    today = datetime.date.today().strftime('%d.%m.%Y')
    prompt = _PROMPT.format(dialogue=dialogue, current=current_str, today=today)
    try:
        raw = ask_llm(prompt)
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            data = json.loads(match.group())
            data = _normalize(data)
            if not data.get('materials'):
                data['materials'] = _extract_materials_fallback(dialogue)
            if not data.get('product_type'):
                data['product_type'] = _extract_product_fallback(dialogue)
            return data
    except Exception:
        pass
    return empty_order()


def _normalize(data: dict) -> dict:
    """Fix common LLM type mismatches."""
    if not isinstance(data, dict):
        return data

    # quantity → int
    if 'quantity' in data:
        try:
            data['quantity'] = int(str(data['quantity']).replace(' ', '').replace(',', ''))
        except (ValueError, TypeError):
            data['quantity'] = None

    # dimensions → float
    dims = data.get('dimensions')
    if isinstance(dims, dict):
        for k in ('width_mm', 'height_mm', 'depth_mm'):
            if k in dims:
                try:
                    dims[k] = float(str(dims[k]).replace(',', '.'))
                except (ValueError, TypeError):
                    dims[k] = None

    # materials / finishing → list
    for key in ('materials', 'finishing'):
        val = data.get(key)
        if isinstance(val, str) and val:
            data[key] = [v.strip() for v in re.split(r'[,;]+', val) if v.strip()]
        elif not isinstance(val, list):
            data[key] = []

    return data


# Keyword → canonical name mapping for fallback material extraction
_MATERIAL_KW = [
    ('мелован',    'мелованная'),
    ('офсет',      'офсет'),
    ('картон',     'картон'),
    ('крафт',      'крафт'),
    ('самоклей',   'самоклейка'),
    ('бумаг',      'бумага'),
    ('пленк',      'плёнка'),
    ('пленок',     'плёнка'),
]

# Density: "130г", "130 г/м²", "350 г/м^2", "500г/кв.м", "80 г/м2", "200 г."
_DENSITY_RE = re.compile(
    r'(\d+)\s*г(?:[/\s]*(?:м(?:[²2]|\^2)|кв\.?\s*м))?',
    re.IGNORECASE
)


def _extract_materials_fallback(text: str) -> list:
    """Simple keyword+density extractor used when LLM returns empty materials."""
    tl = text.lower()
    for kw, name in _MATERIAL_KW:
        if kw in tl:
            idx = tl.find(kw)
            ctx = text[max(0, idx - 10): idx + 40]
            dm = _DENSITY_RE.search(ctx)
            entry = f'{name} {dm.group(0).strip()}' if dm else name
            return [entry]   # stop at first match to avoid duplicates
    return []


def deep_update(base: dict, new: dict) -> None:
    """Merge new values into base, skipping nulls and empty strings."""
    if not isinstance(new, dict) or not isinstance(base, dict):
        return
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_update(base[k], v)
        elif isinstance(v, list) and v:
            base[k] = v
        elif v is not None and v != '' and str(v) not in ('null', 'None'):
            base[k] = v


_DATE_RE = re.compile(r'\b(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?\b')

# Number words → value (both digits and Russian words)
_WORD_NUM = {
    **{str(i): i for i in range(1, 32)},
    'одну': 1, 'одна': 1, 'один': 1,
    'две': 2, 'два': 2, 'пару': 2,
    'три': 3, 'четыре': 4, 'пять': 5,
    'шесть': 6, 'семь': 7, 'восемь': 8,
    'девять': 9, 'десять': 10,
    'одиннадцать': 11, 'двенадцать': 12, 'тринадцать': 13,
    'четырнадцать': 14, 'пятнадцать': 15, 'шестнадцать': 16,
    'семнадцать': 17, 'восемнадцать': 18, 'девятнадцать': 19,
    'двадцать': 20, 'тридцать': 30,
}

_MONTH_NAMES = {
    'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4,
    'май': 5, 'мая': 5, 'июн': 6, 'июл': 7,
    'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12,
}

_UNIT_DAYS = {
    'д': 1,   # день/дня/дней
    'н': 7,   # неделя/недели/недель
    'м': 30,  # месяц/месяца/месяцев
}

# день → дне/дня/дней все начинаются с "де" или "дн"
_UNIT_RE = re.compile(r'\b(д(?:е|н)\w*|недел\w+|месяц\w*)\b', re.IGNORECASE)


def resolve_deadline_date(text: str) -> str | None:
    """
    Fallback date resolver — runs when LLM returned wrong or no date.
    Handles both digit and word-form expressions in any word order:
    «через три недели», «недели через три», «через 2 недели», «10 дней».
    """
    today = datetime.date.today()

    # «к 15 мая» / «к 5 июня 2026»
    m = re.search(
        r'к\s+(\d{1,2})\s+(' + '|'.join(_MONTH_NAMES) + r')\w*(?:\s+(\d{4}))?',
        text.lower()
    )
    if m:
        day = int(m.group(1))
        mon = _MONTH_NAMES[m.group(2)[:3]]
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            d = datetime.date(year, mon, day)
            if d < today:
                d = d.replace(year=d.year + 1)
            return d.strftime('%d.%m.%Y')
        except ValueError:
            pass

    # Already a concrete date like 15.05.2026 or 15/05
    m = _DATE_RE.search(text)
    if m:
        day, mon = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            d = datetime.date(year, mon, day)
            if d < today:
                d = d.replace(year=d.year + 1)
            return d.strftime('%d.%m.%Y')
        except ValueError:
            pass

    # Find unit word (день/неделя/месяц) then look for a number nearby
    m = _UNIT_RE.search(text)
    if m:
        unit = _UNIT_DAYS.get(m.group(1)[0].lower(), 1)
        tokens = text.lower().split()
        unit_idx = next(i for i, t in enumerate(tokens) if _UNIT_RE.match(t))
        # Search ±3 tokens around the unit word
        for offset in range(-3, 4):
            idx = unit_idx + offset
            if 0 <= idx < len(tokens) and idx != unit_idx:
                n = _WORD_NUM.get(tokens[idx].rstrip('.,!?'))
                if n:
                    return (today + datetime.timedelta(days=unit * n)).strftime('%d.%m.%Y')
        # Unit found but no number → assume 1
        return (today + datetime.timedelta(days=unit)).strftime('%d.%m.%Y')

    return None


def resolve_urgency(text: str) -> str | None:
    """Return 'urgent'/'flexible'/None based on keywords in full dialogue text."""
    tl = text.lower()
    if any(w in tl for w in ('срочно', 'срочный', 'срочная', 'asap', 'как можно быстрее')):
        return 'urgent'
    if any(w in tl for w in ('не важен', 'не важно', 'гибко', 'когда удобно',
                              'неспешно', 'спешки нет', 'не горит', 'без спешки')):
        return 'flexible'
    return None


def check_missing(order: dict) -> str | None:
    asked: list = order.setdefault('_asked', [])

    # ── Обязательные поля ────────────────────────────────────
    if not order.get('product_type'):
        return 'Уточните, пожалуйста: что нужно напечатать? (визитки, листовки, буклет, книга, брошюра...)'

    if not order.get('quantity'):
        return 'Сколько экземпляров нужно? Укажите тираж.'

    dims = order.get('dimensions', {})
    if not dims.get('width_mm') or not dims.get('height_mm'):
        return 'Укажите формат изделия, например: А4 (210×297 мм), А5 (148×210 мм), визитка (90×50 мм).'

    if not order.get('materials'):
        return ('Какой материал использовать? Например: мелованная бумага 130 г/м², '
                'офсет 80 г/м², картон 300 г/м².')

    # ── Уточняющие вопросы (задаются по одному, каждый раз один) ─
    pd = order.get('print_details', {})
    if not pd.get('colors') and 'colors' not in asked:
        asked.append('colors')
        return ('Укажите цветность печати:\n'
                '• 4+4 — полноцвет с двух сторон\n'
                '• 4+0 — полноцвет с одной стороны\n'
                '• 1+0 — чёрно-белая')

    if not pd.get('sides') and 'sides' not in asked:
        asked.append('sides')
        return 'Сколько сторон нужно напечатать — одна или две?'

    if not order.get('finishing') and 'finishing' not in asked:
        asked.append('finishing')
        return ('Нужна постпечатная обработка?\n'
                'Например: ламинирование, биговка, фальцовка, скругление углов, навивка на пружину '
                '— или без обработки.')

    if not order.get('deadline', {}).get('date') and 'deadline' not in asked:
        asked.append('deadline')
        return 'Укажите желаемый срок выполнения заказа, или напишите «срок не важен».'

    return None
