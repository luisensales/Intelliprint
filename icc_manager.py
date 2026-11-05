import os
import json
from pathlib import Path
import pikepdf

ICC_DIR = Path(__file__).parent / "icc_profiles"

def get_available_icc_profiles():
    profiles = []
    
    # 1. Scanned local profiles in icc_profiles/
    if ICC_DIR.exists():
        for f in os.listdir(ICC_DIR):
            if f.lower().endswith(('.icc', '.icm')):
                path = ICC_DIR / f
                size_kb = round(path.stat().st_size / 1024, 1)
                
                # Guess family
                family = "CMYK" if any(k in f.lower() for k in ["coated", "cmyk", "fogra", "gracol", "swop"]) else "RGB"
                if "gray" in f.lower():
                    family = "Gray"

                name = f.replace(".icc", "").replace(".icm", "").replace("_", " ")
                profiles.append({
                    "id": f,
                    "filename": f,
                    "name": name,
                    "family": family,
                    "size_kb": size_kb,
                    "source": "local_folder"
                })

    # 2. Add standard catalog references
    catalog_refs = [
        {"id": "CAT_PSO_COATED_V3", "filename": None, "name": "PSO Coated v3 (FOGRA51)", "family": "CMYK", "source": "catalog"},
        {"id": "CAT_PSO_UNCOATED_V3", "filename": None, "name": "PSO Uncoated v3 (FOGRA52)", "family": "CMYK", "source": "catalog"},
        {"id": "CAT_ECICMYK_V2", "filename": None, "name": "eciCMYK v2 (FOGRA59 - Intercambio)", "family": "CMYK", "source": "catalog"},
        {"id": "CAT_SRGB", "filename": None, "name": "sRGB IEC61966-2.1", "family": "RGB", "source": "catalog"}
    ]
    
    # Avoid duplicates by name
    existing_names = [p["name"].lower() for p in profiles]
    for ref in catalog_refs:
        if ref["name"].lower() not in existing_names:
            profiles.append(ref)

    return profiles

def detect_pdf_output_intent(doc_or_pike):
    """
    Detects if the PDF contains an OutputIntent with embedded ICC.
    """
    # Using pikepdf
    try:
        if hasattr(doc_or_pike, 'Root') and '/OutputIntents' in doc_or_pike.Root:
            intents = doc_or_pike.Root['/OutputIntents']
            if len(intents) > 0:
                intent = intents[0]
                subtype = str(intent.get('/S', 'Desconocido')).lstrip('/')
                info = str(intent.get('/OutputConditionIdentifier', intent.get('/Info', 'ICC Incrustado')))
                dest_output = intent.get('/DestOutputProfile', None)
                has_icc_stream = dest_output is not None
                
                family = "CMYK" if any(k in info.lower() for k in ["cmyk", "coated", "fogra", "offset"]) else "RGB"
                
                return {
                    "has_output_intent": True,
                    "subtype": subtype,
                    "identifier": info,
                    "has_icc_stream": has_icc_stream,
                    "detected_family": family
                }
    except Exception:
        pass
        
    return {
        "has_output_intent": False,
        "subtype": None,
        "identifier": "No declarado",
        "has_icc_stream": False,
        "detected_family": "Desconocido"
    }


def apply_icc_to_pdf(pdf_path, selected_icc_id):
    """
    Applies and embeds the selected ICC profile as the PDF OutputIntent.
    Modifies the PDF file at pdf_path.
    Returns metadata of the applied profile.
    """
    if not selected_icc_id:
        return None

    # Standard catalog definitions
    CATALOG_DATA = {
        "CAT_PSO_COATED_V3": {
            "identifier": "FOGRA51",
            "info": "PSO Coated v3 (FOGRA51)",
            "condition": "Offset comercial estucado FOGRA51",
            "family": "CMYK",
            "n": 4
        },
        "CAT_PSO_UNCOATED_V3": {
            "identifier": "FOGRA52",
            "info": "PSO Uncoated v3 (FOGRA52)",
            "condition": "Offset comercial no estucado FOGRA52",
            "family": "CMYK",
            "n": 4
        },
        "CAT_ECICMYK_V2": {
            "identifier": "FOGRA59",
            "info": "eciCMYK v2 (FOGRA59)",
            "condition": "Espacio de intercambio eciCMYK v2",
            "family": "CMYK",
            "n": 4
        },
        "CAT_SRGB": {
            "identifier": "sRGB",
            "info": "sRGB IEC61966-2.1",
            "condition": "sRGB IEC61966-2.1",
            "family": "RGB",
            "n": 3
        }
    }

    icc_bytes = None
    identifier = selected_icc_id
    info = selected_icc_id
    condition = "Condición de caracterización estándar"
    family = "CMYK"
    n_components = 4

    # 1. Local profile in icc_profiles/
    local_file = ICC_DIR / selected_icc_id
    if local_file.exists() and local_file.is_file() and local_file.stat().st_size > 100:
        with open(local_file, "rb") as f:
            icc_bytes = f.read()

        clean_name = selected_icc_id.lower()
        if "coated" in clean_name or "cmyk" in clean_name or "fogra" in clean_name:
            family = "CMYK"
            n_components = 4
            identifier = "FOGRA39" if "300" in clean_name else "FOGRA51"
            info = selected_icc_id.replace(".icc", "").replace(".icm", "").replace("_", " ")
            condition = "Impresión offset comercial estucado"
        elif "srgb" in clean_name or "rgb" in clean_name:
            family = "RGB"
            n_components = 3
            identifier = "sRGB"
            info = "sRGB IEC61966-2.1"
            condition = "Visualización estándar en monitor"
        else:
            family = "CMYK"
            n_components = 4
            info = selected_icc_id
    elif selected_icc_id in CATALOG_DATA:
        c_info = CATALOG_DATA[selected_icc_id]
        identifier = c_info["identifier"]
        info = c_info["info"]
        condition = c_info["condition"]
        family = c_info["family"]
        n_components = c_info["n"]
        # Fallback local stream if available
        fallback_cmyk = ICC_DIR / "ISOcoated_v2_300_bas.icc"
        if family == "CMYK" and fallback_cmyk.exists() and fallback_cmyk.stat().st_size > 100:
            with open(fallback_cmyk, "rb") as f:
                icc_bytes = f.read()

    # Apply with pikepdf
    try:
        pike_doc = pikepdf.open(pdf_path, allow_overwriting_input=True)
        
        intent = pikepdf.Dictionary(
            Type=pikepdf.Name('/OutputIntent'),
            S=pikepdf.Name('/GTS_PDFX'),
            OutputConditionIdentifier=pikepdf.String(identifier),
            Info=pikepdf.String(info),
            OutputCondition=pikepdf.String(condition),
            RegistryName=pikepdf.String('http://www.color.org')
        )

        if icc_bytes:
            icc_stream = pike_doc.make_stream(icc_bytes)
            icc_stream['/N'] = n_components
            intent.DestOutputProfile = icc_stream

        pike_doc.Root['/OutputIntents'] = pikepdf.Array([intent])
        pike_doc.save(pdf_path)
        pike_doc.close()

        return {
            "applied": True,
            "has_output_intent": True,
            "subtype": "GTS_PDFX",
            "identifier": info,
            "has_icc_stream": (icc_bytes is not None),
            "detected_family": family
        }
    except Exception as e:
        print(f"Error aplicando perfil ICC al PDF: {e}")
        return None

