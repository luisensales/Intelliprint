"""
Herramienta de normalización de activos de marca IntelliPrint.
Actualiza todos los logotipos con:
1. Alineación derecha exacta (flush right) entre IntelliPrint y PREPRESS PRECISION ENGINE · ISO 12647.
2. Eliminación de la línea amarilla superior.
3. Eliminación de la parte magenta que sobresalía fuera del bucle azul de la 'P'.
4. Fondo transparente sin rectángulos oscuros externos para uso en documentos y fondos claros.
"""
import pymupdf
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"

def generate_brand_logos():
    print("Regenerando logotipos oficiales de IntelliPrint...")
    mat = pymupdf.Matrix(2.0, 2.0)

    # -------------------------------------------------------------------------
    # 1. IMAGO / SÍMBOLO SOLO (iP)
    # -------------------------------------------------------------------------
    imago_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <!-- Background Badge: Modern Carbon Squircle -->
  <rect x="28" y="28" width="456" height="456" rx="120" fill="#090D18" stroke="#1E293B" stroke-width="5"/>

  <!-- 'P' Loop in Electric Process Cyan -->
  <rect x="192" y="105" width="218" height="195" rx="85" fill="#00A3FF"/>

  <!-- Lower / Right Shard in Hyper-Magenta strictly inside the 'P' loop arc -->
  <path d="M 325 105 A 85 85 0 0 1 410 190 L 410 215 A 85 85 0 0 1 325 300 L 275 202 Z" fill="#FF006E"/>

  <!-- Inner Geometric Aperture (Negative Space) -->
  <rect x="242" y="149" width="90" height="107" rx="38" fill="#090D18"/>

  <!-- Structural Vertical Pillar ('i' stem) in Crisp White -->
  <rect x="105" y="180" width="75" height="225" rx="37" fill="#FFFFFF"/>

  <!-- Precision Node ('i' dot) in Acid Yellow -->
  <rect x="105" y="105" width="75" height="55" rx="26" fill="#F5EE00"/>
</svg>"""

    p_imago_svg = ASSETS_DIR / "Logo-intelliprint-imago.svg"
    p_imago_svg.write_text(imago_svg, encoding="utf-8")
    print(f"SVG Imago guardado: {p_imago_svg}")

    doc_im = pymupdf.open("svg", imago_svg.encode("utf-8"))
    pix_im_alpha = doc_im[0].get_pixmap(matrix=mat, alpha=True)
    p_imago_png = ASSETS_DIR / "Logo-intelliprint-imago.png"
    pix_im_alpha.save(str(p_imago_png))
    print(f"PNG Imago guardado: {p_imago_png}")

    pix_im_rgb = doc_im[0].get_pixmap(matrix=mat, alpha=False)
    p_imago_jpg = ASSETS_DIR / "Logo-intelliprint-imago.jpg"
    pix_im_rgb.save(str(p_imago_jpg))
    print(f"JPG Imago guardado: {p_imago_jpg}")

    # -------------------------------------------------------------------------
    # 2. LOGO COMPLETO HORIZONTAL (Símbolo + Tipografía + Subtítulo Alineado)
    # -------------------------------------------------------------------------
    full_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 920 300" width="920" height="300">
  <!-- Embedded Imago Symbol (Left) -->
  <g transform="translate(10, 20) scale(0.55)">
    <!-- Background Badge: Modern Carbon Squircle -->
    <rect x="28" y="28" width="456" height="456" rx="120" fill="#090D18" stroke="#1E293B" stroke-width="5"/>

    <!-- 'P' Loop in Electric Process Cyan -->
    <rect x="192" y="105" width="218" height="195" rx="85" fill="#00A3FF"/>

    <!-- Lower / Right Shard in Hyper-Magenta strictly inside the 'P' loop arc -->
    <path d="M 325 105 A 85 85 0 0 1 410 190 L 410 215 A 85 85 0 0 1 325 300 L 275 202 Z" fill="#FF006E"/>

    <!-- Inner Geometric Aperture (Negative Space) -->
    <rect x="242" y="149" width="90" height="107" rx="38" fill="#090D18"/>

    <!-- Structural Vertical Pillar ('i' stem) in Crisp White -->
    <rect x="105" y="180" width="75" height="225" rx="37" fill="#FFFFFF"/>

    <!-- Precision Node ('i' dot) in Acid Yellow -->
    <rect x="105" y="105" width="75" height="55" rx="26" fill="#F5EE00"/>
  </g>

  <!-- Typography: Intelli (Light) + Print (Heavy) -->
  <text x="320" y="165" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="124">
    <tspan font-weight="300" fill="#0F172A">Intelli</tspan><tspan font-weight="700" fill="#00A3FF">Print</tspan>
  </text>
  <!-- Subtitle: Flush Right Aligned with 'Print' at x = 888 pt -->
  <text x="320" y="228" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-weight="600" font-size="27.14" fill="#64748B">PREPRESS PRECISION ENGINE · ISO 12647</text>
</svg>"""

    p_full_svg = ASSETS_DIR / "Logo-intelliprint.svg"
    p_full_svg.write_text(full_svg, encoding="utf-8")
    print(f"SVG Full guardado: {p_full_svg}")

    doc_full = pymupdf.open("svg", full_svg.encode("utf-8"))
    pix_full_alpha = doc_full[0].get_pixmap(matrix=mat, alpha=True)
    p_full_png = ASSETS_DIR / "Logo-intelliprint.png"
    pix_full_alpha.save(str(p_full_png))
    print(f"PNG Full guardado: {p_full_png} ({pix_full_alpha.width}x{pix_full_alpha.height})")

    pix_full_rgb = doc_full[0].get_pixmap(matrix=mat, alpha=False)
    p_full_jpg = ASSETS_DIR / "Logo-intelliprint.jpg"
    pix_full_rgb.save(str(p_full_jpg))
    print(f"JPG Full guardado: {p_full_jpg}")

    # -------------------------------------------------------------------------
    # 3. LOGO TIPOGRÁFICO SOLO
    # -------------------------------------------------------------------------
    tipo_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 620 220" width="620" height="220">
  <text x="10" y="125" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="124">
    <tspan font-weight="300" fill="#0F172A">Intelli</tspan><tspan font-weight="700" fill="#00A3FF">Print</tspan>
  </text>
  <text x="10" y="185" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-weight="600" font-size="27.14" fill="#64748B">PREPRESS PRECISION ENGINE · ISO 12647</text>
</svg>"""

    p_tipo_svg = ASSETS_DIR / "Logo-intelliprint-tipo.svg"
    p_tipo_svg.write_text(tipo_svg, encoding="utf-8")
    print(f"SVG Tipo guardado: {p_tipo_svg}")

    doc_tipo = pymupdf.open("svg", tipo_svg.encode("utf-8"))
    pix_tipo_alpha = doc_tipo[0].get_pixmap(matrix=mat, alpha=True)
    p_tipo_png = ASSETS_DIR / "Logo-intelliprint-tipo.png"
    pix_tipo_alpha.save(str(p_tipo_png))
    print(f"PNG Tipo guardado: {p_tipo_png}")

    pix_tipo_rgb = doc_tipo[0].get_pixmap(matrix=mat, alpha=False)
    p_tipo_jpg = ASSETS_DIR / "Logo-intelliprint-tipo.jpg"
    pix_tipo_rgb.save(str(p_tipo_jpg))
    print(f"JPG Tipo guardado: {p_tipo_jpg}")

    print("Todos los activos de marca han sido regenerados con éxito.")

if __name__ == "__main__":
    generate_brand_logos()
