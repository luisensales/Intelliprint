import os
import json
from pathlib import Path

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

