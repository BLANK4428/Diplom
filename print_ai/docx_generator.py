import datetime
import io

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# ── Helpers ───────────────────────────────────────────────────────────────────


def _hide_table_borders(table) -> None:
    """Make all borders of a table invisible."""
    tbl = table._tbl
    tblPr = tbl.find(qn('w:tblPr'))
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        tbl.insert(0, tblPr)
    tblBorders = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'), 'none')
        tblBorders.append(el)
    tblPr.append(tblBorders)


def _para(text: str, doc, bold=False, size=10,
          align=WD_ALIGN_PARAGRAPH.LEFT, color=None, space_after=0) -> None:
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor(*color)
    return p


def _set_col_width(table, col_idx: int, width_cm: float) -> None:
    for row in table.rows:
        row.cells[col_idx].width = Cm(width_cm)


# ── Document builder ──────────────────────────────────────────────────────────

def build_doc(order: dict) -> tuple[bytes, str]:
    """Build styled DOCX in memory. Returns (file_bytes, filename)."""
    doc = Document()
    now = datetime.datetime.now()

    # ── Page margins ──────────────────────────────────────────
    section = doc.sections[0]
    section.top_margin    = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin   = Cm(2.5)
    section.right_margin  = Cm(2)

    # ── Header: company info (right) ──────────────────────────
    hdr_table = doc.add_table(rows=1, cols=2)
    _hide_table_borders(hdr_table)
    hdr_table.columns[0].width = Cm(9)
    hdr_table.columns[1].width = Cm(7.5)

    # Left cell — empty (space for title below)
    hdr_table.cell(0, 0).text = ''

    # Right cell — company block
    rc = hdr_table.cell(0, 1)
    lines = [
        ('Типография «Опера-принт»', True),
        ('Полиграфические услуги', False),
        ('', False),
        ('Менеджер: ________________________', False),
        ('Тел.: +7 (___) ___-__-__', False),
        ('Email: info@opera-print.ru', False),
    ]
    for i, (line, bold) in enumerate(lines):
        p = rc.paragraphs[0] if i == 0 else rc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_after = Pt(1)
        run = p.add_run(line)
        run.font.size = Pt(9)
        run.bold = bold

    doc.add_paragraph()

    # ── Title ─────────────────────────────────────────────────
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(6)
    run = title.add_run('Коммерческое предложение')
    run.bold = True
    run.font.size = Pt(16)

    date_p = doc.add_paragraph()
    date_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_p.paragraph_format.space_after = Pt(14)
    run = date_p.add_run(now.strftime('%d.%m.%Y'))
    run.font.size = Pt(9)

    # ── Intro ─────────────────────────────────────────────────
    dims = order.get('dimensions', {})
    w, h, d = dims.get('width_mm'), dims.get('height_mm'), dims.get('depth_mm')
    size_str = f'{w} × {h} мм' if w and h else None
    if size_str and d:
        size_str += f' × {d} мм'

    materials = order.get('materials') or []
    finishing = order.get('finishing') or []
    pd_info   = order.get('print_details') or {}
    deadline  = order.get('deadline') or {}
    urgency_map = {'urgent': 'Срочный', 'normal': 'Стандартный', 'flexible': 'Гибкий'}

    intro = doc.add_paragraph()
    intro.paragraph_format.space_after = Pt(10)
    run = intro.add_run(
        f'Благодарим за обращение в типографию «Опера-принт». '
        f'На основании вашей заявки от {now.strftime("%d.%m.%Y")} мы подготовили '
        f'коммерческое предложение. Просим ознакомиться и подтвердить заказ.'
    )
    run.font.size = Pt(10)

    # ── «Вы запрашивали:» ─────────────────────────────────────
    def _section_title(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(11)

    def _bullet(text):
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(text)
        run.font.size = Pt(10)

    _section_title('Вы запрашивали:')

    bullets = []
    if order.get('product_type'):
        bullets.append(f"{order['product_type']}")
    if order.get('quantity'):
        bullets.append(f"тираж — {order['quantity']} шт.")
    if size_str:
        bullets.append(f"формат — {size_str}")
    if materials:
        bullets.append(f"материал — {', '.join(materials)}")
    if finishing:
        bullets.append(f"постпечатная обработка — {', '.join(finishing)}")
    if pd_info.get('colors'):
        bullets.append(f"цветность — {pd_info['colors']}")
    if pd_info.get('sides'):
        bullets.append(f"сторонность — {pd_info['sides']} ст.")
    if deadline.get('date'):
        bullets.append(f"срок выполнения — {deadline['date']}")
    if order.get('notes') or pd_info.get('notes'):
        bullets.append(f"примечания — {order.get('notes') or pd_info.get('notes')}")

    for b in bullets:
        _bullet(b)

    doc.add_paragraph()

    # ── «Мы предлагаем:» — таблица ────────────────────────────
    _section_title('Мы предлагаем:')

    tbl_rows = [
        ('Наименование', 'Характеристики', 'Тираж, шт.', 'Срок'),
        (
            order.get('product_type') or '—',
            (', '.join(materials) if materials else '—') +
            (f'; {", ".join(finishing)}' if finishing else '') +
            (f'; {pd_info["colors"]}' if pd_info.get('colors') else ''),
            str(order.get('quantity') or '—'),
            deadline.get('date') or '—',
        ),
    ]

    tbl = doc.add_table(rows=0, cols=4)
    tbl.style = 'Table Grid'
    col_widths = (Cm(4), Cm(7), Cm(2.5), Cm(3))

    for r_idx, row_data in enumerate(tbl_rows):
        row = tbl.add_row()
        is_header = (r_idx == 0)
        for c_idx, text in enumerate(row_data):
            cell = row.cells[c_idx]
            cell.width = col_widths[c_idx]
            run = cell.paragraphs[0].add_run(text)
            run.font.size = Pt(10)
            run.bold = is_header

    doc.add_paragraph()

    # ── Условия ───────────────────────────────────────────────
    _section_title('Условия:')

    deadline_note = ''
    if deadline.get('date'):
        deadline_note = f'Срок изготовления — до {deadline["date"]}. '
    urgency_label = urgency_map.get(deadline.get('urgency', 'normal'), 'Стандартный')

    for item in (
        f'{deadline_note}Приоритет исполнения: {urgency_label}.',
        'Гарантия качества — 2 месяца. При заводском браке — бесплатное переизготовление.',
        'Оплата: 50% предоплата при подтверждении, остаток — при получении заказа.',
    ):
        _bullet(item)

    doc.add_paragraph()

    # ── Подпись ───────────────────────────────────────────────
    outro = doc.add_paragraph()
    outro.paragraph_format.space_after = Pt(12)
    run = outro.add_run(
        'Ждём вашего подтверждения. Свяжитесь с нами любым удобным способом, '
        'контакты указаны в шапке документа.'
    )
    run.font.size = Pt(10)

    sig_tbl = doc.add_table(rows=3, cols=2)
    _hide_table_borders(sig_tbl)
    sig_tbl.columns[0].width = Cm(8)
    sig_tbl.columns[1].width = Cm(8.5)

    sig_data = [
        ('С уважением,', ''),
        ('Менеджер типографии «Опера-принт»', 'Подпись клиента:'),
        ('________________________', '________________________'),
    ]
    for r_idx, (left, right) in enumerate(sig_data):
        for c_idx, text in enumerate((left, right)):
            cell = sig_tbl.cell(r_idx, c_idx)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(text)
            run.font.size = Pt(10)
            run.bold = (r_idx == 1)

    doc.add_paragraph()

    note = doc.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = note.add_run('Документ сформирован автоматически системой Print AI')
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)
    run.italic = True

    # ── Serialize ─────────────────────────────────────────────
    filename = f'order_{now.strftime("%Y%m%d_%H%M%S")}.docx'
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), filename
