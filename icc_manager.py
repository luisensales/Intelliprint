import os
import json
import struct
import io
import hashlib
import threading
from collections import OrderedDict
from pathlib import Path
import pikepdf

ICC_DIR = Path(__file__).parent / "icc_profiles"
MAX_ICC_BYTES = 16 * 1024 * 1024
_validated_profiles = OrderedDict()
_validation_lock = threading.Lock()


def validate_icc_bytes(data):
    """Check the binary profile and a usable LittleCMS transform, not its label.

    Cache only the fingerprint and metadata; embedded profile bytes and native
    transforms are released after validation, keeping the cache small.
    """
    from PIL import ImageCms
    if not isinstance(data, bytes) or not 132 <= len(data) <= MAX_ICC_BYTES:
        raise ValueError("Tamaño de perfil ICC no válido.")
    fingerprint = hashlib.sha256(data).digest()
    with _validation_lock:
        if fingerprint in _validated_profiles:
            _validated_profiles.move_to_end(fingerprint)
            return _validated_profiles[fingerprint]
    declared_size = struct.unpack_from('>I', data, 0)[0]
    if declared_size != len(data) or data[36:40] != b'acsp':
        raise ValueError("Cabecera o longitud del perfil ICC no válidas.")
    count = struct.unpack_from('>I', data, 128)[0]
    end_table = 132 + count * 12
    if not count or end_table > len(data):
        raise ValueError("Tabla de etiquetas ICC incompleta.")
    signatures = set()
    for index in range(count):
        signature, offset, size = struct.unpack_from('>4sII', data, 132 + index * 12)
        if signature in signatures or offset < end_table or size < 8 or offset + size > len(data):
            raise ValueError("Etiquetas ICC duplicadas, truncadas o fuera del perfil.")
        signatures.add(signature)
    try:
        profile = ImageCms.ImageCmsProfile(io.BytesIO(data))
        family = profile.profile.xcolor_space.strip().upper()
        if family not in ('CMYK', 'RGB', 'GRAY'):
            raise ValueError("Espacio ICC no admitido para salida.")
        mode = 'L' if family == 'GRAY' else family
        ImageCms.buildTransformFromOpenProfiles(profile, ImageCms.createProfile('sRGB'),
                                                mode, 'RGB', renderingIntent=1)
        description = ImageCms.getProfileDescription(profile).strip()
    except Exception as exc:
        raise ValueError("El perfil ICC no contiene una transformación de color válida.") from exc
    metadata = family, description
    with _validation_lock:
        _validated_profiles[fingerprint] = metadata
        while len(_validated_profiles) > 32:
            _validated_profiles.popitem(last=False)
    return metadata

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
                try:
                    family, description = validate_icc_bytes(path.read_bytes())
                except ValueError:
                    continue
                size_kb = round(path.stat().st_size / 1024, 1)
                
                if f in FRIENDLY_NAMES:
                    name = FRIENDLY_NAMES[f][0]
                else:
                    name = description or f.replace(".icc", "").replace(".icm", "").replace("_", " ")

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
    """Validate embedded ICC bytes and classify the actual profile color space."""
    empty = dict(has_output_intent=False, subtype=None, identifier='No declarado',
                 profile_name='Sin perfil incrustado', friendly_description='Sin perfil ICC validado',
                 has_icc_stream=False, icc_valid=False, detected_family='Desconocido',
                 validation_error=None)
    document = None
    close_when_done = False
    try:
        if isinstance(doc_or_pike, (str, Path)):
            document = pikepdf.open(doc_or_pike)
            close_when_done = True
        elif isinstance(doc_or_pike, (bytes, bytearray, memoryview)):
            document = pikepdf.open(io.BytesIO(bytes(doc_or_pike)))
            close_when_done = True
        else:
            document = doc_or_pike
        intents = document.Root.get('/OutputIntents', [])
        first_invalid = None
        for intent in intents:
            result = dict(empty, has_output_intent=True)
            try:
                if not isinstance(intent, pikepdf.Dictionary):
                    raise ValueError('OutputIntent con estructura no válida.')
                info = str(intent.get('/OutputConditionIdentifier', intent.get('/Info', 'ICC incrustado')))
                result.update(identifier=info, profile_name=info,
                              subtype=str(intent.get('/S', '')).lstrip('/'))
                stream = intent.get('/DestOutputProfile')
                result['has_icc_stream'] = isinstance(stream, pikepdf.Stream)
                if not result['has_icc_stream']:
                    raise ValueError('OutputIntent sin perfil ICC incrustado.')
                family, description = validate_icc_bytes(stream.read_bytes())
                channels = stream.get('/N')
                if channels is not None and (type(channels) is not int or channels != {'GRAY': 1, 'RGB': 3, 'CMYK': 4}[family]):
                    raise ValueError('El número de canales declarado no coincide con el ICC.')
                if not isinstance(intent.get('/S'), pikepdf.Name):
                    raise ValueError('OutputIntent sin subtipo válido.')
                parts = [description] if description else []
                if info and (not description or info.lower() not in description.lower()):
                    parts.append('(' + info + ')')
                result.update(icc_valid=True, detected_family=family,
                              profile_name=description or info,
                              friendly_description=' '.join(parts) or 'Perfil ICC validado')
                return result
            except Exception as exc:
                result.update(validation_error=str(exc), friendly_description='OutputIntent sin ICC válido')
                first_invalid = first_invalid or result
        return first_invalid or empty
    except Exception as exc:
        return dict(empty, validation_error=str(exc))
    finally:
        if close_when_done and document is not None:
            document.close()


CATALOG_FILES = {
    "CAT_PSO_COATED_V3": "PSOcoated_v3.icc",
    "CAT_PSO_UNCOATED_V3": "PSOuncoated_v3_FOGRA52.icc",
    "CAT_SRGB": "sRGB2014.icc",
}


def resolve_icc_profile(profile_id):
    """Resolve catalog IDs and validate profile bytes without accepting filesystem paths."""
    if not isinstance(profile_id, str) or any(c in profile_id for c in '/\\:'):
        raise ValueError("Selecciona un perfil ICC del catalogo.")
    name = CATALOG_FILES.get(profile_id, profile_id)
    base = ICC_DIR.resolve()
    candidate = (base / name).resolve()
    if candidate.parent != base or candidate.suffix.lower() not in (".icc", ".icm") or not candidate.is_file():
        raise ValueError("Perfil ICC no disponible en el catalogo.")
    data = candidate.read_bytes()
    family, _ = validate_icc_bytes(data)
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
    return {"applied": True, **detect_pdf_output_intent(pdf_path)}
