"""
generate_manual_pdf.py
======================
Generador del Manual de Usuario Oficial de IntelliPrint en PDF A4 de alta fidelidad.
Diseño editorial con membretes de Salesianos Urnieta, CIFP Mendizabala LHII y Gobierno Vasco.
"""

import os
from pathlib import Path
import pymupdf

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_PDF = BASE_DIR / "Manual_de_Usuario_IntelliPrint.pdf"

PAGE_W = 595.3   # A4 Width in pt
PAGE_H = 841.9   # A4 Height in pt
MARGIN_X = 40.0
CONTENT_W = PAGE_W - 2 * MARGIN_X  # 515.3 pt
HEADER_H = 60.0
FOOTER_Y = 810.0

# Paleta de colores
PALETTE = {
    "navy": (31 / 255, 38 / 255, 44 / 255),
    "blue": (37 / 255, 99 / 255, 235 / 255),
    "cyan": (0 / 255, 163 / 255, 255 / 255),
    "purple": (109 / 255, 40 / 255, 217 / 255),
    "slate_dark": (51 / 255, 65 / 255, 85 / 255),
    "slate": (100 / 255, 116 / 255, 139 / 255),
    "light_gray": (248 / 255, 250 / 255, 252 / 255),
    "border": (203 / 255, 213 / 255, 225 / 255),
    "emerald": (5 / 255, 150 / 255, 105 / 255),
    "amber": (217 / 255, 119 / 255, 6 / 255),
}


def draw_page_header_footer(doc: pymupdf.Document, page: pymupdf.Page, page_num: int, total_pages: int, title: str):
    """Cabecera y pie para páginas interiores."""
    # Cabecera sutil
    page.draw_line(
        pymupdf.Point(MARGIN_X, HEADER_H - 12),
        pymupdf.Point(PAGE_W - MARGIN_X, HEADER_H - 12),
        color=PALETTE["border"],
        width=0.6
    )
    page.insert_text(
        pymupdf.Point(MARGIN_X, HEADER_H - 18),
        "INTELLIPRINT v1.2.0 · MANUAL DE USUARIO Y GUÍA TÉCNICA",
        fontsize=7.2,
        fontname="helv",
        color=PALETTE["slate"]
    )
    page.insert_text(
        pymupdf.Point(PAGE_W - MARGIN_X - 160, HEADER_H - 18),
        "Salesianos Urnieta · CIFP Mendizabala LHII",
        fontsize=7.2,
        fontname="helv",
        color=PALETTE["slate"]
    )

    # Pie de página
    page.draw_line(
        pymupdf.Point(MARGIN_X, FOOTER_Y),
        pymupdf.Point(PAGE_W - MARGIN_X, FOOTER_Y),
        color=PALETTE["border"],
        width=0.6
    )
    page.insert_text(
        pymupdf.Point(MARGIN_X, FOOTER_Y + 14),
        "Proyecto de Innovación Aplicada en FP · Departamento de Educación (Eusko Jaurlaritza)",
        fontsize=7.2,
        fontname="helv",
        color=PALETTE["slate"]
    )
    page.insert_text(
        pymupdf.Point(PAGE_W - MARGIN_X - 60, FOOTER_Y + 14),
        f"Pág. {page_num} de {total_pages}",
        fontsize=7.2,
        fontname="helv",
        color=PALETTE["slate"]
    )


def build_manual_pdf():
    print("Iniciando generación del Manual de Usuario en PDF...")
    doc = pymupdf.open()

    # -------------------------------------------------------------------------
    # PÁGINA 1: PORTADA EDITORIAL
    # -------------------------------------------------------------------------
    p_cov = doc.new_page(width=PAGE_W, height=PAGE_H)

    # Banda superior azul marino
    p_cov.draw_rect(pymupdf.Rect(0, 0, PAGE_W, 110), fill=PALETTE["navy"])

    # Logos institucionales en cápsula blanca flotante
    p_sales = ASSETS_DIR / "logo-salesianos.png"
    p_mendi = ASSETS_DIR / "logo-mendizabala.png"
    p_edu = ASSETS_DIR / "logo-dept-educacion-1.png"

    if p_sales.exists() and p_mendi.exists() and p_edu.exists():
        capsule = pymupdf.Rect(MARGIN_X, 25, PAGE_W - MARGIN_X, 85)
        p_cov.draw_rect(capsule, fill=(1, 1, 1), radius=0.08)

        # 3 logos alineados con enlaces interactivos
        r_sales = pymupdf.Rect(MARGIN_X + 15, 32, MARGIN_X + 150, 78)
        p_cov.insert_image(r_sales, filename=str(p_sales), keep_proportion=True)
        p_cov.insert_link({"kind": pymupdf.LINK_URI, "from": r_sales, "uri": "https://salesianosurnieta.com/"})

        p_cov.draw_line(pymupdf.Point(MARGIN_X + 160, 36), pymupdf.Point(MARGIN_X + 160, 74), color=(0.85, 0.85, 0.85), width=0.8)

        r_mendi = pymupdf.Rect(MARGIN_X + 175, 32, MARGIN_X + 315, 78)
        p_cov.insert_image(r_mendi, filename=str(p_mendi), keep_proportion=True)
        p_cov.insert_link({"kind": pymupdf.LINK_URI, "from": r_mendi, "uri": "https://www.mendizabala.eus/"})

        p_cov.draw_line(pymupdf.Point(MARGIN_X + 325, 36), pymupdf.Point(MARGIN_X + 325, 74), color=(0.85, 0.85, 0.85), width=0.8)

        r_edu = pymupdf.Rect(MARGIN_X + 340, 32, MARGIN_X + 490, 78)
        p_cov.insert_image(r_edu, filename=str(p_edu), keep_proportion=True)
        p_cov.insert_link({"kind": pymupdf.LINK_URI, "from": r_edu, "uri": "https://www.euskadi.eus/gobierno-vasco/departamento-educacion/"})

    # Logo central IntelliPrint
    p_full_logo = ASSETS_DIR / "Logo-intelliprint.png"
    if not p_full_logo.exists():
        p_full_logo = ASSETS_DIR / "Logo-intelliprint.jpg"
    p_imago = ASSETS_DIR / "Logo-intelliprint-imago.png"
    if not p_imago.exists():
        p_imago = ASSETS_DIR / "Logo-intelliprint-imago.jpg"

    y_cov = 160.0
    if p_full_logo.exists():
        # Logo sin fondo oscuro centrado armónicamente
        w_logo = 320.0
        h_logo = w_logo * (300.0 / 1140.0)  # ~84 pt
        x_logo = (PAGE_W - w_logo) / 2.0
        p_cov.insert_image(pymupdf.Rect(x_logo, y_cov, x_logo + w_logo, y_cov + h_logo), filename=str(p_full_logo), keep_proportion=True)
        y_cov += h_logo + 25.0
    elif p_imago.exists():
        p_cov.insert_image(pymupdf.Rect(PAGE_W / 2 - 40, y_cov, PAGE_W / 2 + 40, y_cov + 80), filename=str(p_imago), keep_proportion=True)
        y_cov += 100.0

    # Título con contraste marcado de peso: Intelli (Light) + Print (Heavy Cyan)
    font_size_title = 28.0
    w_intelli = pymupdf.get_text_length("Intelli", fontname="helv", fontsize=font_size_title)
    p_cov.insert_text(pymupdf.Point(MARGIN_X, y_cov + 20), "Intelli", fontsize=font_size_title, fontname="helv", color=PALETTE["navy"])
    p_cov.insert_text(pymupdf.Point(MARGIN_X + w_intelli + 1.0, y_cov + 20), "Print", fontsize=font_size_title, fontname="hebo", color=PALETTE["cyan"])

    p_cov.insert_text(pymupdf.Point(MARGIN_X, y_cov + 45), "MANUAL OFICIAL DE USUARIO Y GUÍA DE OPERACIÓN TÉCNICA", fontsize=13.0, fontname="hebo", color=PALETTE["blue"])
    p_cov.insert_text(pymupdf.Point(MARGIN_X, y_cov + 62), "Versión 1.2.0 · Edición para Talleres Gráficos y Formación Profesional", fontsize=9.5, fontname="helv", color=PALETTE["slate"])

    p_cov.draw_line(pymupdf.Point(MARGIN_X, y_cov + 75), pymupdf.Point(PAGE_W - MARGIN_X, y_cov + 75), color=PALETTE["blue"], width=2.0)

    # Caja de Resumen Ejecutivo
    y_box = y_cov + 95
    box_rect = pymupdf.Rect(MARGIN_X, y_box, PAGE_W - MARGIN_X, y_box + 160)
    p_cov.draw_rect(box_rect, fill=PALETTE["light_gray"], color=PALETTE["border"], width=0.8)
    p_cov.draw_rect(pymupdf.Rect(MARGIN_X, y_box, MARGIN_X + 6, y_box + 160), fill=PALETTE["navy"])

    p_cov.insert_text(pymupdf.Point(MARGIN_X + 20, y_box + 24), "SISTEMA INTEGRAL DE PREFLIGHT, NORMALIZACIÓN E IMPOSICIÓN INTELIGENTE", fontsize=10.0, fontname="helv", color=PALETTE["navy"])

    desc_text = (
        "Guía oficial de referencia para operarios de preimpresión, maquinistas de impresión offset y digital, "
        "y alumnado de los Ciclos Formativos de Artes Gráficas de Formación Profesional.\n\n"
        "Cubre de forma exhaustiva la auditoría geométrica y colorimétrica según normas ISO 12647-2 y PDF/X, "
        "el catálogo de perfiles de taller, la corrección automática en 1 clic (conversión RGB/CMYK, sobreimpresión, "
        "líneas pelo, sangre reflejada), el motor de imposición de pliegos de máquina N-Up, el inspector de códigos de barras "
        "y QR a 100% K, la trazabilidad mediante código QR a pie de máquina y el simulador de consecuencias físicas en taller."
    )
    p_cov.insert_textbox(pymupdf.Rect(MARGIN_X + 20, y_box + 34, PAGE_W - MARGIN_X - 20, y_box + 150), desc_text, fontsize=8.5, fontname="helv", color=PALETTE["slate_dark"])

    # Créditos y Marco Institucional al pie de la portada
    y_cred = 680.0
    p_cov.draw_line(pymupdf.Point(MARGIN_X, y_cred), pymupdf.Point(PAGE_W - MARGIN_X, y_cred), color=PALETTE["border"], width=0.6)

    col1_w = CONTENT_W / 2
    # Columna Izquierda: Centros
    p_cov.insert_text(pymupdf.Point(MARGIN_X, y_cred + 20), "CENTROS DESARROLLADORES:", fontsize=8.5, fontname="helv", color=PALETTE["navy"])
    p_cov.insert_text(pymupdf.Point(MARGIN_X, y_cred + 38), "• CPIFP Salesianos Urnieta LHIPI (Gipuzkoa)", fontsize=8.0, fontname="helv", color=PALETTE["slate_dark"])
    p_cov.insert_text(pymupdf.Point(MARGIN_X, y_cred + 52), "• CIFP Mendizabala LHII (Álava)", fontsize=8.0, fontname="helv", color=PALETTE["slate_dark"])
    p_cov.insert_text(pymupdf.Point(MARGIN_X, y_cred + 66), "Departamentos de Artes Gráficas y Preimpresión Digital", fontsize=7.5, fontname="helv", color=PALETTE["slate"])

    # Columna Derecha: Marco
    p_cov.insert_text(pymupdf.Point(MARGIN_X + col1_w + 20, y_cred + 20), "MARCO INSTITUCIONAL Y FINANCIACIÓN:", fontsize=8.5, fontname="helv", color=PALETTE["navy"])
    p_cov.insert_text(pymupdf.Point(MARGIN_X + col1_w + 20, y_cred + 38), "• Proyectos de Innovación Aplicada en FP", fontsize=8.0, fontname="helv", color=PALETTE["slate_dark"])
    p_cov.insert_text(pymupdf.Point(MARGIN_X + col1_w + 20, y_cred + 52), "• Departamento de Educación (Eusko Jaurlaritza / Gobierno Vasco)", fontsize=8.0, fontname="helv", color=PALETTE["slate_dark"])
    p_cov.insert_text(pymupdf.Point(MARGIN_X + col1_w + 20, y_cred + 66), "Convocatoria 2026 - 2027", fontsize=7.5, fontname="helv", color=PALETTE["slate"])

    # Pie institucional inferior
    p_cov.insert_text(pymupdf.Point(MARGIN_X, 810), "IntelliPrint Preflight · Software Libre y de Innovación Gráfica para Formación Profesional", fontsize=7.0, fontname="helv", color=PALETTE["slate"])

    # -------------------------------------------------------------------------
    # PÁGINAS DE CONTENIDO TÉCNICO (Texto estructurado)
    # -------------------------------------------------------------------------

    sections_data = [
        # (Titulo_Seccion, [Subsecciones / Parrafos / Cuadros])
        (
            "1. ¿QUÉ ES INTELLIPRINT?",
            [
                ("1.1. Filosofía de Taller: Objetivo Cero Errores y Cero Desperdicio",
                 "IntelliPrint es una solución informática avanzada de ingeniería gráfica concebida para auditar, normalizar, corregir e imponer documentos PDF antes de su envío a las prensas de impresión offset y digital. En la industria gráfica actual, más del 70% de las paradas no planificadas de máquina y repeticiones de tirada se deben a defectos inadvertidos en los archivos suministrados por clientes: falta de sangre, tipografías compuestas en 4 tintas (Rich Black), exceso de tinta (TAC > 300%), líneas invisibles para el láser CTP o códigos de barras borrosos."),
                ("1.2. Identidad Visual 'iP' y Enlaces Institucionales",
                 "Incorpora el logotipo de vanguardia 'iP' en degradado proceso CMY junto al bloque tipográfico de contraste con 'Intelli' en Light 300 blanco y 'Print' en Heavy 700 cian (#00A3FF). Todos los logotipos institucionales en web y PDF son interactivos y enlazan a Salesianos Urnieta, Mendizabala LHII y Gobierno Vasco."),
                ("1.3. Ahorro Económico, Sostenibilidad y Arquitectura",
                 "Corregir un error de preimpresión en el ordenador cuesta menos de 1 minuto frente a cientos de pliegos desperdiciados en máquina. Desarrollado en Python (FastAPI, PyMuPDF, OpenCV, Pillow) y frontend ultrarrápido en HTML5/Tailwind.")
            ],
            "CALLOUT_EMERALD:Cero Desperdicio: IntelliPrint conecta la ingeniería de software con la física de taller para evitar maculatura y devoluciones."
        ),
        (
            "2. PRIMEROS PASOS Y CONFIGURACIÓN DEL PREFLIGHT",
            [
                ("2.1. Conexión, Modo Cabina D50 e Inspección Preliminar",
                 "Acceso web inmediato sin cliente pesado. Conmutador [🌙 Cabina D50] para protección cromática según ISO 3664 y modo pantalla completa [⛶]. Al arrastrar el PDF, la lectura rápida reporta peso, páginas, recorte en mm, fotos y OutputIntent."),
                ("2.2. Los 6 Perfiles de Verificación Estándar (Paso 2)",
                 "Offset Comercial (300% TAC, 3 mm sangre), Digital Estándar (320% TAC, 2 mm), Prensa (240% TAC, 2 mm), Packaging (280% TAC, 5 mm de troquel), Gran Formato (150 DPI, 5 mm) y Web / Pantalla RGB (0.0 mm de sangre, 96 DPI, sRGB nativo sin restricción de TAC)."),
                ("2.3. Distinción Fundamental: Paso 2 (Destino) vs Paso 3 (Perfil ICC)",
                 "El Paso 2 (Perfil de Destino) es el inspector y baremo de calidad; NO incrusta perfiles en el PDF original. El Paso 3 (Perfil de Color ICC) define qué archivo .icc físico se inyecta como OutputIntent al generar el PDF normalizado o reparado."),
                ("2.4. Editor de Perfiles de Preflight Personalizados FP",
                 "Permite a docentes y jefes de taller configurar tolerancias a medida (DPI, sangrado de 0 a 10 mm, límite de TAC, hairlines y reglas booleanas de fuentes y Pantone) con exportación e importación en archivos JSON.")
            ],
            None
        ),
        (
            "3. EL INFORME DE VERIFICACIÓN (PREFLIGHT REPORT)",
            [
                ("3.1. Semáforo Global de Producción",
                 "Tres tarjetas superiores ofrecen el diagnóstico formal: Resultado Técnico (Apto en verde, Ajustes en ámbar, Rechazado en rojo), Espacio de Color & ICC y Geometría & Cajas (corte y sangre)."),
                ("3.2. Pestaña 1: Hallazgos Técnicos (Findings)",
                 "Lista todas las comprobaciones organizadas por severidad. Para cada fallo (falta de sangre, líneas pelo, imágenes en baja resolución), ofrece un botón de corrección automática inmediata."),
                ("3.3. Pestaña 2: Corrector Ortográfico Editorial",
                 "Audita los textos con un diccionario de 85.000 palabras en español y glosario de Artes Gráficas, permitiendo corregir erratas en titulares y créditos antes de quemar planchas."),
                ("3.4. Pestaña 3: Métricas de Producción y Heatmap de TAC",
                 "Muestra la Cobertura Total de Tinta (TAC) y proyecta un mapa de calor resaltando en amarillo y rojo las zonas que superan el 300% de tinta con grave riesgo de repintado."),
                ("3.5. Pestañas 4, 5 y 6: Separaciones CMYK, Slider y Firma",
                 "Mesa de luz para aislar canales C, M, Y, K; comparador antes/después con cortinilla interactiva; y panel de Release con lienzo táctil para la firma de autorización de tirada."),
                ("3.6. Barra de Herramientas Ergonómica Segmentada",
                 "Estructura las acciones en tres bandejas especializadas: Acciones Principales (Taller en 1 Clic, Descargar PDF, Ficha Técnica), Prensa & Taller (Imposición Pliego, Tinteros CIP3, Ficha Maquinista) y Ajustes Técnicos (Marcas FOGRA, TAC, Códigos QR, Margen).")
            ],
            "CALLOUT_BLUE:Densitometría Virtual: Inspeccione la plancha del Negro (K) para asegurarse de que textos de 6 pt no manchan los cuerpos de color."
        ),
        (
            "4. SUITE DE CORRECCIONES EN 1 CLIC",
            [
                ("4.1. Taller en 1 Clic (Batch Auto-Fix)",
                 "Aplica en secuencia no destructiva: normalización de cajas PDF, generación de sangre reflejada de 3 mm si faltaba, conversión RGB a CMYK, sobreimpresión automática en textos negros y ensanchamiento de líneas finas a 0.30 pt."),
                ("4.2. Conversión RGB a CMYK y Tintas Planas",
                 "Convierte mapas de bits RGB a CMYK con el perfil de salida elegido y descompone colores Pantone no presupuestados a cuatricromía estándar para prensas de 4 cuerpos."),
                ("4.3. Corrección de Sobreimpresión (Overprint)",
                 "Fuerza sobreimpresión en textos negros 100% K para evitar descalces, y retira la sobreimpresión accidental en objetos blancos para que no desaparezcan en el CTP."),
                ("4.4. Hairlines y Vectorización de Tipografías",
                 "Eleva filetes menores a 0.25 pt a 0.30 pt garantizando su reproducción en plancha, y vectoriza fuentes tipográficas para solventar problemas de tipografías no incrustadas."),
                ("4.5. Sangre Reflejada (+3 mm) y Limitador de TAC",
                 "Genera una extensión en espejo de 3 mm en los bordes para eliminar filetes blancos en la guillotina, y comprime sombras al 300% de TAC impidiendo el maculado en pila."),
                ("4.6. Tira de Control Normalizada FOGRA / ISO 12647-2",
                 "Inyecta marcas de corte y tira espectrofotométrica en espacio nativo DeviceCMYK: sólidos 100%, escala tonal 50%, altas luces (3%, 5%), sombras (95%, 98%), trapping, tríada de Balance de Grises (CMY50 vs REF50) y miras vernier de arrastre (slur) y doblado (doubling).")
            ],
            None
        ),
        (
            "5. MÓDULOS AVANZADOS: IMPOSICIÓN, CIP3, CÓDIGOS Y HOT-FOLDER",
            [
                ("5.1. Motor de Imposición de Pliegos N-Up",
                 "Montaje de pliegos en SRA3, A3, A4, B2 o B1. Permite esquemas de Paso y Repetición (tarjetas y flyers) o Cuadernillo Grapado para revistas. Gestiona automáticamente los 3 casos de sangre (sin sangre, con 3 mm, o recortando marcas previas duplicadas)."),
                ("5.2. Exportación de Datos CIP3 / PPF v3.0 & Preajuste de Tinteros",
                 "Calcula la cobertura de tinta del pliego dividida en 16, 24 o 32 zonas longitudinales. Estima consumos en kg y gramos de tinta CMYK según tirada y papel, detecta zonas secas en rodillos y genera archivo .ppf y Ficha PDF para el maquinista."),
                ("5.3. Inspector y Corrector de Códigos de Barras y QR a 100% K",
                 "Detección por visión artificial (OpenCV) de códigos EAN-13, QR, UPC y Code 128. Comprueba el dígito GS1 y si las barras están tramadas en 4 tintas (Rich Black). En 1 clic regenera el código vectorial en 100% K puro con zona de reserva blanca (Quiet Zone)."),
                ("5.4. Carpeta Caliente (Hot-Folder) y Cola de Lotes",
                 "Procesa decenas de archivos concurrentemente. El servicio en segundo plano vigila la carpeta hotfolder/in/; al depositar un PDF, lo analiza y mueve a out_aprobados/ o a out_rechazados/ con el informe para el cliente."),
                ("5.5. Inspector de Margen de Seguridad y Lomo",
                 "Distingue hojas sueltas (tarjetas 85x55: margen 3 mm, lomo 0 mm) frente a publicaciones (≥ 4 págs: margen 3 mm, lomo 8 mm). Dibuja avisos visuales sobre textos en riesgo de corte.")
            ],
            "CALLOUT_AMBER:Alerta de Códigos de Barras: Un código impreso en 4 tintas CMYK provoca rechazo en escáneres láser de supermercado. Exija siempre 100% K puro."
        ),
        (
            "6. TRAZABILIDAD QR DEL MAQUINISTA Y MODO DIDÁCTICO FP",
            [
                ("6.1. Código QR en el Margen Técnico (Slug) y Ficha Móvil",
                 "Al imponer pliegos se inyecta en el rebaje un código QR 100% K de 9x9 mm. El maquinista enfoca la cámara y abre la consola web móvil (/verify/{job_id}) a pie de máquina en 1 segundo con semáforo, tintas y descargas directas."),
                ("6.2. Banco Didáctico Ampliado de 20 Retos Oficiales FP",
                 "20 casos de estudio reales organizados en 3 categorías: Iniciación FP (7 retos: Rich Black, RGB sRGB, sin sangre, 72 DPI, fuentes no embebidas, sin TrimBox, texto tramado), Intermedio FP (7 retos: TAC 365%, 5 Pantones, blanco sobreimpreso, trapping, orla fina, negro knockout, tinteros CIP3) y Avanzado FP (6 retos: código 4 tintas, lomo medianil, barniz calado, QR farmacia, SRA3 sin calles, solapa pegado)."),
                ("6.3. Simulador Físico de Consecuencias en Taller",
                 "Sliders interactivos que simulan descalce de planchas offset, repintado en pila por exceso de tinta, oscilación y filete blanco de guillotina, y pérdida de líneas en insoladora CTP."),
                ("6.4. Quiz Técnico y Ficha Oficial del Alumno (PDF A4)",
                 "Cuestionario de 5 preguntas de normativa ISO con baremo de notas y emisión automática de la Ficha Oficial de Práctica en PDF A4 con sellos y casillas para firmas docentes.")
            ],
            "CALLOUT_PURPLE:Formación Profesional: El simulador físico enseña a los estudiantes de Artes Gráficas las consecuencias mecánicas reales que provocan los fallos de PDF en el taller."
        ),
        (
            "7. DOCUMENTACIÓN DE SALIDA Y PREGUNTAS FRECUENTES (FAQ)",
            [
                ("7.1. Certificado Técnico de Preflight, Guía Cliente y CIP3 (PDF A4)",
                 "Certificado formal para el archivo de taller con huella SHA-256; Guía didáctica para el cliente con tutoriales de corrección en InDesign/Photoshop; y hoja de llaves de tintero CIP3."),
                ("7.2. ¿Qué diferencia real hay entre el Paso 2 y el Paso 3?",
                 "El Paso 2 (Perfil de Destino) es el inspector de reglas y tolerancias; NO incrusta perfiles en el PDF. El Paso 3 (Perfil ICC) define qué perfil físico viaja como OutputIntent al normalizar el archivo."),
                ("7.3. ¿Por qué el perfil 'Web / Pantalla' no tiene sangre?",
                 "Los documentos para pantallas digitales no sufren corte mecánico ni plegado físico. Exige 0.0 mm de sangre, admite y recomienda modo RGB a 96 DPI y desactiva el límite de TAC."),
                ("7.4. Respuestas Técnicas de Taller y Normativa ISO",
                 "Rich Black en texto fino causa descalce por vibración mecánica; la sangre reflejada prolonga los 3 mm exteriores sin tocar el diseño; y el sistema cumple ISO 12647-2, ISO 15930, CIP3 e ISO 15420.")
            ],
            None
        )
    ]

    # Generar páginas de contenido
    for sec_title, subsections, callout in sections_data:
        p = doc.new_page(width=PAGE_W, height=PAGE_H)
        cur_y = HEADER_H + 10

        # Título de Sección
        p.insert_text(pymupdf.Point(MARGIN_X, cur_y), sec_title, fontsize=14.0, fontname="helv", color=PALETTE["navy"])
        cur_y += 6
        p.draw_line(pymupdf.Point(MARGIN_X, cur_y), pymupdf.Point(PAGE_W - MARGIN_X, cur_y), color=PALETTE["blue"], width=1.5)
        cur_y += 18

        # Subsecciones
        for sub_title, sub_desc in subsections:
            # Subtítulo
            p.insert_text(pymupdf.Point(MARGIN_X, cur_y), sub_title, fontsize=10.0, fontname="helv", color=PALETTE["blue"])
            cur_y += 13

            # Párrafo descriptivo
            lines_est = len(sub_desc) / 95.0
            h_text = max(28.0, lines_est * 12.0 + 8.0)
            text_rect = pymupdf.Rect(MARGIN_X, cur_y, PAGE_W - MARGIN_X, cur_y + h_text)
            p.insert_textbox(text_rect, sub_desc, fontsize=8.2, fontname="helv", color=PALETTE["slate_dark"])
            cur_y += h_text + 10

        # Callout destacado si existe
        if callout:
            cur_y += 6
            c_type, c_text = callout.split(":", 1)
            c_box = pymupdf.Rect(MARGIN_X, cur_y, PAGE_W - MARGIN_X, cur_y + 44)

            if "EMERALD" in c_type:
                fill_c, bdr_c = (0.93, 0.98, 0.94), PALETTE["emerald"]
            elif "AMBER" in c_type:
                fill_c, bdr_c = (0.99, 0.96, 0.90), PALETTE["amber"]
            elif "PURPLE" in c_type:
                fill_c, bdr_c = (0.96, 0.94, 0.99), PALETTE["purple"]
            else:
                fill_c, bdr_c = (0.94, 0.96, 0.99), PALETTE["blue"]

            p.draw_rect(c_box, fill=fill_c, color=PALETTE["border"], width=0.6)
            p.draw_rect(pymupdf.Rect(MARGIN_X, cur_y, MARGIN_X + 4, cur_y + 44), fill=bdr_c)
            p.insert_textbox(pymupdf.Rect(MARGIN_X + 14, cur_y + 6, PAGE_W - MARGIN_X - 10, cur_y + 38), c_text, fontsize=7.8, fontname="helv", color=PALETTE["slate_dark"])

    # Aplicar cabeceras y pies de página a todas las páginas interiores (páginas 2 en adelante)
    total_pages = len(doc)
    for i in range(1, total_pages):
        draw_page_header_footer(doc, doc[i], page_num=i + 1, total_pages=total_pages, title="MANUAL DE USUARIO")

    # Guardar PDF optimizado
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUTPUT_PDF), deflate=True, garbage=4)
    doc.close()
    print(f"Manual PDF generado con éxito: {OUTPUT_PDF} ({OUTPUT_PDF.stat().st_size} bytes, {total_pages} páginas)")
    return OUTPUT_PDF

if __name__ == "__main__":
    build_manual_pdf()

