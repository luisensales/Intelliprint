"""
Herramienta de normalización de activos de marca IntelliPrint.
Genera versiones transparentes de alta resolución de Logo-intelliprint.svg, PNG y JPG
sin fondo azul oscuro y sin los 4 puntos de cuatricromía al final del subtítulo.
"""
import pymupdf
from PIL import Image
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"

def generate_brand_logos():
    print("Normalizando logotipos oficiales de IntelliPrint...")

    # 1. Logo Completo Horizontal (Símbolo + Tipografía + Subtítulo) SIN FONDO OSCURO y SIN LOS 4 PUNTOS
    # Dimensión exacta: 1120 x 300 pt
    full_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1140 300" width="1140" height="300">
  <!-- Embedded Imago Symbol (Left) -->
  <g transform="translate(10, 20) scale(0.55)">
    <rect x="28" y="28" width="456" height="456" rx="120" fill="#090D18" stroke="#1E293B" stroke-width="5"/>
    <rect x="192" y="105" width="218" height="195" rx="85" fill="#00A3FF"/>
    <path d="M 325 105 C 375 105, 410 145, 410 202 C 410 260, 375 300, 325 300 L 192 300 L 290 202 Z" fill="#FF006E"/>
    <rect x="242" y="149" width="90" height="107" rx="38" fill="#090D18"/>
    <rect x="105" y="180" width="75" height="225" rx="37" fill="#FFFFFF"/>
    <rect x="105" y="105" width="75" height="55" rx="26" fill="#F5EE00"/>
    <line x1="310" y1="80" x2="310" y2="105" stroke="#F5EE00" stroke-width="5" stroke-linecap="round"/>
  </g>

  <!-- Typography: Intelli (Light) + Print (Heavy) -->
  <text x="320" y="165" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="124">
    <tspan font-weight="300" fill="#0F172A" letter-spacing="2">Intelli</tspan><tspan font-weight="700" fill="#00A3FF" letter-spacing="-1">Print</tspan>
  </text>
  <text x="325" y="228" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-weight="600" font-size="28" fill="#64748B" letter-spacing="4">PREPRESS PRECISION ENGINE · ISO 12647</text>
</svg>"""

    svg_path = ASSETS_DIR / "Logo-intelliprint.svg"
    svg_path.write_text(full_svg, encoding="utf-8")
    print(f"SVG guardado: {svg_path}")

    # Render a PNG transparente de alta definición (300 DPI) con PyMuPDF
    doc = pymupdf.open("svg", full_svg.encode("utf-8"))
    p = doc[0]
    # Usamos matriz o dpi para obtener alta resolución
    mat = pymupdf.Matrix(2.0, 2.0)
    pix_alpha = p.get_pixmap(matrix=mat, alpha=True)
    png_path = ASSETS_DIR / "Logo-intelliprint.png"
    pix_alpha.save(str(png_path))
    print(f"PNG transparente guardado: {png_path} ({pix_alpha.width}x{pix_alpha.height})")

    # Render a JPG sobre blanco para compatibilidad
    pix_rgb = p.get_pixmap(matrix=mat, alpha=False)
    jpg_path = ASSETS_DIR / "Logo-intelliprint.jpg"
    pix_rgb.save(str(jpg_path))
    print(f"JPG guardado: {jpg_path}")

    # 2. Logo Tipográfico Solo (sin isotipo) SIN FONDO OSCURO y SIN LOS 4 PUNTOS
    tipo_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 880 220" width="880" height="220">
  <text x="20" y="125" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="112">
    <tspan font-weight="300" fill="#0F172A" letter-spacing="2">Intelli</tspan><tspan font-weight="700" fill="#00A3FF" letter-spacing="-1">Print</tspan>
  </text>
  <text x="24" y="185" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-weight="600" font-size="24" fill="#64748B" letter-spacing="4">PREPRESS PRECISION ENGINE · ISO 12647</text>
</svg>"""

    svg_tipo_path = ASSETS_DIR / "Logo-intelliprint-tipo.svg"
    svg_tipo_path.write_text(tipo_svg, encoding="utf-8")
    print(f"SVG tipo guardado: {svg_tipo_path}")

    doc_tipo = pymupdf.open("svg", tipo_svg.encode("utf-8"))
    pix_tipo = doc_tipo[0].get_pixmap(matrix=mat, alpha=True)
    png_tipo_path = ASSETS_DIR / "Logo-intelliprint-tipo.png"
    pix_tipo.save(str(png_tipo_path))
    print(f"PNG tipo guardado: {png_tipo_path}")

    pix_tipo_rgb = doc_tipo[0].get_pixmap(matrix=mat, alpha=False)
    jpg_tipo_path = ASSETS_DIR / "Logo-intelliprint-tipo.jpg"
    pix_tipo_rgb.save(str(jpg_tipo_path))
    print(f"JPG tipo guardado: {jpg_tipo_path}")

    print("Normalización de logos completada con éxito.")

if __name__ == "__main__":
    generate_brand_logos()
