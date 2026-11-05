import pymupdf as fitz
import pikepdf
import sys
import os
import re
from decimal import Decimal

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

def scan_content_stream(commands, resources, page_num, results):
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
                        scan_content_stream(sub_cmds, sub_resources, page_num, results)
                    except Exception:
                        pass

        # Text operations (Tj, TJ, ', ")
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
                    results["black_text_overprint"] += 1
                else:
                    results["black_text_knockout"] += 1
                    msg = f"Pág {page_num}: Texto negro 100% en calado (knockout). Debe sobreimprimir para evitar desajuste de registro."
                    if msg not in results["warnings_details"]:
                        results["warnings_details"].append(msg)

            if spot_name:
                check_spot_ink(spot_name, state['op'] if is_fill else state['OP'], page_num, results, context="texto")

        # Vector fill operations
        elif op_str in ['f', 'F', 'f*', 'b', 'b*', 'B', 'B*']:
            cs_type, spot_name = state['fill_cs']
            if spot_name:
                check_spot_ink(spot_name, state['op'], page_num, results, context="relleno")

        # Vector stroke operations
        elif op_str in ['s', 'S', 'b', 'b*', 'B', 'B*']:
            cs_type, spot_name = state['stroke_cs']
            if spot_name:
                check_spot_ink(spot_name, state['OP'], page_num, results, context="trazo")

def check_spot_ink(spot_name, is_overprinting, page_num, results, context="objeto"):
    if is_varnish_name(spot_name):
        if is_overprinting:
            results["varnish_overprint"] += 1
        else:
            results["varnish_knockout"] += 1
            msg = f"Pág {page_num}: Barniz/Acabado '{spot_name}' ({context}) en CALADO (knockout). ¡Debe sobreimprimir siempre!"
            if msg not in results["errors_details"]:
                results["errors_details"].append(msg)
    elif is_pantone_name(spot_name):
        if is_overprinting:
            results["pantone_overprint"] += 1
            msg = f"Pág {page_num}: Pantone '{spot_name}' ({context}) con SOBREIMPRESIÓN activada. No debe sobreimprimir salvo indicación expresa."
            if msg not in results["warnings_details"]:
                results["warnings_details"].append(msg)
        else:
            results["pantone_knockout"] += 1
    else:
        if is_overprinting:
            results["other_spot_overprint"] += 1
        else:
            results["other_spot_knockout"] += 1

def check_pdf(file_path, target_dpi=300):
    if not os.path.exists(file_path):
        print(f"Error: El archivo {file_path} no existe.")
        return

    print(f"--- Analizando: {os.path.basename(file_path)} ---")
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        print(f"Error al abrir el PDF: {e}")
        return

    # 1. Chequear Cajas (Sangre / TrimBox)
    print(f"\n[1] CAJAS DE PÁGINA (Pág 1)")
    page = doc[0]  
    mediabox = page.mediabox
    trimbox = page.trimbox
    bleedbox = page.bleedbox

    print(f"  - MediaBox (Lienzo total): {mediabox}")
    print(f"  - TrimBox  (Corte final):  {trimbox}")
    print(f"  - BleedBox (Área sangre):  {bleedbox}")

    if mediabox != trimbox:
        if trimbox.width == 0 or trimbox.height == 0:
            print("  => NOTA: TrimBox no está bien definido (ancho o alto = 0).")
        else:
            print("  => CONCLUSIÓN: El archivo tiene SANGRE definida (MediaBox es distinto al TrimBox).")
    else:
        print("  => CONCLUSIÓN: El archivo NO tiene sangre (MediaBox = TrimBox).")

    # 2. Chequear Imágenes (Resolución y Color Space)
    print(f"\n[2] IMÁGENES (Color y Resolución)")
    
    warnings_color = False
    warnings_dpi = False

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)
        
        if not image_list:
            continue
            
        print(f"\n  -- Página {page_num + 1} -- ({len(image_list)} imágenes encontradas)")
        
        for img_index, img in enumerate(image_list):
            xref = img[0]
            
            try:
                base_image = doc.extract_image(xref)
                if not base_image:
                    continue
            except Exception as e:
                print(f"    [Img {img_index+1}] Error extrayendo: {e}")
                continue
                
            colorspace = base_image.get("colorspace", "Desconocido")
            width = base_image.get("width", 0)
            height = base_image.get("height", 0)
            
            rects = page.get_image_rects(xref)
            dpi_x = 0
            dpi_y = 0
            
            if rects:
                rect = rects[0]
                if rect.width > 0:
                    physical_width_in = rect.width / 72.0
                    dpi_x = round(width / physical_width_in)
                if rect.height > 0:
                    physical_height_in = rect.height / 72.0
                    dpi_y = round(height / physical_height_in)
            
            is_cmyk = False
            cs_name = str(colorspace)
            if colorspace == 1: cs_name = "Escala de Grises"
            elif colorspace == 3: cs_name = "RGB"
            elif colorspace == 4: 
                cs_name = "CMYK"
                is_cmyk = True
            elif "CMYK" in cs_name.upper():
                is_cmyk = True

            print(f"    [Img {img_index+1}] Color: {cs_name} | Tamaño original: {width}x{height} px", end="")
            
            if rects:
                print(f" | Resolución pág: ~{dpi_x} PPI")
                avg_dpi = (dpi_x + dpi_y) / 2
                if avg_dpi < target_dpi and avg_dpi > 0:
                    print(f"      -> ⚠️ ADVERTENCIA: Resolución baja (Menor a {target_dpi} PPI)")
                    warnings_dpi = True
            else:
                print(" | (Imagen sin posición explícita)")

            if not is_cmyk and colorspace != 1:
                print(f"      -> ⚠️ ADVERTENCIA: La imagen está en {cs_name}, NO en CMYK/Grises.")
                warnings_color = True

    doc.close()

    # 3. Chequear Sobreimpresión y Tintas Especiales (pikepdf)
    print(f"\n[3] SOBREIMPRESIÓN Y TINTAS ESPECIALES (Texto negro 100%, Barnices y Pantones)")
    
    overprint_results = {
        'black_text_overprint': 0,
        'black_text_knockout': 0,
        'varnish_overprint': 0,
        'varnish_knockout': 0,
        'pantone_overprint': 0,
        'pantone_knockout': 0,
        'other_spot_overprint': 0,
        'other_spot_knockout': 0,
        'warnings_details': [],
        'errors_details': []
    }

    try:
        pike_doc = pikepdf.open(file_path)
        for page_idx, p_page in enumerate(pike_doc.pages, 1):
            cmds = list(pikepdf.parse_content_stream(p_page))
            scan_content_stream(cmds, p_page.get('/Resources'), page_idx, overprint_results)
        pike_doc.close()

        total_black = overprint_results['black_text_overprint'] + overprint_results['black_text_knockout']
        print(f"  - Texto Negro 100%:")
        print(f"      • En sobreimpresión (correcto): {overprint_results['black_text_overprint']}")
        print(f"      • En calado/knockout:          {overprint_results['black_text_knockout']}")
        if overprint_results['black_text_knockout'] > 0:
            print(f"      ⚠️ ADVERTENCIA: Se detectaron {overprint_results['black_text_knockout']} apariciones de texto negro 100% que calan. Deben sobreimprimir.")

        total_varnish = overprint_results['varnish_overprint'] + overprint_results['varnish_knockout']
        print(f"  - Barnices y Acabados Técnicos:")
        if total_varnish > 0:
            print(f"      • En sobreimpresión (correcto): {overprint_results['varnish_overprint']}")
            print(f"      • En calado/knockout (ERROR):   {overprint_results['varnish_knockout']}")
            if overprint_results['varnish_knockout'] > 0:
                print(f"      ❌ ERROR CRÍTICO: {overprint_results['varnish_knockout']} elementos de barniz/acabado calan el contenido inferior.")
        else:
            print("      • No se detectaron tintas de barniz/acabado.")

        total_pantone = overprint_results['pantone_overprint'] + overprint_results['pantone_knockout']
        print(f"  - Tintas Planas / Pantones:")
        if total_pantone > 0:
            print(f"      • En calado (correcto):        {overprint_results['pantone_knockout']}")
            print(f"      • En sobreimpresión (revisar):  {overprint_results['pantone_overprint']}")
            if overprint_results['pantone_overprint'] > 0:
                print(f"      ⚠️ ADVERTENCIA: {overprint_results['pantone_overprint']} apariciones de Pantone sobreimprimen (no deben sobreimprimir salvo intención de diseño).")
        else:
            print("      • No se detectaron tintas Pantone.")

        if overprint_results['errors_details']:
            print(f"\n  Detalles de Errores Críticos:")
            for e in overprint_results['errors_details'][:5]:
                print(f"    - {e}")
            if len(overprint_results['errors_details']) > 5:
                print(f"    ... y {len(overprint_results['errors_details']) - 5} más.")

        if overprint_results['warnings_details']:
            print(f"\n  Detalles de Advertencias:")
            for w in overprint_results['warnings_details'][:5]:
                print(f"    - {w}")
            if len(overprint_results['warnings_details']) > 5:
                print(f"    ... y {len(overprint_results['warnings_details']) - 5} más.")

    except Exception as e:
        print(f"  ⚠️ No se pudo completar el análisis de sobreimpresión con pikepdf: {e}")

    # 4. Resumen Final
    print("\n[4] RESUMEN FINAL")
    has_errors = (overprint_results['varnish_knockout'] > 0)
    has_warnings = (warnings_color or warnings_dpi or 
                    overprint_results['black_text_knockout'] > 0 or 
                    overprint_results['pantone_overprint'] > 0)

    if not has_errors and not has_warnings:
        print("✅ Todo parece correcto para impresión (Imágenes, geometría y sobreimpresión cumplen el estándar).")
    elif has_errors:
        print("❌ Se encontraron ERRORES CRÍTICOS (Revisar barnices en calado).")
    else:
        print("⚠️ Se encontraron ADVERTENCIAS importantes que revisar (Ver detalles arriba).")

if __name__ == "__main__":
    pdf_path = ""
    dpi = 300
    
    if len(sys.argv) < 2:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            print("Por favor, selecciona un archivo PDF en la ventana emergente...")
            pdf_path = filedialog.askopenfilename(
                title="Selecciona el PDF a revisar",
                filetypes=[("Archivos PDF", "*.pdf")]
            )
        except Exception:
            pdf_path = input("Arrastra aquí tu archivo PDF o escribe la ruta: ").strip()
            if pdf_path.startswith('"') and pdf_path.endswith('"'):
                pdf_path = pdf_path[1:-1]
    else:
        pdf_path = sys.argv[1]
        
    if len(sys.argv) > 2:
        try:
             dpi = int(sys.argv[2])
        except:
             pass
             
    if pdf_path and pdf_path.strip() != "":
        check_pdf(pdf_path, target_dpi=dpi)
    else:
        print("No se seleccionó ningún archivo.")
        
    input("\nPresiona ENTER para salir...")
