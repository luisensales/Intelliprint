"""
profile_manager.py
==================
Gestor de Perfiles de Preflight (Estándar y Personalizados).
Permite a talleres gráficos y docentes de FP crear perfiles a medida
con tolerancias personalizadas de sangre, resolución DPI, límite TAC,
grosor mínimo de líneas y espacios de color.
"""

from __future__ import annotations

import json
import math
import re
from pdf_utils import atomic_output
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

BASE_DIR = Path(__file__).parent
CUSTOM_PROFILES_FILE = BASE_DIR / "custom_profiles.json"
STANDARD_PROFILES_FILE = BASE_DIR / "IntelliPrint_perfiles_v1.json"

DEFAULT_BUILTIN_PROFILES = [
    {
        "id": "OFFSET_300",
        "name": "Offset Comercial 300%",
        "destination": "Impresión Offset en Papel Estucado (ISO 12647-2)",
        "target_dpi": 300,
        "min_bleed_mm": 3.0,
        "max_tac": 300,
        "min_hairline_pt": 0.25,
        "safety_margin_mm": 3.0,
        "color_family": "CMYK",
        "allow_spot_colors": True,
        "require_fonts_embedded": True,
        "is_custom": False,
        "is_builtin": True
    },
    {
        "id": "DIGITAL_200",
        "name": "Impresión Digital Estándar",
        "destination": "Prensas Digitales Tóner / Inkjet Producción",
        "target_dpi": 200,
        "min_bleed_mm": 3.0,
        "max_tac": 320,
        "min_hairline_pt": 0.25,
        "safety_margin_mm": 3.0,
        "color_family": "CMYK",
        "allow_spot_colors": True,
        "require_fonts_embedded": True,
        "is_custom": False,
        "is_builtin": True
    },
    {
        "id": "PERIODICO_TAC240",
        "name": "Prensa y Papel Periódico",
        "destination": "Rotativa Offset / Papel Prensa Absorbente",
        "target_dpi": 200,
        "min_bleed_mm": 2.0,
        "max_tac": 240,
        "min_hairline_pt": 0.30,
        "safety_margin_mm": 4.0,
        "color_family": "CMYK",
        "allow_spot_colors": False,
        "require_fonts_embedded": True,
        "is_custom": False,
        "is_builtin": True
    },
    {
        "id": "PACKAGING_CARTONCILLO",
        "name": "Packaging y Cartoncillo",
        "destination": "Estuches, Cajas Plegables y Envases con Troquel",
        "target_dpi": 300,
        "min_bleed_mm": 5.0,
        "max_tac": 300,
        "min_hairline_pt": 0.25,
        "safety_margin_mm": 4.0,
        "color_family": "CMYK",
        "allow_spot_colors": True,
        "require_fonts_embedded": True,
        "is_custom": False,
        "is_builtin": True
    },
    {
        "id": "PANTALLA_RGB",
        "name": "Web, Pantalla y Documento Digital (RGB)",
        "destination": "Publicación Web, Visualización en Pantalla y Móvil (sRGB) · Sin sangre (0 mm)",
        "target_dpi": 96,
        "min_bleed_mm": 0.0,
        "max_tac": 400,
        "min_hairline_pt": 0.50,
        "safety_margin_mm": 0.0,
        "color_family": "RGB",
        "allow_spot_colors": False,
        "require_fonts_embedded": True,
        "is_custom": False,
        "is_builtin": True
    },
    {
        "id": "GRAN_FORMATO",
        "name": "Gran Formato y Cartelería",
        "destination": "Lonas, Vinilos, Banners y Displays Publicitarios",
        "target_dpi": 150,
        "min_bleed_mm": 5.0,
        "max_tac": 320,
        "min_hairline_pt": 0.35,
        "safety_margin_mm": 5.0,
        "color_family": "CMYK",
        "allow_spot_colors": True,
        "require_fonts_embedded": True,
        "is_custom": False,
        "is_builtin": True
    }
]


def validate_custom_profile(data):
    if not isinstance(data, dict):
        raise ValueError("Cada perfil debe ser un objeto.")
    profile_id = data.get("id")
    if not isinstance(profile_id, str) or not re.fullmatch(r"CUSTOM_[\w-]{1,100}", profile_id):
        raise ValueError("Identificador de perfil personalizado invalido.")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError("El perfil necesita un nombre de hasta 200 caracteres.")
    result = dict(DEFAULT_BUILTIN_PROFILES[0], **data)
    result.update(name=name.strip(), is_custom=True, is_builtin=False)
    if not isinstance(result.get("destination"), str):
        raise ValueError("El destino del perfil debe ser texto.")
    ranges = {"target_dpi": (1, 9600), "min_bleed_mm": (0, 100), "max_tac": (100, 400),
              "min_hairline_pt": (0.01, 10), "safety_margin_mm": (0, 100)}
    for key, (minimum, maximum) in ranges.items():
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f"{key} debe estar entre {minimum} y {maximum}.")
    for key in ("allow_spot_colors", "require_fonts_embedded"):
        if not isinstance(result[key], bool):
            raise ValueError(f"{key} debe ser verdadero o falso.")
    if result["color_family"] not in ("RGB", "CMYK"):
        raise ValueError("La familia de color debe ser RGB o CMYK.")
    return result


def load_custom_profiles():
    if not CUSTOM_PROFILES_FILE.exists():
        return []
    with open(CUSTOM_PROFILES_FILE, encoding="utf-8") as stream:
        data = json.load(stream)
    profiles = data.get("custom_profiles", []) if isinstance(data, dict) else []
    result, seen = [], set()
    for profile in profiles if isinstance(profiles, list) else []:
        try:
            valid = validate_custom_profile(profile)
        except ValueError:
            continue  # Recover legacy files without propagating broken records.
        if valid["id"] not in seen:
            result.append(valid)
            seen.add(valid["id"])
    return result


def save_custom_profiles_to_disk(profiles):
    validated = [validate_custom_profile(p) for p in profiles]
    payload = {"version": "1.2.0", "updated_at": datetime.now().isoformat(), "custom_profiles": validated}
    with atomic_output(CUSTOM_PROFILES_FILE) as temporary:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def import_custom_profiles(profiles):
    if not isinstance(profiles, list):
        raise ValueError("custom_profiles debe ser una lista.")
    incoming = [validate_custom_profile(p) for p in profiles]
    ids = [p["id"] for p in incoming]
    if len(ids) != len(set(ids)):
        raise ValueError("Hay identificadores duplicados en la importacion.")
    current = load_custom_profiles()
    current_ids = {p["id"] for p in current}
    additions = [p for p in incoming if p["id"] not in current_ids]
    save_custom_profiles_to_disk(current + additions)
    return {"status": "success", "imported": len(additions), "total_custom": len(current) + len(additions)}


def get_all_profiles() -> List[Dict[str, Any]]:
    """Devuelve la lista unificada de perfiles estándar y personalizados."""
    builtin = list(DEFAULT_BUILTIN_PROFILES)
    custom = load_custom_profiles()
    return builtin + custom


def get_profile_by_id(profile_id: str) -> Dict[str, Any]:
    """Obtiene un perfil por su ID con fallback seguro a OFFSET_300."""
    all_p = get_all_profiles()
    for p in all_p:
        if p["id"] == profile_id:
            return p
    return DEFAULT_BUILTIN_PROFILES[0]


def _numeric_value(data: Dict[str, Any], *keys: str, default):
    """Keep explicit zero values; only skip missing or empty fields."""
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return default


def create_custom_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    """Crea un nuevo perfil personalizado con validación de rangos."""
    raw_name = data.get("name", "Nuevo Perfil Personalizado").strip()
    safe_slug = "".join(c if c.isalnum() else "_" for c in raw_name.upper())[:24]
    profile_id = f"CUSTOM_{safe_slug}_{uuid.uuid4().hex[:4]}"

    new_profile = {
        "id": profile_id,
        "name": raw_name,
        "destination": data.get("destination", "Perfil personalizado de imprenta").strip(),
        "target_dpi": int(_numeric_value(data, "target_dpi", "dpi", default=300)),
        "min_bleed_mm": float(_numeric_value(data, "min_bleed_mm", "bleed_mm", default=3.0)),
        "max_tac": int(_numeric_value(data, "max_tac", "tac_limit", "tac", default=300)),
        "min_hairline_pt": float(_numeric_value(data, "min_hairline_pt", "hairline_pt", default=0.25)),
        "safety_margin_mm": float(_numeric_value(data, "safety_margin_mm", "safety_margin", default=3.0)),
        "color_family": data.get("color_family", "CMYK"),
        "allow_spot_colors": data.get("allow_spot_colors", True),
        "require_fonts_embedded": data.get("require_fonts_embedded", True),
        "is_custom": True,
        "is_builtin": False,
        "created_at": datetime.now().strftime("%d/%m/%Y %H:%M")
    }

    current = load_custom_profiles()
    new_profile = validate_custom_profile(new_profile)
    current.append(new_profile)
    save_custom_profiles_to_disk(current)
    return new_profile


def update_custom_profile(profile_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Actualiza los parámetros de un perfil personalizado existente."""
    current = load_custom_profiles()
    target_idx = None
    for idx, p in enumerate(current):
        if p["id"] == profile_id:
            target_idx = idx
            break

    if target_idx is None:
        return None

    p = current[target_idx]
    p["name"] = data.get("name", p["name"]).strip()
    p["destination"] = data.get("destination", p["destination"]).strip()
    p["target_dpi"] = int(_numeric_value(data, "target_dpi", "dpi", default=p["target_dpi"]))
    p["min_bleed_mm"] = float(_numeric_value(data, "min_bleed_mm", "bleed_mm", default=p["min_bleed_mm"]))
    p["max_tac"] = int(_numeric_value(data, "max_tac", "tac_limit", "tac", default=p["max_tac"]))
    p["min_hairline_pt"] = float(_numeric_value(data, "min_hairline_pt", "hairline_pt", default=p["min_hairline_pt"]))
    p["safety_margin_mm"] = float(_numeric_value(data, "safety_margin_mm", "safety_margin", default=p["safety_margin_mm"]))
    p["color_family"] = data.get("color_family", p["color_family"])
    p["allow_spot_colors"] = data.get("allow_spot_colors", p["allow_spot_colors"])
    p["require_fonts_embedded"] = data.get("require_fonts_embedded", p["require_fonts_embedded"])
    p["updated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")

    p = validate_custom_profile(p)
    current[target_idx] = p
    save_custom_profiles_to_disk(current)
    return p


def delete_custom_profile(profile_id: str) -> bool:
    """Elimina un perfil personalizado."""
    current = load_custom_profiles()
    filtered = [p for p in current if p["id"] != profile_id]
    if len(filtered) != len(current):
        save_custom_profiles_to_disk(filtered)
        return True
    return False

