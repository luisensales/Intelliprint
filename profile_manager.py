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


def load_custom_profiles() -> List[Dict[str, Any]]:
    """Carga los perfiles personalizados guardados en custom_profiles.json."""
    if not CUSTOM_PROFILES_FILE.exists():
        return []
    try:
        with open(CUSTOM_PROFILES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("custom_profiles", [])
    except Exception as e:
        print(f"[profile_manager] Error leyendo perfiles personalizados: {e}")
        return []


def save_custom_profiles_to_disk(profiles: List[Dict[str, Any]]):
    """Persiste los perfiles personalizados en disco."""
    try:
        payload = {
            "version": "1.2.0",
            "updated_at": datetime.now().isoformat(),
            "custom_profiles": profiles
        }
        with open(CUSTOM_PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[profile_manager] Error guardando perfiles personalizados: {e}")


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
        "target_dpi": int(data.get("target_dpi") or data.get("dpi") or 300),
        "min_bleed_mm": float(_numeric_value(data, "min_bleed_mm", "bleed_mm", default=3.0)),
        "max_tac": int(data.get("max_tac") or data.get("tac_limit") or data.get("tac") or 300),
        "min_hairline_pt": float(data.get("min_hairline_pt") or data.get("hairline_pt") or 0.25),
        "safety_margin_mm": float(_numeric_value(data, "safety_margin_mm", "safety_margin", default=3.0)),
        "color_family": data.get("color_family", "CMYK"),
        "allow_spot_colors": bool(data.get("allow_spot_colors", True)),
        "require_fonts_embedded": bool(data.get("require_fonts_embedded", True)),
        "is_custom": True,
        "is_builtin": False,
        "created_at": datetime.now().strftime("%d/%m/%Y %H:%M")
    }

    current = load_custom_profiles()
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
    p["target_dpi"] = int(data.get("target_dpi") or data.get("dpi") or p["target_dpi"])
    p["min_bleed_mm"] = float(_numeric_value(data, "min_bleed_mm", "bleed_mm", default=p["min_bleed_mm"]))
    p["max_tac"] = int(data.get("max_tac") or data.get("tac_limit") or data.get("tac") or p["max_tac"])
    p["min_hairline_pt"] = float(data.get("min_hairline_pt") or data.get("hairline_pt") or p["min_hairline_pt"])
    p["safety_margin_mm"] = float(_numeric_value(data, "safety_margin_mm", "safety_margin", default=p["safety_margin_mm"]))
    p["color_family"] = data.get("color_family", p["color_family"])
    p["allow_spot_colors"] = bool(data.get("allow_spot_colors", p["allow_spot_colors"]))
    p["require_fonts_embedded"] = bool(data.get("require_fonts_embedded", p["require_fonts_embedded"]))
    p["updated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")

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

