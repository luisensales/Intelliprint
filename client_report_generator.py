"""
client_report_generator.py
==========================
Generador de Informe Pedagógico para el Cliente y Diseñador (páginas A4).

Produce una guía visual, comprensible y sin tecnicismos hostiles que el
taller de imprenta puede remitir al diseñador/cliente explicando exactamente
qué incidencias se detectaron en su PDF y cómo solucionarlas en InDesign / Illustrator.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

import pymupdf

from report_images import collect_report_image_issues

PAGE_W = 595.3
PAGE_H = 841.9
MARGIN_X = 35.0
CONTENT_W = PAGE_W - 2 * MARGIN_X  # 525.3 pt
HEADER_H = 70.0
FOOTER_Y = 808.0


def _palette():
    return {
        "navy": (31 / 255, 38 / 255, 44 / 255),
        "blue": (0.13, 0.40, 0.85),
        "indigo": (0.28, 0.25, 0.75),
        "slate": (0.35, 0.40, 0.48),
        "slate_dark": (0.12, 0.16, 0.22),
        "light": (0.96, 0.97, 0.99),
        "green": (0.10, 0.60, 0.35),
        "green_bg": (0.93, 0.98, 0.94),
        "green_border": (0.60, 0.85, 0.68),
        "amber": (0.85, 0.50, 0.05),
        "amber_bg": (0.99, 0.96, 0.90),
        "amber_border": (0.92, 0.78, 0.55),
        "red": (0.85, 0.20, 0.20),
        "red_bg": (0.99, 0.93, 0.93),
        "red_border": (0.92, 0.68, 0.68),
        "border": (0.82, 0.86, 0.90),
    }


_CR_STRINGS = {
    "es": {
        "guide_header": "· GUÍA DE ARTE FINAL",
        "guide_sub_1": "Informe pedagógico para el diseñador y cliente",
        "guide_sub_2_screen": "Control de calidad y preflight para pantallas y medios digitales",
        "guide_sub_2_print": "Control de calidad y preflight de arte final para imprenta",
        "footer_org": "IntelliPrint Preflight · Proyecto de Innovación Aplicada en FP · Salesianos Urnieta / CIFP Mendizabala LHII",
        "ref_job": "Ref. Trabajo:",
        "footer_note_screen": "Este informe ha sido generado para facilitar una comunicación clara y constructiva entre el diseñador, el cliente y el equipo técnico.",
        "footer_note_print": "Este informe ha sido generado para facilitar una comunicación clara y constructiva entre el diseñador y la imprenta.",
        "file_reviewed": "Archivo revisado:",
        "meta_line": "Fecha: {date}   |   Páginas: {pages}   |   Estándar: {standard}",
        "std_screen": "Pantalla / Documento Digital (sRGB)",
        "std_offset": "Imprenta Offset / Digital (ISO 12647-2)",
        "std_digital": "Impresión Digital Estándar (Tóner / Inkjet)",
        "std_newspaper": "Prensa y Papel Periódico (TAC 240%)",
        "std_packaging": "Packaging y Cartoncillo (Troquel)",
        "std_wide": "Gran Formato y Cartelería",
        "badge_ready_screen": "LISTO PARA PANTALLA",
        "badge_ready_screen_sub": "Optimizado para visualización digital",
        "badge_ready_print": "LISTO PARA IMPRESIÓN",
        "badge_ready_print_sub": "Sin incidencias pendientes en la verificación",
        "badge_critical": "REQUIERE AJUSTES PREVIOS",
        "badge_critical_screen_sub": "Puntos críticos para pantalla",
        "badge_critical_print_sub": "Puntos críticos antes de máquina",
        "badge_warn": "RECOMENDACIONES DE MEJORA",
        "badge_warn_screen_sub": "Avisos para optimizar la visualización",
        "badge_warn_print_sub": "Avisos para optimizar la tirada",
        "no_initial_history": "Historial inicial no disponible: se muestra únicamente la verificación del PDF actual.",
        "sec_pending": "INCIDENCIAS PENDIENTES EN EL PDF ACTUAL",
        "sec_resolved": "CORREGIDOS / YA NO DETECTADOS EN EL PDF ACTUAL",
        "sec_verified": "VERIFICACIÓN DE CALIDAD EN EL DOCUMENTO",
        "sec_images": "IMÁGENES QUE REQUIEREN AJUSTES",
        "continuation": "continuación",
        "prefix_resolved": "Diagnóstico inicial: ",
        "prefix_active": "Por qué afecta a la tirada: ",
        "label_resolved": "Resultado de la corrección y comprobación:",
        "label_active": "Cómo corregirlo en tu programa de maquetación (InDesign / Illustrator):",
        "badge_resolved": "REVISADO",
        "img_unspecified": "sin indicar",
        "img_unidentified": "sin identificar",
        "img_label": "Pág. {page} · Imagen {index}",
        "img_see_1": "Ver imagen en",
        "img_see_2": "la página {page}",
        "img_res": "Resolución: {dpi} ppp   |   Mínimo del perfil: {target} ppp",
        "img_color": "Color: {color}   |   {dims}",
        "img_size_na": "tamaño no disponible",
        "opt_header": "¿CÓMO PROCEDER AHORA? ELIGE LA OPCIÓN MÁS CÓMODA PARA TI",
        "opt_a_title": "Opción A: Corregir en tu programa de diseño",
        "opt_a_screen": (
            "Si prefieres mantener el control absoluto de tu archivo original, abre tu documento en InDesign, Illustrator o Canva, "
            "aplica los ajustes recomendados arriba y vuelve a exportar un nuevo PDF interactivo o digital en espacio sRGB.\n\n"
            "Envíanos el nuevo archivo y lo verificaremos de inmediato sin coste adicional."
        ),
        "opt_a_print": (
            "Si prefieres mantener el control absoluto de tu archivo original, abre tu documento en InDesign o Illustrator, "
            "aplica los ajustes recomendados arriba y vuelve a exportar un nuevo PDF (recomendado: estándar PDF/X-4 con sangrado).\n\n"
            "Envíanos el nuevo archivo y lo verificaremos de inmediato sin coste adicional."
        ),
        "opt_b_title": "Opción B: Corrección automática en taller",
        "opt_b_screen": (
            "¿Tienes urgencia o no dispones del archivo editable? Nuestro taller cuenta con el sistema profesional IntelliPrint, "
            "capaz de optimizar fuentes, normalizar imágenes a sRGB y ajustar el peso del PDF para visualización ágil.\n\n"
            "Indícanoslo por email o formulario y prepararemos el documento listo para pantalla y web."
        ),
        "opt_b_print": (
            "¿Tienes urgencia o no dispones del archivo editable? Nuestro taller cuenta con el sistema profesional IntelliPrint, "
            "capaz de corregir en 1 clic: sangrado sintético por reflejo, conversión a CMYK, trazado de fuentes y sobreimpresión de negro.\n\n"
            "Indícanoslo por email o teléfono y prepararemos el documento listo para máquina."
        ),
        "page_badge": "Guía {num} / {total}",
        "ok_screen": [
            ("Geometría y Visualización Digital", "Dimensiones de página adaptadas para visualización en pantalla y dispositivos digitales; no requiere sangrado de corte."),
            ("Espacio de Color RGB", "Imágenes y gráficos en espacio RGB / sRGB, optimizados para una reproducción cromática viva y fiel en monitores y navegadores."),
            ("Tipografías y Textos", "Todas las fuentes están debidamente incrustadas o trazadas; lectura nítida garantizada sin sustitución tipográfica."),
            ("Renderizado y Luminancia", "Documento optimizado para visualización fluida en visores PDF y web, sin dependencias de tintas físicas ni sobreimpresión."),
        ],
        "ok_print": [
            ("Sangrado y Geometría ISO", "El documento dispone de cajas de página y sangrado correcto (+3 mm) para un corte limpio en guillotina."),
            ("Espacio de Color CMYK", "Imágenes y gráficos vectoriales preparados para 4 tintas sin dependencias de color RGB."),
            ("Tipografías y Textos", "Todas las fuentes están debidamente incrustadas o trazadas; no habrá sustitución de tipos."),
            ("Sobreimpresión y Cobertura", "Los textos negros sobreimprimen al 100% K y la cobertura total de tinta respeta el límite de 300%."),
        ],
    },
    "eu": {
        "guide_header": "· AZKEN ARTEAREN GIDA",
        "guide_sub_1": "Diseinatzaile eta bezeroarentzako txosten pedagogikoa",
        "guide_sub_2_screen": "Pantaila eta euskarri digitaletarako kalitate-kontrola eta preflighta",
        "guide_sub_2_print": "Inprentarako azken artearen kalitate-kontrola eta preflighta",
        "footer_org": "IntelliPrint Preflight · LHko Berrikuntza Aplikatuko Proiektua · Salesianos Urnieta / CIFP Mendizabala LHII",
        "ref_job": "Lan-erref.:",
        "footer_note_screen": "Txosten hau diseinatzailearen, bezeroaren eta talde teknikoaren arteko komunikazio argi eta eraikitzailea errazteko sortu da.",
        "footer_note_print": "Txosten hau diseinatzailearen eta inprentaren arteko komunikazio argi eta eraikitzailea errazteko sortu da.",
        "file_reviewed": "Berrikusitako fitxategia:",
        "meta_line": "Data: {date}   |   Orriak: {pages}   |   Estandarra: {standard}",
        "std_screen": "Pantaila / Dokumentu Digitala (sRGB)",
        "std_offset": "Offset / Digital Inprenta (ISO 12647-2)",
        "std_digital": "Inprimaketa Digital Estandarra (Tonerra / Inkjet)",
        "std_newspaper": "Prentsa eta Egunkari-papera (TAC %240)",
        "std_packaging": "Packaginga eta Kartoitxoa (Trokela)",
        "std_wide": "Formatu Handia eta Kartelgintza",
        "badge_ready_screen": "PANTAILARAKO PREST",
        "badge_ready_screen_sub": "Ikuskatze digitalerako optimizatua",
        "badge_ready_print": "INPRIMATZEKO PREST",
        "badge_ready_print_sub": "Egiaztapenean gertakari aktiborik gabe",
        "badge_critical": "AURREKO DOIKUNTZAK BEHAR DITU",
        "badge_critical_screen_sub": "Pantailarako puntu kritikoak",
        "badge_critical_print_sub": "Makinarako puntu kritikoak",
        "badge_warn": "HOBEKUNTZA GOMENDIOAK",
        "badge_warn_screen_sub": "Ikuskatzea hobetzeko oharrak",
        "badge_warn_print_sub": "Tirada hobetzeko oharrak",
        "no_initial_history": "Hasierako historia ez dago eskuragarri: uneko PDFaren egiaztapena soilik erakusten da.",
        "sec_pending": "UNEKO PDFAN DAUDEN GERTAKARIAK",
        "sec_resolved": "ZUZENDUTA / UNEKO PDFAN EZ DIRA AGERI",
        "sec_verified": "DOKUMENTUAREN KALITATE-EGIAZTAPENA",
        "sec_images": "DOIKUNTZAK BEHAR DITUZTEN IRUDIAK",
        "continuation": "jarraipena",
        "prefix_resolved": "Hasierako diagnostikoa: ",
        "prefix_active": "Tiradan duen eragina: ",
        "label_resolved": "Zuzenketaren eta egiaztapenaren emaitza:",
        "label_active": "Nola zuzendu zure maketazio-programan (InDesign / Illustrator):",
        "badge_resolved": "BERRIKUSITA",
        "img_unspecified": "zehaztu gabe",
        "img_unidentified": "identifikatu gabe",
        "img_label": "{page}. orr. · {index}. irudia",
        "img_see_1": "Ikusi irudia",
        "img_see_2": "{page}. orrialdean",
        "img_res": "Bereizmena: {dpi} ppp   |   Profilaren gutxienekoa: {target} ppp",
        "img_color": "Kolorea: {color}   |   {dims}",
        "img_size_na": "tamaina ez dago eskuragarri",
        "opt_header": "NOLA JARRAITU ORAIN? AUKERATU ZURETZAT EROSOENA DEN BIDEA",
        "opt_a_title": "A aukera: Zure diseinu-programan zuzentzea",
        "opt_a_screen": (
            "Jatorrizko fitxategiaren kontrol osoa mantendu nahi baduzu, ireki dokumentua InDesign, Illustrator edo Canvan, "
            "aplikatu goiko doikuntzak eta esportatu berriro PDF interaktibo edo digital bat sRGB espazioan.\n\n"
            "Bidali fitxategi berria eta berehala egiaztatuko dugu kostu gehigarririk gabe."
        ),
        "opt_a_print": (
            "Jatorrizko fitxategiaren kontrol osoa mantendu nahi baduzu, ireki dokumentua InDesign edo Illustratorren, "
            "aplikatu goiko doikuntzak eta esportatu PDF berria (gomendatua: PDF/X-4 estandarra odoldurarekin).\n\n"
            "Bidali fitxategi berria eta berehala egiaztatuko dugu kostu gehigarririk gabe."
        ),
        "opt_b_title": "B aukera: Tailerrean zuzenketa automatikoa",
        "opt_b_screen": (
            "Presa duzu edo ez duzu fitxategi editagarririk? Gure tailerrak IntelliPrint sistema profesionala du: "
            "letra-tipoak optimizatu, irudiak sRGBra normalizatu eta PDFaren pisua egokitu ditzakegu.\n\n"
            "Jakinarazi posta elektronikoz eta dokumentua pantaila eta weberako prest utziko dugu."
        ),
        "opt_b_print": (
            "Presa duzu edo ez duzu fitxategi editagarririk? Gure tailerrak IntelliPrint sistema profesionala du "
            "klik bakarrez zuzentzeko: ispilu bidezko odoldura sintetikoa, CMYK bihurketa, letra-tipoen trazatua eta beltzaren gaininprimaketa.\n\n"
            "Jakinarazi posta elektronikoz edo telefonoz eta dokumentua makinarako prest utziko dugu."
        ),
        "page_badge": "Gida {num} / {total}",
        "ok_screen": [
            ("Geometria eta Pantaila-ikuskatzea", "Orrialde-neurriak pantaila eta gailu digitaletarako egokituak; ez du ebaketa-odoldurarik behar."),
            ("RGB Kolore Espazioa", "Irudi eta grafikoak RGB / sRGB espazioan daude, monitore eta nabigatzaileetan kolore bizi eta leiala bermatzeko."),
            ("Tipografiak eta Testuak", "Letra-tipo guztiak behar bezala kapsulatuta edo trazatuta daude; irakurketa garbia bermatua."),
            ("Errendatzea eta Luminantzia", "PDF bisore eta weberako ikuskatze arinerako optimizatua, tinta fisikoen mendekotasunik gabe."),
        ],
        "ok_print": [
            ("Odoldura eta ISO Geometria", "Dokumentuak orrialde-kaxak eta odoldura zuzena (+3 mm) ditu gillotinan ebaketa garbia lortzeko."),
            ("CMYK Kolore Espazioa", "Irudiak eta grafiko bektorialak 4 tintetarako prestatuak, RGB mendekotasunik gabe."),
            ("Tipografiak eta Testuak", "Letra-tipo guztiak behar bezala kapsulatuta edo trazatuta daude; ez da ordezkapen tipografikorik egongo."),
            ("Gaininprimaketa eta Estaldura", "Testu beltzek %100 K-n gaininprimatzen dute eta tinta-estaldura osoak %300eko muga errespetatzen du."),
        ],
    },
    "en": {
        "guide_header": "· FINAL ARTWORK GUIDE",
        "guide_sub_1": "Educational report for the designer and client",
        "guide_sub_2_screen": "Quality control and preflight for screens and digital media",
        "guide_sub_2_print": "Quality control and preflight of final artwork for print",
        "footer_org": "IntelliPrint Preflight · Applied VET Innovation Project · Salesianos Urnieta / CIFP Mendizabala LHII",
        "ref_job": "Job Ref.:",
        "footer_note_screen": "This report was generated to support clear, constructive communication between designer, client, and technical team.",
        "footer_note_print": "This report was generated to support clear, constructive communication between designer and print shop.",
        "file_reviewed": "Reviewed file:",
        "meta_line": "Date: {date}   |   Pages: {pages}   |   Standard: {standard}",
        "std_screen": "Screen / Digital Document (sRGB)",
        "std_offset": "Offset / Digital Press (ISO 12647-2)",
        "std_digital": "Standard Digital Printing (Toner / Inkjet)",
        "std_newspaper": "Newsprint & Coldset Press (TAC 240%)",
        "std_packaging": "Packaging & Folding Carton (Die-cut)",
        "std_wide": "Wide Format & Signage",
        "badge_ready_screen": "READY FOR SCREEN",
        "badge_ready_screen_sub": "Optimized for digital viewing",
        "badge_ready_print": "READY FOR PRESS",
        "badge_ready_print_sub": "No open issues found during verification",
        "badge_critical": "ADJUSTMENTS REQUIRED",
        "badge_critical_screen_sub": "Critical items for screen delivery",
        "badge_critical_print_sub": "Critical items before press",
        "badge_warn": "RECOMMENDATIONS",
        "badge_warn_screen_sub": "Warnings to optimize viewing",
        "badge_warn_print_sub": "Warnings to optimize the print run",
        "no_initial_history": "Initial baseline unavailable: showing current PDF verification only.",
        "sec_pending": "OPEN ISSUES IN CURRENT PDF",
        "sec_resolved": "FIXED / NO LONGER DETECTED IN CURRENT PDF",
        "sec_verified": "DOCUMENT QUALITY VERIFICATION",
        "sec_images": "IMAGES REQUIRING ATTENTION",
        "continuation": "continued",
        "prefix_resolved": "Initial diagnosis: ",
        "prefix_active": "Why it affects production: ",
        "label_resolved": "Fix outcome and verification:",
        "label_active": "How to fix it in your layout software (InDesign / Illustrator):",
        "badge_resolved": "REVIEWED",
        "img_unspecified": "unspecified",
        "img_unidentified": "unidentified",
        "img_label": "Page {page} · Image {index}",
        "img_see_1": "View image on",
        "img_see_2": "page {page}",
        "img_res": "Resolution: {dpi} ppi   |   Profile minimum: {target} ppi",
        "img_color": "Color: {color}   |   {dims}",
        "img_size_na": "dimensions unavailable",
        "opt_header": "HOW TO PROCEED NOW? CHOOSE THE OPTION THAT FITS BEST",
        "opt_a_title": "Option A: Fix in your design software",
        "opt_a_screen": (
            "If you prefer full control over your source file, open your document in InDesign, Illustrator, or Canva, "
            "apply the adjustments listed above, and re-export a digital PDF in sRGB.\n\n"
            "Send us the updated file and we will re-verify it right away at no extra charge."
        ),
        "opt_a_print": (
            "If you prefer full control over your source file, open your document in InDesign or Illustrator, "
            "apply the adjustments listed above, and re-export a print-ready PDF (recommended: PDF/X-4 with bleed).\n\n"
            "Send us the updated file and we will re-verify it right away at no extra charge."
        ),
        "opt_b_title": "Option B: Automated fix at the print shop",
        "opt_b_screen": (
            "In a hurry or missing the editable source? Our workshop uses IntelliPrint to optimize fonts, "
            "normalize images to sRGB, and prepare lightweight PDFs for crisp digital viewing.\n\n"
            "Let us know by email and we will prepare the document ready for screen and web."
        ),
        "opt_b_print": (
            "In a hurry or missing the editable source? Our workshop uses IntelliPrint to fix in one click: "
            "mirrored synthetic bleed, CMYK conversion, font outlining, and 100% K overprint.\n\n"
            "Let us know by email or phone and we will prepare the file ready for press."
        ),
        "page_badge": "Guide {num} / {total}",
        "ok_screen": [
            ("Geometry & Digital Viewing", "Page dimensions are suited for screens and digital devices; no trim bleed is needed."),
            ("RGB Color Space", "Images and graphics use RGB / sRGB for vibrant, accurate rendering across monitors and browsers."),
            ("Typography & Fonts", "All fonts are properly embedded or outlined; sharp rendering guaranteed without font substitution."),
            ("Rendering & Luminance", "Document is optimized for smooth PDF and web viewing without press ink dependencies."),
        ],
        "ok_print": [
            ("Bleed & ISO Geometry", "The document includes valid page boxes and +3 mm bleed for a clean guillotine trim."),
            ("CMYK Color Space", "Images and vector graphics are prepared for 4-color CMYK printing without RGB dependencies."),
            ("Typography & Fonts", "All fonts are properly embedded or outlined; no font substitution will occur on press."),
            ("Overprint & Ink Coverage", "Black body text overprints at 100% K and total area coverage stays within the 300% limit."),
        ],
    },
}


def _cr_lang(lang: str | None) -> str:
    return lang if lang in _CR_STRINGS else "es"


def _cr_tr(lang: str | None, key: str, **kwargs) -> Any:
    val = _CR_STRINGS[_cr_lang(lang)][key]
    return val.format(**kwargs) if isinstance(val, str) and kwargs else val


_CAT_TRANSLATIONS = {
    "eu": {
        "bleed": (
            "Perimetroko odoldura falta da (+3 mm 4 ertzetan)",
            "Diseinua ebaketa-lerro zehatzean amaitzen da. Inprentako gillotinan ebakitzean, paperaren edozein desplazamendu txikik ertzetan marra edo ertz zuri deserosoak sortuko ditu.",
            [
                "InDesignen: Fitxategia > Dokumentuaren doikuntza > Odoldura: idatzi 3 mm 4 aldeetan.",
                "Luzatu ertza ukitzen duten hondo, irudi eta kolore guztiak kanpoko GIDA GORRIra arte.",
                "PDFa esportatzean: 'Markak eta odoldura' fitxan, aktibatu 'Erabili dokumentuaren odoldura-ezarpenak'.",
            ],
        ),
        "rgb": (
            "RGB kolore-moduko irudiak detektatu dira",
            "Irudiak RGB espazioan daude (pantailetarako argi-espazioa). Inprentan 4 CMYK tintekin inprimatzen da; ustekabeko bihurketa batek kolore biziak itzali ditzake.",
            [
                "Photoshopen: Irudia > Modua > CMYK kolorea (ISO Coated v2 edo FOGRA39 profil estandarrarekin).",
                "Edo InDesignen PDFa esportatzean: Irteera > Kolore-bihurketa: 'Bihurtu helmugara (balioak mantenduz)' CMYK ISO Coated v2 helmugarekin.",
            ],
        ),
        "rgb_screen": (
            "CMYK irudiak pantailarako dokumentu batean (RGB)",
            "Helmugak RGB eskatzen du. CMYK irudiek kolore itzalagoak erakuts ditzakete pantailetan eta nabigatzaileetan.",
            [
                "Photoshopen: bihurtu irudiak sRGB profilera eta eguneratu estekak dokumentuan.",
                "Esportatu PDFa pantailarako adostutako RGB profilarekin eta egiaztatu berriro.",
            ],
        ),
        "fonts": (
            "Kapsulatu gabeko tipografiak PDFan",
            "PDF fitxategiak ez ditu letra-tipoak barne. Inprentako RIPak letra-tipo bera instalatuta ez badu, beste batekin ordezkatuko du diseinua desitxuratuz.",
            [
                "InDesign / Illustratorren: hautatu testuak eta sakatu Testua > Sortu sestra (Ctrl+Shift+O).",
                "Edo esportatu PDF/X-4 edo PDF/X-1a gisa, letra-tipoen kapsulazio osoa bermatzen duten industriako estandarrak baitira.",
            ],
        ),
        "black": (
            "Testu txikiak beltz konposatuan (C+M+Y+K) edo zulatuta",
            "12 pt baino txikiagoko irakurketa-testua lau tintaz osatuta dago. Offset makinan erregistro-desdoikuntza txikienak ere kolore-haloak edo testu lausoa sortuko ditu.",
            [
                "Aplikatu irakurketa-testu guztiei [Beltza] %100 K lagin purua (0 C / 0 M / 0 Y / 100 K).",
                "InDesignen: Hobespenak > Beltzaren itxura > egiaztatu '%100eko beltza gaininprimatu' aktibatuta dagoela.",
            ],
        ),
        "hairlines": (
            "Hari edo lerro meheegiak (< 0.25 pt)",
            "0.25 pt baino lodiera txikiagoko trazak daude. Offset plantxen CTP grabazioan, lerro horiek ahulegiak dira eta paperean desagertu egin daitezke.",
            [
                "InDesign / Illustratorreko Traza leihoan: handitu lerro guztien lodiera gutxienez 0.30 pt edo 0.50 pt-ra.",
            ],
        ),
        "spots": (
            "Tinta lauak (Pantone) kuatrikomiako lan batean",
            "Fitxategiak tinta zuzen bereziak ditu. Zure tirada 4 CMYK tintetan kontratatuta badago, tinta lauak deskonposatu egin behar dira plantxa gehigarririk ez behartzeko.",
            [
                "InDesignen: Leihoa > Laginak > klik bikoitza Pantone laginean > Kolore mota: aldatu 'Prozesua'-ra.",
            ],
        ),
        "tac": (
            "Gehiegizko tinta-estaldura osoa (> %300)",
            "Dokumentuko gune ilunek %300etik gorako tinta-batura pilatzen dute (C+M+Y+K). Horrek papera asetzen du eta orriak pilatzean orbanak (repintado) sor ditzake.",
            [
                "InDesignen PDFa esportatzean: Irteera > Helmuga: hautatu 'ISO Coated v2 300% (ECI)' profil estandarra, tinta automatikoki mugatzen baitu.",
            ],
        ),
        "safety_margin": (
            "Testuak ebaketa-lerrotik gertuegi (< 3 mm)",
            "Ebaketa-lerrotik (TrimBox) 3 mm baino gutxiagora testu edo elementu biziak antzeman dira. Gillotinak +-1 mm-ko tolerantzia mekanikoa du eta ertzean dauden elementuak moztuta gera daitezke.",
            [
                "InDesign / Illustratorren: aktibatu marjina-gidak eta kokatu testuak gutxienez orri-ertzetik 3 mm barrura.",
            ],
        ),
        "resolution": (
            "Irudien bereizmen eskasa edo egiaztaezina",
            "Profilaren gutxieneko bereizmenaren azpiko edo neurtu ezin diren irudiak daude; pixelatua edo zorroztasun-galera eragin dezakete.",
            [
                "InDesign / Illustratorren: berrikusi estekak eta erabili jatorrizko irudi egokiak amaierako tamainan.",
                "Txikitu kokatutako tamaina edo ordezkatu irudia; birlaginketaz ppp-ak igotzeak ez du xehetasunik berreskuratzen.",
            ],
        ),
    },
    "en": {
        "bleed": (
            "Missing Perimeter Bleed (+3 mm on all 4 sides)",
            "The artwork ends right at the trim edge. During guillotine cutting, even a tiny paper shift will expose unwanted white slivers along the borders.",
            [
                "In InDesign: File > Document Setup > Bleed: set 3 mm on Top, Bottom, Inside, and Outside.",
                "Extend all edge-touching backgrounds, images, and color fills out to the outer RED bleed guide.",
                "When exporting PDF: under 'Marks and Bleeds', enable 'Use Document Bleed Settings'.",
            ],
        ),
        "rgb": (
            "Images Detected in RGB Color Mode",
            "Images are stored in RGB (screen light space). Offset and digital presses print with 4 CMYK inks; uncalibrated conversions can dull vivid colors.",
            [
                "In Photoshop: Image > Mode > CMYK Color (using standard ISO Coated v2 or FOGRA39 profile).",
                "Or in InDesign PDF export: Output > Color Conversion: 'Convert to Destination (Preserve Numbers)' targeting Document CMYK - ISO Coated v2.",
            ],
        ),
        "rgb_screen": (
            "CMYK Images in a Screen Document (RGB)",
            "The target profile requires RGB. CMYK images can look muted or shift hue across displays and browsers.",
            [
                "In Photoshop: convert images to sRGB and update links in the layout document.",
                "Re-export the PDF using the agreed RGB screen profile and verify again.",
            ],
        ),
        "fonts": (
            "Unembedded Fonts in PDF",
            "The PDF omits one or more font subsets. If the press RIP lacks the same installed typeface, it will substitute another font and break the layout.",
            [
                "In InDesign / Illustrator: select text frames and run Type > Create Outlines (Ctrl+Shift+O).",
                "Or export as PDF/X-4 or PDF/X-1a, industry standards that enforce complete font embedding.",
            ],
        ),
        "black": (
            "Small Body Text in Rich Black (C+M+Y+K) or Knockout",
            "Body text below 12 pt uses four-color black. On offset presses, microscopic plate misregistration creates color fringes or blurry text.",
            [
                "Apply the pure [Black] 100% K swatch (0 C / 0 M / 0 Y / 100 K) to all body copy.",
                "In InDesign: Preferences > Appearance of Black > verify 'Overprint [Black] Swatch at 100%' is enabled.",
            ],
        ),
        "hairlines": (
            "Ultra-Thin Rules or Hairlines (< 0.25 pt)",
            "Strokes thinner than 0.25 pt were detected. During CTP plate imaging, ultra-thin rules can drop out completely on press.",
            [
                "In the Stroke panel (InDesign / Illustrator): increase line weights to at least 0.30 pt or 0.50 pt.",
            ],
        ),
        "spots": (
            "Spot / Pantone Inks in a 4-Color CMYK Job",
            "Special spot inks remain in the file. For a standard 4-color CMYK run, spot swatches must be converted to process to avoid extra press plates.",
            [
                "In InDesign: Window > Color > Swatches > double-click the Pantone swatch > Color Mode / Type: set to 'Process'.",
            ],
        ),
        "tac": (
            "Excessive Total Ink Coverage (TAC > 300%)",
            "Dark areas exceed 300% total ink (C+M+Y+K). Heavy ink saturates the stock and causes set-off smudging when sheets stack.",
            [
                "In InDesign PDF export: Output > Destination: choose 'ISO Coated v2 300% (ECI)' to cap ink coverage automatically.",
            ],
        ),
        "safety_margin": (
            "Text Too Close to Trim Edge (< 3 mm)",
            "Text or live elements sit closer than 3 mm to the TrimBox. Guillotine cutting has +-1 mm mechanical tolerance, risking clipped or unbalanced margins.",
            [
                "In InDesign / Illustrator: keep titles, folios, and body text at least 3 mm inside the page trim.",
            ],
        ),
        "resolution": (
            "Insufficient or Unverifiable Image Resolution",
            "One or more images fall below the profile minimum PPI or could not be measured accurately, risking pixelation or softness.",
            [
                "In InDesign / Illustrator: check Links panel and supply high-resolution originals at final placement size.",
                "Scale down the placed image or replace it; upsampling pixels does not restore real detail.",
            ],
        ),
    },
}


def _localize_item(item: Dict[str, Any], lang: str, is_screen: bool = False) -> Dict[str, Any]:
    lang = _cr_lang(lang)
    out = dict(item)
    sev = item.get("severity", "AVISO")
    if lang == "es":
        out["display_severity"] = sev
        return out
    sev_map = {
        "eu": {"CRÍTICO": "KRITIKOA", "AVISO": "OHARRA", "INFO": "INFO"},
        "en": {"CRÍTICO": "CRITICAL", "AVISO": "WARNING", "INFO": "INFO"},
    }
    out["display_severity"] = sev_map.get(lang, {}).get(sev, sev)
    cat = item.get("category")
    key = "rgb_screen" if (cat == "rgb" and is_screen) else cat
    trans = _CAT_TRANSLATIONS.get(lang, {}).get(key)
    if trans:
        out["title"], out["problem"], out["solution"] = trans[0], trans[1], list(trans[2])
    if item.get("detail"):
        out["detail"] = None
    if item.get("status") == "resolved":
        if lang == "eu":
            out["solution"] = [
                "Hasierako analisian detektatua eta zuzendutako PDFaren azken egiaztapenean desagertua.",
                "Egiaztatu emaitza bisualki inprimaketa baimendu aurretik.",
            ]
        elif lang == "en":
            out["solution"] = [
                "Detected in the initial scan and no longer present in the latest fixed PDF check.",
                "Visually inspect the output before signing off for production.",
            ]
    return out


def _draw_header(page: pymupdf.Page, assets_dir: Path, p: dict, is_screen: bool = False, lang: str = "es"):
    """Dibuja la cabecera corporativa con logos institucionales."""
    page.draw_rect(pymupdf.Rect(0, 0, PAGE_W, HEADER_H), fill=p["navy"])

    imago_path = assets_dir / "Logo-intelliprint-imago.png"
    if not imago_path.exists():
        imago_path = assets_dir / "Logo-intelliprint-imago.jpg"
    full_logo_path = assets_dir / "Logo-intelliprint.png"
    if not full_logo_path.exists():
        full_logo_path = assets_dir / "Logo-intelliprint.jpg"

    if imago_path.exists():
        page.insert_image(pymupdf.Rect(26, 12, 74, 58), filename=str(imago_path), keep_proportion=True)
        text_x = 82
    elif full_logo_path.exists():
        page.insert_image(pymupdf.Rect(26, 14, 146, 54), filename=str(full_logo_path), keep_proportion=True)
        text_x = 154
    else:
        text_x = 35

    page.insert_text(pymupdf.Point(text_x, 28), "Intelli", fontsize=12.5, color=(1, 1, 1), fontname="helv")
    w_intelli = pymupdf.get_text_length("Intelli", fontname="helv", fontsize=12.5)
    page.insert_text(pymupdf.Point(text_x + w_intelli, 28), "Print", fontsize=12.5, color=(0.0, 0.64, 1.0), fontname="hebo")
    w_print = pymupdf.get_text_length("Print", fontname="hebo", fontsize=12.5)
    page.insert_text(pymupdf.Point(text_x + w_intelli + w_print + 5, 28), _cr_tr(lang, "guide_header"), fontsize=9.5, color=(0.85, 0.90, 0.95), fontname="helv")
    page.insert_text(
        pymupdf.Point(text_x, 41),
        _cr_tr(lang, "guide_sub_1"),
        fontsize=7.6,
        color=(0.78, 0.85, 0.92),
        fontname="helv",
    )
    subtitle = _cr_tr(lang, "guide_sub_2_screen" if is_screen else "guide_sub_2_print")
    page.insert_text(
        pymupdf.Point(text_x, 52),
        subtitle,
        fontsize=7.2,
        color=(0.65, 0.74, 0.84),
        fontname="helv",
    )

    p_sales = assets_dir / "logo-salesianos.png"
    p_mendi = assets_dir / "logo-mendizabala.png"
    p_edu = assets_dir / "logo-dept-educacion-1.png"

    if p_sales.exists() and p_mendi.exists() and p_edu.exists():
        capsule = pymupdf.Rect(340, 12, 567, 58)
        page.draw_rect(capsule, fill=(1, 1, 1), radius=0.08)
        x0 = 346
        slot_w = 68.0
        r_sales = pymupdf.Rect(x0, 16, x0 + slot_w, 54)
        page.insert_image(r_sales, filename=str(p_sales), keep_proportion=True)
        div1_x = x0 + slot_w + 3.0
        page.draw_line(pymupdf.Point(div1_x, 18), pymupdf.Point(div1_x, 52), color=(0.88, 0.88, 0.88), width=0.6)
        
        x1 = div1_x + 4.0
        r_mendi = pymupdf.Rect(x1, 16, x1 + slot_w, 54)
        page.insert_image(r_mendi, filename=str(p_mendi), keep_proportion=True)
        div2_x = x1 + slot_w + 3.0
        page.draw_line(pymupdf.Point(div2_x, 18), pymupdf.Point(div2_x, 52), color=(0.88, 0.88, 0.88), width=0.6)
        
        x2 = div2_x + 4.0
        r_edu = pymupdf.Rect(x2, 16, 561, 54)
        page.insert_image(r_edu, filename=str(p_edu), keep_proportion=True)

        # Enlaces interactivos en los logotipos de la cabecera PDF
        page.insert_link({"kind": pymupdf.LINK_URI, "from": r_sales, "uri": "https://salesianosurnieta.com/"})
        page.insert_link({"kind": pymupdf.LINK_URI, "from": r_mendi, "uri": "https://www.mendizabala.eus/"})
        page.insert_link({"kind": pymupdf.LINK_URI, "from": r_edu, "uri": "https://www.euskadi.eus/gobierno-vasco/departamento-educacion/"})


def _draw_footer(page: pymupdf.Page, p: dict, job_id: str, is_screen: bool = False, lang: str = "es"):
    """Dibuja el pie de página institucional del informe."""
    page.draw_line(
        pymupdf.Point(MARGIN_X, FOOTER_Y),
        pymupdf.Point(PAGE_W - MARGIN_X, FOOTER_Y),
        color=p["border"],
        width=0.5,
    )
    page.insert_text(
        pymupdf.Point(MARGIN_X, FOOTER_Y + 12),
        _cr_tr(lang, "footer_org"),
        fontsize=7.2,
        fontname="helv",
        color=p["slate"],
    )
    page.insert_text(
        pymupdf.Point(PAGE_W - MARGIN_X - 100, FOOTER_Y + 12),
        f"{_cr_tr(lang, 'ref_job')} {job_id[:16]}",
        fontsize=7.2,
        fontname="helv",
        color=p["slate"],
    )
    footer_note = _cr_tr(lang, "footer_note_screen" if is_screen else "footer_note_print")
    page.insert_text(
        pymupdf.Point(MARGIN_X, FOOTER_Y + 22),
        footer_note,
        fontsize=6.8,
        fontname="helv",
        color=(0.55, 0.60, 0.68),
    )


def _extract_pedagogical_items(job_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Analiza las incidencias técnicas y las traduce a explicaciones pedagógicas
    orientadas a diseñadores (con instrucciones para InDesign / Illustrator / Photoshop).
    """
    findings = job_data.get("findings", [])
    summary = job_data.get("job_summary", {})
    meta = job_data.get("job_meta", {})
    profile_id = meta.get("profile_id") or summary.get("profile_id") or "OFFSET_300"
    is_screen = (
        summary.get("required_color_family") == "RGB"
        or profile_id in ("PANTALLA_RGB", "SCREEN_RGB")
    )
    items = []

    # Resolución: conservar la gravedad del preflight, también si no fue medible.
    resolution_findings = [
        f for f in findings
        if f.get("rule_id") == "PRINT_IMAGE_EFFECTIVE_PPI"
        and f.get("severity") in ("ERROR", "WARNING")
    ]
    low_res_images = summary.get("low_res_images", 0)
    if resolution_findings or low_res_images > 0:
        errors = sum(f.get("severity") == "ERROR" for f in resolution_findings)
        warnings = sum(f.get("severity") == "WARNING" for f in resolution_findings)
        pages = sorted({
            f["page"] for f in resolution_findings
            if isinstance(f.get("page"), int) and f["page"] > 0
        })
        pages_text = ", ".join(str(page) for page in pages[:4]) or "sin indicar"
        if len(pages) > 4:
            pages_text += f" y {len(pages) - 4} más"
        target_dpi = summary.get("target_dpi", 300)
        counts = f"{errors} {'error' if errors == 1 else 'errores'} y {warnings} {'aviso' if warnings == 1 else 'avisos'}"
        if not resolution_findings:
            counts = f"{low_res_images} imágenes por debajo de {target_dpi} ppp"
        items.append({
            "category": "resolution",
            "icon": "RESOLUCIÓN",
            "severity": "CRÍTICO" if errors else "AVISO",
            "title": "Resolución de Imágenes Insuficiente o No Verificable",
            "problem": f"{counts}. Págs.: {pages_text}. Riesgo de pixelado o nitidez sin verificar.",
            "solution": [
                f"En InDesign / Illustrator: revisa los vínculos y usa originales con al menos {target_dpi} ppp al tamaño final.",
                "Reduce el tamaño colocado o sustituye la imagen; aumentar los ppp por remuestreo no recupera detalle."
            ]
        })

    # 1. Sangrado (Bleed) - Solo exigible en impresión física
    has_bleed_err = any(f.get("rule_id") == "BLEED_GEOMETRY_3MM" for f in findings)
    if not is_screen and (has_bleed_err or summary.get("bleed_status") == "FAIL"):
        items.append({
            "category": "bleed",
            "icon": "SANGRADO",
            "severity": "CRÍTICO",
            "title": "Falta Sangrado Perimetral (+3 mm en los 4 bordes)",
            "problem": "El diseño termina en el borde exacto de corte. Al cortar en la guillotina de imprenta, cualquier oscilación mínima del papel provocará filetes o líneas blancas no deseadas en los extremos.",
            "solution": [
                "En InDesign: Archivo > Ajustar documento > Sangrado: escribe 3 mm en los 4 lados.",
                "Estira todos los fondos, imágenes y colores que toquen el borde hasta la GUÍA ROJA exterior.",
                "Al exportar el PDF: en la pestaña 'Marcas y sangrados', activa 'Utilizar configuración de sangrado del documento'."
            ]
        })

    # 2. Modo de color RGB / CMYK
    has_rgb_err = any(f.get("rule_id") == "SOURCE_COLOR_DIAGNOSTIC" for f in findings)
    non_cmyk_imgs = summary.get("non_cmyk_images", 0)
    if has_rgb_err or (non_cmyk_imgs > 0 and not is_screen):
        items.append({
            "category": "rgb",
            "icon": "COLOR",
            "severity": "CRÍTICO",
            "title": f"Imágenes en Modo de Color RGB ({non_cmyk_imgs} detectadas)",
            "problem": "Las imágenes están en RGB (espacio de luz para pantallas). En imprenta se imprime con 4 tintas CMYK (Cian, Magenta, Amarillo y Negro). Una conversión imprevista puede apagar colores vivos.",
            "solution": [
                "En Photoshop: Imagen > Modo > Color CMYK (con perfil estándar ISO Coated v2 o FOGRA39).",
                "O en InDesign al exportar PDF: Salida > Conversión de color: 'Convertir a destino (mantener valores)' indicando perfil de destino Documento CMYK - ISO Coated v2."
            ]
        })

    # 3. Tipografías no incrustadas
    has_font_err = any(f.get("rule_id") == "USED_FONTS_EMBEDDED" for f in findings)
    if has_font_err:
        items.append({
            "category": "fonts",
            "icon": "FUENTES",
            "severity": "AVISO",
            "title": "Tipografías No Incrustadas en el PDF",
            "problem": "El archivo PDF no contiene las fuentes tipográficas. Si el procesador (RIP) de la imprenta no dispone de la misma fuente instalada, se sustituirá por otra deformando el diseño.",
            "solution": [
                "En InDesign / Illustrator: selecciona los textos y pulsa Texto > Crear contornos (Ctrl+Shift+O).",
                "O exporta como PDF/X-4 o PDF/X-1a, estándares de la industria que garantizan la incrustación íntegra de las fuentes."
            ]
        })

    # 4. Textos negros en cuatricromía / calado
    has_black_err = any(
        f.get("rule_id") in ("BLACK_TEXT_KNOCKOUT", "BLACK_TEXT_KNOCKOUT_100", "RICH_BLACK_SMALL_TEXT", "WHITE_OVERPRINT")
        for f in findings
    )
    if has_black_err:
        items.append({
            "category": "black",
            "icon": "NEGRO",
            "severity": "AVISO",
            "title": "Textos Pequeños en Negro Compuesto (C+M+Y+K) o en Calado",
            "problem": "Hay texto de lectura menor de 12 pt compuesto por las cuatro tintas. En máquina offset, cualquier microdesajuste de registro entre planchas creará halos de color o texto borroso.",
            "solution": [
                "Aplica a todos los textos de lectura la muestra pura [Negro] 100% K (0 C / 0 M / 0 Y / 100 K).",
                "En InDesign: Preferencias > Apariencia de negro > comprueba que esté marcada la opción 'Sobreimprimir negro al 100%'."
            ]
        })

    # 5. Filetes ultrafinos (Hairlines < 0.25 pt)
    has_hairline_err = any(
        f.get("rule_id") in ("HAIRLINE_WIDTH", "HAIRLINE_STROKE", "HAIRLINE_DETECTED")
        for f in findings
    )
    if has_hairline_err:
        items.append({
            "category": "hairlines",
            "icon": "TRAZOS",
            "severity": "AVISO",
            "title": "Filetes o Líneas Demasiado Finas (< 0.25 pt)",
            "problem": "Hay trazos con un grosor menor de 0.25 pt. En el grabado CTP de planchas offset, estas líneas son tan débiles que desaparecen y no imprimen en el papel.",
            "solution": [
                "En la ventana Trazo de InDesign / Illustrator: aumenta el grosor de todas las líneas a un mínimo de 0.30 pt o 0.50 pt."
            ]
        })

    # 6. Tintas planas / Pantone sin descomponer
    has_spots = any(f.get("rule_id") in ("SPOT_COLOR_FOUND", "SPOT_COLOR_NOT_ALLOWED") for f in findings)
    if has_spots:
        items.append({
            "category": "spots",
            "icon": "TINTAS",
            "severity": "INFO",
            "title": "Tintas Planas (Pantone) en Trabajo de Cuatricromía",
            "problem": "El archivo incluye tintas directas especiales. Si tu tirada está contratada a 4 tintas CMYK, las tintas planas deben descomponerse para no requerir planchas adicionales.",
            "solution": [
                "En InDesign: Ventana > Muestras > doble clic en la muestra Pantone > Tipo de color: cambiar a 'Proceso'."
            ]
        })

    # 7. Cobertura de tinta excesiva (TAC > 300%)
    has_tac_err = any(f.get("rule_id") == "MAX_INK_COVERAGE" for f in findings)
    if has_tac_err:
        items.append({
            "category": "tac",
            "icon": "TINTA",
            "severity": "AVISO",
            "title": "Cobertura Total de Tinta Excesiva (> 300%)",
            "problem": "Zonas oscuras del documento acumulan más del 300% de suma de tintas (C+M+Y+K). Esto satura el papel y provoca repintado (manchas) al apilar los pliegos en máquina.",
            "solution": [
                "Al exportar tu PDF en InDesign: Salida > Destino: selecciona el perfil estándar 'ISO Coated v2 300% (ECI)' que limita la tinta automáticamente."
            ]
        })

    # 8. Margen de seguridad de corte (TrimBox < 3 mm)
    has_safety_margin_err = any(f.get("rule_id") == "SAFETY_MARGIN_TRIMBOX" for f in findings)
    if has_safety_margin_err:
        items.append({
            "category": "safety_margin",
            "icon": "CORTE",
            "severity": "AVISO",
            "title": "Textos Próximos a la Línea de Corte (< 3 mm)",
            "problem": "Se han detectado textos o elementos vivos a menos de 3 mm de la línea de corte (TrimBox). La guillotina de corte tiene una tolerancia mecánica de ±1 mm; si los elementos están muy pegados al borde, corren riesgo de quedar amputados o visualmente descompensados.",
            "solution": [
                "En InDesign / Illustrator: activa las guías de márgenes (Márgenes y columnas) y sitúa los textos al menos a 3 mm hacia el interior del borde de página.",
                "Mantén una distancia prudencial en titulares y pies de página para garantizar un margen visual limpio tras el guillotinado."
            ]
        })

    if is_screen:
        for item in items:
            if item["category"] == "rgb":
                item["title"] = "Imágenes CMYK en un documento para pantalla (RGB)"
                item["problem"] = "El destino exige RGB. Las imágenes CMYK pueden mostrar colores apagados en pantallas y navegadores."
                item["solution"] = [
                    "En Photoshop: convierte las imágenes al perfil sRGB y actualiza los vínculos en el documento.",
                    "Exporta el PDF con el perfil RGB acordado para pantalla y vuelve a verificarlo."
                ]

    rules_by_category = {
        "resolution": {"PRINT_IMAGE_EFFECTIVE_PPI"},
        "bleed": {"BLEED_GEOMETRY_3MM"},
        "rgb": {"SOURCE_COLOR_DIAGNOSTIC"},
        "fonts": {"USED_FONTS_EMBEDDED"},
        "black": {"BLACK_TEXT_KNOCKOUT", "BLACK_TEXT_KNOCKOUT_100", "RICH_BLACK_SMALL_TEXT", "WHITE_OVERPRINT"},
        "hairlines": {"HAIRLINE_WIDTH", "HAIRLINE_STROKE", "HAIRLINE_DETECTED"},
        "spots": {"SPOT_COLOR_FOUND", "SPOT_COLOR_NOT_ALLOWED"},
        "tac": {"MAX_INK_COVERAGE"},
        "safety_margin": {"SAFETY_MARGIN_TRIMBOX"},
    }
    handled = set().union(*rules_by_category.values())
    for item in items:
        current = [f for f in findings if f.get("rule_id") in rules_by_category[item["category"]]]
        if current:
            item["severity"] = ("CRÍTICO" if any(f.get("severity") == "ERROR" for f in current)
                                else "AVISO" if any(f.get("severity") == "WARNING" for f in current) else "INFO")
            pages = sorted({f["page"] for f in current if isinstance(f.get("page"), int) and f["page"] > 0})
            item["detail"] = f"Incidencias: {len(current)}. Páginas: {', '.join(map(str, pages)) or 'sin indicar'}."
    # Las reglas sin guía específica también deben aparecer en la ficha.
    other_rules = {}
    for finding in findings:
        if finding.get("rule_id") not in handled and finding.get("severity") in ("ERROR", "WARNING"):
            other_rules.setdefault(finding.get("rule_id"), []).append(finding)
    for rule_id, current in other_rules.items():
        messages = list(dict.fromkeys(f.get("message") or f.get("title") or "Revisión técnica pendiente." for f in current))
        items.append({
            "category": rule_id or "other",
            "icon": "REVISIÓN",
            "severity": "CRÍTICO" if any(f.get("severity") == "ERROR" for f in current) else "AVISO",
            "title": current[0].get("title") or "Incidencia técnica pendiente",
            "problem": "\n".join(messages),
            "solution": ["Revisa esta incidencia en el documento de origen y vuelve a exportar el PDF con el perfil acordado con el taller."],
        })

    severity_order = {"CRÍTICO": 0, "AVISO": 1, "INFO": 2}
    items.sort(key=lambda it: (severity_order[it["severity"]], it["category"] != "resolution"))
    return items


def _resolved_pedagogical_items(job_data):
    """Keep the initial diagnosis separate from issues still found in the PDF."""
    original = job_data.get("original_analysis")
    if not isinstance(original, dict):
        return []
    # A color conversion can change an image's title (RGB -> CMYK) without
    # repairing its resolution. Compare rule/page counts rather than titles.
    remaining = Counter((f.get("rule_id"), f.get("page"))
                        for f in job_data.get("findings", [])
                        if f.get("severity") in ("ERROR", "WARNING"))
    no_longer_found = []
    for finding in original.get("findings", []):
        if finding.get("severity") not in ("ERROR", "WARNING"):
            continue
        key = (finding.get("rule_id"), finding.get("page"))
        if remaining[key]:
            remaining[key] -= 1
        else:
            no_longer_found.append(finding)
    history = {
        "findings": no_longer_found,
        "job_summary": {
            "target_dpi": original.get("job_summary", {}).get("target_dpi", 300),
            "required_color_family": original.get("job_summary", {}).get("required_color_family", "CMYK"),
            "non_cmyk_images": sum(f.get("rule_id") == "SOURCE_COLOR_DIAGNOSTIC" for f in no_longer_found),
        },
        "job_meta": original.get("job_meta", job_data.get("job_meta", {})),
    }
    items = _extract_pedagogical_items(history)
    for item in items:
        item["status"] = "resolved"
        item["solution"] = [
            "Presente en el análisis inicial y ausente en la última verificación del PDF corregido.",
            "Comprueba visualmente el resultado antes de autorizar la impresión."
        ]
        if item["category"] == "black":
            item["solution"].append(
                "Si el texto se ha trazado, revisa su color en las separaciones: pasar a curvas no corrige por sí solo el negro compuesto."
            )
    return items


def _wrap_lines(text, width, fontsize, fontname="helv"):
    lines = []
    for paragraph in str(text).splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}" if line else word
            if pymupdf.get_text_length(candidate, fontname=fontname, fontsize=fontsize) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            for char in word:
                if line and pymupdf.get_text_length(line + char, fontname=fontname, fontsize=fontsize) > width:
                    lines.append(line)
                    line = ""
                line += char
        lines.append(line)
    return lines


def _item_layout(item, lang: str = "es"):
    lines = []
    title_lines = _wrap_lines(item["title"], CONTENT_W - 74, 8.5)
    y = 15.0
    for title in title_lines:
        lines.append((62, y, title, 8.5, "navy"))
        y += 11
    y += 3
    if item.get("detail"):
        for line in _wrap_lines(item["detail"], CONTENT_W - 20, 7):
            lines.append((10, y, line, 7, "slate"))
            y += 9.5
    prefix = _cr_tr(lang, "prefix_resolved" if item.get("status") == "resolved" else "prefix_active")
    for line in _wrap_lines(prefix + item["problem"], CONTENT_W - 20, 7):
        lines.append((10, y, line, 7, "slate_dark"))
        y += 9.5
    y += 3
    label = _cr_tr(lang, "label_resolved" if item.get("status") == "resolved" else "label_active")
    lines.append((10, y, label, 7, "blue"))
    y += 12
    for step in item["solution"]:
        for line in _wrap_lines(f"> {step}", CONTENT_W - 36, 6.8):
            lines.append((18, y, line, 6.8, "slate_dark"))
            y += 9.5
        y += 1.5
    return max(105, y + 1), lines


def _draw_item(page, item, y, height, lines, p, lang: str = "es"):
    resolved = item.get("status") == "resolved"
    tone = "green" if resolved else "red" if item["severity"] == "CRÍTICO" else "amber"
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, PAGE_W - MARGIN_X, y + height),
                   fill=p[f"{tone}_bg"], color=p[f"{tone}_border"], width=0.8, radius=0.04)
    page.draw_rect(pymupdf.Rect(MARGIN_X + 8, y + 6, MARGIN_X + 56, y + 19),
                   fill=p[tone], radius=0.08)
    badge_txt = _cr_tr(lang, "badge_resolved") if resolved else (item.get("display_severity") or item["severity"])
    page.insert_text(pymupdf.Point(MARGIN_X + 10, y + 15), badge_txt,
                     fontsize=6.2, fontname="helv", color=(1, 1, 1))
    for x, offset, text, size, color in lines:
        page.insert_text(pymupdf.Point(MARGIN_X + x, y + offset), text,
                         fontsize=size, fontname="helv", color=p[color])


def _draw_section_heading(page, title, y, p):
    page.insert_text(pymupdf.Point(MARGIN_X, y + 12), title, fontsize=9.2, fontname="helv", color=p["navy"])
    page.draw_line(pymupdf.Point(MARGIN_X, y + 16), pymupdf.Point(PAGE_W - MARGIN_X, y + 16),
                   color=p["navy"], width=0.8)


def _item_parts(item, max_height, lang: str = "es"):
    """Continue exceptionally long findings instead of clipping their text."""
    height, lines = _item_layout(item, lang=lang)
    if height <= max_height:
        return [(item, height, lines)]
    body = [line for line in lines if line[0] != 62]
    parts = []
    while body:
        part = dict(item)
        if parts:
            part["title"] += f" ({_cr_tr(lang, 'continuation')})"
        title_lines = _wrap_lines(part["title"], CONTENT_W - 74, 8.5)
        chunk = [(62, 15 + i * 11, text, 8.5, "navy") for i, text in enumerate(title_lines)]
        start_y = chunk[-1][1] + 14
        original_y = body[0][1]
        taken = 0
        for x, offset, text, size, color in body:
            relative_y = start_y + offset - original_y
            if relative_y + 10 > max_height and taken:
                break
            chunk.append((x, relative_y, text, size, color))
            taken += 1
        parts.append((part, max(105, chunk[-1][1] + 10), chunk))
        body = body[taken:]
    return parts


def _draw_image_issue(page, entry, y, p, source, lang: str = "es"):
    """Identify each painted image, including multiple placements of one XObject."""
    dpi = entry.get("effective_dpi")
    dpi_text = f"{dpi:g}" if isinstance(dpi, (int, float)) and dpi > 0 else "N/D"
    target = entry.get("target_dpi", 300)
    target_text = f"{target:g}" if isinstance(target, (int, float)) else str(target or "N/D")
    index = entry.get("index")
    page_label = entry.get("page") or _cr_tr(lang, "img_unspecified")
    label = _cr_tr(
        lang,
        "img_label",
        page=page_label,
        index=index if index is not None else _cr_tr(lang, "img_unidentified"),
    )
    issue_lines = _wrap_lines(" · ".join(entry.get("issues", [])), CONTENT_W - 124, 7.2)
    height = max(78, 58 + len(issue_lines) * 9.5 + 8)
    tone = "red" if entry.get("severity") == "ERROR" else "amber"
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, PAGE_W - MARGIN_X, y + height),
                   fill=p[f"{tone}_bg"], color=p[f"{tone}_border"], width=0.7, radius=0.04)
    preview = pymupdf.Rect(MARGIN_X + 8, y + 8, MARGIN_X + 96, y + height - 8)
    page.draw_rect(preview, fill=(1, 1, 1), color=p["border"], width=0.5)
    thumbnail = False
    if source is not None and entry.get("bbox"):
        try:
            source_page = source[int(entry["page"]) - 1]
            clip = (pymupdf.Rect(entry["bbox"]) * source_page.rotation_matrix) & source_page.rect
            if not clip.is_empty and not clip.is_infinite:
                scale = min(2, 176 / clip.width, 124 / clip.height)
                pixmap = source_page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False)
                page.insert_image(preview, stream=pixmap.tobytes("png"), keep_proportion=True)
                thumbnail = True
        except (ValueError, IndexError, TypeError, RuntimeError):
            pass
    if not thumbnail:
        page.insert_text(pymupdf.Point(preview.x0 + 5, preview.y0 + 24),
                         _cr_tr(lang, "img_see_1"), fontsize=7, fontname="helv", color=p["slate"])
        page.insert_text(pymupdf.Point(preview.x0 + 5, preview.y0 + 35),
                         _cr_tr(lang, "img_see_2", page=page_label), fontsize=7, fontname="helv", color=p["slate"])
    x = MARGIN_X + 108
    page.insert_text(pymupdf.Point(x, y + 16), label, fontsize=9, fontname="hebo", color=p["navy"])
    page.insert_text(pymupdf.Point(x, y + 30),
                     _cr_tr(lang, "img_res", dpi=dpi_text, target=target_text),
                     fontsize=7.5, fontname="helv", color=p["slate_dark"])
    color = entry.get("colorspace") or _cr_tr(lang, "img_unidentified")
    dimensions = (f"{entry['width_px']} x {entry['height_px']} px"
                  if entry.get("width_px") and entry.get("height_px") else _cr_tr(lang, "img_size_na"))
    page.insert_text(pymupdf.Point(x, y + 43),
                     _cr_tr(lang, "img_color", color=color, dims=dimensions),
                     fontsize=7.2, fontname="helv", color=p["slate"])
    for line_index, line in enumerate(issue_lines):
        page.insert_text(pymupdf.Point(x, y + 58 + line_index * 9.5), line,
                         fontsize=7.2, fontname="helv", color=p[tone])
    return height


def generate_client_educational_report_pdf(job_data: Dict[str, Any], output_path: str | Path, pdf_path=None, lang: str = "es"):
    """
    Genera la guía A4 completa, con incidencias actuales e historial separados.
    """
    lang = _cr_lang(lang)
    output_path = Path(output_path)
    output_path.parent.mkdir(exist_ok=True, parents=True)

    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    assets_dir = Path(__file__).parent / "assets"
    p = _palette()

    meta = job_data.get("job_meta", {})
    summary = job_data.get("job_summary", {})
    job_id = meta.get("job_id", "N/A")
    filename = meta.get("filename", "documento.pdf")

    profile_id = meta.get("profile_id") or summary.get("profile_id") or "OFFSET_300"
    prof = {}
    try:
        from profile_manager import get_profile_by_id
        prof = get_profile_by_id(profile_id)
    except Exception:
        pass

    color_family = summary.get("required_color_family") or prof.get("color_family", "CMYK")
    is_screen = (
        color_family == "RGB"
        or profile_id in ("PANTALLA_RGB", "CUSTOM_RGB", "SCREEN_RGB")
        or (prof.get("min_bleed_mm", 3.0) == 0.0 and color_family == "RGB")
    )

    if is_screen:
        standard_label = _cr_tr(lang, "std_screen")
    elif profile_id == "OFFSET_300":
        standard_label = _cr_tr(lang, "std_offset")
    elif profile_id == "DIGITAL_200":
        standard_label = _cr_tr(lang, "std_digital")
    elif profile_id == "PERIODICO_TAC240":
        standard_label = _cr_tr(lang, "std_newspaper")
    elif profile_id == "PACKAGING_CARTONCILLO":
        standard_label = _cr_tr(lang, "std_packaging")
    elif profile_id == "GRAN_FORMATO":
        standard_label = _cr_tr(lang, "std_wide")
    elif prof.get("name"):
        standard_label = prof["name"]
    else:
        standard_label = _cr_tr(lang, "std_offset")

    # 1. Cabecera corporativa
    _draw_header(page, assets_dir, p, is_screen=is_screen, lang=lang)

    # 2. Tarjeta resumen del archivo y estado general
    y_card = HEADER_H + 12.0
    card_h = 58.0
    page.draw_rect(
        pymupdf.Rect(MARGIN_X, y_card, PAGE_W - MARGIN_X, y_card + card_h),
        fill=p["light"],
        color=p["border"],
        width=0.8,
        radius=0.04,
    )

    page.insert_text(
        pymupdf.Point(MARGIN_X + 12, y_card + 18),
        f"{_cr_tr(lang, 'file_reviewed')} {filename[:45]}",
        fontsize=9.5,
        fontname="helv",
        color=p["navy"],
    )

    now_str = datetime.now().strftime("%d/%m/%Y · %H:%M")
    page.insert_text(
        pymupdf.Point(MARGIN_X + 12, y_card + 34),
        _cr_tr(lang, "meta_line", date=now_str, pages=summary.get("pages", 1), standard=standard_label),
        fontsize=7.5,
        fontname="helv",
        color=p["slate"],
    )

    items = [_localize_item(it, lang, is_screen=is_screen) for it in _extract_pedagogical_items(job_data)]
    resolved_items = [_localize_item(it, lang, is_screen=is_screen) for it in _resolved_pedagogical_items(job_data)]
    has_critical = any(it["severity"] == "CRÍTICO" for it in items)
    has_issues = len(items) > 0

    # Badge de estado en la esquina derecha de la tarjeta
    badge_w = 175.0
    badge_x = PAGE_W - MARGIN_X - badge_w - 10.0
    badge_y = y_card + 10.0
    badge_h = 38.0

    if not has_issues:
        badge_bg = p["green_bg"]
        badge_border = p["green_border"]
        badge_text_col = p["green"]
        if is_screen:
            badge_title = _cr_tr(lang, "badge_ready_screen")
            badge_sub = _cr_tr(lang, "badge_ready_screen_sub")
        else:
            badge_title = _cr_tr(lang, "badge_ready_print")
            badge_sub = _cr_tr(lang, "badge_ready_print_sub")
    elif has_critical:
        badge_bg = p["red_bg"]
        badge_border = p["red_border"]
        badge_text_col = p["red"]
        badge_title = _cr_tr(lang, "badge_critical")
        badge_sub = _cr_tr(lang, "badge_critical_screen_sub" if is_screen else "badge_critical_print_sub")
    else:
        badge_bg = p["amber_bg"]
        badge_border = p["amber_border"]
        badge_text_col = p["amber"]
        badge_title = _cr_tr(lang, "badge_warn")
        badge_sub = _cr_tr(lang, "badge_warn_screen_sub" if is_screen else "badge_warn_print_sub")

    page.draw_rect(
        pymupdf.Rect(badge_x, badge_y, badge_x + badge_w, badge_y + badge_h),
        fill=badge_bg,
        color=badge_border,
        width=1.0,
        radius=0.08,
    )
    page.insert_text(
        pymupdf.Point(badge_x + 10, badge_y + 16),
        badge_title,
        fontsize=8.0,
        fontname="helv",
        color=badge_text_col,
    )
    page.insert_text(
        pymupdf.Point(badge_x + 10, badge_y + 30),
        badge_sub,
        fontsize=6.8,
        fontname="helv",
        color=p["slate_dark"],
    )

    # 3. Sección pedagógica: "¿Qué hemos detectado y cómo solucionarlo?"
    y_sec = y_card + card_h + 10.0
    if job_data.get("original_analysis_unavailable"):
        notice = _cr_tr(lang, "no_initial_history")
        page.insert_text(pymupdf.Point(MARGIN_X + 4, y_sec + 10), notice,
                         fontsize=7, fontname="helv", color=p["amber"])
        y_sec += 20

    page.insert_text(
        pymupdf.Point(MARGIN_X, y_sec + 12),
        (_cr_tr(lang, "sec_pending") if has_issues else
         _cr_tr(lang, "sec_resolved") if resolved_items else
         _cr_tr(lang, "sec_verified")),
        fontsize=9.2,
        fontname="helv",
        color=p["navy"],
    )
    page.draw_line(
        pymupdf.Point(MARGIN_X, y_sec + 16),
        pymupdf.Point(PAGE_W - MARGIN_X, y_sec + 16),
        color=p["navy"],
        width=0.8,
    )

    y_content = y_sec + 22.0
    max_issues_y = 630.0  # Límite vertical antes del bloque de opciones

    if not has_issues and not resolved_items:
        # Estado perfecto: mostrar 4 tarjetas verdes de conformidad
        checks = _cr_tr(lang, "ok_screen" if is_screen else "ok_print")
        box_h = 42.0
        gap = 8.0
        cur_y = y_content + 5.0
        for title, desc in checks:
            page.draw_rect(
                pymupdf.Rect(MARGIN_X, cur_y, PAGE_W - MARGIN_X, cur_y + box_h),
                fill=p["green_bg"],
                color=p["green_border"],
                width=0.7,
                radius=0.04,
            )
            page.insert_text(
                pymupdf.Point(MARGIN_X + 12, cur_y + 15),
                f"[OK]  {title}",
                fontsize=8.5,
                fontname="helv",
                color=p["green"],
            )
            page.insert_textbox(
                pymupdf.Rect(MARGIN_X + 12, cur_y + 19, PAGE_W - MARGIN_X - 12, cur_y + box_h - 2),
                desc,
                fontsize=7.4,
                fontname="helv",
                color=p["slate_dark"],
            )
            cur_y += box_h + gap

    else:
        sections = []
        if items:
            sections.append((_cr_tr(lang, "sec_pending"), items))
        if resolved_items:
            sections.append((_cr_tr(lang, "sec_resolved"), resolved_items))
        cur_y = y_content
        for section_index, (heading, section_items) in enumerate(sections):
            cards_on_page = 0
            if section_index:
                _draw_footer(page, p, job_id, is_screen=is_screen, lang=lang)
                page = doc.new_page(width=PAGE_W, height=PAGE_H)
                _draw_header(page, assets_dir, p, is_screen=is_screen, lang=lang)
                _draw_section_heading(page, heading, HEADER_H + 12, p)
                cur_y = HEADER_H + 34
            for item in section_items:
                for part, height, lines in _item_parts(item, max_issues_y - y_content, lang=lang):
                    if cards_on_page >= 4 or cur_y + height > max_issues_y:
                        _draw_footer(page, p, job_id, is_screen=is_screen, lang=lang)
                        page = doc.new_page(width=PAGE_W, height=PAGE_H)
                        _draw_header(page, assets_dir, p, is_screen=is_screen, lang=lang)
                        _draw_section_heading(page, f"{heading} ({_cr_tr(lang, 'continuation')})", HEADER_H + 12, p)
                        cur_y = HEADER_H + 34
                        cards_on_page = 0
                    _draw_item(page, part, cur_y, height, lines, p, lang=lang)
                    cur_y += height + 8
                    cards_on_page += 1

    image_issues = collect_report_image_issues(job_data)
    if image_issues:
        source = None
        source_path = pdf_path or meta.get("last_fixed_pdf_path") or meta.get("batch_fixed_pdf_path") or meta.get("pdf_path")
        if source_path:
            try:
                source = pymupdf.open(source_path)
            except (OSError, ValueError, RuntimeError):
                pass
        try:
            _draw_footer(page, p, job_id, is_screen=is_screen, lang=lang)
            page = doc.new_page(width=PAGE_W, height=PAGE_H)
            _draw_header(page, assets_dir, p, is_screen=is_screen, lang=lang)
            _draw_section_heading(page, _cr_tr(lang, "sec_images"), HEADER_H + 12, p)
            image_y = HEADER_H + 34
            for entry in image_issues:
                line_count = len(_wrap_lines(" · ".join(entry.get("issues", [])), CONTENT_W - 124, 7.2))
                height = max(78, 58 + line_count * 9.5 + 8)
                if image_y + height > max_issues_y:
                    _draw_footer(page, p, job_id, is_screen=is_screen, lang=lang)
                    page = doc.new_page(width=PAGE_W, height=PAGE_H)
                    _draw_header(page, assets_dir, p, is_screen=is_screen, lang=lang)
                    _draw_section_heading(page, f"{_cr_tr(lang, 'sec_images')} ({_cr_tr(lang, 'continuation')})", HEADER_H + 12, p)
                    image_y = HEADER_H + 34
                _draw_image_issue(page, entry, image_y, p, source, lang=lang)
                image_y += height + 8
        finally:
            if source is not None:
                source.close()

    # 4. Bloque inferior: "¿Cómo proceder? Dos opciones sencillas" (Y: 642 a 792 pt)
    y_opt = 642.0
    opt_h = 145.0
    page.draw_rect(
        pymupdf.Rect(MARGIN_X, y_opt, PAGE_W - MARGIN_X, y_opt + opt_h),
        fill=(1, 1, 1),
        color=p["border"],
        width=0.8,
        radius=0.04,
    )

    # Cabecera del bloque de opciones
    page.draw_rect(
        pymupdf.Rect(MARGIN_X, y_opt, PAGE_W - MARGIN_X, y_opt + 24),
        fill=p["indigo"],
    )
    page.insert_text(
        pymupdf.Point(MARGIN_X + 12, y_opt + 16),
        _cr_tr(lang, "opt_header"),
        fontsize=8.5,
        fontname="helv",
        color=(1, 1, 1),
    )

    # Dos columnas: Opción A y Opción B
    col_w = (CONTENT_W - 16.0) / 2.0
    col1_x = MARGIN_X + 8.0
    col2_x = col1_x + col_w + 8.0
    inner_y = y_opt + 32.0
    inner_h = opt_h - 40.0

    # Opción A: Estudio del cliente
    page.draw_rect(
        pymupdf.Rect(col1_x, inner_y, col1_x + col_w, inner_y + inner_h),
        fill=p["light"],
        color=p["border"],
        width=0.6,
        radius=0.04,
    )
    page.insert_text(
        pymupdf.Point(col1_x + 10, inner_y + 16),
        _cr_tr(lang, "opt_a_title"),
        fontsize=8.2,
        fontname="helv",
        color=p["navy"],
    )
    optA_text = _cr_tr(lang, "opt_a_screen" if is_screen else "opt_a_print")
    page.insert_textbox(
        pymupdf.Rect(col1_x + 10, inner_y + 24, col1_x + col_w - 10, inner_y + inner_h - 6),
        optA_text,
        fontsize=7.0,
        fontname="helv",
        color=p["slate_dark"],
    )

    # Opción B: Taller IntelliPrint
    page.draw_rect(
        pymupdf.Rect(col2_x, inner_y, col2_x + col_w, inner_y + inner_h),
        fill=(0.94, 0.98, 0.96),
        color=p["green_border"],
        width=0.6,
        radius=0.04,
    )
    page.insert_text(
        pymupdf.Point(col2_x + 10, inner_y + 16),
        _cr_tr(lang, "opt_b_title"),
        fontsize=8.2,
        fontname="helv",
        color=p["green"],
    )
    optB_text = _cr_tr(lang, "opt_b_screen" if is_screen else "opt_b_print")
    page.insert_textbox(
        pymupdf.Rect(col2_x + 10, inner_y + 24, col2_x + col_w - 10, inner_y + inner_h - 6),
        optB_text,
        fontsize=7.0,
        fontname="helv",
        color=p["slate_dark"],
    )

    # 5. Pie de página
    _draw_footer(page, p, job_id, is_screen=is_screen, lang=lang)
    for number, report_page in enumerate(doc, 1):
        report_page.insert_text(pymupdf.Point(PAGE_W - MARGIN_X - 54, HEADER_H - 4),
                                _cr_tr(lang, "page_badge", num=number, total=len(doc)), fontsize=6.5, fontname="helv",
                                color=(0.78, 0.85, 0.92))

    doc.save(str(output_path), deflate=True, garbage=4)
    doc.close()

