"""
didactic_engine.py
==================
Motor Didáctico y Simulador de Taller Gráfico para Formación Profesional (FP).
Desarrollado para CPIFP Salesianos Urnieta LHIPI y CIFP Mendizabala LHII
en el marco del proyecto de innovación aplicada de Artes Gráficas (Gobierno Vasco).

Proporciona:
1. Catálogo y generador dinámico de "Retos de Taller FP" (Casos reales con errores controlados).
2. Simulador visual interactivo de consecuencias físicas en taller:
   - Descalce de Registro CMYK en texto fino (Rich Black).
   - Efecto Repintado / Maculado en pila por exceso de TAC (> 300%).
   - Desvío de Guillotina y Filete Blanco por falta de sangre (Bleed 0 mm).
   - Pérdida de Líneas Finas en insolación CTP (< 0.25 pt).
   - Fallo de Escaneo de Códigos de Barras en cuatricromía.
3. Motor de Autoevaluación / Quiz Técnico con Rúbrica FP e ISO 12647-2 / PDF/X.
4. Generador de Hoja de Práctica y Evaluación del Alumno en PDF A4.
"""

from __future__ import annotations

import io
import math
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import pymupdf
import pikepdf
from PIL import Image, ImageDraw, ImageFont, ImageFilter

PAGE_W = 595.3
PAGE_H = 841.9
MARGIN_X = 35.0
CONTENT_W = PAGE_W - 2 * MARGIN_X
HEADER_H = 70.0
FOOTER_Y = 808.0

# ---------------------------------------------------------------------------
# CATÁLOGO DE RETOS DE TALLER FP
# ---------------------------------------------------------------------------

SCENARIOS_CATALOG = [
    # =========================================================================
    # CATEGORÍA 1: INICIACIÓN FP (GRADO MEDIO / 1º GS) - 7 RETOS
    # =========================================================================
    {
        "id": "reto_tarjeta_richblack",
        "category": "iniciacion",
        "title": "Reto 1: Tarjeta Corporativa con Rich Black y Sin Sangrado",
        "level": "Iniciación FP (Grado Medio / 1º GS)",
        "module": "Tratamiento de Imagen y Preimpresión Digital",
        "doc_type": "Tarjeta de Visita (85 x 55 mm)",
        "description": "El cliente aporta una tarjeta de visita corporativa con los textos de 6 pt compuestos en 4 tintas (Rich Black 300%) y el fondo colocado al corte exacto (0 mm de sangre).",
        "target_errors": [
            "Texto de 6 pt en 4 tintas (CMYK) con grave riesgo de descalce de registro en máquina.",
            "Falta total de sangre perimetral (0 mm de sangrado exterior).",
            "Resolución deficiente en isotipo gráfico (72 DPI)."
        ],
        "learning_goals": [
            "Comprender la diferencia entre 100% K puro y Negro Enriquecido en tipografía menuda.",
            "Aplicar los 3 mm de sangrado exterior exigidos por la norma de producción.",
            "Verificar la resolución nativa mínima de 300 DPI."
        ],
        "iso_norm": "ISO 12647-2 / ISO 15930 (PDF/X-1a)"
    },
    {
        "id": "reto_flyer_rgb_srgb",
        "category": "iniciacion",
        "title": "Reto 2: Flyer Nocturno en Espacio de Color RGB sin Separación",
        "level": "Iniciación FP (Grado Medio / 1º GS)",
        "module": "Tratamiento de Imagen y Colorimetría",
        "doc_type": "Flyer Publicitario A6 (105 x 148 mm)",
        "description": "Flyer para un festival nocturno con fotografías exportadas en sRGB y titulares en colores saturados fuera del gamut imprimible en cuatricromía offset.",
        "target_errors": [
            "Imágenes en espacio de color RGB (sRGB IEC61966-2.1) sin separación a CMYK.",
            "Colores fuera de gama (gamut clipping) que perderán luminosidad al imprimir.",
            "Ausencia de perfil de propósito de salida (Output Intent PDF/X)."
        ],
        "learning_goals": [
            "Dominar la conversión de color con perfil estandarizado (ISO Coated v2 / FOGRA39).",
            "Identificar los límites del espacio cromático CMYK frente al RGB de monitor.",
            "Configurar el Output Intent para asegurar la fidelidad cromática en taller."
        ],
        "iso_norm": "ISO 12647-2 / FOGRA39 / PDF/X-4"
    },
    {
        "id": "reto_triptico_sin_sangre",
        "category": "iniciacion",
        "title": "Reto 3: Tríptico Envolvente con Fondos al Corte y Cajas al Ras",
        "level": "Iniciación FP (Grado Medio / 1º GS)",
        "module": "Diseño y Ensamblado de Publicaciones",
        "doc_type": "Tríptico A4 Plegado (297 x 210 mm)",
        "description": "Folleto desplegable de 3 palas con fondos oscuros al corte exacto (0 mm de sangre) y bloques de texto que invaden las líneas de plegado (hendido).",
        "target_errors": [
            "Cero milímetros de sangrado en los 4 bordes perimetrales (0 mm BleedBox).",
            "Textos ubicados a menos de 2 mm de las líneas de doblado de las palas.",
            "Riesgo de filetes blancos en guillotina y corte de texto al plegar."
        ],
        "learning_goals": [
            "Añadir +3 mm de sangrado perimetral en documentos plegados.",
            "Respetar la zona de seguridad mínima de 4 mm respecto al corte y hendido.",
            "Calcular la compensación de anchura de la pala interior envolvente (97-100-100 mm)."
        ],
        "iso_norm": "ISO 12647-2 (Tolerancia de corte mecánico ±0.5 mm)"
    },
    {
        "id": "reto_poster_baja_resolucion",
        "category": "iniciacion",
        "title": "Reto 4: Cartel Promocional con Imágenes Web a 72 DPI",
        "level": "Iniciación FP (Grado Medio / 1º GS)",
        "module": "Tratamiento de Imagen y Resolución Digital",
        "doc_type": "Cartel A3 (297 x 420 mm)",
        "description": "Cartel de evento musical donde la imagen principal de fondo fue descargada de una red social y escalada al 400%, alcanzando una resolución efectiva de apenas 72 DPI.",
        "target_errors": [
            "Resolución efectiva de 72 DPI (muy inferior al estándar de 300 DPI en offset).",
            "Pixelado y efecto escalera visible a simple vista en la imagen central.",
            "Logotipo corporativo en mapa de bits con compresión JPEG agresiva."
        ],
        "learning_goals": [
            "Calcular la resolución efectiva en función de la escala de colocación.",
            "Diferenciar entre resolución nativa de archivo y resolución de salida a tamaño final.",
            "Exigir la sustitución por originales en alta resolución (≥ 300 DPI)."
        ],
        "iso_norm": "ISO 12647-2 (Resolución recomendada ≥ 300 DPI para trama 150-175 lpi)"
    },
    {
        "id": "reto_marcapaginas_fuentes_no_incrustadas",
        "category": "iniciacion",
        "title": "Reto 5: Marcapáginas Cultural con Tipografías No Incrustadas",
        "level": "Iniciación FP (Grado Medio / 1º GS)",
        "module": "Tipografía y Tecnologías de Preimpresión",
        "doc_type": "Marcapáginas (50 x 200 mm)",
        "description": "Marcapáginas con citas literarias en tipografías ornamentales que no fueron incrustadas en el PDF, provocando que el RIP del flujo de trabajo las sustituya por fuentes del sistema.",
        "target_errors": [
            "Tipografías no incrustadas en el archivo PDF (fuentes referenciadas externamente).",
            "Riesgo crítico de reflow tipográfico y sustitución arbitraria por Courier/Helvetica.",
            "Textos en cuerpo 7 pt con tracking negativo que se empastarán en tirada."
        ],
        "learning_goals": [
            "Comprobar que todas las fuentes estén incrustadas como subconjunto (Subset).",
            "Entender el peligro de la sustitución automática de glifos en los RIP PostScript/PDF.",
            "Aplicar la vectorización de emergencia o incrustación obligatoria según PDF/X."
        ],
        "iso_norm": "ISO 15930-1 (PDF/X-1a: Incrustación obligatoria del 100% de fuentes)"
    },
    {
        "id": "reto_adhesivo_corte_inexistente",
        "category": "iniciacion",
        "title": "Reto 6: Adhesivo Promocional sin Cajas de Página (TrimBox/BleedBox)",
        "level": "Iniciación FP (Grado Medio / 1º GS)",
        "module": "Geometría del PDF y Preimpresión Digital",
        "doc_type": "Adhesivo Cuadrado (60 x 60 mm)",
        "description": "Archivo PDF exportado desde un software ofimático donde solo existe MediaBox, careciendo de TrimBox (línea de corte) y BleedBox (sangrado), impidiendo el posicionado automático en el RIP.",
        "target_errors": [
            "Ausencia de TrimBox y BleedBox normalizados en la estructura del PDF.",
            "Tamaño de lienzo indefinido que bloquea el centrado en mesa de corte digital.",
            "Textos a menos de 1 mm del borde perimetral del adhesivo."
        ],
        "learning_goals": [
            "Conocer la jerarquía de cajas PDF: MediaBox, CropBox, BleedBox y TrimBox.",
            "Ajustar las cajas de página con herramientas de producción y preflight.",
            "Garantizar la interoperabilidad con mesas de corte Kongsberg y plotters."
        ],
        "iso_norm": "ISO 15930-7 (Definición geométrica exacta en PDF/X-4)"
    },
    {
        "id": "reto_cupon_descuento_tramado",
        "category": "iniciacion",
        "title": "Reto 7: Cupón Descuento con Texto Legal en Gris Tramado al 40%",
        "level": "Iniciación FP (Grado Medio / 1º GS)",
        "module": "Control de Calidad y Tramado en Offset",
        "doc_type": "Cupón Promocional (140 x 70 mm)",
        "description": "Cupón con letra legal minúscula (cuerpo 4.5 pt) coloreada en gris mediante un tramado de semitono al 40% K, lo que rompe los trazos finos de las letras al formarse por puntos de trama dispersos.",
        "target_errors": [
            "Texto de cuerpo pequeño (4.5 pt) tramado con punto de semitono al 40% K.",
            "Pérdida de legibilidad por el tamaño de los puntos de trama en relación al ojo de la letra.",
            "Falta de sangre en la zona del cupón perforado."
        ],
        "learning_goals": [
            "Reconocer por qué las letras menores de 7 pt deben ser trazo continuo (100% K).",
            "Comprender la relación entre lineatura de trama (lpi) y definición de contornos tipográficos.",
            "Ajustar estilos de carácter para textos legales en imprenta."
        ],
        "iso_norm": "ISO 12647-2 (Reproducción tipográfica y umbrales de legibilidad)"
    },

    # =========================================================================
    # CATEGORÍA 2: INTERMEDIO FP (1º GRADO SUPERIOR / TALLER) - 7 RETOS
    # =========================================================================
    {
        "id": "reto_folleto_tac_hairlines",
        "category": "intermedio",
        "title": "Reto 8: Folleto Promocional con TAC 365% y Líneas Pelo (CTP)",
        "level": "Intermedio (Taller de Impresión Offset / Digital)",
        "module": "Impresión Offset y Control de Producción",
        "doc_type": "Folleto A5 (148 x 210 mm)",
        "description": "Folleto publicitario con un fondo fotográfico nocturno cuya cobertura total de tinta (TAC) alcanza el 365% y filetes dorados decorativos de 0.06 pt no reproducibles en CTP.",
        "target_errors": [
            "Exceso extremo de cobertura de tinta (TAC 365% vs límite de 300%-320%).",
            "Líneas ultrafinas (0.06 pt) no reproducibles en plancha CTP térmica.",
            "Riesgo crítico de repintado y maculado en la pila de salida de máquina."
        ],
        "learning_goals": [
            "Comprender los límites de absorción del papel estucado según ISO 12647-2.",
            "Controlar la curva de transferencia en CTP y umbral mínimo de trazo (0.25 pt).",
            "Aplicar conversión con perfil DeviceLink o reducción de TAC sin alterar el contraste."
        ],
        "iso_norm": "ISO 12647-2: Cobertura máxima de tinta ≤ 300% (Offset hojas)"
    },
    {
        "id": "reto_catalogo_pantone_excesivo",
        "category": "intermedio",
        "title": "Reto 9: Catálogo Comercial con 5 Tintas Planas Pantone Directas",
        "level": "Intermedio (1º Grado Superior)",
        "module": "Gestión del Color y Costes de Taller",
        "doc_type": "Catálogo A4 (210 x 297 mm)",
        "description": "Catálogo comercial diseñado con 5 tintas planas Pantone diferentes además de cuatricromía CMYK, disparando los costes de producción en una máquina offset estándar de 4 colores.",
        "target_errors": [
            "5 colores directos Pantone en un trabajo presupuestado para 4 tintas CMYK.",
            "Imposibilidad de imprimir en máquina de 4 cuerpos en una sola tirada sin 2ª pasada.",
            "Diferencias tonales en conversión descontrolada de Pantone a CMYK."
        ],
        "learning_goals": [
            "Identificar y convertir tintas planas a CMYK usando tablas LAB oficiales.",
            "Diferenciar entre trabajos de tirada cuatricromía estándar vs colores corporativos obligatorios.",
            "Calcular el impacto en costes de planchas CTP y horas de máquina."
        ],
        "iso_norm": "ISO 12647-2 / Especificaciones ECI para Impresión Comercial"
    },
    {
        "id": "reto_dossier_sobreimpresion_blanco",
        "category": "intermedio",
        "title": "Reto 10: Dossier Corporativo con Blanco en Sobreimpresión (White Overprint)",
        "level": "Intermedio (1º Grado Superior)",
        "module": "Preimpresión y Separaciones de Color",
        "doc_type": "Dossier A4 (210 x 297 mm)",
        "description": "El logotipo corporativo blanco situado sobre un fondo fotográfico oscuro tiene activado accidentalmente el atributo de sobreimpresión (overprint), haciendo que desaparezca en la plancha.",
        "target_errors": [
            "Elemento vectorial blanco con sobreimpresión activada (/OP true).",
            "Desaparición total del logotipo al rasterizar y separar en planchas CTP.",
            "Error invisible en visores PDF convencionales que no simulan sobreimpresión."
        ],
        "learning_goals": [
            "Comprender la diferencia entre Calado (Knockout) y Sobreimpresión (Overprint).",
            "Activar la previsualización de separaciones y sobreimpresión en el flujo de trabajo.",
            "Reparar automáticamente el blanco en sobreimpresión forzando su calado."
        ],
        "iso_norm": "Ghent Workgroup (GWG) Preflight Specification: White Overprint = ERROR"
    },
    {
        "id": "reto_menu_trapping_descalce",
        "category": "intermedio",
        "title": "Reto 11: Carta de Menú con Texto Amarillo sobre Azul sin Reventado (Trapping)",
        "level": "Intermedio (1º Grado Superior)",
        "module": "Impresión Offset y Control de Registro",
        "doc_type": "Carta de Restaurante (150 x 300 mm)",
        "description": "Tipografía amarilla (100% Y) colocada sobre un fondo azul oscuro (100% C + 70% M) sin ningún trazo de reventado (trapping), provocando filetes blancos en cuanto la máquina vibra.",
        "target_errors": [
            "Falta de reventado (trapping) en colores adyacentes de alta luminancia.",
            "Aparición de filetes blancos de papel entre el amarillo y el azul por descalce mecánico.",
            "Carencia de margen de auto-trapping (mínimo 0.15 pt / 0.05 mm en offset)."
        ],
        "learning_goals": [
            "Aprender la teoría del reventado: ensanchar el color más claro sobre el más oscuro.",
            "Configurar motores de auto-trapping en el RIP antes de filmar planchas.",
            "Inspeccionar las separaciones de color para verificar el solape entre tintas."
        ],
        "iso_norm": "ISO 12647-2 (Tolerancia de descalce de registro en máquina offset ≤ 0.08 mm)"
    },
    {
        "id": "reto_diploma_guilloche_fino",
        "category": "intermedio",
        "title": "Reto 12: Orla de Diploma con Filetes Guilloche de 0.08 pt y TAC Elevado",
        "level": "Intermedio (1º Grado Superior)",
        "module": "Tecnología CTP y Productos de Seguridad",
        "doc_type": "Diploma A4 Horizontal (297 x 210 mm)",
        "description": "Orla decorativa clásica de diploma académico con complejos trazos guilloche de seguridad de 0.08 pt y masa perimetral con TAC al 330% sobre papel verjurado no estucado.",
        "target_errors": [
            "Trazos ornamentales de 0.08 pt por debajo del umbral mínimo de plancha CTP (0.25 pt).",
            "Riesgo de desaparición de la orla durante el tiraje por arrastre de emulsión.",
            "Exceso de tinta (TAC 330%) en papel poroso no estucado (Offset / WLC)."
        ],
        "learning_goals": [
            "Ajustar el grosor mínimo de filete según la resolución CTP y soporte de impresión.",
            "Aplicar curvas de compensación de ganancia de punto para líneas finas.",
            "Adecuar el límite de tinta al tipo de papel según norma ISO (260% en offset no estucado)."
        ],
        "iso_norm": "ISO 12647-2 (Papel Tipo 4 no estucado: TAC máx. 260%-280%)"
    },
    {
        "id": "reto_manual_k_knockout",
        "category": "intermedio",
        "title": "Reto 13: Manual de Taller con Texto 100% K en Calado (Knockout)",
        "level": "Intermedio (1º Grado Superior)",
        "module": "Preimpresión Editorial y Flujos de Trabajo",
        "doc_type": "Manual Técnico A5 (148 x 210 mm)",
        "description": "Cuerpo de texto en negro 100% K que cala las masas de color de fondo en vez de sobreimprimir, dejando huecos blancos en las planchas CMY vulnerables a cualquier descalce de registro.",
        "target_errors": [
            "Texto negro 100% K configurado en calado (knockout) sobre fondos de color.",
            "Huecos en blanco en las planchas de Cyan, Magenta y Amarillo para cada letra.",
            "Bordes blancos y halos alrededor de las letras en máquina offset."
        ],
        "learning_goals": [
            "Comprender la regla de oro de preimpresión: Texto 100% K debe sobreimprimir siempre.",
            "Aplicar la regla de auto-sobreimpresión de negro en el RIP o motor de preflight.",
            "Ahorrar tiempos de ajuste de registro en la puesta a punto de máquina."
        ],
        "iso_norm": "Ghent Workgroup: 100% Black text must overprint"
    },
    {
        "id": "reto_calendario_tinteros_descompensados",
        "category": "intermedio",
        "title": "Reto 14: Calendario de Sobremesa con Descompensación de Tinteros CIP3",
        "level": "Intermedio (1º Grado Superior)",
        "module": "Impresión Offset y Estandarización CIP3",
        "doc_type": "Calendario Triangular (210 x 100 mm)",
        "description": "Diseño con una gran masa oscura continua en el lateral izquierdo (cobertura 90%) y área totalmente blanca en el derecho (0%), generando una descompensación extrema entre las llaves de tinta del tintero.",
        "target_errors": [
            "Desequilibrio lateral extremo de entintado entre zonas adyacentes de tintero.",
            "Riesgo de emulsión de agua en los rodillos dadores de las llaves con consumo 0%.",
            "Dificultad de regulación del equilibrio agua-tinta y posible efecto fantasma (ghosting)."
        ],
        "learning_goals": [
            "Calcular los perfiles zonales de apertura de tintero CIP3 / PPF.",
            "Comprender la mecánica de las llaves de tintero y los rodillos zonales.",
            "Diseñar franjas de compensación (take-off bars) para mantener consumo uniforme."
        ],
        "iso_norm": "CIP3 Print Production Format (PPF) v3.0 / ISO 12647-2"
    },

    # =========================================================================
    # CATEGORÍA 3: AVANZADO FP (2º GS / MÁSTER PACKAGING Y EDITORIAL) - 6 RETOS
    # =========================================================================
    {
        "id": "reto_packaging_barcode_cmyk",
        "category": "avanzado",
        "title": "Reto 15: Estuche Packaging con Código de Barras EAN-13 en 4 Tintas",
        "level": "Avanzado (Packaging y Troquelado)",
        "module": "Troquelado, Packaging y Trazabilidad",
        "doc_type": "Estuche Cosmético (120 x 180 mm)",
        "description": "Estuche desplegado con código de barras EAN-13 impreso en 4 tintas sin reserva blanca, y textos legales a 1.2 mm del trazo de hendido y troquel.",
        "target_errors": [
            "Código de barras EAN-13 tramado en cuatricromía (provoca rechazo en escáneres ópticos).",
            "Falta de zona de silencio lateral (Quiet Zone) en el código de barras.",
            "Invasión de la zona de seguridad y línea de troquelado (menos de 3 mm)."
        ],
        "learning_goals": [
            "Conocer las especificaciones GS1 para códigos de barras comerciales (100% K y quiet zone).",
            "Dominar las tolerancias de troquelado y hendido en cartoncillo.",
            "Evitar devoluciones comerciales por código ilegible en lineales de venta."
        ],
        "iso_norm": "ISO/IEC 15420 (GS1 EAN-13) & ISO 12647-2"
    },
    {
        "id": "reto_revista_seguridad_lomo",
        "category": "avanzado",
        "title": "Reto 16: Portada y Pliegos de Revista con Textos en el Medianil/Lomo",
        "level": "Avanzado (Imposición y Encuadernación)",
        "module": "Gestión de la Producción Gráfica y Acabados",
        "doc_type": "Revista A4 (210 x 297 mm, 16 págs)",
        "description": "Publicación editorial grapada en la que los folios explicativos y pies de foto tocan el pliegue del lomo (medianil) a 2 mm del pliegue sin considerar la trepa o desplazamiento.",
        "target_errors": [
            "Textos e información crítica ubicados dentro de la zona de hendido del lomo (8 mm).",
            "Imágenes no separadas a CMYK (perfil de cámara sRGB).",
            "Falta de consideración del desplazamiento o trepa en cuadernillos grapados."
        ],
        "learning_goals": [
            "Calcular la reserva de medianil y lomo según el tipo de encuadernación (grapa vs rústica).",
            "Separación cromática según el soporte (FOGRA39 / FOGRA51).",
            "Comprender el efecto físico de la guillotina trilateral en publicaciones plegadas."
        ],
        "iso_norm": "ISO 12647-2 / Especificaciones ECI para Edición Gráfica"
    },
    {
        "id": "reto_etiqueta_barniz_calado",
        "category": "avanzado",
        "title": "Reto 17: Etiqueta de Vino con Barniz UVI Calando en vez de Sobreimprimir",
        "level": "Avanzado (Acabados Especiales y Etiquetas)",
        "module": "Serigrafía, Barnices y Acabados de Alto Valor",
        "doc_type": "Etiqueta Enológica (90 x 130 mm)",
        "description": "Etiqueta adhesiva de vino con una capa de barniz serigráfico selectivo (Varnish) colocada con atributo knockout, provocando que se elimine la impresión CMYK inferior.",
        "target_errors": [
            "Tinta especial de barniz serigráfico calando las tintas de cuatricromía subyacentes.",
            "Aparición de huecos blancos no entintados debajo de la capa de brillo.",
            "Definición errónea de la separación técnica de barniz en el PDF."
        ],
        "learning_goals": [
            "Configurar las tintas de acabado técnico (Barniz, Stamping, Golpe seco) en sobreimpresión obligatoria.",
            "Definir nombres normalizados de tintas directas técnicas en flujos packaging.",
            "Verificar en Adobe Acrobat Output Preview o IntelliPrint el comportamiento de las capas."
        ],
        "iso_norm": "ISO 12647-2 / Especificaciones GWG Packaging"
    },
    {
        "id": "reto_prospecto_qr_richblack",
        "category": "avanzado",
        "title": "Reto 18: Prospecto Farmacéutico con Código QR en 4 Tintas sobre Papel Fino",
        "level": "Avanzado (Packaging Farmacéutico)",
        "module": "Prospectos y Control de Calidad Farmacéutica",
        "doc_type": "Prospecto Médico Plegado (140 x 210 mm)",
        "description": "Prospecto farmacéutico con código QR para prospecto digital impreso en papel biblia de 45 g/m² compuesto en negro enriquecido (Rich Black), empastándose los módulos.",
        "target_errors": [
            "Código QR de alta densidad compuesto en 4 tintas (Rich Black 300%).",
            "Ganancia de punto excesiva en papel biblia fino no estucado que cierra los micropíxeles.",
            "Imposibilidad de escaneo por pacientes o farmacéuticos."
        ],
        "learning_goals": [
            "Generar códigos 2D bidimensionales (QR, DataMatrix) estrictamente en 100% K puro.",
            "Calcular la ganancia de punto en papeles de bajo gramaje (38-50 g/m²).",
            "Verificar la legibilidad con lectores ópticos de control de calidad."
        ],
        "iso_norm": "ISO/IEC 18004 (Código QR) / ISO 15378 (Materiales de envasado farmacéutico)"
    },
    {
        "id": "reto_imposicion_sra3_descuadre",
        "category": "avanzado",
        "title": "Reto 19: Pliego de Imposición SRA3 sin Calles de Corte ni Marcas de Taller",
        "level": "Avanzado (Imposición y Montaje de Pliegos)",
        "module": "Imposición Digital y CTP",
        "doc_type": "Pliego SRA3 Montado a Mano (450 x 320 mm)",
        "description": "Pliego SRA3 montado artesanalmente por un diseñador con 8 tarjetas pegadas a corte cero sin calle de separación, sin marcas de corte, sin cruces de registro y sin tira FOGRA.",
        "target_errors": [
            "Ausencia de calles de corte y sangre intermedia entre poses (gutter 0 mm).",
            "Carencia de marcas de imprenta (cruces de registro, marcas de corte y colas de alondra).",
            "Falta de tira de control densitométrica ISO 12647-2 para ajuste de color en máquina."
        ],
        "learning_goals": [
            "Utilizar el motor de imposición paramétrica de taller en vez de montaje manual.",
            "Calcular las calles mínimas de corte según la cuchilla de la guillotina (mínimo 4 mm).",
            "Incorporar tiras de control espectrofotométrico normalizadas (FOGRA / Idealliance)."
        ],
        "iso_norm": "ISO 12647-2 / CIP3 / CIP4 JDF Imposition Standards"
    },
    {
        "id": "reto_caja_pegado_barnizado",
        "category": "avanzado",
        "title": "Reto 20: Envase Alimentario con Masa de Tinta y Barniz en la Solapa de Pegado",
        "level": "Avanzado (Troquelado y Líneas de Encolado)",
        "module": "Plegado y Pegado de Envases Plegables",
        "doc_type": "Caja de Cartoncillo Plegable (200 x 280 mm)",
        "description": "Envase alimentario cuya pestaña lateral de pegado (glue flap) está completamente cubierta por tinta negra y barniz de sobreimpresión, impidiendo la adhesión química de la cola PUR caliente en la plegadora-pegadora.",
        "target_errors": [
            "Masa de tinta y barniz cubriendo la solapa de encolado (Glue Flap de 15 mm).",
            "Riesgo de apertura espontánea del envase en la línea de envasado del cliente.",
            "Costosa parada de máquina plegadora-pegadora por fallo de pegado."
        ],
        "learning_goals": [
            "Diseñar reservas en blanco obligatorias en las solapas de pegado de packaging.",
            "Comprender la química de los adhesivos hot-melt y colas frías sobre cartón.",
            "Supervisar los planos de troquel y trazado estructural en preimpresión."
        ],
        "iso_norm": "ECMA Packaging Standards / ISO 12647-2"
    }
]

# ---------------------------------------------------------------------------
# GENERADOR DINÁMICO DE ARCHIVOS SINTÉTICOS DE RETO (PDF REALES)
# ---------------------------------------------------------------------------

def generate_scenario_pdf(scenario_id: str, output_path: Path) -> Path:
    """
    Genera un PDF sintético con los errores intencionados del reto seleccionado
    para que el alumno pueda inspeccionarlo directamente con el motor de preflight.
    Soporta los 20 retos del catálogo en las 3 categorías formativas de FP.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()

    # -----------------------------------------------------------------------
    # RETO 1: Tarjeta Corporativa con Rich Black y Sin Sangrado
    # -----------------------------------------------------------------------
    if scenario_id == "reto_tarjeta_richblack":
        w, h = 240.94, 155.91 # 85 x 55 mm
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)
        page.set_mediabox(pymupdf.Rect(0, 0, w, h))

        # Fondo oscuro al corte exacto (Rich black C=60, M=50, Y=40, K=100)
        page.draw_rect(pymupdf.Rect(0, 0, w, h), fill=(0.04, 0.03, 0.03))
        page.draw_rect(pymupdf.Rect(10, 10, w - 10, h - 10), color=(0.85, 0.70, 0.20), width=0.8)

        page.insert_text(pymupdf.Point(20, 40), "SERVICIOS GRÁFICOS NORTE", fontsize=11, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(20, 56), "Consultoría Gráfica & Packaging", fontsize=7.5, fontname="helv", color=(0.85, 0.70, 0.20))
        page.insert_text(pymupdf.Point(20, 85), "Director Técnico: Martin Otegui", fontsize=6.0, fontname="helv", color=(0.05, 0.05, 0.06))
        page.insert_text(pymupdf.Point(20, 97), "Tel: +34 943 00 11 22 · info@graficasnorte.eus", fontsize=5.5, fontname="helv", color=(0.05, 0.05, 0.06))
        page.insert_text(pymupdf.Point(20, 108), "Parque Tecnológico Miramon, Donostia", fontsize=5.5, fontname="helv", color=(0.05, 0.05, 0.06))

        img = Image.new("RGB", (40, 40), color=(220, 180, 50))
        d = ImageDraw.Draw(img)
        d.rectangle([5, 5, 35, 35], outline=(30, 30, 30), width=2)
        d.text((12, 12), "GN", fill=(20, 20, 20))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        page.insert_image(pymupdf.Rect(w - 60, 30, w - 20, 70), stream=buf.getvalue())

    # -----------------------------------------------------------------------
    # RETO 2: Flyer Nocturno en Espacio de Color RGB sin Separación
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_flyer_rgb_srgb":
        w, h = 297.64, 419.53 # A6
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        # Fondo con gradiente simulado en RGB vivo
        page.draw_rect(pymupdf.Rect(0, 0, w, h), fill=(0.05, 0.02, 0.15))
        page.insert_text(pymupdf.Point(30, 50), "ELECTRO NIGHT FESTIVAL 2026", fontsize=15, fontname="helv", color=(0.0, 0.95, 0.95))
        page.insert_text(pymupdf.Point(30, 75), "Live Acts · Visuals · Kursaal Donostia", fontsize=9, fontname="helv", color=(1.0, 0.1, 0.7))

        # Imagen decorativa en RGB puro de cámara (sRGB no separado)
        img_rgb = Image.new("RGB", (180, 120), color=(15, 30, 80))
        idraw = ImageDraw.Draw(img_rgb)
        idraw.ellipse([20, 10, 160, 110], fill=(0, 240, 255), outline=(255, 0, 180), width=4)
        idraw.text((40, 50), "sRGB GAMUT CLIP", fill=(255, 255, 255))
        buf = io.BytesIO()
        img_rgb.save(buf, format="JPEG", quality=85)
        page.insert_image(pymupdf.Rect(30, 100, w - 30, 220), stream=buf.getvalue())

        page.insert_text(pymupdf.Point(30, 260), "Artistas Confirmados:", fontsize=11, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(30, 285), "DJ SynthWave · Visual Beats Crew · Neon Live", fontsize=8.5, fontname="helv", color=(0.7, 0.8, 1))
        page.insert_text(pymupdf.Point(30, 360), "Entradas a la venta en www.electrofpeuskadi.eus", fontsize=8, fontname="helv", color=(0.0, 0.9, 0.8))

    # -----------------------------------------------------------------------
    # RETO 3: Tríptico Envolvente con Fondos al Corte y Cajas al Ras
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_triptico_sin_sangre":
        w, h = 841.89, 595.28 # A4 Horizontal
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        panel_w = w / 3.0 # 280.6 pt cada pala
        # Pala 1 (Izquierda)
        page.draw_rect(pymupdf.Rect(0, 0, panel_w, h), fill=(0.12, 0.22, 0.35))
        # Pala 2 (Centro)
        page.draw_rect(pymupdf.Rect(panel_w, 0, panel_w * 2, h), fill=(0.16, 0.28, 0.42))
        # Pala 3 (Derecha)
        page.draw_rect(pymupdf.Rect(panel_w * 2, 0, w, h), fill=(0.20, 0.35, 0.50))

        # Líneas de plegado (hendido)
        page.draw_line(pymupdf.Point(panel_w, 0), pymupdf.Point(panel_w, h), color=(0.8, 0.8, 0.9), width=0.5)
        page.draw_line(pymupdf.Point(panel_w * 2, 0), pymupdf.Point(panel_w * 2, h), color=(0.8, 0.8, 0.9), width=0.5)

        # Textos invadiendo líneas de plegado (a 1 pt de distancia)
        page.insert_text(pymupdf.Point(panel_w - 90, 80), "PALA INTERIOR", fontsize=12, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(panel_w - 4, 140), "TEXTO AL BORDE DEL PLIEGUE (PELIGRO DE CORTE)", fontsize=6.5, fontname="helv", color=(1, 0.4, 0.4))
        page.insert_text(pymupdf.Point(panel_w * 2 - 4, 140), "COLUMNA DE CONTACTO PEGADA AL HENDIDO", fontsize=6.5, fontname="helv", color=(1, 0.4, 0.4))

    # -----------------------------------------------------------------------
    # RETO 4: Cartel Promocional con Imágenes Web a 72 DPI
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_poster_baja_resolucion":
        w, h = 841.89, 1190.55 # A3
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        page.draw_rect(pymupdf.Rect(0, 0, w, 200), fill=(0.15, 0.15, 0.20))
        page.insert_text(pymupdf.Point(60, 110), "BIZKAIA GRAPHIC EXPO 2026", fontsize=32, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(60, 150), "Feria Internacional de Artes Gráficas y Packaging", fontsize=16, fontname="helv", color=(0.85, 0.70, 0.20))

        # Imagen web de 72 DPI estirada en gran formato
        img_72 = Image.new("RGB", (120, 160), color=(180, 70, 40))
        idraw = ImageDraw.Draw(img_72)
        idraw.rectangle([10, 10, 110, 150], outline=(255, 255, 255), width=3)
        idraw.text((20, 70), "LOW-RES 72 DPI", fill=(255, 255, 255))
        buf = io.BytesIO()
        img_72.save(buf, format="JPEG", quality=40)
        # Se coloca en un cuadro enorme de 600x500 pt -> resolución resultante ~17 DPI
        page.insert_image(pymupdf.Rect(120, 260, 720, 760), stream=buf.getvalue())
        page.insert_text(pymupdf.Point(120, 800), "Imagen principal colocada a escala 450% sin resolución nativa suficiente", fontsize=11, fontname="helv", color=(0.4, 0.4, 0.4))

    # -----------------------------------------------------------------------
    # RETO 5: Marcapáginas Cultural con Tipografías No Incrustadas
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_marcapaginas_fuentes_no_incrustadas":
        w, h = 141.73, 566.93 # 50 x 200 mm
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        page.draw_rect(pymupdf.Rect(0, 0, w, h), fill=(0.96, 0.94, 0.90))
        page.draw_rect(pymupdf.Rect(8, 8, w - 8, h - 8), color=(0.5, 0.3, 0.2), width=1)
        page.insert_text(pymupdf.Point(20, 60), "DONOSTIA", fontsize=14, fontname="times-bold", color=(0.4, 0.2, 0.1))
        page.insert_text(pymupdf.Point(20, 85), "HIRIBURU KULTURALA", fontsize=7, fontname="times-italic", color=(0.6, 0.4, 0.2))

        # Texto que invade márgenes perimetrales (1 mm = 2.8 pt)
        page.insert_text(pymupdf.Point(3.0, 250), "«Irakurtzea bidaia bat da mugitu gabe»", fontsize=6.8, fontname="times-roman", color=(0.2, 0.2, 0.2))
        page.insert_text(pymupdf.Point(3.0, 320), "Fuente tipográfica no incrustada en el PDF", fontsize=5.8, fontname="times-roman", color=(0.8, 0.1, 0.1))

    # -----------------------------------------------------------------------
    # RETO 6: Adhesivo Promocional sin Cajas de Página (TrimBox/BleedBox)
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_adhesivo_corte_inexistente":
        w, h = 170.08, 170.08 # 60 x 60 mm
        page = doc.new_page(width=w, height=h)
        # No asignamos TrimBox ni BleedBox (solo MediaBox por defecto)

        page.draw_circle(pymupdf.Point(w / 2, h / 2), 80, fill=(0.1, 0.5, 0.3))
        page.insert_text(pymupdf.Point(25, 75), "ECO BASQUE", fontsize=15, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(35, 95), "100% ORGANIKOA", fontsize=8.5, fontname="helv", color=(0.9, 0.9, 0.2))
        # Texto rozando el borde perimetral
        page.insert_text(pymupdf.Point(4.0, 155), "Certificado Euskadi Calidad · Lote 2026", fontsize=5.5, fontname="helv", color=(0.2, 0.2, 0.2))

    # -----------------------------------------------------------------------
    # RETO 7: Cupón Descuento con Texto Legal en Gris Tramado al 40%
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_cupon_descuento_tramado":
        w, h = 396.85, 198.43 # 140 x 70 mm
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        page.draw_rect(pymupdf.Rect(0, 0, w, h), fill=(0.98, 0.98, 0.95))
        page.draw_rect(pymupdf.Rect(10, 10, w - 10, h - 10), color=(0.8, 0.2, 0.2), width=1.5)
        page.insert_text(pymupdf.Point(25, 50), "VALE DESCUENTO 20%", fontsize=18, fontname="helv", color=(0.8, 0.1, 0.1))
        page.insert_text(pymupdf.Point(25, 75), "En servicios de encuadernación y plastificado", fontsize=9.5, fontname="helv", color=(0.3, 0.3, 0.3))

        # Texto legal en gris 40% tramado de cuerpo diminuto (4.5 pt)
        page.insert_text(pymupdf.Point(25, 120), "Condiciones legales: Válido hasta el 31/12/2026 en establecimientos asociados. No acumulable a otras promociones.", fontsize=4.5, fontname="helv", color=(0.60, 0.60, 0.60))
        page.insert_text(pymupdf.Point(25, 132), "El texto gris en cuerpo 4.5 pt produce puntos de semitono rotos e ilegibles al imprimir en máquina offset.", fontsize=4.5, fontname="helv", color=(0.60, 0.60, 0.60))

    # -----------------------------------------------------------------------
    # RETO 8: Folleto Promocional con TAC 365% y Líneas Pelo (CTP)
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_folleto_tac_hairlines":
        w, h = 419.53, 595.28 # A5
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        # Fondo con gran densidad de tinta (simula TAC 365%)
        page.draw_rect(pymupdf.Rect(0, 0, w, h), fill=(0.02, 0.01, 0.01))

        # Líneas pelo (hairlines < 0.25 pt)
        page.draw_line(pymupdf.Point(30, 80), pymupdf.Point(w - 30, 80), color=(0.95, 0.85, 0.40), width=0.06)
        page.draw_line(pymupdf.Point(30, 84), pymupdf.Point(w - 30, 84), color=(0.95, 0.85, 0.40), width=0.08)
        page.draw_line(pymupdf.Point(30, 520), pymupdf.Point(w - 30, 520), color=(0.95, 0.85, 0.40), width=0.05)

        page.insert_text(pymupdf.Point(40, 120), "CONCIERTO SINFÓNICO NOCTURNO", fontsize=18, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(40, 145), "Gran Gala de Apertura · Temporada 2026/2027", fontsize=11, fontname="helv", color=(0.9, 0.8, 0.4))
        page.insert_text(pymupdf.Point(40, 180), "Auditorio Kursaal · Donostia-San Sebastián", fontsize=10, fontname="helv", color=(0.8, 0.8, 0.8))

        page.draw_rect(pymupdf.Rect(35, 220, w - 35, 480), fill=(0.08, 0.06, 0.07), color=(0.9, 0.8, 0.4), width=0.1)
        page.insert_text(pymupdf.Point(50, 260), "Programa de Obras:", fontsize=12, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(50, 290), "1. Obertura Festiva - D. Shostakovich", fontsize=9, fontname="helv", color=(0.85, 0.85, 0.85))
        page.insert_text(pymupdf.Point(50, 315), "2. Sinfonía Nº 9 en Mi menor - A. Dvorak", fontsize=9, fontname="helv", color=(0.85, 0.85, 0.85))
        page.insert_text(pymupdf.Point(50, 340), "3. Danzas Polovtsianas - A. Borodin", fontsize=9, fontname="helv", color=(0.85, 0.85, 0.85))

    # -----------------------------------------------------------------------
    # RETO 9: Catálogo Comercial con 5 Tintas Planas Pantone Directas
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_catalogo_pantone_excesivo":
        w, h = 595.28, 841.89 # A4
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        page.draw_rect(pymupdf.Rect(0, 0, w, 140), fill=(0.1, 0.15, 0.25))
        page.insert_text(pymupdf.Point(50, 70), "CATÁLOGO DE TENDENCIAS OTOÑO/INVIERNO", fontsize=18, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(50, 100), "Edición Coleccionista con 5 Tintas Directas Pantone", fontsize=11, fontname="helv", color=(0.9, 0.7, 0.3))

        # Muestrario de las 5 tintas spot
        pantones = [
            ("PANTONE 186 C (Rojo)", (0.85, 0.1, 0.2)),
            ("PANTONE 286 C (Azul Real)", (0.1, 0.2, 0.8)),
            ("PANTONE 368 C (Verde)", (0.3, 0.75, 0.2)),
            ("PANTONE 123 C (Amarillo)", (0.95, 0.8, 0.1)),
            ("PANTONE Reflex Blue C", (0.05, 0.1, 0.5))
        ]
        y_pos = 180
        for name, col in pantones:
            page.draw_rect(pymupdf.Rect(50, y_pos, 110, y_pos + 40), fill=col)
            page.insert_text(pymupdf.Point(130, y_pos + 25), name, fontsize=10, fontname="helv", color=(0.2, 0.2, 0.2))
            y_pos += 65

    # -----------------------------------------------------------------------
    # RETO 10: Dossier Corporativo con Blanco en Sobreimpresión (White Overprint)
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_dossier_sobreimpresion_blanco":
        w, h = 595.28, 841.89 # A4
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        # Fondo oscuro continuo
        page.draw_rect(pymupdf.Rect(0, 0, w, h), fill=(0.08, 0.12, 0.22))
        page.insert_text(pymupdf.Point(50, 80), "MEMORIA ANUAL DE SOSTENIBILIDAD", fontsize=20, fontname="helv", color=(0.3, 0.7, 0.9))

        # Logotipo blanco con advertencia de White Overprint
        page.draw_rect(pymupdf.Rect(50, 180, 250, 280), fill=(1, 1, 1))
        page.insert_text(pymupdf.Point(70, 240), "LOGO BLANCO", fontsize=16, fontname="helv", color=(0.08, 0.12, 0.22))
        page.insert_text(pymupdf.Point(50, 310), "AVISO TÉCNICO: Elemento blanco configurado con /OP true (Sobreimpresión activa).", fontsize=8.5, fontname="helv", color=(1, 0.4, 0.4))
        page.insert_text(pymupdf.Point(50, 325), "En el RIP de preimpresión este logotipo desaparecerá al filmar las planchas.", fontsize=8.5, fontname="helv", color=(0.8, 0.8, 0.8))

    # -----------------------------------------------------------------------
    # RETO 11: Carta de Menú con Texto Amarillo sobre Azul sin Reventado
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_menu_trapping_descalce":
        w, h = 425.20, 850.39 # 150 x 300 mm
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        # Fondo azul intenso (100% Cyan + 50% Magenta)
        page.draw_rect(pymupdf.Rect(0, 0, w, h), fill=(0.0, 0.4, 0.85))

        page.insert_text(pymupdf.Point(40, 90), "RESTAURANTE MARITIMO", fontsize=18, fontname="helv", color=(1, 1, 1))
        # Texto amarillo puro sobre azul sin trapping
        page.insert_text(pymupdf.Point(40, 150), "MENÚ DEGUSTACIÓN CANTÁBRICO", fontsize=13, fontname="helv", color=(1.0, 0.95, 0.0))
        page.insert_text(pymupdf.Point(40, 180), "Primeros Platos (Texto 100% Y sobre 100% C):", fontsize=10, fontname="helv", color=(1.0, 0.95, 0.0))
        page.insert_text(pymupdf.Point(40, 210), "· Txangurro a la Donostiarra al Horno", fontsize=9, fontname="helv", color=(1.0, 0.95, 0.0))
        page.insert_text(pymupdf.Point(40, 230), "· Kokotxas de Merluza al Pil-Pil Tradicional", fontsize=9, fontname="helv", color=(1.0, 0.95, 0.0))
        page.insert_text(pymupdf.Point(40, 320), "Incidencia: Falta de auto-trapping en bordes de alto contraste luminotécnico.", fontsize=8, fontname="helv", color=(1, 1, 1))

    # -----------------------------------------------------------------------
    # RETO 12: Orla de Diploma con Filetes Guilloche de 0.08 pt y TAC Elevado
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_diploma_guilloche_fino":
        w, h = 841.89, 595.28 # A4 Horizontal
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        page.draw_rect(pymupdf.Rect(0, 0, w, h), fill=(0.99, 0.98, 0.95))
        # Filetes ornamentales ultrafinos (0.07 pt y 0.09 pt)
        for offset in range(12, 32, 4):
            page.draw_rect(pymupdf.Rect(offset, offset, w - offset, h - offset), color=(0.7, 0.5, 0.1), width=0.07)

        page.insert_text(pymupdf.Point(120, 140), "DIPLOMA DE EXCELENCIA TÉCNICA EN ARTES GRÁFICAS", fontsize=18, fontname="times-bold", color=(0.2, 0.2, 0.2))
        page.insert_text(pymupdf.Point(220, 220), "Se otorga el presente reconocimiento al alumno/a por su destreza en preimpresión.", fontsize=10, fontname="times-italic", color=(0.3, 0.3, 0.3))

        # Medallón oscuro con TAC 340%
        page.draw_circle(pymupdf.Point(w / 2, 380), 50, fill=(0.04, 0.02, 0.02), color=(0.7, 0.5, 0.1), width=0.08)
        page.insert_text(pymupdf.Point(w / 2 - 25, 385), "SELLO CTP", fontsize=10, fontname="helv", color=(0.9, 0.8, 0.3))

    # -----------------------------------------------------------------------
    # RETO 13: Manual de Taller con Texto 100% K en Calado (Knockout)
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_manual_k_knockout":
        w, h = 419.53, 595.28 # A5
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        page.draw_rect(pymupdf.Rect(0, 0, w, 100), fill=(0.2, 0.5, 0.8))
        page.insert_text(pymupdf.Point(30, 60), "MANUAL DE OPERACIÓN DE PRENSA", fontsize=14, fontname="helv", color=(1, 1, 1))

        # Franja de color donde el texto negro está calando
        page.draw_rect(pymupdf.Rect(20, 140, w - 20, 300), fill=(0.9, 0.6, 0.2))
        page.insert_text(pymupdf.Point(35, 175), "INSTRUCCIÓN CRÍTICA DE SEGURIDAD:", fontsize=11, fontname="helv", color=(0, 0, 0))
        page.insert_text(pymupdf.Point(35, 205), "El texto negro 100% K está configurado en calado (knockout).", fontsize=9, fontname="helv", color=(0, 0, 0))
        page.insert_text(pymupdf.Point(35, 225), "Esto genera huecos en blanco en las planchas de color inferiores.", fontsize=8.5, fontname="helv", color=(0, 0, 0))
        page.insert_text(pymupdf.Point(35, 245), "Cualquier descalce de registro en máquina dejará ver el papel blanco.", fontsize=8.5, fontname="helv", color=(0, 0, 0))

    # -----------------------------------------------------------------------
    # RETO 14: Calendario de Sobremesa con Descompensación de Tinteros CIP3
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_calendario_tinteros_descompensados":
        w, h = 595.28, 283.46 # 210 x 100 mm
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        # Mitad izquierda: masa negra densa (cobertura ~90%)
        page.draw_rect(pymupdf.Rect(0, 0, w / 2, h), fill=(0.02, 0.02, 0.02))
        page.insert_text(pymupdf.Point(20, 50), "CALENDARIO 2026", fontsize=18, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(20, 90), "ZONA DE LLAVES 1-8: COBERTURA 92%", fontsize=10, fontname="helv", color=(0.8, 0.8, 0.2))

        # Mitad derecha: completamente blanca (cobertura 0%)
        page.insert_text(pymupdf.Point(w / 2 + 20, 50), "ZONA DE LLAVES 9-16: COBERTURA 0%", fontsize=10, fontname="helv", color=(0.2, 0.2, 0.2))
        page.insert_text(pymupdf.Point(w / 2 + 20, 90), "Desbalance extremo de consumo en el tintero CIP3", fontsize=8.5, fontname="helv", color=(0.5, 0.5, 0.5))

    # -----------------------------------------------------------------------
    # RETO 15: Estuche Packaging con Código de Barras EAN-13 en 4 Tintas
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_packaging_barcode_cmyk":
        w, h = 340.16, 510.24 # 120 x 180 mm
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        page.draw_rect(pymupdf.Rect(0, 0, w, h), fill=(0.95, 0.94, 0.92))
        page.insert_text(pymupdf.Point(30, 60), "CREMA DERMO-REPARADORA BIO", fontsize=14, fontname="helv", color=(0.2, 0.4, 0.3))
        page.insert_text(pymupdf.Point(30, 80), "Con Extracto Puro de Caléndula y Karité", fontsize=8.5, fontname="helv", color=(0.4, 0.5, 0.4))

        # Texto legal que invade zona de seguridad (a 1.2 mm = 3.4 pt del borde)
        page.insert_text(pymupdf.Point(3.4, 150), "Lote: 2026-X9 / Caducidad: 12/2028 / Fabricado en la UE para Laboratorios DermoLab S.L.", fontsize=5.0, fontname="helv", color=(0.1, 0.1, 0.1))

        # Código de barras en 4 tintas
        bx, by = 60.0, 360.0
        bw, bh = 140.0, 60.0
        page.insert_text(pymupdf.Point(bx, by - 10), "Código de Barras Comercial (EAN-13):", fontsize=7.5, fontname="helv", color=(0.2, 0.2, 0.2))

        random.seed(42)
        cur_x = bx
        while cur_x < bx + bw:
            bar_w = random.choice([1.2, 2.4, 3.6])
            page.draw_rect(pymupdf.Rect(cur_x, by, cur_x + bar_w, by + bh), fill=(0.15, 0.10, 0.08))
            cur_x += bar_w + random.choice([1.2, 2.4])

        page.insert_text(pymupdf.Point(bx + 15, by + bh + 12), "8 412345 678905", fontsize=9, fontname="helv", color=(0.15, 0.10, 0.08))

    # -----------------------------------------------------------------------
    # RETO 16: Portada y Pliegos de Revista con Textos en el Medianil/Lomo
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_revista_seguridad_lomo":
        w, h = 595.28, 841.89 # A4
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        page.draw_rect(pymupdf.Rect(0, 0, w, 120), fill=(0.10, 0.25, 0.45))
        page.insert_text(pymupdf.Point(40, 70), "REVISTA TÉCNICA DE FP INDUSTRIAL", fontsize=20, fontname="helv", color=(1, 1, 1))
        page.insert_text(pymupdf.Point(40, 95), "Edición Euskadi 2026 · Nuevas Tecnologías en Artes Gráficas", fontsize=10, fontname="helv", color=(0.8, 0.9, 1))

        # Texto que invade el medianil (a 3 mm del lomo izquierdo)
        page.insert_text(pymupdf.Point(8.5, 200), "NOTA EDITORIAL AL BORDE DEL PLIEGUE (PELIGRO DE PÉRDIDA EN ENCUADERNACIÓN)", fontsize=6.5, fontname="helv", color=(0.8, 0.1, 0.1))
        page.insert_text(pymupdf.Point(40, 240), "La digitalización de los procesos de preimpresión...", fontsize=10, fontname="helv", color=(0.2, 0.2, 0.2))

    # -----------------------------------------------------------------------
    # RETO 17: Etiqueta de Vino con Barniz UVI Calando en vez de Sobreimprimir
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_etiqueta_barniz_calado":
        w, h = 255.12, 368.50 # 90 x 130 mm
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        page.draw_rect(pymupdf.Rect(0, 0, w, h), fill=(0.15, 0.10, 0.12))
        page.insert_text(pymupdf.Point(25, 60), "SEÑORÍO DE ÁLAVA", fontsize=16, fontname="times-bold", color=(0.9, 0.8, 0.4))
        page.insert_text(pymupdf.Point(25, 85), "Gran Reserva 2020 · Rioja Alavesa", fontsize=9, fontname="times-italic", color=(0.7, 0.7, 0.7))

        # Hueco calado para barniz que elimina la tinta inferior
        page.draw_rect(pymupdf.Rect(30, 140, w - 30, 240), fill=(1, 1, 1))
        page.insert_text(pymupdf.Point(40, 180), "ZONA DE BARNIZ UVI EN CALADO", fontsize=8.5, fontname="helv", color=(0.8, 0.1, 0.1))
        page.insert_text(pymupdf.Point(40, 200), "Fallo: Deja hueco blanco al calar en vez de sobreimprimir", fontsize=7.0, fontname="helv", color=(0.3, 0.3, 0.3))

    # -----------------------------------------------------------------------
    # RETO 18: Prospecto Farmacéutico con Código QR en 4 Tintas
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_prospecto_qr_richblack":
        w, h = 396.85, 595.28 # 140 x 210 mm
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        page.insert_text(pymupdf.Point(25, 40), "PARACETAMOL RETARD 1000 mg", fontsize=14, fontname="helv", color=(0, 0, 0))
        page.insert_text(pymupdf.Point(25, 60), "Comprimidos de liberación prolongada EFG", fontsize=8.5, fontname="helv", color=(0.3, 0.3, 0.3))

        # QR denso en Rich Black
        qrx, qry = 30.0, 100.0
        qrs = 100.0
        page.draw_rect(pymupdf.Rect(qrx, qry, qrx + qrs, qry + qrs), fill=(1, 1, 1), color=(0.04, 0.03, 0.04), width=1)
        # Módulos QR en 4 tintas
        for row in range(10):
            for col in range(10):
                if (row + col) % 2 == 0 or (row in (0, 9) and col in (0, 9)):
                    page.draw_rect(
                        pymupdf.Rect(qrx + col * 10, qry + row * 10, qrx + (col + 1) * 10, qry + (row + 1) * 10),
                        fill=(0.04, 0.03, 0.04) # Rich Black
                    )
        page.insert_text(pymupdf.Point(qrx, qry + qrs + 15), "QR médico en Rich Black (falla en escáner por empastado)", fontsize=7, fontname="helv", color=(0.8, 0.1, 0.1))

    # -----------------------------------------------------------------------
    # RETO 19: Pliego de Imposición SRA3 sin Calles de Corte ni Marcas de Taller
    # -----------------------------------------------------------------------
    elif scenario_id == "reto_imposicion_sra3_descuadre":
        w, h = 1275.59, 907.09 # SRA3 (450 x 320 mm)
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        # Montaje de 8 poses pegadas con gutter 0 mm
        cw, ch = 240.94, 155.91
        start_x, start_y = 150.0, 150.0
        for r in range(2):
            for c in range(4):
                px = start_x + c * cw
                py = start_y + r * ch
                page.draw_rect(pymupdf.Rect(px, py, px + cw, py + ch), fill=(0.15, 0.25, 0.40), color=(1, 1, 1), width=0.5)
                page.insert_text(pymupdf.Point(px + 20, py + 40), f"TARJETA #{r*4 + c + 1}", fontsize=11, fontname="helv", color=(1, 1, 1))
                page.insert_text(pymupdf.Point(px + 20, py + 70), "Gutter 0 mm (Sin calle de corte)", fontsize=7.5, fontname="helv", color=(0.9, 0.8, 0.2))

        page.insert_text(pymupdf.Point(150, 520), "MONTAJE SRA3 MANUAL: Sin marcas de corte, sin cruces de registro, sin tira de control.", fontsize=12, fontname="helv", color=(0.8, 0.1, 0.1))

    # -----------------------------------------------------------------------
    # RETO 20: Envase Alimentario con Masa de Tinta y Barniz en la Solapa de Pegado
    # -----------------------------------------------------------------------
    else: # reto_caja_pegado_barnizado u otros
        w, h = 566.93, 793.70 # 200 x 280 mm
        page = doc.new_page(width=w, height=h)
        page.set_trimbox(page.rect)

        # Solapa de pegado (15 mm = 42.5 pt)
        flap_w = 42.5
        page.draw_rect(pymupdf.Rect(0, 0, flap_w, h), fill=(0.02, 0.02, 0.02))
        page.insert_text(pymupdf.Point(6, 200), "SOLAPA DE PEGADO", fontsize=7.0, fontname="helv", color=(1, 1, 1), rotate=90)
        page.insert_text(pymupdf.Point(22, 200), "ERROR: Tinta y barniz en área de cola", fontsize=6.5, fontname="helv", color=(1, 0.4, 0.4), rotate=90)

        # Cuerpo del envase
        page.draw_rect(pymupdf.Rect(flap_w, 0, w, h), fill=(0.94, 0.92, 0.88))
        page.insert_text(pymupdf.Point(flap_w + 30, 80), "COPOS DE AVENA INTEGRAL BIO", fontsize=18, fontname="helv", color=(0.2, 0.4, 0.2))
        page.insert_text(pymupdf.Point(flap_w + 30, 110), "Envase de Cartoncillo 350 g/m²", fontsize=10, fontname="helv", color=(0.5, 0.5, 0.5))

    doc.save(str(output_path))
    doc.close()

    # Si el reto involucra tintas directas especiales (Reto 9 o Reto 17), inyectarlas con pikepdf
    if scenario_id == "reto_catalogo_pantone_excesivo":
        try:
            pdoc = pikepdf.open(str(output_path), allow_overwriting_input=True)
            p0 = pdoc.pages[0]
            if '/Resources' not in p0:
                p0['/Resources'] = pikepdf.Dictionary()
            if '/ColorSpace' not in p0['/Resources']:
                p0['/Resources']['/ColorSpace'] = pikepdf.Dictionary()
            cs = p0['/Resources']['/ColorSpace']
            spot_list = ['PANTONE 186 C', 'PANTONE 286 C', 'PANTONE 368 C', 'PANTONE 123 C', 'PANTONE Reflex Blue C']
            for i, name in enumerate(spot_list):
                cs[f'/CS_SPOT_{i}'] = pikepdf.Array([
                    pikepdf.Name('/Separation'),
                    pikepdf.Name(f'/{name}'),
                    pikepdf.Name('/DeviceCMYK')
                ])
            pdoc.save(str(output_path))
            pdoc.close()
        except Exception as e:
            print(f"[generate_scenario_pdf] Aviso inyectando spot colors: {e}")

    elif scenario_id == "reto_etiqueta_barniz_calado":
        try:
            pdoc = pikepdf.open(str(output_path), allow_overwriting_input=True)
            p0 = pdoc.pages[0]
            if '/Resources' not in p0:
                p0['/Resources'] = pikepdf.Dictionary()
            if '/ColorSpace' not in p0['/Resources']:
                p0['/Resources']['/ColorSpace'] = pikepdf.Dictionary()
            cs = p0['/Resources']['/ColorSpace']
            cs['/CS_VARNISH'] = pikepdf.Array([
                pikepdf.Name('/Separation'),
                pikepdf.Name('/Barniz_UVI_Brillo'),
                pikepdf.Name('/DeviceCMYK')
            ])
            pdoc.save(str(output_path))
            pdoc.close()
        except Exception as e:
            print(f"[generate_scenario_pdf] Aviso inyectando barniz spot: {e}")

    return output_path

# ---------------------------------------------------------------------------
# SIMULADOR VISUAL DE CONSECUENCIAS FÍSICAS EN TALLER
# ---------------------------------------------------------------------------

def simulate_register_misalignment(shift_px: int = 4) -> io.BytesIO:
    """
    Simula visualmente el descalce de registro en planchas CMYK.
    Cuando un texto tipográfico fino (6-8 pt) o un logotipo se diseña en 4 tintas
    (Rich Black) en vez de 100% K puro, cualquier vibración o dilatación del papel
    en la máquina offset provoca halos visibles de cian, magenta y amarillo.
    """
    w, h = 560, 200
    base = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(base)

    # Dibuja fondo cuadriculado suave de referencia
    for x in range(0, w, 20):
        draw.line([(x, 0), (x, h)], fill=(245, 245, 248))
    for y in range(0, h, 20):
        draw.line([(0, y), (w, y)], fill=(245, 245, 248))

    # Creamos capas separadas para C, M, Y, K
    def render_text_layer(color, offset):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # Línea de prueba fina
        d.line([(40 + offset[0], 50 + offset[1]), (520 + offset[0], 50 + offset[1])], fill=color, width=2)
        # Texto de muestra de simulación
        try:
            # Usar default font o básico
            font_title = ImageFont.load_default()
        except Exception:
            font_title = None

        d.text((40 + offset[0], 70 + offset[1]), "TEXTO EN 4 TINTAS (RICH BLACK) - VIBRACIÓN DE REGISTRO OFFSET", fill=color)
        d.text((40 + offset[0], 100 + offset[1]), "C=75%  M=68%  Y=67%  K=90%  --> Descalce de planchas CTP en tirada", fill=color)
        d.text((40 + offset[0], 130 + offset[1]), "Resultado en papel: Texto borroso con halo multicolor no apto para lectura", fill=color)
        return img

    s = max(1, min(shift_px, 12))
    # Capa Cyan (desfasada a la izquierda)
    layer_c = render_text_layer((0, 160, 230, 210), (-s, 0))
    # Capa Magenta (desfasada hacia arriba-derecha)
    layer_m = render_text_layer((230, 0, 125, 210), (s, -int(s * 0.7)))
    # Capa Yellow (desfasada hacia abajo)
    layer_y = render_text_layer((255, 220, 0, 190), (0, s))
    # Capa Black (eje central)
    layer_k = render_text_layer((30, 30, 30, 240), (0, 0))

    # Fusionar capas
    base.alpha_composite(layer_c)
    base.alpha_composite(layer_m)
    base.alpha_composite(layer_y)
    base.alpha_composite(layer_k)

    # Anotación explicativa en la imagen
    draw_final = ImageDraw.Draw(base)
    draw_final.rectangle([(0, h - 28), (w, h)], fill=(20, 25, 35))
    draw_final.text((15, h - 20), f"SIMULACIÓN DIDÁCTICA FP: Desfase de planchas a +{s * 0.05:.2f} mm | Solución: Usar 100% K Puro", fill=(255, 220, 100))

    buf = io.BytesIO()
    base.convert("RGB").save(buf, format="PNG")
    buf.seek(0)
    return buf


def simulate_setoff_stain(tac_percent: int = 360) -> io.BytesIO:
    """
    Simula visualmente el efecto físico de "Repintado / Maculado en Pila" (Set-off).
    Si la cobertura total de tinta (TAC) excede el 300%-320%, el papel estucado no puede
    absorber el vehículo oleoso ni fijar los pigmentos a tiempo. En la pila de salida,
    la presión de las hojas superiores transfiere tinta fresca al dorso de la siguiente hoja.
    """
    w, h = 560, 220
    base = Image.new("RGB", (w, h), (250, 248, 245))
    draw = ImageDraw.Draw(base)

    # Lado Izquierdo: Hoja impresa original (anverso)
    draw.rectangle([(20, 20), (260, 180)], fill=(15, 12, 10), outline=(180, 180, 180), width=1)
    draw.text((35, 35), "ANVERSO (CARA)", fill=(240, 240, 240))
    draw.text((35, 60), f"Masa de color oscuro con TAC={tac_percent}%", fill=(200, 200, 200))
    draw.text((35, 80), "(Capa de tinta excesivamente gruesa)", fill=(180, 180, 180))

    # Lado Derecho: Reverso de la siguiente hoja en la pila (manchada por repintado)
    draw.rectangle([(300, 20), (540, 180)], fill=(255, 255, 255), outline=(180, 180, 180), width=1)
    draw.text((315, 35), "REVERSO (DORSO)", fill=(40, 40, 40))
    draw.text((315, 60), "Página posterior en blanco afectada", fill=(100, 100, 100))

    # Mancha de repintado en el dorso (proporcional al exceso de TAC)
    excess = max(0, tac_percent - 300)
    alpha = min(220, int(excess * 3.5))

    stain_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(stain_layer)

    if excess > 0:
        # Dibujar manchas irregulares simulando contacto de presión en pila
        for i in range(12):
            cx = random.randint(340, 500)
            cy = random.randint(80, 160)
            r = random.randint(15, 45)
            sdraw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(30, 25, 20, int(alpha * 0.7)))

    # Aplicar desenfoque para dar aspecto oleoso de transferencia de tinta
    stain_layer = stain_layer.filter(ImageFilter.GaussianBlur(radius=6))

    base_rgba = base.convert("RGBA")
    base_rgba.alpha_composite(stain_layer)

    final_img = base_rgba.convert("RGB")
    fdraw = ImageDraw.Draw(final_img)

    # Pie explicativo
    fdraw.rectangle([(0, h - 28), (w, h)], fill=(140, 30, 30) if excess > 0 else (20, 120, 50))
    msg = f"EFECTO EN TALLER: Repintado Severo en Pila (TAC={tac_percent}% > 300%) | Rechazo de Tirada" if excess > 0 else f"TAC CORRECTO: {tac_percent}% dentro de norma ISO 12647-2 (Secado óptimo)"
    fdraw.text((15, h - 20), msg, fill=(255, 255, 255))

    buf = io.BytesIO()
    final_img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def simulate_guillotine_shift(has_bleed: bool = False, cut_error_mm: float = 1.5) -> io.BytesIO:
    """
    Simula visualmente el desvío de la guillotina de corte.
    Si un archivo tiene fondo al corte pero NO dispone de 3 mm de sangrado (Bleed),
    cualquier variación física en el pisón o la cuchilla de la guillotina dejará
    un antiestético "filete blanco" en el contorno del impreso final.
    """
    w, h = 560, 220
    base = Image.new("RGB", (w, h), (240, 242, 245))
    draw = ImageDraw.Draw(base)

    # Área nominal del trabajo
    trim_x1, trim_y1 = 120, 40
    trim_x2, trim_y2 = 440, 160

    # Si tiene sangre, el fondo se extiende 30px (equiv 3mm)
    bleed_px = 25 if has_bleed else 0
    bg_x1, bg_y1 = trim_x1 - bleed_px, trim_y1 - bleed_px
    bg_x2, bg_y2 = trim_x2 + bleed_px, trim_y2 + bleed_px

    # Dibujar fondo impreso (azul intenso)
    draw.rectangle([(bg_x1, bg_y1), (bg_x2, bg_y2)], fill=(20, 60, 140))
    draw.text((bg_x1 + 15, bg_y1 + 15), "FONDO IMPRESO", fill=(180, 200, 255))

    # Línea nominal de TrimBox (Corte teórico)
    draw.rectangle([(trim_x1, trim_y1), (trim_x2, trim_y2)], outline=(0, 255, 120), width=2)
    draw.text((trim_x1 + 10, trim_y1 + 35), "Línea Teórica de Corte (TrimBox)", fill=(0, 255, 120))

    # Cuchilla de guillotina desfasada (error de corte)
    shift_px = int(cut_error_mm * 12)
    blade_x1 = trim_x1 + shift_px
    blade_y1 = trim_y1
    blade_x2 = trim_x2 + shift_px
    blade_y2 = trim_y2

    # Línea de la cuchilla real
    draw.rectangle([(blade_x1, blade_y1), (blade_x2, blade_y2)], outline=(255, 50, 50), width=2)

    # Si no tiene sangre, entre el borde del fondo (bg_x1) y la cuchilla (blade_x1) aparece papel blanco
    if not has_bleed and shift_px > 0:
        # Filete blanco visible
        draw.rectangle([(bg_x1, blade_y1), (blade_x1, blade_y2)], fill=(255, 255, 255), outline=(255, 0, 0), width=1)
        draw.text((blade_x1 - 100, blade_y1 + 55), "FILETE BLANCO!", fill=(220, 20, 20))

    # Pie informativo
    draw.rectangle([(0, h - 28), (w, h)], fill=(160, 30, 30) if not has_bleed else (20, 120, 50))
    status_text = f"SIN SANGRE: Filete blanco visible de {cut_error_mm} mm | Solución: Añadir +3 mm de sangrado" if not has_bleed else f"CON SANGRE (+3 mm): Corte limpio y perfecto incluso con oscilación de cuchilla de {cut_error_mm} mm"
    draw.text((15, h - 20), status_text, fill=(255, 255, 255))

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    buf.seek(0)
    return buf


def simulate_ctp_hairline(stroke_pt: float = 0.08) -> io.BytesIO:
    """
    Simula visualmente la pérdida o debilitamiento de líneas finas (Hairlines)
    en el láser del insolador térmico CTP (Computer to Plate) a 2400 DPI.
    Las líneas < 0.25 pt no reciben suficiente energía de exposición o se lavan
    en la procesadora química, desapareciendo en la plancha de aluminio.
    """
    w, h = 560, 200
    base = Image.new("RGB", (w, h), (245, 246, 248))
    draw = ImageDraw.Draw(base)

    # Panel izquierdo: Diseño en pantalla (Vectorial)
    draw.rectangle([(20, 20), (260, 160)], fill=(255, 255, 255), outline=(200, 200, 200), width=1)
    draw.text((30, 30), "EN PANTALLA (InDesign / Illustrator)", fill=(40, 40, 40))
    draw.text((30, 50), f"Línea vectorial de {stroke_pt} pt", fill=(100, 100, 100))
    # En pantalla se ve una línea delgada nítida
    draw.line([(40, 90), (240, 90)], fill=(0, 0, 0), width=1)
    draw.line([(40, 110), (240, 110)], fill=(0, 0, 0), width=1)
    draw.text((30, 130), "En monitor siempre parece visible", fill=(120, 120, 120))

    # Panel derecho: Plancha CTP / Papel impreso
    draw.rectangle([(300, 20), (540, 160)], fill=(230, 235, 240), outline=(200, 200, 200), width=1)
    draw.text((310, 30), "EN PLANCHA CTP / PAPEL IMPRESO", fill=(40, 40, 40))

    if stroke_pt < 0.25:
        draw.text((310, 50), f"Láser CTP 2400 DPI (Pérdida de emulsión)", fill=(180, 40, 40))
        # Línea quebrada o ausente
        # Dibuja puntos dispersos simulando rotura
        for x in range(320, 520, 8):
            if random.random() > 0.65:
                draw.point((x, 90), fill=(100, 100, 100))
                draw.point((x + 1, 90), fill=(140, 140, 140))
        draw.text((310, 130), "¡TRAZO ROTO O INEXISTENTE EN TIRADA!", fill=(180, 20, 20))
    else:
        draw.text((310, 50), f"Láser CTP 2400 DPI (Fijación correcta)", fill=(20, 120, 50))
        draw.line([(320, 90), (520, 90)], fill=(20, 20, 20), width=2)
        draw.text((310, 130), "Trazo sólido y continuo asegurado", fill=(20, 120, 50))

    # Pie informativo
    draw.rectangle([(0, h - 28), (w, h)], fill=(160, 30, 30) if stroke_pt < 0.25 else (20, 120, 50))
    msg = f"PELIGRO CTP: Grosor {stroke_pt} pt < 0.25 pt mínimo de norma | Solución automática: Corregir a 0.30 pt" if stroke_pt < 0.25 else f"TRAZO CORRECTO: {stroke_pt} pt ≥ 0.25 pt (Fijación garantizada en plancha)"
    draw.text((15, h - 20), msg, fill=(255, 255, 255))

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ---------------------------------------------------------------------------
# MOTOR DE AUTOEVALUACIÓN / QUIZ TÉCNICO FP
# ---------------------------------------------------------------------------

QUESTIONS_FP = [
    {
        "id": "q_rich_black",
        "question": "¿Por qué motivo NO se debe utilizar Negro Enriquecido (Rich Black / 4 tintas) en tipografías menudas (≤ 8 pt)?",
        "options": [
            "Porque consume más memoria RAM al rasterizar en el RIP.",
            "Porque cualquier desfase microscópico de registro entre planchas provocará halos de color y texto borroso e ilegible.",
            "Porque la tinta negra no se mezcla bien químicamente con el amarillo.",
            "Porque la norma ISO prohíbe imprimir textos de menos de 10 pt."
        ],
        "correct_index": 1,
        "explanation": "En máquina offset o digital de hojas, un texto fino en 4 tintas requiere que las 4 planchas coincidan con precisión de micrómetros. Una variación mínima genera desenfoque y halos cromáticos. Los textos menudos deben ir siempre en 100% K puro con sobreimpresión.",
        "iso_ref": "ISO 12647-2 / Buenas Prácticas Ghent Workgroup"
    },
    {
        "id": "q_bleed_margin",
        "question": "¿Cuál es la función principal del Sangrado exterior de 3 mm en un documento gráfico destinado a corte?",
        "options": [
            "Dejar espacio suficiente para colocar la firma del diseñador gráfico.",
            "Asegurar que los colores y fotos de fondo se extiendan más allá de la línea de corte para evitar filetes blancos si la guillotina oscila.",
            "Permitir que la encuadernadora aplique la cola caliente en el lomo.",
            "Servir como margen para que el maquinista apoye las pinzas de arrastre."
        ],
        "correct_index": 1,
        "explanation": "La guillotina de taller corta cientos o miles de hojas apiladas con una tolerancia mecánica habitual de ±0.5 a 1 mm. Si los fondos terminan en la línea exacta de corte (TrimBox), cualquier desviación deja visible el blanco del papel.",
        "iso_ref": "ISO 12647-2 / Especificaciones ECI"
    },
    {
        "id": "q_tac_limit",
        "question": "¿Qué consecuencia física grave provoca en taller superar el límite de Cobertura Total de Tinta (TAC > 300%-320%)?",
        "options": [
            "La plancha CTP se quema debido al exceso de calor del láser térmico.",
            "El papel estucado no puede absorber tanta tinta, provocando repintado (maculado) en la pila de salida y bloqueando el secado.",
            "Las letras en tipografía palo seco cambian automáticamente a tipografía con serifa.",
            "El archivo PDF aumenta 10 veces su tamaño en disco."
        ],
        "correct_index": 1,
        "explanation": "El exceso de tinta satura la superficie del papel, impidiendo el anclaje y secado por oxidación/absorción. Al caer las hojas en la pila de salida, la cara entintada mancha el dorso de la hoja superior (repintado), inutilizando la tirada completa.",
        "iso_ref": "ISO 12647-2 (Límite TAC 300% para estucado FOGRA39/51)"
    },
    {
        "id": "q_hairline_ctp",
        "question": "¿Por qué las líneas de espesor inferior a 0.25 pt (Hairlines) son un problema crítico en preimpresión?",
        "options": [
            "Porque la tinta offset se expande tanto que se convierten en líneas de 5 mm de ancho.",
            "Porque el láser del CTP no llega a polimerizar la capa fotosensible de la plancha, perdiéndose el trazo durante el tiraje.",
            "Porque consumen demasiada tinta en los rodillos dadores de la batería.",
            "Porque están reservadas exclusivamente a los billetes de curso legal."
        ],
        "correct_index": 1,
        "explanation": "A resoluciones de insolación estándar (2400 DPI), un trazo de 0.05 pt equivale a menos de un píxel de láser. Durante el revelado y tirada, la fricción del agua de mojado y la mantilla de caucho arranca la emulsión débil, rompiendo la línea.",
        "iso_ref": "Especificaciones Técnicas CTP & Ghent Output Suite"
    },
    {
        "id": "q_barcode_k",
        "question": "¿Por qué los códigos de barras comerciales (EAN-13, QR) deben imprimirse en 100% K y no en cuatricromía?",
        "options": [
            "Porque los lectores ópticos e industriales usan láseres rojos que exigen máximo contraste fotométrico y nitidez sin sangrado de registro.",
            "Porque el consorcio GS1 cobra un canon extra si se imprime en colores.",
            "Porque los supermercados no disponen de pantallas a color en caja.",
            "Porque las 4 tintas pesan demasiado en el embalaje del producto."
        ],
        "correct_index": 0,
        "explanation": "El lector láser comercial emite luz roja y detecta la absorción del negro. Si el código está compuesto en 4 tintas, cualquier descalce de registro o ganancia de punto borronea las barras y los huecos (zona muda / quiet zone), provocando fallos de lectura en caja.",
        "iso_ref": "ISO/IEC 15420 / Estándar Internacional GS1"
    }
]

def evaluate_student_quiz(answers: Dict[str, int]) -> Dict[str, Any]:
    """
    Evalúa las respuestas del alumno, calcula la calificación de 0 a 10,
    y genera el diagnóstico pedagógico con referencias a normas de Artes Gráficas.
    """
    total = len(QUESTIONS_FP)
    correct_count = 0
    feedback_items = []

    for q in QUESTIONS_FP:
        qid = q["id"]
        chosen = answers.get(qid, -1)
        is_ok = (chosen == q["correct_index"])
        if is_ok:
            correct_count += 1

        feedback_items.append({
            "question_id": qid,
            "question": q["question"],
            "chosen_index": chosen,
            "correct_index": q["correct_index"],
            "is_correct": is_ok,
            "explanation": q["explanation"],
            "iso_ref": q["iso_ref"]
        })

    score = round((correct_count / total) * 10, 1)

    if score >= 9.0:
        level = "Sobresaliente (Competencia Técnica Avanzada en Preimpresión)"
    elif score >= 7.0:
        level = "Notable (Sólido Criterio de Taller y Control de Calidad)"
    elif score >= 5.0:
        level = "Aprobado (Conocimientos Básicos de Taller Adquiridos)"
    else:
        level = "Insuficiente (Requiere Repaso de Incidencias Físicas y Normas ISO)"

    return {
        "score": score,
        "total_questions": total,
        "correct_answers": correct_count,
        "level": level,
        "evaluated_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "feedback": feedback_items
    }

# ---------------------------------------------------------------------------
# GENERADOR DE HOJA DE PRÁCTICA Y EVALUACIÓN DEL ALUMNO (PDF A4)
# ---------------------------------------------------------------------------

def generate_student_worksheet_pdf(
    student_name: str,
    school_name: str,
    scenario_info: Dict[str, Any],
    quiz_results: Optional[Dict[str, Any]],
    output_pdf_path: Path,
    assets_dir: Path
) -> Path:
    """
    Genera la Hoja de Práctica Oficial de Taller en PDF A4 con sellos de
    Salesianos Urnieta, CIFP Mendizabala LHII y Gobierno Vasco (Hezkuntza Saila).
    """
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    # 1. Cabecera Corporativa Institucional
    navy = (31 / 255, 38 / 255, 44 / 255)
    page.draw_rect(pymupdf.Rect(0, 0, PAGE_W, HEADER_H), fill=navy)

    imago_path = assets_dir / "Logo-intelliprint-imago.jpg"
    if imago_path.exists():
        page.insert_image(pymupdf.Rect(26, 12, 74, 58), filename=str(imago_path), keep_proportion=True)
        text_x = 84
    else:
        text_x = 35

    page.insert_text(
        pymupdf.Point(text_x, 32),
        "INTELLIPRINT · FICHA DE PRÁCTICA Y EVALUACIÓN FP",
        fontsize=11.0,
        color=(1, 1, 1),
        fontname="helv",
    )
    page.insert_text(
        pymupdf.Point(text_x, 48),
        "Simulador Didáctico de Preimpresión y Consecuencias en Taller Gráfico",
        fontsize=7.8,
        color=(0.75, 0.82, 0.90),
        fontname="helv",
    )

    # Sellos institucionales de los centros
    p_sales = assets_dir / "logo-salesianos.png"
    p_mendi = assets_dir / "logo-mendizabala.png"
    p_edu = assets_dir / "logo-dept-educacion-1.png"

    if p_sales.exists() and p_mendi.exists() and p_edu.exists():
        capsule = pymupdf.Rect(325, 12, 567, 58)
        page.draw_rect(capsule, fill=(1, 1, 1), radius=0.08)
        page.insert_image(pymupdf.Rect(332, 16, 400, 54), filename=str(p_sales), keep_proportion=True)
        page.draw_line(pymupdf.Point(404, 18), pymupdf.Point(404, 52), color=(0.88, 0.88, 0.88), width=0.6)
        page.insert_image(pymupdf.Rect(408, 16, 478, 54), filename=str(p_mendi), keep_proportion=True)
        page.draw_line(pymupdf.Point(482, 18), pymupdf.Point(482, 52), color=(0.88, 0.88, 0.88), width=0.6)
        page.insert_image(pymupdf.Rect(486, 16, 560, 54), filename=str(p_edu), keep_proportion=True)

    # 2. Bloque de Datos del Alumno y Práctica
    y = 86.0
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, PAGE_W - MARGIN_X, y + 54), fill=(0.96, 0.97, 0.99), color=(0.82, 0.86, 0.90), width=0.6)

    alumno = student_name if student_name.strip() else "Alumno/a de Artes Gráficas"
    centro = school_name if school_name.strip() else "CPIFP Salesianos Urnieta / CIFP Mendizabala LHII"

    page.insert_text(pymupdf.Point(MARGIN_X + 12, y + 18), f"Estudiante: {alumno}", fontsize=9.0, fontname="helv", color=(0.15, 0.20, 0.25))
    page.insert_text(pymupdf.Point(MARGIN_X + 12, y + 33), f"Centro Educativo: {centro}", fontsize=8.2, fontname="helv", color=(0.35, 0.40, 0.48))
    page.insert_text(pymupdf.Point(MARGIN_X + 12, y + 46), f"Módulo / Nivel: {scenario_info.get('module', 'Preimpresión Digital')} · {scenario_info.get('level', 'FP')}", fontsize=8.0, fontname="helv", color=(0.35, 0.40, 0.48))

    score_val = quiz_results.get("score", 0.0) if quiz_results else None
    if score_val is not None:
        score_box = pymupdf.Rect(PAGE_W - MARGIN_X - 110, y + 8, PAGE_W - MARGIN_X - 12, y + 46)
        color_score = (0.10, 0.60, 0.35) if score_val >= 5.0 else (0.85, 0.20, 0.20)
        page.draw_rect(score_box, fill=(1, 1, 1), color=color_score, width=1.0)
        page.insert_text(pymupdf.Point(score_box.x0 + 10, score_box.y0 + 18), f"CALIFICACIÓN FP", fontsize=7.0, fontname="helv", color=color_score)
        page.insert_text(pymupdf.Point(score_box.x0 + 18, score_box.y0 + 34), f"{score_val:.1f} / 10", fontsize=13.0, fontname="helv", color=color_score)

    # 3. Reto de Taller Analizado
    y += 66.0
    page.insert_text(pymupdf.Point(MARGIN_X, y), "1. CASO PRÁCTICO ASIGNADO", fontsize=10.0, fontname="helv", color=navy)
    page.draw_line(pymupdf.Point(MARGIN_X, y + 3), pymupdf.Point(PAGE_W - MARGIN_X, y + 3), color=(0.28, 0.25, 0.75), width=1.2)

    y += 16.0
    page.insert_text(pymupdf.Point(MARGIN_X, y), f"Título del Reto: {scenario_info.get('title', 'Caso de Taller')}", fontsize=9.0, fontname="helv", color=(0.15, 0.2, 0.3))
    page.insert_text(pymupdf.Point(MARGIN_X, y + 13), f"Tipo de Trabajo: {scenario_info.get('doc_type', 'Documento Comercial')} · Norma de Referencia: {scenario_info.get('iso_norm', 'ISO 12647-2')}", fontsize=8.0, fontname="helv", color=(0.4, 0.45, 0.5))

    y += 26.0
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, PAGE_W - MARGIN_X, y + 38), fill=(0.98, 0.98, 0.99), color=(0.88, 0.90, 0.92), width=0.5)
    page.insert_text(pymupdf.Point(MARGIN_X + 10, y + 14), "Descripción del trabajo entregado por el cliente:", fontsize=7.5, fontname="helv", color=(0.3, 0.35, 0.4))
    desc = scenario_info.get("description", "")
    page.insert_textbox(pymupdf.Rect(MARGIN_X + 10, y + 16, PAGE_W - MARGIN_X - 10, y + 36), desc, fontsize=7.8, fontname="helv", color=(0.15, 0.2, 0.25))

    # 4. Errores Críticos que el Alumno Debe Diagnosticar
    y += 50.0
    page.insert_text(pymupdf.Point(MARGIN_X, y), "2. DIAGNÓSTICO TÉCNICO Y CONSECUENCIAS FÍSICAS EN MÁQUINA", fontsize=10.0, fontname="helv", color=navy)
    page.draw_line(pymupdf.Point(MARGIN_X, y + 3), pymupdf.Point(PAGE_W - MARGIN_X, y + 3), color=(0.28, 0.25, 0.75), width=1.2)

    y += 14.0
    errors = scenario_info.get("target_errors", [])
    for idx, err in enumerate(errors, 1):
        page.draw_circle(pymupdf.Point(MARGIN_X + 6, y + 5), 2.5, fill=(0.85, 0.20, 0.20))
        page.insert_text(pymupdf.Point(MARGIN_X + 16, y + 8), f"Incidencia {idx}: {err}", fontsize=8.2, fontname="helv", color=(0.2, 0.2, 0.2))
        y += 16.0

    # 5. Aprendizajes Clave y Procedimiento de Corrección
    y += 8.0
    page.insert_text(pymupdf.Point(MARGIN_X, y), "3. PROCEDIMIENTO DE CORRECCIÓN EN PREIMPRESIÓN (InDesign / Acrobat / IntelliPrint)", fontsize=10.0, fontname="helv", color=navy)
    page.draw_line(pymupdf.Point(MARGIN_X, y + 3), pymupdf.Point(PAGE_W - MARGIN_X, y + 3), color=(0.28, 0.25, 0.75), width=1.2)

    y += 14.0
    goals = scenario_info.get("learning_goals", [])
    for idx, goal in enumerate(goals, 1):
        page.draw_circle(pymupdf.Point(MARGIN_X + 6, y + 5), 2.5, fill=(0.10, 0.60, 0.35))
        page.insert_text(pymupdf.Point(MARGIN_X + 16, y + 8), f"Paso {idx}: {goal}", fontsize=8.2, fontname="helv", color=(0.2, 0.2, 0.2))
        y += 16.0

    # 6. Rúbrica y Resultados del Cuestionario
    if quiz_results:
        y += 10.0
        page.insert_text(pymupdf.Point(MARGIN_X, y), "4. RESULTADOS DE LA EVALUACIÓN TEÓRICO-PRÁCTICA", fontsize=10.0, fontname="helv", color=navy)
        page.draw_line(pymupdf.Point(MARGIN_X, y + 3), pymupdf.Point(PAGE_W - MARGIN_X, y + 3), color=(0.28, 0.25, 0.75), width=1.2)

        y += 16.0
        page.insert_text(
            pymupdf.Point(MARGIN_X, y),
            f"Nivel alcanzado: {quiz_results.get('level', '')} ({quiz_results.get('correct_answers', 0)} / {quiz_results.get('total_questions', 0)} respuestas acertadas)",
            fontsize=8.5,
            fontname="helv",
            color=(0.15, 0.2, 0.3)
        )
        y += 14.0

        for fb in quiz_results.get("feedback", [])[:4]: # Mostrar hasta 4 ítems
            icon_color = (0.10, 0.60, 0.35) if fb["is_correct"] else (0.85, 0.20, 0.20)
            mark = "[ACIERTO]" if fb["is_correct"] else "[REVISAR]"
            page.insert_text(pymupdf.Point(MARGIN_X + 8, y), f"{mark} {fb['question'][:75]}...", fontsize=7.2, fontname="helv", color=icon_color)
            y += 10.0
            page.insert_text(pymupdf.Point(MARGIN_X + 24, y), f"Fundamento técnico: {fb['explanation'][:100]}...", fontsize=6.8, fontname="helv", color=(0.4, 0.45, 0.5))
            y += 13.0

    # 7. Firma Docente y Validación
    y = 740.0
    box_firma_w = (CONTENT_W - 30) / 2
    # Caja Profesor
    page.draw_rect(pymupdf.Rect(MARGIN_X, y, MARGIN_X + box_firma_w, y + 55), color=(0.82, 0.86, 0.90), width=0.6)
    page.insert_text(pymupdf.Point(MARGIN_X + 10, y + 15), "Vº Bº PROFESOR / EVALUADOR:", fontsize=7.2, fontname="helv", color=(0.3, 0.35, 0.4))
    page.insert_text(pymupdf.Point(MARGIN_X + 10, y + 46), "Firma y Sello del Departamento", fontsize=6.8, fontname="helv", color=(0.6, 0.65, 0.7))

    # Caja Alumno
    page.draw_rect(pymupdf.Rect(MARGIN_X + box_firma_w + 30, y, PAGE_W - MARGIN_X, y + 55), color=(0.82, 0.86, 0.90), width=0.6)
    page.insert_text(pymupdf.Point(MARGIN_X + box_firma_w + 40, y + 15), "CONFORMIDAD DEL ALUMNO/A:", fontsize=7.2, fontname="helv", color=(0.3, 0.35, 0.4))
    page.insert_text(pymupdf.Point(MARGIN_X + box_firma_w + 40, y + 46), "Fecha y Firma del Estudiante", fontsize=6.8, fontname="helv", color=(0.6, 0.65, 0.7))

    # Pie institucional
    page.draw_line(pymupdf.Point(MARGIN_X, FOOTER_Y), pymupdf.Point(PAGE_W - MARGIN_X, FOOTER_Y), color=(0.82, 0.86, 0.90), width=0.5)
    page.insert_text(
        pymupdf.Point(MARGIN_X, FOOTER_Y + 12),
        "IntelliPrint Didactic Engine · CPIFP Salesianos Urnieta LHIPI / CIFP Mendizabala LHII · Hezkuntza Saila (Gobierno Vasco)",
        fontsize=7.0,
        fontname="helv",
        color=(0.35, 0.40, 0.48),
    )

    doc.save(str(output_pdf_path))
    doc.close()
    return output_pdf_path

