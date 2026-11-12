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


_MANUAL_UI = {
    'es': {
        'back': 'Volver a la aplicación',
        'download': 'Descargar PDF',
        'print': 'Imprimir',
        'edition': 'Edición',
        'search_label': 'Buscador rápido:',
        'search_ph': 'Buscar apartado, control o término (ej. sangrado, TAC, CIP3)...',
        'search_tip': 'Escribe 2 o más letras para filtrar capítulos y términos al instante (Esc para limpiar).',
        'matches_tpl': '{n} coincidencias en {c} capítulos',
        'no_matches': 'Sin coincidencias para esa búsqueda',
        'role_title': 'Ruta por perfil:',
        'roles': {'all': 'Todos', 'designer': '🎨 Diseñador', 'workshop': '🏭 Taller', 'teacher': '👨‍🏫 Docente', 'student': '🎓 Alumno'},
        'role_descs': {
            'all': 'Mostrando los 9 capítulos completos del manual de usuario.',
            'designer': '🎨 <strong>Ruta Diseñador / Creativo / Cliente:</strong> Capítulos recomendados: 1, 2, 3, 4 y 8 (preparación de arte final, sangrado +3 mm, sRGB vs CMYK, interpretación de la Guía de Arte Final y Portal de Visto Bueno digital).',
            'workshop': '🏭 <strong>Ruta Técnico de Taller / Preimpresión:</strong> Capítulos recomendados: 1, 2, 3, 4, 5, 6 y 8 (preflight profundo GWG, correcciones en 1 clic, imposición de pliegos, marcas FOGRA, CIP3 PPF y Hot-Folder de taller).',
            'teacher': '👨‍🏫 <strong>Ruta Docente de Formación Profesional:</strong> Capítulos recomendados: 1, 2, 3, 7 y 8 (catálogo de 20 retos formativos, diseño de perfiles personalizados de preflight para prácticas y rúbricas de evaluación FP).',
            'student': '🎓 <strong>Ruta Estudiante / Alumno de FP:</strong> Capítulos recomendados: 1, 4, 5, 7, 8 y 9 (metodología de resolución de incidencias, cuestionario técnico con retroalimentación, simuladores de defectos de imprenta y glosario).',
        },
        'lang_note': '',
    },
    'eu': {
        'back': 'Itzuli aplikaziora',
        'download': 'Deskargatu PDFa',
        'print': 'Inprimatu',
        'edition': 'Edizioa',
        'search_label': 'Bilatzaile azkarra:',
        'search_ph': 'Bilatu atala, kontrola edo terminoa (adib. sangradua, TAC, CIP3)...',
        'search_tip': 'Idatzi 2 letra edo gehiago atalak eta terminoak berehala iragazteko (Esc garbitzeko).',
        'matches_tpl': '{n} bat-etortze {c} kapitulutan',
        'no_matches': 'Ez dago emaitzarik bilaketa horretarako',
        'role_title': 'Profilaren araberako ibilbidea:',
        'roles': {'all': 'Guztiak', 'designer': '🎨 Diseinatzailea', 'workshop': '🏭 Tailerra', 'teacher': '👨‍🏫 Irakaslea', 'student': '🎓 Ikaslea'},
        'role_descs': {
            'all': 'Erabiltzaile-eskuliburuko 9 kapituluak osorik erakusten.',
            'designer': '🎨 <strong>Diseinatzaile / Sortzaile / Bezero Ibilbidea:</strong> Gomendatutako kapituluak: 1, 2, 3, 4 eta 8 (azken artea prestatzea, +3 mm odoljarioa, sRGB vs CMYK, Azken Artearen Gida eta Bezeroaren Oniritzi Portala).',
            'workshop': '🏭 <strong>Tailerreko Teknikari / Aurreinprimaketa Ibilbidea:</strong> Gomendatutako kapituluak: 1, 2, 3, 4, 5, 6 eta 8 (GWG aurreegiaztapena, 1 klika zuzenketak, pleguen inposizioa, FOGRA markak, CIP3 PPF eta Hot-Folder).',
            'teacher': '👨‍🏫 <strong>LHko Irakasle Ibilbidea:</strong> Gomendatutako kapituluak: 1, 2, 3, 7 eta 8 (20 erronka didaktiko, neurrira egindako profilak eta ebaluazio-errubrikak).',
            'student': '🎓 <strong>LHko Ikasle Ibilbidea:</strong> Gomendatutako kapituluak: 1, 4, 5, 7, 8 eta 9 (gorabeherak konpontzeko metodologia, galdetegi teknikoa eta simulagailuak).',
        },
        'lang_note': 'Nabigazioa, bilatzailea eta ibilbideak euskaraz daude; testu tekniko osoa gaztelaniaz kontsultatzen da.',
    },
    'en': {
        'back': 'Back to application',
        'download': 'Download PDF',
        'print': 'Print',
        'edition': 'Edition',
        'search_label': 'Quick search:',
        'search_ph': 'Search section, control or term (e.g. bleed, TAC, CIP3)...',
        'search_tip': 'Type 2+ characters to filter chapters and terms instantly (Esc to clear).',
        'matches_tpl': '{n} matches across {c} chapters',
        'no_matches': 'No matches found for that query',
        'role_title': 'Reading path by role:',
        'roles': {'all': 'All', 'designer': '🎨 Designer', 'workshop': '🏭 Pressroom', 'teacher': '👨‍🏫 Teacher', 'student': '🎓 Student'},
        'role_descs': {
            'all': 'Showing all 9 chapters of the user manual.',
            'designer': '🎨 <strong>Designer / Client Path:</strong> Recommended chapters: 1, 2, 3, 4 & 8 (artwork prep, +3 mm bleed, sRGB vs CMYK, Client Artwork Guide & digital Approval Portal).',
            'workshop': '🏭 <strong>Prepress & Pressroom Path:</strong> Recommended chapters: 1, 2, 3, 4, 5, 6 & 8 (deep GWG preflight, 1-click fixes, imposition, FOGRA strips, CIP3 PPF & workshop Hot-Folder).',
            'teacher': '👨‍🏫 <strong>VET Teacher Path:</strong> Recommended chapters: 1, 2, 3, 7 & 8 (20 didactic challenges, custom exam profiles, weighted rubrics & competency analytics).',
            'student': '🎓 <strong>VET Student Path:</strong> Recommended chapters: 1, 4, 5, 7, 8 & 9 (troubleshooting workflow, technical quiz with feedback, press simulators & glossary).',
        },
        'lang_note': 'Navigation, search and reading paths are in English; canonical reference sections remain in Spanish.',
    },
}


def render_manual_page(embedded=False, lang='es'):
    lang = lang if lang in _MANUAL_UI else 'es'
    ui = _MANUAL_UI[lang]
    chapters = [b for b in parse_manual() if b['kind'] == 'heading' and b['level'] == 2]
    toc_items = []
    for b in chapters:
        roles = CHAPTER_ROLES.get(b['anchor'], ['designer', 'workshop', 'teacher', 'student'])
        roles_attr = ' '.join(roles)
        toc_items.append(f'<li data-roles="{roles_attr}" data-anchor="{b["anchor"]}"><a href="#{b["anchor"]}">{html.escape(b["text"])}</a></li>')
    toc = ''.join(toc_items)
    embedded_class = ' embedded' if embedded else ''
    article_html = render_manual_article()
    embed_qs = '&embed=1' if embedded else ''
    lang_links = ''.join(
        f'<a href="/manual?lang={code}{embed_qs}" class="lang-pill{" active" if code == lang else ""}">{code.upper()}</a>'
        for code in ('es', 'eu', 'en')
    )
    lang_note_html = f'<p class="lang-note">{html.escape(ui["lang_note"])}</p>' if ui['lang_note'] else ''
    role_descs_json = (
        f'all: {ui["role_descs"]["all"]!r}, '
        f'designer: {ui["role_descs"]["designer"]!r}, '
        f'workshop: {ui["role_descs"]["workshop"]!r}, '
        f'teacher: {ui["role_descs"]["teacher"]!r}, '
        f'student: {ui["role_descs"]["student"]!r}'
    )
    return f'''<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{MANUAL_TITLE} {ui["edition"]} {MANUAL_EDITION}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f6fa;color:#17212c;font:16px/1.65 system-ui,sans-serif}}
header{{background:white;border-bottom:1px solid #d9dfe7;padding:16px 24px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}}
header img{{width:42px;height:42px;object-fit:contain}}header strong{{font-size:19px;color:#000}}header a,button{{font:inherit}}
.actions{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-left:auto}}a{{color:#174ea6;text-decoration-thickness:1px;text-underline-offset:3px}}
button{{background:white;border:1px solid #b9c7d5;border-radius:6px;padding:4px 12px;cursor:pointer}}
.lang-pills{{display:inline-flex;gap:4px;background:#f1f4f7;border:1px solid #d0dae4;border-radius:8px;padding:2px}}
.lang-pill{{text-decoration:none;font-size:11.5px;font-weight:700;padding:3px 8px;border-radius:6px;color:#334155}}
.lang-pill.active{{background:#1a73e8;color:white}}
.layout{{display:grid;grid-template-columns:280px minmax(0,960px);gap:28px;max-width:1280px;margin:24px auto;padding:0 24px}}
nav{{position:sticky;top:16px;align-self:start;background:white;padding:18px;border:1px solid #d9dfe7;border-radius:8px;max-height:calc(100vh - 32px);overflow-y:auto}}
.nav-header{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px;font-size:14px;color:#202124}}
.search-box{{margin:0 0 12px;position:relative}}
.search-input-wrap{{position:relative;display:flex;align-items:center}}
#manualSearchInput{{width:100%;padding:7px 28px 7px 10px;border:1px solid #c5d0dc;border-radius:6px;font-size:13px;outline:none;background:#f8fafc}}
#manualSearchInput:focus{{border-color:#1a73e8;background:white;box-shadow:0 0 0 2px rgba(26,115,232,.15)}}
#manualSearchClear{{position:absolute;right:6px;border:0;background:transparent;padding:2px 6px;font-size:15px;color:#64748b;display:none;line-height:1}}
#manualSearchMeta{{display:block;margin-top:5px;font-size:11.5px;color:#174ea6;font-weight:600}}
.role-selector{{margin:0 0 14px;padding:12px 0;border-top:1px solid #e8eaed;border-bottom:1px solid #e8eaed}}
.role-title{{display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#5f6368;margin-bottom:8px}}
.role-pills{{display:flex;flex-wrap:wrap;gap:5px}}
.role-btn{{background:#f1f4f7;border:1px solid #c5d0dc;border-radius:12px;padding:3px 9px;font-size:11.5px;font-weight:600;cursor:pointer;color:#333;transition:all .15s;line-height:1.3}}
.role-btn:hover{{background:#e2ecf7;border-color:#1a73e8;color:#1a73e8}}
.role-btn.active{{background:#1a73e8;color:white;border-color:#1557b0}}
.role-banner{{background:#e8f0fe;border-left:4px solid #1a73e8;padding:9px 11px;margin:0 0 14px;border-radius:4px;font-size:12px;line-height:1.45;color:#174ea6}}
.lang-note{{background:#f8fafc;border:1px solid #e2e8f0;padding:7px 9px;border-radius:6px;font-size:11.5px;color:#475569;margin:0 0 12px}}
nav ol{{padding-left:0;list-style:none;margin:0 0 12px}}nav li{{margin:8px 0;font-size:13.5px;transition:opacity .2s}}
nav li.highlighted a{{font-weight:700;color:#1a73e8}}
nav li.highlighted::before{{content:"✓ ";color:#1a73e8;font-weight:700}}
nav li.dimmed{{opacity:.38}}
nav li.search-hidden{{display:none}}
.search-tip{{font-size:12px;color:#5f6368;margin:0}}
article{{background:white;border:1px solid #d9dfe7;border-radius:8px;padding:32px 38px;min-width:0}}
article .search-hit{{background:#fef9c3;border-left:4px solid #eab308;padding:4px 8px;border-radius:4px}}
article .search-dimmed{{display:none}}
h1,h2,h3,h4{{color:#000;line-height:1.25;scroll-margin-top:22px}}h1{{font-size:32px;margin:0 0 20px}}h2{{font-size:26px;margin:44px 0 18px;transition:background-color .2s}}
h2.highlighted{{background:#f0f6ff;padding:6px 10px;border-left:5px solid #1a73e8;border-radius:0 6px 6px 0}}
h2.dimmed{{opacity:.45}}
h3{{font-size:21px;margin:30px 0 12px}}h4{{font-size:17px;margin:22px 0 10px;color:#174ea6}}p{{margin:0 0 15px}}li{{margin:6px 0}}
.table-scroll{{overflow-x:auto;margin:18px 0 24px}}table{{border-collapse:collapse;width:100%;font-size:14px;line-height:1.5}}
th,td{{border:1px solid #d9d9d9;padding:10px 12px;vertical-align:middle;text-align:left}}th{{background:#e8f0fa;color:#000}}
tbody tr:nth-child(even){{background:#f7f9fc}}code{{font-size:.9em;background:#f1f4f7;padding:1px 4px}}.embedded header{{display:none}}
@media(max-width:850px){{.layout{{display:block;margin:12px auto;padding:0 12px}}nav{{position:static;margin-bottom:12px;max-height:none}}article{{padding:24px 18px}}h1{{font-size:27px}}}}
@media print{{body{{background:white;font:10.5pt/1.4 Arial,sans-serif}}header,nav{{display:none!important}}.layout{{display:block;margin:0;padding:0;max-width:none}}article{{border:0;padding:0}}h2,h3,h4{{break-after:avoid}}tr{{break-inside:avoid}}thead{{display:table-header-group}}.table-scroll{{overflow:visible}}a{{color:inherit}}@page{{size:A4;margin:18mm}}}}
</style></head><body class="{embedded_class.strip()}">
<header><img src="/assets/Logo-intelliprint-imago.png" alt=""><strong>{MANUAL_TITLE}</strong><div class="actions">
<div class="lang-pills" aria-label="Idioma / Hizkuntza / Language">{lang_links}</div>
<a href="/">{ui["back"]}</a><a href="/api/manual/download/pdf">{ui["download"]}</a><button onclick="window.print()">{ui["print"]}</button></div></header>
<div class="layout"><nav aria-label="Índice del manual">
<div class="nav-header"><strong>{ui["edition"]} {MANUAL_EDITION}</strong><div class="lang-pills">{lang_links}</div></div>
{lang_note_html}
<div class="search-box">
<label for="manualSearchInput" class="role-title">{html.escape(ui["search_label"])}</label>
<div class="search-input-wrap">
<input type="search" id="manualSearchInput" placeholder="{html.escape(ui["search_ph"])}" autocomplete="off">
<button type="button" id="manualSearchClear" aria-label="Limpiar búsqueda">×</button>
</div>
<span id="manualSearchMeta"></span>
</div>
<div class="role-selector" aria-label="Seleccionar perfil de lectura">
<span class="role-title">{html.escape(ui["role_title"])}</span>
<div class="role-pills">
<button type="button" class="role-btn active" data-filter="all">{ui["roles"]["all"]}</button>
<button type="button" class="role-btn" data-filter="designer">{ui["roles"]["designer"]}</button>
<button type="button" class="role-btn" data-filter="workshop">{ui["roles"]["workshop"]}</button>
<button type="button" class="role-btn" data-filter="teacher">{ui["roles"]["teacher"]}</button>
<button type="button" class="role-btn" data-filter="student">{ui["roles"]["student"]}</button>
</div></div>
<div id="role-banner" class="role-banner" style="display:none;"></div>
<ol>{toc}</ol><p class="search-tip">{html.escape(ui["search_tip"])}</p></nav>
<article aria-label="Manual completo">{article_html}</article></div>
<script>
(function() {{
  const roleDescs = {{
    {role_descs_json}
  }};
  const matchesTpl = {ui["matches_tpl"]!r};
  const noMatchesMsg = {ui["no_matches"]!r};
  const buttons = document.querySelectorAll('.role-btn');
  const banner = document.getElementById('role-banner');
  const tocItems = document.querySelectorAll('nav ol li');
  const headings = document.querySelectorAll('article h2[data-roles]');
  const searchInput = document.getElementById('manualSearchInput');
  const clearBtn = document.getElementById('manualSearchClear');
  const metaEl = document.getElementById('manualSearchMeta');
  const articleEl = document.querySelector('article');
  let activeRole = 'all';

  function normText(s) {{
    return String(s || '').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
  }}

  // Agrupar cada bloque de article bajo su capítulo H2
  const blocks = articleEl ? Array.from(articleEl.children) : [];
  let currentChapter = 'intro';
  const chapterGroups = new Map();
  blocks.forEach((el) => {{
    if (el.tagName === 'H2' && el.id) currentChapter = el.id;
    el.dataset.chapter = currentChapter;
    if (!chapterGroups.has(currentChapter)) chapterGroups.set(currentChapter, []);
    chapterGroups.get(currentChapter).push(el);
  }});

  function applySearchAndRole() {{
    const q = normText(searchInput ? searchInput.value.trim() : '');
    const isSearching = q.length >= 2;
    if (clearBtn) clearBtn.style.display = (searchInput && searchInput.value) ? 'block' : 'none';

    const matchedChapters = new Set();
    let hitCount = 0;

    blocks.forEach((el) => {{
      el.classList.remove('search-hit', 'search-dimmed');
      if (!isSearching) return;
      const text = normText(el.textContent);
      if (text.includes(q)) {{
        el.classList.add('search-hit');
        matchedChapters.add(el.dataset.chapter);
        hitCount += 1;
      }}
    }});

    if (isSearching) {{
      blocks.forEach((el) => {{
        if (!matchedChapters.has(el.dataset.chapter)) el.classList.add('search-dimmed');
      }});
      if (metaEl) {{
        metaEl.textContent = hitCount
          ? matchesTpl.replace('{{n}}', String(hitCount)).replace('{{c}}', String(matchedChapters.size))
          : noMatchesMsg;
      }}
    }} else if (metaEl) {{
      metaEl.textContent = '';
    }}

    buttons.forEach(btn => btn.classList.toggle('active', btn.dataset.filter === activeRole));
    if (activeRole === 'all') {{
      banner.style.display = 'none';
      tocItems.forEach(li => {{
        li.classList.remove('dimmed', 'highlighted');
        li.classList.toggle('search-hidden', isSearching && !matchedChapters.has(li.dataset.anchor));
      }});
      headings.forEach(h => {{ h.classList.remove('dimmed', 'highlighted'); }});
    }} else {{
      banner.innerHTML = roleDescs[activeRole] || '';
      banner.style.display = 'block';
      tocItems.forEach(li => {{
        const roles = (li.dataset.roles || '').split(' ');
        const matches = roles.includes(activeRole);
        li.classList.toggle('highlighted', matches);
        li.classList.toggle('dimmed', !matches);
        li.classList.toggle('search-hidden', isSearching && !matchedChapters.has(li.dataset.anchor));
      }});
      headings.forEach(h => {{
        const roles = (h.dataset.roles || '').split(' ');
        const matches = roles.includes(activeRole);
        h.classList.toggle('highlighted', matches);
        h.classList.toggle('dimmed', !matches);
      }});
    }}
  }}

  buttons.forEach(btn => {{
    btn.addEventListener('click', () => {{
      activeRole = btn.dataset.filter;
      applySearchAndRole();
    }});
  }});

  if (searchInput) {{
    searchInput.addEventListener('input', applySearchAndRole);
    searchInput.addEventListener('keydown', (ev) => {{
      if (ev.key === 'Escape') {{
        searchInput.value = '';
        applySearchAndRole();
      }}
    }});
  }}
  if (clearBtn) {{
    clearBtn.addEventListener('click', () => {{
      if (searchInput) searchInput.value = '';
      applySearchAndRole();
      if (searchInput) searchInput.focus();
    }});
  }}
}})();
</script>
</body></html>'''
