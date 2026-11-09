import os
import json
import struct
from pathlib import Path
import pikepdf

ICC_DIR = Path(__file__).parent / "icc_profiles"

FRIENDLY_NAMES = {
    "PSOcoated_v3.icc": ("PSO Coated v3 (FOGRA51 - Estucado)", "CMYK"),
    "PSOuncoated_v3_FOGRA52.icc": ("PSO Uncoated v3 (FOGRA52 - No estucado)", "CMYK"),
    "ISOcoated_v2_300_bas.icc": ("ISO Coated v2 300% (FOGRA39 - Estucado)", "CMYK"),
    "ISOcoated_v2_eci.icc": ("ISO Coated v2 ECI (FOGRA39)", "CMYK"),
    "sRGB2014.icc": ("sRGB IEC61966-2.1 (Pantalla/Web)", "RGB"),
    "AdobeRGB1998.icc": ("Adobe RGB 1998 (Fotografía/RGB amplio)", "RGB")
}

def get_available_icc_profiles():
    profiles = []
    seen_keys = set()
    
    # 1. Scanned local profiles in icc_profiles/
    if ICC_DIR.exists():
        for f in os.listdir(ICC_DIR):
            if f.lower().endswith(('.icc', '.icm')):
                path = ICC_DIR / f
                if not path.is_file() or path.stat().st_size < 100:
                    continue
                size_kb = round(path.stat().st_size / 1024, 1)
                
                if f in FRIENDLY_NAMES:
                    name, family = FRIENDLY_NAMES[f]
                else:
                    family = "CMYK" if any(k in f.lower() for k in ["coated", "cmyk", "fogra", "gracol", "swop"]) else "RGB"
                    if "gray" in f.lower():
                        family = "Gray"
                    name = f.replace(".icc", "").replace(".icm", "").replace("_", " ")

                seen_keys.add(f.lower())
                seen_keys.add(name.lower())

                profiles.append({
                    "id": f,
                    "filename": f,
                    "name": name,
                    "family": family,
                    "size_kb": size_kb,
                    "source": "local_folder"
                })

    # 2. Add standard catalog references (only if not already provided locally)
    catalog_refs = [
        {"id": "CAT_PSO_COATED_V3", "filename": "PSOcoated_v3.icc", "name": "PSO Coated v3 (FOGRA51)", "family": "CMYK", "source": "catalog"},
        {"id": "CAT_PSO_UNCOATED_V3", "filename": "PSOuncoated_v3_FOGRA52.icc", "name": "PSO Uncoated v3 (FOGRA52)", "family": "CMYK", "source": "catalog"},
        {"id": "CAT_ECICMYK_V2", "filename": None, "name": "eciCMYK v2 (FOGRA59 - Intercambio)", "family": "CMYK", "source": "catalog"},
        {"id": "CAT_SRGB", "filename": "sRGB2014.icc", "name": "sRGB IEC61966-2.1", "family": "RGB", "source": "catalog"}
    ]
    
    for ref in catalog_refs:
        # Check if already covered by local file
        ref_fn = (ref.get("filename") or "").lower()
        ref_n = ref["name"].lower()
        if not ref_fn or not (ICC_DIR / ref["filename"]).is_file():
            continue
        if ref_fn and ref_fn in seen_keys:
            continue
        if any(ref_n in p["name"].lower() or p["name"].lower() in ref_n for p in profiles):
            continue
        profiles.append(ref)

    return profiles

def parse_icc_description(icc_bytes):
    """
    Parses the internal friendly profile description from raw ICC binary bytes.
    Supports 'desc' (ASCII/Latin1) and 'mluc' (Unicode UTF-16BE) records.
    """
    if not icc_bytes or len(icc_bytes) < 132:
        return None
    try:
        tag_count = struct.unpack('>I', icc_bytes[128:132])[0]
        for i in range(tag_count):
            offset = 132 + i * 12
            if offset + 12 > len(icc_bytes):
                break
            tag_sig = icc_bytes[offset:offset+4]
            tag_offset = struct.unpack('>I', icc_bytes[offset+4:offset+8])[0]
            tag_size = struct.unpack('>I', icc_bytes[offset+8:offset+12])[0]
            if tag_sig == b'desc':
                if tag_offset + 12 > len(icc_bytes):
                    break
                desc_type = icc_bytes[tag_offset:tag_offset+4]
                if desc_type == b'desc':
                    ascii_len = struct.unpack('>I', icc_bytes[tag_offset+8:tag_offset+12])[0]
                    return icc_bytes[tag_offset+12:tag_offset+12+max(0, ascii_len-1)].decode('latin1', errors='ignore').strip()
                elif desc_type == b'mluc':
                    rec_count = struct.unpack('>I', icc_bytes[tag_offset+8:tag_offset+12])[0]
                    str_len = struct.unpack('>I', icc_bytes[tag_offset+20:tag_offset+24])[0]
                    str_off = struct.unpack('>I', icc_bytes[tag_offset+24:tag_offset+28])[0]
                    start = tag_offset + str_off
                    return icc_bytes[start:start+str_len].decode('utf-16-be', errors='ignore').strip()
    except Exception:
        pass
    return None

def detect_pdf_output_intent(doc_or_pike):
    """
    Detects if the PDF contains an OutputIntent with embedded ICC.
    Accepts a pikepdf.Pdf object, file path (str or Path), or bytes.
    """
    close_when_done = False
    pike_doc = None
    if isinstance(doc_or_pike, (str, Path)):
        try:
            pike_doc = pikepdf.open(str(doc_or_pike))
            close_when_done = True
        except Exception:
            return {
                "has_output_intent": False,
                "subtype": None,
                "identifier": "No declarado",
                "profile_name": "Sin perfil incrustado",
                "friendly_description": "Sin perfil incrustado (DeviceCMYK genérico)",
                "has_icc_stream": False,
                "detected_family": "Desconocido"
            }
    else:
        pike_doc = doc_or_pike

    try:
        if hasattr(pike_doc, 'Root') and '/OutputIntents' in pike_doc.Root:
            intents = pike_doc.Root['/OutputIntents']
            if len(intents) > 0:
                intent = intents[0]
                subtype = str(intent.get('/S', 'Desconocido')).lstrip('/')
                info = str(intent.get('/OutputConditionIdentifier', intent.get('/Info', 'ICC Incrustado')))
                dest_output = intent.get('/DestOutputProfile', None)
                has_icc_stream = dest_output is not None

                profile_desc = None
                if has_icc_stream:
                    try:
                        stream_bytes = dest_output.read_bytes()
                        profile_desc = parse_icc_description(stream_bytes)
                    except Exception:
                        pass

                # Build descriptive friendly name
                parts = []
                if profile_desc:
                    parts.append(profile_desc)
                if info and info not in ['ICC Incrustado', 'None', 'Desconocido']:
                    if not profile_desc or info.lower() not in profile_desc.lower():
                        parts.append(f"({info})")
                elif not profile_desc and info:
                    parts.append(info)

                friendly_desc = " ".join(parts).strip() if parts else "OutputIntent documental incrustado"
                family = "CMYK" if any(k in (friendly_desc + " " + info).lower() for k in ["cmyk", "coated", "fogra", "offset", "uncoated", "iso", "pso"]) else "RGB"

                return {
                    "has_output_intent": True,
                    "subtype": subtype,
                    "identifier": info,
                    "profile_name": profile_desc or info,
                    "friendly_description": friendly_desc,
                    "has_icc_stream": has_icc_stream,
                    "detected_family": family
                }
    except Exception:
        pass
    finally:
        if close_when_done and pike_doc:
            try:
                pike_doc.close()
            except Exception:
                pass

    return {
        "has_output_intent": False,
        "subtype": None,
        "identifier": "No declarado",
        "profile_name": "Sin perfil incrustado",
        "friendly_description": "Sin perfil incrustado (DeviceCMYK genérico)",
        "has_icc_stream": False,
        "detected_family": "Desconocido"
    }


CATALOG_FILES = {
    "CAT_PSO_COATED_V3": "PSOcoated_v3.icc",
    "CAT_PSO_UNCOATED_V3": "PSOuncoated_v3_FOGRA52.icc",
    "CAT_SRGB": "sRGB2014.icc",
}


def resolve_icc_profile(profile_id):
    """Resolve catalog IDs and validate profile bytes without accepting filesystem paths."""
    from PIL import ImageCms
    if not isinstance(profile_id, str) or any(c in profile_id for c in '/\\:'):
        raise ValueError("Selecciona un perfil ICC del catalogo.")
    name = CATALOG_FILES.get(profile_id, profile_id)
    base = ICC_DIR.resolve()
    candidate = (base / name).resolve()
    if candidate.parent != base or candidate.suffix.lower() not in (".icc", ".icm") or not candidate.is_file():
        raise ValueError("Perfil ICC no disponible en el catalogo.")
    data = candidate.read_bytes()
    if len(data) < 128 or data[36:40] != b"acsp":
        raise ValueError("El archivo no es un perfil ICC valido.")
    try:
        profile = ImageCms.ImageCmsProfile(str(candidate))
        family = profile.profile.xcolor_space.strip().upper()
    except Exception as exc:
        raise ValueError("Perfil ICC invalido.") from exc
    if family not in ("CMYK", "RGB", "GRAY"):
        raise ValueError("Espacio de color ICC no admitido.")
    return candidate, family


def apply_icc_to_pdf(pdf_path, selected_icc_id):
    from pdf_utils import atomic_output
    if not selected_icc_id:
        return None
    profile_path, family = resolve_icc_profile(selected_icc_id)
    name = FRIENDLY_NAMES.get(profile_path.name, (profile_path.stem, family))[0]
    with atomic_output(pdf_path) as temporary:
        with pikepdf.open(pdf_path) as pdf:
            stream = pdf.make_stream(profile_path.read_bytes())
            stream.N = {"CMYK": 4, "RGB": 3, "GRAY": 1}[family]
            intent = pdf.make_indirect(pikepdf.Dictionary(
                Type=pikepdf.Name.OutputIntent, S=pikepdf.Name.GTS_PDFX,
                OutputConditionIdentifier=pikepdf.String(name), Info=pikepdf.String(name),
                RegistryName=pikepdf.String("http://www.color.org"), DestOutputProfile=stream,
            ))
            pdf.Root.OutputIntents = pikepdf.Array([intent])
            pdf.save(temporary)
    return {"applied": True, "has_output_intent": True, "subtype": "GTS_PDFX",
            "identifier": name, "profile_name": name, "has_icc_stream": True,
            "detected_family": family}
