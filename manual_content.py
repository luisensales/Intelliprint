"""Canonical manual content shared by Markdown, web, Word and PDF outputs."""

import html
import re
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).parent
MANUAL_SOURCE = BASE_DIR / 'MANUAL_DE_USUARIO_INTELLIPRINT.md'
MANUAL_EDITION = '2026.11.2'
MANUAL_UPDATED = '2026-11-12'
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


CHAPTER_ROLES = {
    '1-uso-del-manual-y-conceptos-de-trabajo': ['designer', 'workshop', 'teacher', 'student'],
    '2-acceso-y-navegacion-de-la-interfaz': ['designer', 'workshop', 'teacher'],
    '3-archivo-de-entrada-perfiles-e-icc': ['designer', 'workshop', 'teacher'],
    '4-lectura-y-revision-del-informe': ['designer', 'workshop', 'teacher', 'student'],
    '5-correcciones-y-taller-en-1-clic': ['workshop', 'student'],
    '6-modulos-de-produccion': ['workshop'],
    '7-modo-didactico-para-formacion-profesional': ['teacher', 'student'],
    '8-descargas-archivo-de-trabajos-y-manuales': ['designer', 'workshop', 'teacher', 'student'],
    '9-preguntas-frecuentes-y-verificacion-final': ['student', 'workshop'],
}


def render_manual_article():
    rendered = []
    for block in parse_manual():
        kind = block['kind']
        if kind == 'heading':
            level = min(block['level'], 4)
            roles_attr = ''
            if block['level'] == 2:
                roles = CHAPTER_ROLES.get(block['anchor'], ['designer', 'workshop', 'teacher', 'student'])
                roles_attr = f' data-roles="{" ".join(roles)}"'
            rendered.append(f'<h{level} id="{block["anchor"]}"{roles_attr}>{inline_html(block["text"])}</h{level}>')
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
    toc_items = []
    for b in chapters:
        roles = CHAPTER_ROLES.get(b['anchor'], ['designer', 'workshop', 'teacher', 'student'])
        roles_attr = ' '.join(roles)
        toc_items.append(f'<li data-roles="{roles_attr}"><a href="#{b["anchor"]}">{html.escape(b["text"])}</a></li>')
    toc = ''.join(toc_items)
    embedded_class = ' embedded' if embedded else ''
    article_html = render_manual_article()
    return f'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{MANUAL_TITLE} Edición {MANUAL_EDITION}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f6fa;color:#17212c;font:16px/1.65 system-ui,sans-serif}}
header{{background:white;border-bottom:1px solid #d9dfe7;padding:16px 24px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}}
header img{{width:42px;height:42px;object-fit:contain}}header strong{{font-size:19px;color:#000}}header a,button{{font:inherit}}
.actions{{display:flex;gap:12px;flex-wrap:wrap;margin-left:auto}}a{{color:#174ea6;text-decoration-thickness:1px;text-underline-offset:3px}}
button{{background:white;border:1px solid #b9c7d5;border-radius:6px;padding:4px 12px;cursor:pointer}}
.layout{{display:grid;grid-template-columns:260px minmax(0,960px);gap:28px;max-width:1280px;margin:24px auto;padding:0 24px}}
nav{{position:sticky;top:16px;align-self:start;background:white;padding:18px;border:1px solid #d9dfe7;border-radius:8px}}
.nav-header{{margin-bottom:12px;font-size:14px;color:#202124}}
.role-selector{{margin:0 0 14px;padding:12px 0;border-top:1px solid #e8eaed;border-bottom:1px solid #e8eaed}}
.role-title{{display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#5f6368;margin-bottom:8px}}
.role-pills{{display:flex;flex-wrap:wrap;gap:5px}}
.role-btn{{background:#f1f4f7;border:1px solid #c5d0dc;border-radius:12px;padding:3px 9px;font-size:11.5px;font-weight:600;cursor:pointer;color:#333;transition:all .15s;line-height:1.3}}
.role-btn:hover{{background:#e2ecf7;border-color:#1a73e8;color:#1a73e8}}
.role-btn.active{{background:#1a73e8;color:white;border-color:#1557b0}}
.role-banner{{background:#e8f0fe;border-left:4px solid #1a73e8;padding:9px 11px;margin:0 0 14px;border-radius:4px;font-size:12px;line-height:1.45;color:#174ea6}}
nav ol{{padding-left:0;list-style:none;margin:0 0 12px}}nav li{{margin:8px 0;font-size:13.5px;transition:opacity .2s}}
nav li.highlighted a{{font-weight:700;color:#1a73e8}}
nav li.highlighted::before{{content:"✓ ";color:#1a73e8;font-weight:700}}
nav li.dimmed{{opacity:.38}}
.search-tip{{font-size:12px;color:#5f6368;margin:0}}
article{{background:white;border:1px solid #d9dfe7;border-radius:8px;padding:32px 38px;min-width:0}}
h1,h2,h3,h4{{color:#000;line-height:1.25;scroll-margin-top:22px}}h1{{font-size:32px;margin:0 0 20px}}h2{{font-size:26px;margin:44px 0 18px;transition:background-color .2s}}
h2.highlighted{{background:#f0f6ff;padding:6px 10px;border-left:5px solid #1a73e8;border-radius:0 6px 6px 0}}
h2.dimmed{{opacity:.45}}
h3{{font-size:21px;margin:30px 0 12px}}h4{{font-size:17px;margin:22px 0 10px;color:#174ea6}}p{{margin:0 0 15px}}li{{margin:6px 0}}
.table-scroll{{overflow-x:auto;margin:18px 0 24px}}table{{border-collapse:collapse;width:100%;font-size:14px;line-height:1.5}}
th,td{{border:1px solid #d9d9d9;padding:10px 12px;vertical-align:middle;text-align:left}}th{{background:#e8f0fa;color:#000}}
tbody tr:nth-child(even){{background:#f7f9fc}}code{{font-size:.9em;background:#f1f4f7;padding:1px 4px}}.embedded header{{display:none}}
@media(max-width:850px){{.layout{{display:block;margin:12px auto;padding:0 12px}}nav{{position:static;margin-bottom:12px}}article{{padding:24px 18px}}h1{{font-size:27px}}}}
@media print{{body{{background:white;font:10.5pt/1.4 Arial,sans-serif}}header,nav{{display:none!important}}.layout{{display:block;margin:0;padding:0;max-width:none}}article{{border:0;padding:0}}h2,h3,h4{{break-after:avoid}}tr{{break-inside:avoid}}thead{{display:table-header-group}}.table-scroll{{overflow:visible}}a{{color:inherit}}@page{{size:A4;margin:18mm}}}}
</style></head><body class="{embedded_class.strip()}">
<header><img src="/assets/Logo-intelliprint-imago.png" alt=""><strong>{MANUAL_TITLE}</strong><div class="actions">
<a href="/">Volver a la aplicación</a><a href="/api/manual/download/pdf">Descargar PDF</a><button onclick="window.print()">Imprimir</button></div></header>
<div class="layout"><nav aria-label="Índice del manual">
<div class="nav-header"><strong>Edición {MANUAL_EDITION}</strong></div>
<div class="role-selector" aria-label="Seleccionar perfil de lectura">
<span class="role-title">Ruta por perfil:</span>
<div class="role-pills">
<button type="button" class="role-btn active" data-filter="all">Todos</button>
<button type="button" class="role-btn" data-filter="designer">🎨 Diseñador</button>
<button type="button" class="role-btn" data-filter="workshop">🏭 Taller</button>
<button type="button" class="role-btn" data-filter="teacher">👨‍🏫 Docente</button>
<button type="button" class="role-btn" data-filter="student">🎓 Alumno</button>
</div></div>
<div id="role-banner" class="role-banner" style="display:none;"></div>
<ol>{toc}</ol><p class="search-tip">Usa la búsqueda del navegador para localizar un control.</p></nav>
<article aria-label="Manual completo">{article_html}</article></div>
<script>
(function() {{
  const roleDescs = {{
    all: 'Mostrando los 9 capítulos completos del manual de usuario.',
    designer: '🎨 <strong>Ruta Diseñador / Creativo / Cliente:</strong> Capítulos recomendados: 1, 2, 3, 4 y 8 (preparación de arte final, sangrado +3 mm, sRGB vs CMYK, interpretación de la Guía de Arte Final y Portal de Visto Bueno digital).',
    workshop: '🏭 <strong>Ruta Técnico de Taller / Preimpresión:</strong> Capítulos recomendados: 1, 2, 3, 4, 5, 6 y 8 (preflight profundo GWG, correcciones en 1 clic, imposición de pliegos, marcas FOGRA, CIP3 PPF y Hot-Folder de taller).',
    teacher: '👨‍🏫 <strong>Ruta Docente de Formación Profesional:</strong> Capítulos recomendados: 1, 2, 3, 7 y 8 (catálogo de 20 retos formativos, diseño de perfiles personalizados de preflight para prácticas y rúbricas de evaluación FP).',
    student: '🎓 <strong>Ruta Estudiante / Alumno de FP:</strong> Capítulos recomendados: 1, 4, 5, 7, 8 y 9 (metodología de resolución de incidencias, cuestionario técnico con retroalimentación, simuladores de defectos de imprenta y glosario).'
  }};
  const buttons = document.querySelectorAll('.role-btn');
  const banner = document.getElementById('role-banner');
  const tocItems = document.querySelectorAll('nav ol li');
  const headings = document.querySelectorAll('article h2[data-roles]');

  function applyRole(role) {{
    buttons.forEach(btn => btn.classList.toggle('active', btn.dataset.filter === role));
    if (role === 'all') {{
      banner.style.display = 'none';
      tocItems.forEach(li => {{ li.classList.remove('dimmed', 'highlighted'); }});
      headings.forEach(h => {{ h.classList.remove('dimmed', 'highlighted'); }});
    }} else {{
      banner.innerHTML = roleDescs[role] || '';
      banner.style.display = 'block';
      tocItems.forEach(li => {{
        const roles = (li.dataset.roles || '').split(' ');
        const matches = roles.includes(role);
        li.classList.toggle('highlighted', matches);
        li.classList.toggle('dimmed', !matches);
      }});
      headings.forEach(h => {{
        const roles = (h.dataset.roles || '').split(' ');
        const matches = roles.includes(role);
        h.classList.toggle('highlighted', matches);
        h.classList.toggle('dimmed', !matches);
      }});
    }}
  }}

  buttons.forEach(btn => {{
    btn.addEventListener('click', () => applyRole(btn.dataset.filter));
  }});
}})();
</script>
</body></html>'''
