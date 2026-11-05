import os
import re
import json
import pymupdf as fitz
import pikepdf
from decimal import Decimal
from pathlib import Path
from icc_manager import detect_pdf_output_intent
from spellcheck_engine import PrepressSpellChecker

VARNISH_KEYWORDS = ['barniz', 'varnish', 'laca', 'lacquer', 'uv', 'gloss', 'brillo', 'mate', 'matt', 'acabado', 'dieline', 'troquel', 'stamping']

def is_varnish_name(name):
    clean = re.sub(r'[^a-zA-Z0-9]', '', str(name)).lower()
    return any(k in clean for k in VARNISH_KEYWORDS)

def is_pantone_name(name):
    clean = re.sub(r'[^a-zA-Z0-9]', '', str(name)).lower()
    return 'pantone' in clean or 'pms' in clean

def resolve_cs(cs_ref, resources):
    if isinstance(cs_ref, pikepdf.Name):
        cs_str = str(cs_ref).lstrip('/')
        if resources and '/ColorSpace' in resources and cs_ref in resources['/ColorSpace']:
            return resolve_cs(resources['/ColorSpace'][cs_ref], resources)
        return (cs_str, None)
    elif isinstance(cs_ref, pikepdf.Array) and len(cs_ref) > 0:
        cs_type = str(cs_ref[0]).lstrip('/')
        if cs_type in ['Separation', 'DeviceN'] and len(cs_ref) > 1:
            spot_name = str(cs_ref[1]).lstrip('/')
            return (cs_type, spot_name)
        return (cs_type, None)
    return (str(cs_ref), None)

def scan_content_stream(commands, resources, page_num, overprint_data):
    ext_gstates = {}
    if resources and '/ExtGState' in resources:
        for k, v in resources['/ExtGState'].items():
            ext_gstates[k] = v

    xobjects = {}
    if resources and '/XObject' in resources:
        for k, v in resources['/XObject'].items():
            xobjects[k] = v

    state_stack = []
    state = {
        'op': False,
        'OP': False,
        'OPM': 0,
        'fill_cs': ('DeviceGray', None),
        'stroke_cs': ('DeviceGray', None),
        'fill_color': (0,),
        'stroke_color': (0,),
        'text_render_mode': 0
    }

    for operands, operator in commands:
        op_str = str(operator)

        if op_str == 'q':
            state_stack.append(dict(state))
        elif op_str == 'Q':
            if state_stack:
                state = state_stack.pop()
        elif op_str == 'gs':
            if operands and operands[0] in ext_gstates:
                gs_dict = ext_gstates[operands[0]]
                if '/op' in gs_dict:
                    state['op'] = bool(gs_dict['/op'])
                if '/OP' in gs_dict:
                    state['OP'] = bool(gs_dict['/OP'])
                if '/OPM' in gs_dict:
                    state['OPM'] = int(gs_dict['/OPM'])
        elif op_str == 'Tr':
            if operands:
                try:
                    state['text_render_mode'] = int(operands[0])
                except Exception:
                    pass
        elif op_str == 'g':
            state['fill_cs'] = ('DeviceGray', None)
            state['fill_color'] = tuple(float(x) for x in operands)
        elif op_str == 'G':
            state['stroke_cs'] = ('DeviceGray', None)
            state['stroke_color'] = tuple(float(x) for x in operands)
        elif op_str == 'k':
            state['fill_cs'] = ('DeviceCMYK', None)
            state['fill_color'] = tuple(float(x) for x in operands)
        elif op_str == 'K':
            state['stroke_cs'] = ('DeviceCMYK', None)
            state['stroke_color'] = tuple(float(x) for x in operands)
        elif op_str == 'rg':
            state['fill_cs'] = ('DeviceRGB', None)
            state['fill_color'] = tuple(float(x) for x in operands)
        elif op_str == 'RG':
            state['stroke_cs'] = ('DeviceRGB', None)
            state['stroke_color'] = tuple(float(x) for x in operands)
        elif op_str == 'cs':
            if operands:
                state['fill_cs'] = resolve_cs(operands[0], resources)
        elif op_str == 'CS':
            if operands:
                state['stroke_cs'] = resolve_cs(operands[0], resources)
        elif op_str in ['sc', 'scn']:
            state['fill_color'] = tuple(float(x) for x in operands if isinstance(x, (int, float, Decimal)))
        elif op_str in ['SC', 'SCN']:
            state['stroke_color'] = tuple(float(x) for x in operands if isinstance(x, (int, float, Decimal)))
        elif op_str == 'Do':
            if operands and operands[0] in xobjects:
                xobj = xobjects[operands[0]]
                if isinstance(xobj, pikepdf.Stream) and xobj.get('/Subtype') == '/Form':
                    sub_resources = xobj.get('/Resources', resources)
                    try:
                        sub_cmds = list(pikepdf.parse_content_stream(xobj))
                        scan_content_stream(sub_cmds, sub_resources, page_num, overprint_data)
                    except Exception:
                        pass

        # Text operations
        elif op_str in ['Tj', "'", '"', 'TJ']:
            mode = state['text_render_mode']
            is_fill = (mode in [0, 2])
            is_stroke = (mode in [1, 2])

            is_pure_black = False
            cs_type, spot_name = state['fill_cs']
            if cs_type == 'DeviceGray' and len(state['fill_color']) >= 1:
                if abs(state['fill_color'][0]) < 0.01:
                    is_pure_black = True
            elif cs_type == 'DeviceCMYK' and len(state['fill_color']) >= 4:
                c, m, y, k = state['fill_color'][:4]
                if c < 0.01 and m < 0.01 and y < 0.01 and k >= 0.99:
                    is_pure_black = True

            if is_pure_black and is_fill:
                if state['op']:
                    overprint_data["black_text_overprint"] += 1
                else:
                    overprint_data["black_text_knockout"] += 1
                    overprint_data["incidents"].append({
                        "page": page_num,
                        "type": "BLACK_TEXT_KNOCKOUT",
                        "severity": "WARNING",
                        "category": "Sobreimpresión",
                        "title": "Texto negro 100% en calado (knockout)",
                        "message": "Texto en negro 100% K sin sobreimpresión. Puede generar filetes blancos si hay desajuste de registro en máquina."
                    })

            if spot_name:
                check_spot(spot_name, state['op'] if is_fill else state['OP'], page_num, overprint_data, "texto")

        # Vector fills
        elif op_str in ['f', 'F', 'f*', 'b', 'b*', 'B', 'B*']:
            cs_type, spot_name = state['fill_cs']
            if spot_name:
                check_spot(spot_name, state['op'], page_num, overprint_data, "relleno")

        # Vector strokes
        elif op_str in ['s', 'S', 'b', 'b*', 'B', 'B*']:
            cs_type, spot_name = state['stroke_cs']
            if spot_name:
                check_spot(spot_name, state['OP'], page_num, overprint_data, "trazo")

def check_spot(spot_name, is_overprinting, page_num, overprint_data, context="objeto"):
    if is_varnish_name(spot_name):
        if is_overprinting:
            overprint_data["varnish_overprint"] += 1
        else:
            overprint_data["varnish_knockout"] += 1
            overprint_data["incidents"].append({
                "page": page_num,
                "type": "VARNISH_KNOCKOUT",
                "severity": "ERROR",
                "category": "Sobreimpresión",
                "title": f"Barniz/Acabado '{spot_name}' en calado",
                "message": f"El barniz o capa técnica '{spot_name}' ({context}) no sobreimprime. ¡Borrará la impresión subyacente!"
            })
    elif is_pantone_name(spot_name):
        if is_overprinting:
            overprint_data["pantone_overprint"] += 1
            overprint_data["incidents"].append({
                "page": page_num,
                "type": "PANTONE_OVERPRINT",
                "severity": "WARNING",
                "category": "Sobreimpresión",
                "title": f"Color Pantone '{spot_name}' sobreimprimiendo",
                "message": f"El color directo '{spot_name}' ({context}) sobreimprime sobre tintas inferiores, lo que puede alterar su tono real."
            })
        else:
            overprint_data["pantone_knockout"] += 1


class IntelliPrintEngine:
    def __init__(self):
        self.spellchecker = PrepressSpellChecker()

    def run_preflight(self, pdf_path, profile_id="OFFSET_300", icc_choice="preserve", selected_icc=None):
        findings = []
        rules_evaluated = {}

        # 1. Target Profile Criteria
        target_dpi = 300
        req_family = "CMYK"
        requires_bleed = True
        
        if profile_id == "DIGITAL_200":
            target_dpi = 200
            req_family = "CMYK"
            requires_bleed = True
        elif profile_id == "PANTALLA_RGB":
            target_dpi = 96
            req_family = "RGB"
            requires_bleed = False

        # Open with PyMuPDF
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            return {
                "technical_result": "fail",
                "error": f"No se pudo abrir el documento PDF: {e}",
                "findings": []
            }

        page_count = len(doc)
        total_images = 0
        low_res_images = 0
        non_cmyk_images = 0

        # Boxes and Bleed inspection
        first_page = doc[0]
        mediabox = first_page.mediabox
        trimbox = first_page.trimbox
        bleedbox = first_page.bleedbox

        has_explicit_trim = (trimbox != mediabox and trimbox.width > 0 and trimbox.height > 0)
        
        # Calculate bleed in mm
        bleed_top = round((trimbox.y0 - mediabox.y0) * 25.4 / 72.0, 1)
        bleed_bottom = round((mediabox.y1 - trimbox.y1) * 25.4 / 72.0, 1)
        bleed_left = round((trimbox.x0 - mediabox.x0) * 25.4 / 72.0, 1)
        bleed_right = round((mediabox.x1 - trimbox.x1) * 25.4 / 72.0, 1)
        avg_bleed_mm = max(0, min(bleed_top, bleed_bottom, bleed_left, bleed_right))

        if requires_bleed:
            if not has_explicit_trim or avg_bleed_mm < 2.99:
                findings.append({
                    "page": 1,
                    "rule_id": "BLEED_GEOMETRY_3MM",
                    "severity": "ERROR",
                    "category": "Geometría",
                    "title": "Sangrado insuficiente o ausente",
                    "message": f"El perfil {profile_id} exige 3 mm de sangre por lado. Se detectó ~{avg_bleed_mm} mm."
                })
            else:
                rules_evaluated["BLEED_GEOMETRY_3MM"] = "PASS"

        # Images & Resolution inspection
        for p_idx in range(page_count):
            page = doc[p_idx]
            img_list = page.get_images(full=True)
            total_images += len(img_list)

            for i_idx, img in enumerate(img_list):
                xref = img[0]
                base_img = doc.extract_image(xref)
                if not base_img:
                    continue

                cs = base_img.get("colorspace", "Desconocido")
                width_px = base_img.get("width", 0)
                height_px = base_img.get("height", 0)

                rects = page.get_image_rects(xref)
                dpi_x, dpi_y = 0, 0
                if rects and rects[0].width > 0 and rects[0].height > 0:
                    r = rects[0]
                    dpi_x = round(width_px / (r.width / 72.0))
                    dpi_y = round(height_px / (r.height / 72.0))
                    effective_dpi = round((dpi_x + dpi_y) / 2)

                    if effective_dpi < target_dpi:
                        low_res_images += 1
                        findings.append({
                            "page": p_idx + 1,
                            "rule_id": "PRINT_IMAGE_EFFECTIVE_PPI",
                            "severity": "ERROR" if requires_bleed else "WARNING",
                            "category": "Imágenes",
                            "title": f"Resolución insuficiente ({effective_dpi} ppp)",
                            "message": f"Imagen {i_idx+1} en pág {p_idx+1} colocada a {effective_dpi} ppp efectivos (mínimo {target_dpi} ppp en {profile_id})."
                        })

                # Color check for images
                is_cmyk = (cs == 4 or "CMYK" in str(cs).upper())
                is_gray = (cs == 1 or "GRAY" in str(cs).upper())
                if req_family == "CMYK" and not is_cmyk and not is_gray:
                    non_cmyk_images += 1
                    findings.append({
                        "page": p_idx + 1,
                        "rule_id": "SOURCE_COLOR_DIAGNOSTIC",
                        "severity": "WARNING",
                        "category": "Color",
                        "title": f"Imagen en espacio {cs}",
                        "message": f"Imagen en espacio {cs}. Se admite para conversión gestionada, pero se aconseja verificar su apariencia."
                    })

        # Font Embedding Inspection
        fonts_found = []
        for p_idx in range(page_count):
            page = doc[p_idx]
            for f in page.get_fonts():
                font_name = f[3]
                is_embedded = (f[1] != "" or f[2] != "")
                fonts_found.append({"name": font_name, "embedded": is_embedded, "page": p_idx + 1})
                if not is_embedded:
                    findings.append({
                        "page": p_idx + 1,
                        "rule_id": "USED_FONTS_EMBEDDED",
                        "severity": "ERROR",
                        "category": "Tipografías",
                        "title": f"Fuente no incrustada: {font_name}",
                        "message": f"La fuente '{font_name}' no está incrustada en el PDF. Puede sustituirse o corromperse al imprimir."
                    })

        # OutputIntent & Document Color
        output_intent_info = {"has_output_intent": False, "identifier": "No declarado"}
        overprint_data = {
            "black_text_overprint": 0,
            "black_text_knockout": 0,
            "varnish_overprint": 0,
            "varnish_knockout": 0,
            "pantone_overprint": 0,
            "pantone_knockout": 0,
            "incidents": []
        }

        try:
            pike_doc = pikepdf.open(pdf_path)
            output_intent_info = detect_pdf_output_intent(pike_doc)
            
            # Run overprint & spot check
            for p_idx, p_page in enumerate(pike_doc.pages, 1):
                cmds = list(pikepdf.parse_content_stream(p_page))
                scan_content_stream(cmds, p_page.get('/Resources'), p_idx, overprint_data)
            pike_doc.close()
        except Exception:
            pass

        # Check Output Intent requirements
        if req_family == "CMYK":
            if not output_intent_info["has_output_intent"] or output_intent_info["detected_family"] != "CMYK":
                findings.append({
                    "page": 1,
                    "rule_id": "DOCUMENT_OUTPUT_ICC",
                    "severity": "ERROR",
                    "category": "Color",
                    "title": "ICC de salida CMYK ausente o no detectado",
                    "message": f"El perfil {profile_id} exige un OutputIntent documental CMYK válido incrustado."
                })
        elif req_family == "RGB":
            if not output_intent_info["has_output_intent"] or output_intent_info["detected_family"] != "RGB":
                findings.append({
                    "page": 1,
                    "rule_id": "DOCUMENT_OUTPUT_ICC",
                    "severity": "WARNING",
                    "category": "Color",
                    "title": "ICC de salida RGB ausente",
                    "message": "Se recomienda declarar un perfil sRGB para garantizar reproducción uniforme en pantalla."
                })

        # Merge overprint incidents
        for inc in overprint_data["incidents"]:
            findings.append({
                "page": inc["page"],
                "rule_id": inc["type"],
                "severity": inc["severity"],
                "category": inc["category"],
                "title": inc["title"],
                "message": inc["message"]
            })

        # Run Spellchecker
        spell_suggestions = self.spellchecker.check_pdf_text(doc)

        doc.close()

        # Compute Technical Result
        has_errors = any(f["severity"] == "ERROR" for f in findings)
        has_warnings = any(f["severity"] == "WARNING" for f in findings)
        
        if has_errors:
            tech_status = "FAIL"
            tech_label = "NO CUMPLE"
        elif has_warnings:
            tech_status = "PASS_WITH_WARNINGS"
            tech_label = "CUMPLE CON AVISOS"
        else:
            tech_status = "PASS"
            tech_label = "CUMPLE"

        content_status = "PENDING_REVIEW" if spell_suggestions else "RESOLVED"
        content_label = f"Revisión editorial pendiente ({len(spell_suggestions)} sugerencias)" if spell_suggestions else "Sin erratas detectadas"

        return {
            "job_summary": {
                "profile_id": profile_id,
                "pages": page_count,
                "total_images": total_images,
                "low_res_images": low_res_images,
                "fonts_count": len(fonts_found),
                "bleed_detected_mm": avg_bleed_mm,
                "icc_detected": output_intent_info,
                "icc_choice_applied": icc_choice,
                "selected_icc": selected_icc,
                "overprint_stats": {
                    "black_text_overprint": overprint_data["black_text_overprint"],
                    "black_text_knockout": overprint_data["black_text_knockout"],
                    "varnish_overprint": overprint_data["varnish_overprint"],
                    "varnish_knockout": overprint_data["varnish_knockout"],
                    "pantone_overprint": overprint_data["pantone_overprint"],
                    "pantone_knockout": overprint_data["pantone_knockout"]
                }
            },
            "triple_result": {
                "technical": {
                    "status": tech_status,
                    "label": tech_label,
                    "errors_count": sum(1 for f in findings if f["severity"] == "ERROR"),
                    "warnings_count": sum(1 for f in findings if f["severity"] == "WARNING")
                },
                "content": {
                    "status": content_status,
                    "label": content_label,
                    "suggestions_count": len(spell_suggestions)
                },
                "release": {
                    "status": "PENDING_AUTHORIZATION",
                    "label": "Pendiente de visto bueno del operario"
                }
            },
            "findings": findings,
            "spell_suggestions": spell_suggestions
        }

