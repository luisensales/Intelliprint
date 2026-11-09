"""Canonical manual content shared by Markdown, web, Word and PDF outputs."""

import html
import re
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).parent
MANUAL_SOURCE = BASE_DIR / 'MANUAL_DE_USUARIO_INTELLIPRINT.md'
MANUAL_EDITION = '2026.11'
MANUAL_UPDATED = '2026-11-09'
MANUAL_TITLE = 'Manual de usuario de IntelliPrint'


def read_manual():
    return MANUAL_SOURCE.read_text(encoding='utf-8')


def anchor(text):
    plain = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', plain.lower()).strip('-')


def inline_parts(text):
    pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`')
    offset = 0
    for match in pattern.finditer(text):
        if match.start() > offset:
            yield 'text', text[offset:match.start()], None
        if match.group(1) is not None:
            yield 'link', match.group(1), match.group(2)
        elif match.group(3) is not None:
            yield 'bold', match.group(3), None
        else:
            yield 'code', match.group(4), None
        offset = match.end()
    if offset < len(text):
        yield 'text', text[offset:], None


def plain_text(text):
    return ''.join(value for _, value, _ in inline_parts(text))


def inline_html(text):
    output = []
    for kind, value, target in inline_parts(text):
        value = html.escape(value)
        if kind == 'bold':
            output.append(f'<strong>{value}</strong>')
        elif kind == 'code':
            output.append(f'<code>{value}</code>')
        elif kind == 'link':
            output.append(f'<a href="{html.escape(target, quote=True)}">{value}</a>')
        else:
            output.append(value)
    return ''.join(output)


def parse_manual(source=None):
    """Parse the intentionally small, documented Markdown subset used here."""
    source = read_manual() if source is None else source
    lines = re.sub(r'<!--.*?-->', '', source, flags=re.S).splitlines()
    blocks, paragraph = [], []

    def flush():
        if paragraph:
            blocks.append({'kind': 'paragraph', 'text': ' '.join(paragraph)})
            paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            flush()
        elif match := re.match(r'^(#{1,4})\s+(.+)$', line):
            flush()
            blocks.append({'kind': 'heading', 'level': len(match[1]), 'text': match[2], 'anchor': anchor(match[2])})
        elif line.startswith('|'):
            flush()
            rows = []
            while index < len(lines) and lines[index].strip().startswith('|'):
                row = [cell.strip() for cell in lines[index].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-{3,}:?', cell) for cell in row):
                    rows.append(row)
                index += 1
            if rows:
                if any(len(row) != len(rows[0]) for row in rows):
                    raise ValueError('Tabla del manual con columnas inconsistentes.')
                blocks.append({'kind': 'table', 'rows': rows})
            continue
        elif re.match(r'^\d+\.\s+', line):
            flush()
            items = []
            while index < len(lines) and re.match(r'^\d+\.\s+', lines[index].strip()):
                items.append(re.sub(r'^\d+\.\s+', '', lines[index].strip()))
                index += 1
            blocks.append({'kind': 'ordered_list', 'items': items})
            continue
        elif line.startswith('- '):
            flush()
            blocks.append({'kind': 'bullet', 'text': line[2:]})
        else:
            paragraph.append(line)
        index += 1
    flush()
    return blocks


def render_manual_article():
    rendered = []
    for block in parse_manual():
        kind = block['kind']
        if kind == 'heading':
            level = min(block['level'], 4)
            rendered.append(f'<h{level} id="{block["anchor"]}">{inline_html(block["text"])}</h{level}>')
        elif kind == 'paragraph':
            rendered.append(f'<p>{inline_html(block["text"])}</p>')
        elif kind == 'ordered_list':
            rendered.append('<ol>' + ''.join(f'<li>{inline_html(item)}</li>' for item in block['items']) + '</ol>')
        elif kind == 'bullet':
            rendered.append(f'<ul><li>{inline_html(block["text"])}</li></ul>')
        elif kind == 'table':
            rows = block['rows']
            header = '<tr>' + ''.join(f'<th scope="col">{inline_html(cell)}</th>' for cell in rows[0]) + '</tr>'
            body = ''.join('<tr>' + ''.join(f'<td>{inline_html(cell)}</td>' for cell in row) + '</tr>' for row in rows[1:])
            rendered.append(f'<div class="table-scroll"><table><thead>{header}</thead><tbody>{body}</tbody></table></div>')
    return '\n'.join(rendered)


def render_manual_page(embedded=False):
    chapters = [b for b in parse_manual() if b['kind'] == 'heading' and b['level'] == 2]
    toc = ''.join(f'<li><a href="#{b["anchor"]}">{html.escape(b["text"])}</a></li>' for b in chapters)
    embedded_class = ' embedded' if embedded else ''
    return f'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{MANUAL_TITLE} Edición {MANUAL_EDITION}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f6fa;color:#17212c;font:16px/1.65 system-ui,sans-serif}}
header{{background:white;border-bottom:1px solid #d9dfe7;padding:16px 24px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}}
header img{{width:42px;height:42px;object-fit:contain}}header strong{{font-size:19px;color:#000}}header a,button{{font:inherit}}
.actions{{display:flex;gap:12px;flex-wrap:wrap;margin-left:auto}}a{{color:#174ea6;text-decoration-thickness:1px;text-underline-offset:3px}}
button{{background:white;border:1px solid #b9c7d5;border-radius:6px;padding:4px 12px;cursor:pointer}}
.layout{{display:grid;grid-template-columns:235px minmax(0,960px);gap:28px;max-width:1260px;margin:24px auto;padding:0 24px}}
nav{{position:sticky;top:16px;align-self:start;background:white;padding:18px;border:1px solid #d9dfe7;border-radius:8px}}
nav ol{{padding-left:0;list-style:none}}nav li{{margin:8px 0;font-size:14px}}nav strong{{color:#000}}
article{{background:white;border:1px solid #d9dfe7;border-radius:8px;padding:32px 38px;min-width:0}}
h1,h2,h3,h4{{color:#000;line-height:1.25;scroll-margin-top:22px}}h1{{font-size:32px;margin:0 0 20px}}h2{{font-size:26px;margin:44px 0 18px}}
h3{{font-size:21px;margin:30px 0 12px}}h4{{font-size:18px;margin:22px 0 10px}}p{{margin:0 0 15px}}li{{margin:6px 0}}
.table-scroll{{overflow-x:auto;margin:18px 0 24px}}table{{border-collapse:collapse;width:100%;font-size:14px;line-height:1.5}}
th,td{{border:1px solid #d9d9d9;padding:10px 12px;vertical-align:middle;text-align:left}}th{{background:#e8f0fa;color:#000}}
tbody tr:nth-child(even){{background:#f7f9fc}}code{{font-size:.9em;background:#f1f4f7;padding:1px 4px}}.embedded header{{display:none}}
@media(max-width:850px){{.layout{{display:block;margin:12px auto;padding:0 12px}}nav{{position:static;margin-bottom:12px}}article{{padding:24px 18px}}h1{{font-size:27px}}}}
@media print{{body{{background:white;font:10.5pt/1.4 Arial,sans-serif}}header,nav{{display:none!important}}.layout{{display:block;margin:0;padding:0;max-width:none}}article{{border:0;padding:0}}h2,h3,h4{{break-after:avoid}}tr{{break-inside:avoid}}thead{{display:table-header-group}}.table-scroll{{overflow:visible}}a{{color:inherit}}@page{{size:A4;margin:18mm}}}}
</style></head><body class="{embedded_class.strip()}">
<header><img src="/assets/Logo-intelliprint-imago.png" alt=""><strong>{MANUAL_TITLE}</strong><div class="actions">
<a href="/">Volver a la aplicación</a><a href="/api/manual/download/pdf">PDF</a><a href="/api/manual/download/docx">Word</a><a href="/api/manual/download/md">Markdown</a><button onclick="window.print()">Imprimir</button></div></header>
<div class="layout"><nav aria-label="Índice del manual"><strong>Edición {MANUAL_EDITION}</strong><ol>{toc}</ol><p>Usa la búsqueda del navegador para localizar un control.</p></nav>
<article aria-label="Manual completo">{render_manual_article()}</article></div></body></html>'''
