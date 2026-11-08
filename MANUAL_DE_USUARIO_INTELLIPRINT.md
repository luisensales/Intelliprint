# MANUAL DE USUARIO Y GUÍA DE OPERACIÓN TÉCNICA
# INTELLIPRINT PREFLIGHT & TALLER DIGITAL

---

```
========================================================================================
                              INTELLIPRINT v1.2.0
               SISTEMA DE PREFLIGHT, NORMALIZACIÓN E IMPOSICIÓN
                 PARA ARTES GRÁFICAS Y FORMACIÓN PROFESIONAL
========================================================================================
  Centros Desarrolladores:
    • CPIFP Salesianos Urnieta LHIPI (Gipuzkoa)
    • CIFP Mendizabala LHII (Álava)
  Proyecto de Innovación Aplicada y Transferencia del Conocimiento
  Departamento de Educación · Eusko Jaurlaritza / Gobierno Vasco
========================================================================================
```

---

## ÍNDICE GENERAL

1. [¿QUÉ ES INTELLIPRINT?](#1-qué-es-intelliprint)
   - 1.1. Misión y Filosofía de Taller Gráfico
   - 1.2. Objetivos de Producción y Formación Profesional
   - 1.3. Arquitectura del Sistema
2. [PRIMEROS PASOS Y REQUISITOS](#2-primeros-pasos-y-requisitos)
   - 2.1. Acceso a la Plataforma Web
   - 2.2. Requisitos de Archivo (Formatos Admitidos)
   - 2.3. Estructura de la Interfaz Principal
3. [CONFIGURACIÓN DEL ANÁLISIS DE ENTRADA](#3-configuración-del-análisis-de-entrada)
   - 3.1. Carga de Archivos (Arrastrar y Soltar / Selección)
   - 3.2. Inspección Rápida Preliminar
   - 3.3. Selección de Perfiles de Verificación (Preflight Profiles)
   - 3.4. Gestión de Espacios de Color y Perfiles ICC (Output Intent)
4. [EL INFORME DE VERIFICACIÓN (PREFLIGHT REPORT)](#4-el-informe-de-verificación-preflight-report)
   - 4.1. Semáforo de Producción y Calificación Global
   - 4.2. Pestaña 1: Hallazgos e Incidencias Técnicas (Findings)
   - 4.3. Pestaña 2: Corrector Ortográfico Editorial y Glosario
   - 4.4. Pestaña 3: Métricas de Producción y Heatmap de TAC
   - 4.5. Pestaña 4: Visor Densitométrico de Separaciones CMYK
   - 4.6. Pestaña 5: Comparador Visual Antes / Después (Slider)
   - 4.7. Pestaña 6: Hoja de Aprobación y Firma de Producción (Release)
5. [SUITE DE HERRAMIENTAS Y CORRECCIONES EN 1 CLIC](#5-suite-de-herramientas-y-correcciones-en-1-clic)
   - 5.1. "Taller en 1 Clic" (Batch Auto-Fix)
   - 5.2. Corrección de Espacio de Color (RGB a CMYK con Perfil ICC)
   - 5.3. Conversión de Tintas Planas (Spot / Pantone a CMYK)
   - 5.4. Corrección de Sobreimpresión (K100% Overprint, Blanco Knockout, Tintas Técnicas)
   - 5.5. Corrección de Líneas Finas (Hairlines a 0.30 pt)
   - 5.6. Vectorización de Tipografías (Font Outlining)
   - 5.7. Normalización de Geometría y Cajas PDF (TrimBox / BleedBox)
   - 5.8. Generador de Sangre Reflejada (+3 mm Mirror Bleed)
   - 5.9. Inyector de Marcas de Imprenta y Tiras de Control
   - 5.10. Limitador de Cobertura Total de Tinta (TAC 300%)
6. [MÓDULOS AVANZADOS DE PRODUCCIÓN](#6-módulos-avanzados-de-producción)
   - 6.1. Motor de Imposición de Pliegos (Imposition Engine N-Up)
   - 6.2. Inspector y Corrector de Códigos de Barras y QR (100% K)
   - 6.3. Procesamiento por Lote y Carpeta Caliente (Batch & Hot-Folder)
   - 6.4. Inspector de Margen de Seguridad y Lomo / Medianil
   - 6.5. Trazabilidad de Taller y Ficha para el Maquinista (Código QR en Pliego)
7. [MODO DIDÁCTICO Y SIMULADOR DE TALLER FP](#7-modo-didáctico-y-simulador-de-taller-fp)
   - 7.1. Banco de Retos Prácticos Reales (Casos de Estudio FP)
   - 7.2. Simulador Físico de Consecuencias en Taller (Efectos Reales en Máquina)
   - 7.3. Cuestionario de Autoevaluación Técnica (Quiz FP)
   - 7.4. Emisión de Ficha Oficial de Práctica y Evaluación (PDF A4)
8. [DOCUMENTACIÓN DE SALIDA Y ENTREGABLES](#8-documentación-de-salida-y-entregables)
   - 8.1. Certificado Técnico de Preflight Oficial (PDF A4)
   - 8.2. Guía Pedagógica para el Cliente / Diseñador (PDF A4)
   - 8.3. Reporte de Datos en Formato JSON
9. [PREGUNTAS FRECUENTES Y SOLUCIÓN DE PROBLEMAS (FAQ)](#9-preguntas-frecuentes-y-solución-de-problemas-faq)

---

## 1. ¿QUÉ ES INTELLIPRINT?

### 1.1. Misión y Filosofía de Taller Gráfico
**IntelliPrint** es una plataforma integral de ingeniería de software gráfico diseñada para auditar, normalizar, corregir e imponer documentos PDF antes de su entrada a las prensas de impresión offset y digital.

Nacida en el entorno productivo y educativo de la Formación Profesional de Artes Gráficas del País Vasco (desarrollada conjuntamente por **CPIFP Salesianos Urnieta LHIPI** y **CIFP Mendizabala LHII**, con respaldo del **Departamento de Educación del Gobierno Vasco**), su filosofía radica en el concepto de **"Cero Errores y Cero Desperdicio"**.

En la industria gráfica tradicional, más del 70% de las incidencias en máquina (repintados, paradas de tirada por descalce de texto fino, filetes blancos por falta de sangre, códigos de barras ilegibles en supermercados o amputación de textos por guillotina) se originan por fallos en los artes finales suministrados por agencias y diseñadores externos. IntelliPrint actúa como un cortafuegos inteligente entre el diseño y la máquina de imprimir.

### 1.2. Objetivos de Producción y Formación Profesional
1. **Reducción de Maculatura y Desperdicio:** Minimizar el consumo inútil de papel, tinta, planchas CTP y energía, reduciendo el impacto medioambiental.
2. **Validación Rápida:** Reducir el tiempo medio de revisión técnica de archivos a menos de 1 minuto por trabajo.
3. **Didáctica y Transferencia del Conocimiento:** Ofrecer no solo una herramienta industrial, sino un entorno pedagógico donde alumnos de FP y operarios comprendan la física del taller gráfico.
4. **Trazabilidad Total:** Enlazar la preimpresión con el maquinista mediante códigos QR dinámicos impresos en el pliego de máquina.

### 1.3. Arquitectura del Sistema
IntelliPrint combina un potente backend en **Python (FastAPI, PyMuPDF, PikePDF, OpenCV, Pillow)** con un frontend web ligero, reactivo y de alta velocidad en **HTML5, Tailwind CSS y JavaScript moderno**, sin dependencias pesadas de cliente. Puede ejecutarse localmente en redes de taller o desplegarse en la nube mediante contenedores Docker.

---

## 2. PRIMEROS PASOS Y REQUISITOS

### 2.1. Acceso a la Plataforma Web
Para comenzar a utilizar IntelliPrint:
1. Abra su navegador web habitual (Google Chrome, Mozilla Firefox, Microsoft Edge o Safari recomendados).
2. Introduzca la dirección del servidor (en local habitualmente `http://localhost:8000` o la URL asignada en su red de centro/empresa).
3. Verificará que el sistema está operativo si en la cabecera superior derecha aparece el indicador verde: `● Motor Activo`.

### 2.2. Requisitos de Archivo (Formatos Admitidos)
- **Formato:** Archivos `.pdf` (versiones 1.3 a 2.0, PDF/X-1a, PDF/X-3, PDF/X-4).
- **Tamaño recomendado:** Hasta 500 MB por archivo.
- **Tipos de documento:** Tarjetas de visita, folletos, flyers, cartelería, revistas, packaging, papelería corporativa o catálogos editoriales completos.

### 2.3. Estructura de la Interfaz Principal
La pantalla principal se divide en tres grandes zonas:
1. **Cabecera Institucional:** Muestra los logos oficiales de Salesianos Urnieta, Mendizabala y Eusko Jaurlaritza, junto a los accesos directos al **Modo Didáctico FP** y al botón **Nuevo PDF**.
2. **Zona de Carga y Configuración:** Área de arrastre del PDF, selector de perfiles de taller y catálogo de perfiles ICC de salida.
3. **Panel de Resultados y Herramientas (Workspace):** Se despliega automáticamente tras analizar el archivo, ofreciendo el semáforo de producción, las pestañas de diagnóstico y la botonera de corrección rápida.

---

## 3. CONFIGURACIÓN DEL ANÁLISIS DE ENTRADA

### 3.1. Carga de Archivos
- **Método 1 (Arrastrar y Soltar):** Arrastre el archivo PDF desde el explorador de archivos de su ordenador y suéltelo dentro de la caja discontinua azul con el icono de subida.
- **Método 2 (Explorador):** Haga clic en "Seleccionar PDF" para buscar el archivo en sus carpetas locales.

### 3.2. Inspección Rápida Preliminar
Nada más seleccionar el archivo, el sistema realiza una lectura instantánea sin bloqueo, informando de:
- Nombre del documento y peso en megabytes.
- Número total de páginas.
- Dimensiones físicas exactas de corte (en milímetros).
- Cantidad de imágenes rasterizadas embebidas.
- Perfil de salida (*OutputIntent*) detectado en el PDF original.

### 3.3. Selección de Perfiles de Verificación (Preflight Profiles)
En el desplegable "Perfil de Verificación", elija el estándar de calidad adecuado al destino del producto:
- **Offset Comercial (ISO Coated v2 / 300% TAC):** Para folletos, catálogos y revistas de alta calidad en papel estucado.
- **Impresión Digital Estándar:** Para tiradas cortas en prensa láser/tóner o inkjet de producción.
- **Prensa y Papel Periódico (TAC 240%):** Para publicaciones en papel prensa de alta absorción.
- **Packaging y Cartoncillo:** Para estuches, cajas y packaging con tintas especiales y troquel.
- **Gran Formato y Cartelería:** Para lonas y vinilos donde la distancia de visualización admite 150 DPI.

### 3.4. Gestión de Espacios de Color y Perfiles ICC (Output Intent)
El bloque de gestión de color permite decidir qué hacer con los perfiles del documento:
- **Preservar Perfil Existente:** Respeta el OutputIntent que ya traiga el archivo de origen.
- **Asignar Perfil Estándar:** Inyecta las condiciones de impresión recomendadas por Fogra/ECI si el archivo carece de ellas.
- **Catálogo ICC Integrado:** Permite forzar la conversión a perfiles como *ISO Coated v2 300% (ECI)*, *PSO Coated v3 (FOGRA51)*, *PSO Uncoated v3 (FOGRA52)*, *Adobe RGB (1998)* o *sRGB v4*.

Haga clic en el botón azul **"Iniciar Preflight Completo"** para procesar el trabajo.

---

## 4. EL INFORME DE VERIFICACIÓN (PREFLIGHT REPORT)

### 4.1. Semáforo de Producción y Calificación Global
En la parte superior se presentan tres tarjetas resumen:
1. **1. Resultado Técnico:**
   - `✓ APTO PARA IMPRESIÓN (SIN ERRORES CRÍTICOS)` en verde si cumple las normas.
   - `⚠ REQUIERE AJUSTES PREVIOS` en ámbar si contiene advertencias tolerables.
   - `✕ RECHAZADO (NO APTO PARA PRODUCCIÓN)` en rojo si contiene errores graves que provocarían maculatura o parada de máquina.
2. **2. Espacio de Color & ICC:** Muestra el perfil de salida y la presencia de imágenes RGB o tintas directas.
3. **3. Geometría & Cajas:** Muestra si el sangrado perimetral de 3 mm está presente o ausente.

### 4.2. Pestaña 1: Hallazgos e Incidencias Técnicas (Findings)
Agrupa todas las reglas comprobadas, clasificadas por colores de severidad:
- **Rojo (Crítico):** Líneas finas (*hairlines* < 0.25 pt) que desaparecerán en CTP, exceso de TAC que provocará repintado, textos negros pequeños en cuatricromía (*Rich Black*) que generarán descalce, ausencia de sangrado en fondos al corte.
- **Ámbar (Advertencia):** Imágenes entre 200 y 299 DPI, fuentes tipográficas no incrustadas, espacios de color RGB en proceso offset.
- **Verde (Aprobado):** Reglas conformes con la norma ISO.

*Cada hallazgo incluye un botón directo de solución cuando la corrección automática está disponible.*

### 4.3. Pestaña 2: Corrector Ortográfico Editorial y Glosario
IntelliPrint cuenta con un motor lingüístico integrado con más de 85.000 términos en español y un glosario técnico de Artes Gráficas:
- Detecta erratas en titulares, textos legales y créditos de página.
- Permite **Aceptar sugerencia**, **Ignorar** o **Añadir al Glosario Técnico del Taller** para que no vuelva a marcar términos técnicos del sector (p. ej. *Fogra*, *CTP*, *pantone*, *troquel*).

### 4.4. Pestaña 3: Métricas de Producción y Heatmap de TAC
Ofrece datos densitométricos precisos:
- Distribución de resolución de imágenes (DPI mínimo, medio y máximo).
- Porcentaje de objetos vectoriales frente a mapas de bits.
- **Cálculo de Cobertura Total de Tinta (TAC):** Muestra el valor porcentual más alto detectado en la página y genera un mapa de calor visual donde las zonas con exceso de tinta aparecen resaltadas.

### 4.5. Pestaña 4: Visor Densitométrico de Separaciones CMYK
Simula la mesa de luz de preimpresión:
- Permite aislar y conmutar de forma independiente las 4 planchas de proceso: **Cian (C)**, **Magenta (M)**, **Amarillo (Y)** y **Negro (K)**.
- El operario puede inspeccionar la plancha de Negro para certificar que el texto fino no tiene presencia en los canales de color.

### 4.6. Pestaña 5: Comparador Visual Antes / Después (Slider)
Tras aplicar cualquier corrección, esta pestaña activa un visor comparativo interactivo con cortinilla deslizante para verificar píxel a píxel que el contenido visual no ha sufrido desplazamientos indeseados.

### 4.7. Pestaña 6: Hoja de Aprobación y Firma de Producción (Release)
Módulo formal de taller donde el responsable de preimpresión o el cliente:
- Introduce el nombre del operador que autoriza el trabajo.
- Selecciona la máquina de destino (Offset 4 colores, Prensa Digital, Plotter).
- Puede estampar su firma digital sobre un lienzo táctil para emitir la autorización de tirada.

---

## 5. SUITE DE HERRAMIENTAS Y CORRECCIONES EN 1 CLIC

En la barra de acciones superior, IntelliPrint pone a disposición del usuario las herramientas de corrección sin necesidad de devolver el archivo al programa de maquetación:

```
[🪄 Taller en 1 Clic]  [✂ Marcas Imprenta]  [💧 Limitar TAC 300%]  [⊞ Imposición Pliego]
[|||| Códigos & QR]   [📁 Lote & Hot-Folder] [📐 Margen & Lomo]     [📱 Ficha Maquinista]
```

### 5.1. "Taller en 1 Clic" (Batch Auto-Fix)
Aplica en secuencia no destructiva las correcciones estándar recomendadas para entrar a imprenta:
1. Normalización de cajas PDF (MediaBox y TrimBox).
2. Generación de sangre reflejada de +3 mm si faltaba.
3. Conversión de imágenes RGB a CMYK con el perfil de color elegido.
4. Activación de sobreimpresión automática en textos negros (100% K).
5. Corrección de líneas pelo inferiores a 0.25 pt elevándolas a 0.30 pt.
6. Vectorización de tipografías conflictivas.

### 5.2. Corrección de Espacio de Color (RGB a CMYK)
Convierte todas las fotografías y objetos en espacio RGB al perfil CMYK seleccionado (por ejemplo, ISO Coated v2 / FOGRA39) mediante transformaciones colorimétricas directas, evitando las desviaciones de tono en máquina.

### 5.3. Conversión de Tintas Planas (Spot / Pantone a CMYK)
Si el archivo contiene tintas directas no presupuestadas (Pantone) y la tirada se realizará en cuatricromía convencional (4 cuerpos), este botón descompone las tintas directas en sus equivalentes CMYK óptimos.

### 5.4. Corrección de Sobreimpresión (Overprint)
- **Negro 100%:** Aplica el atributo de sobreimpresión (*overprint*) a todos los textos negros pequeños, evitando que calen el fondo y previniendo descalces.
- **Blanco:** Desactiva la sobreimpresión accidental en objetos y textos blancos (que de lo contrario desaparecerían en el CTP).
- **Barnices y Troqueles:** Aplica sobreimpresión obligatoria a las tintas técnicas para que no eliminen el diseño que va debajo.

### 5.5. Corrección de Líneas Finas (Hairlines)
Identifica trazos vectoriales de grosor inferior a 0.25 pt (habituales en diseños exportados de Illustrator o AutoCAD) y los ensancha de forma segura a **0.30 pt**, garantizando su transferencia en la plancha CTP sin modificar la estética del diseño.

### 5.6. Vectorización de Tipografías (Font Outlining)
Convierte todos los textos y glifos del documento en trazos vectoriales geométricos (*curvas*). Es la solución definitiva ante tipografías no incrustadas, fuentes protegidas por licencia o incompatibilidades con el RIP.

### 5.7. Normalización de Geometría y Cajas PDF
Alinea y corrige las cajas de página estándar de Adobe (**MediaBox, CropBox, TrimBox, BleedBox y ArtBox**) para que coincidan con las dimensiones reales de corte y sangrado.

### 5.8. Generador de Sangre Reflejada (+3 mm Mirror Bleed)
Cuando un cliente envía un diseño que termina justo en el borde de corte (0 mm de sangre), esta herramienta analiza el perímetro y genera automáticamente una extensión exterior de 3 mm mediante espejo simétrico de los píxeles perimetrales. Al cortar en la guillotina, desaparece el riesgo de filetes blancos.

### 5.9. Inyector de Marcas de Imprenta y Tiras de Control
Agranda el lienzo del documento para inyectar marcas normalizadas en el rebaje técnico (*slug*):
- Cruces de registro en los 4 ejes.
- Marcas de corte exteriores (offset 3 mm) alineadas con el TrimBox.
- Tiras de escala densitométrica CMYK (parches de 10% a 100%).
- Datos del trabajo con identificación institucional: `IntelliPrint-SalesianosUrnieta-CIFPMendizabalaLHII`.

### 5.10. Limitador de Cobertura Total de Tinta (TAC 300%)
Aplica una curva de reducción selectiva sobre las sombras más densas que superan el 300% de tinta, manteniendo la neutralidad cromática y los contrastes de sombra pero reduciendo el espesor de capa para evitar el repintado en la salida de máquina.

---

## 6. MÓDULOS AVANZADOS DE PRODUCCIÓN

### 6.1. Motor de Imposición de Pliegos (Imposition Engine N-Up)
Permite realizar el montaje de imposición de taller directamente desde el navegador:
- **Formatos de Pliego Estándar:** SRA3 (320 × 450 mm), A3 (297 × 420 mm), A4, 50 × 70 cm (B2) o 70 × 100 cm (B1).
- **Esquemas de Imposición:**
  - *Paso y Repetición (N-Up Step and Repeat):* Para tarjetas de visita, flyers, etiquetas o postales.
  - *Cuadernillo Grapado / Plegado:* Emparejamiento de páginas exteriores e interiores para revistas.
- **Tratamiento Automático de Sangrado:**
  - *Caso A (Sin sangre):* Montaje en TrimBox con aviso técnico.
  - *Caso B (Con 3 mm de sangre):* Imposición de BleedBox completo y marcas de corte desplazadas hacia el interior marcando el corte exacto.
  - *Caso C (Marcas previas incrustadas):* Recorte selectivo al TrimBox descartando marcas antiguas del cliente para evitar marcas dobles.
- Incluye cálculo en vivo de poses por pliego, porcentaje de aprovechamiento del papel y descarga del PDF impuesto con marcas y código QR.

### 6.2. Inspector y Corrector de Códigos de Barras y QR
- **Detección Morfológica Inteligente:** Localiza códigos EAN-13, EAN-8, UPC, Code 128 y Códigos QR en cualquier página mediante filtrado morfológico y gradientes direccionales Scharr en OpenCV.
- **Validación Aritmética GS1:** Comprueba el dígito de control (módulo 10).
- **Muestreo Cromático Nativo:** Analiza si las barras están formadas por **Negro 100% Puro (K)** o por **Negro Enriquecido (Rich Black a 4 tintas CMYK)**.
- **Corrector en 1 Clic:** Re-genera el código como elemento vectorial a 300 DPI en **100% K puro sobreimpreso** e inyecta la zona muda perimetral (*quiet zone*) opaca en blanco para garantizar su lectura en cualquier escáner comercial.

### 6.3. Procesamiento por Lote y Carpeta Caliente (Batch & Hot-Folder)
Diseñado para entornos de alta producción:
- **Subida Masiva:** Arrastre 20 o 50 PDFs a la vez en la cola de trabajo. IntelliPrint los analiza en paralelo mediante subprocesos multihilo.
- **Acciones Colectivas:** Botones para "Corregir Todo el Lote" y "Descargar Todo en ZIP Normalizado".
- **Hot-Folder Automatizado (Daemon de Fondo):**
  - Monitoriza la carpeta del sistema `hotfolder/in/`.
  - Cuando un diseñador o cliente deposita un archivo, el sistema comprueba la estabilidad de escritura (*file lock*), ejecuta el preflight y aplica las correcciones automáticas.
  - Si el archivo cumple los criterios, se mueve a `hotfolder/out_aprobados/` acompañado de su Certificado Técnico.
  - Si presenta errores irreparables, se desvía a `hotfolder/out_rechazados/` junto con la Guía Pedagógica explicativa para el cliente.

### 6.4. Inspector de Margen de Seguridad y Lomo / Medianil
Audita la proximidad de los elementos críticos respecto a los bordes de corte y plegado:
- **Detección Automática de Tipo de Impreso:**
  - *Hoja suelta (Single Leaf):* Tarjetas de visita (85 × 55 mm), folletos simples y flyers. Aplica margen de seguridad de 3 mm y lomo de 0 mm.
  - *Publicación encuadernada (Bound Publication):* Documentos de 4 o más páginas. Aplica margen de seguridad de 3 mm en cortes y reserva especial de **8 mm en el lomo/medianil** (alternando izquierda/derecha según páginas pares e impares).
- **Visor con Capas de Inspección:** Dibuja sobre el diseño la línea roja de corte (TrimBox), la línea verde de zona de seguridad, la franja morada del lomo y cajas de alerta rojas sobre los textos que invaden las zonas de riesgo.

### 6.5. Trazabilidad de Taller y Ficha para el Maquinista
- **Inyección de QR en el Pliego:** Tanto en la imposición de pliegos como al añadir marcas de imprenta, el sistema estampa en el margen técnico inferior un código QR en negro 100% K de $9 \times 9\text{ mm}$ junto al texto de cabecera.
- **Ficha Móvil de Verificación (`/verify/{job_id}`):**
  - El maquinista enfoca el QR con su teléfono o tablet a pie de máquina y accede al instante a una pantalla optimizada de taller.
  - Visualiza el semáforo de producción: `✓ LISTO PARA IMPRESIÓN` o `⚠ REQUIERE AJUSTES`.
  - Consulta los parámetros de máquina: perfil ICC de salida, cuerpos de tinta que debe preparar en batería (CMYK + Pantones), valor máximo de TAC, verificación de sangre, estado de códigos de barras y dimensiones del pliego.
  - Dispone de botones táctiles para descargar el certificado, la guía del cliente o el pliego de imposición.

---

## 7. MODO DIDÁCTICO Y SIMULADOR DE TALLER FP

Accediendo desde el botón morado superior **`[ 🎓 Modo Didáctico FP ]`**, se abre el entorno educativo diseñado específicamente para la formación de futuros técnicos en preimpresión y producción gráfica:

```
[ 🎯 1. Retos Prácticos FP ] [ ⚙️ 2. Simulador Físico ] [ 📝 3. Autoevaluación FP ] [ 📄 4. Ficha Alumno PDF ]
```

### 7.1. Banco de Retos Prácticos Reales (Casos de Estudio FP)
Contiene ejercicios prediseñados listos para cargar con 1 clic:
- **Reto 1: Tarjeta Corporativa con Rich Black y Sin Sangrado (Iniciación FP)**
- **Reto 2: Folleto Promocional con TAC 365% y Líneas Pelo CTP (Intermedio)**
- **Reto 3: Estuche Packaging con Código de Barras en 4 Tintas (Avanzado)**
- **Reto 4: Portada de Revista con Textos en el Medianil / Lomo (Avanzado)**

*Al hacer clic en "Cargar Reto en IntelliPrint", el sistema sintetiza el archivo con sus defectos exactos y carga el preflight completo para que el alumno realice la diagnosis.*

### 7.2. Simulador Físico de Consecuencias en Taller
Permite al alumnado experimentar visualmente qué le ocurriría al trabajo físico en el taller mediante simulaciones interactivas con deslizadores:
1. **Descalce de Registro (Rich Black):** Slider de desfase de planchas (de 0.05 a 0.50 mm). Muestra los halos cian y magenta y el emborronamiento del texto de 6 pt.
2. **Repintado en Pila (Exceso de TAC):** Slider de TAC (260% a 380%). Simula el manchado oleoso por contacto sobre el dorso de la siguiente hoja en la bandeja de salida.
3. **Guillotine Shift & Filete Blanco:** Conmutador de sangre (+3 mm vs 0 mm) y oscilación de cuchilla. Muestra el borde blanco del papel que queda al descubierto.
4. **Pérdida en Plancha CTP (Hairlines):** Slider de trazo (0.04 a 0.40 pt). Muestra cómo el láser térmico a 2400 DPI pierde la emulsión y borra la línea en tirada.

### 7.3. Cuestionario de Autoevaluación Técnica (Quiz FP)
- Test interactivo con 5 preguntas clave de taller (normas ISO 12647-2, ISO 15930, tolerancias de corte y GS1).
- Calificación automática de 0 a 10 con baremo: *Sobresaliente, Notable, Aprobado o Insuficiente*.
- Desglose con la justificación técnica de taller y la norma de referencia para cada respuesta.

### 7.4. Emisión de Ficha Oficial de Práctica y Evaluación (PDF A4)
Genera un documento PDF oficial A4 con membrete institucional de **Salesianos Urnieta**, **CIFP Mendizabala LHII** y el **Departamento de Educación del Gobierno Vasco**:
- Incluye el nombre del estudiante, centro educativo y módulo formativo.
- Resumen del reto analizado y diagnóstico técnico.
- Rúbrica y calificación obtenida en el cuestionario.
- Casillas con espacio reservado para la firma y sello del profesor/evaluador y conformidad del estudiante.

---

## 8. DOCUMENTACIÓN DE SALIDA Y ENTREGABLES

Desde la botonera de resultados o la ficha de verificación, IntelliPrint genera tres modalidades de salida documental:

### 8.1. Certificado Técnico de Preflight Oficial (PDF A4)
- Documento técnico riguroso de una página A4 para el jefe de taller y el archivo de producción.
- Incorpora sellos institucionales, código SHA-256 de integridad del archivo, datos densitométricos, geometría de cajas, perfil ICC de salida y veredicto formal de tirada.

### 8.2. Guía Pedagógica para el Cliente / Diseñador (PDF A4)
- Informe visual, cordial y didáctico redactado sin jerga hostil.
- Explica de forma gráfica al diseñador qué incidencias se encontraron en su arte final y **cómo corregirlas paso a paso en Adobe InDesign, Adobe Illustrator o Photoshop** antes de reenviar el PDF.

### 8.3. Reporte de Datos en Formato JSON
- Archivo estructurado con todas las métricas, árboles de objetos, perfiles y reglas evaluadas para su integración automática con sistemas ERP / MIS de imprenta (como Prinect, Pace o sistemas de gestión gráfica).

---

## 9. PREGUNTAS FRECUENTES Y SOLUCIÓN DE PROBLEMAS (FAQ)

**1. ¿Por qué el preflight marca error crítico en un texto negro si en pantalla se ve perfectamente negro?**
> En monitor, un texto compuesto por C=70 M=60 Y=50 K=90 se muestra negro oscuro. Sin embargo, en la imprenta requiere cuatro planchas de impresión distintas. Si el texto es menudo (6 u 8 pt), cualquier vibración mínima de máquina provocará un descalce con halos de color. Pulse "Taller en 1 Clic" o "Sobreimpresión" para convertirlo automáticamente a 100% K puro sobreimpreso.

**2. ¿El generador de sangre reflejada modifica el contenido original del diseño?**
> No. La sangre reflejada solo toma una franja de 3 mm del borde exterior y la proyecta simétricamente hacia afuera (más allá de la línea de corte TrimBox). La zona visible final del impreso permanece 100% inalterada.

**3. ¿Qué diferencia hay entre la Ficha Técnica para el Maquinista y el Certificado de Preflight?**
> El Certificado es un informe administrativo y de calidad en PDF A4. La Ficha del Maquinista (`/verify/{job_id}`) es una consola web móvil ultra-rápida pensada para abrirse en segundos a pie de máquina escaneando el código QR impreso en el pliego, mostrando solo los parámetros operativos esenciales (tintas, perfiles, TAC y riesgos).

**4. ¿Cómo se activa el Hot-Folder automatizado en la imprenta?**
> En la ventana "Lote & Hot-Folder", pulse el botón "Iniciar Hot-Folder". A partir de ese momento, cualquier PDF copiado a la carpeta compartida de red `hotfolder/in/` será procesado en segundo plano de manera continua.

**5. ¿Cumple IntelliPrint con las normas internacionales de Artes Gráficas?**
> Sí. Todas las tolerancias y reglas de comprobación y corrección están parametrizadas con base en las normas **ISO 12647-2** (Offset en pliegos), **ISO 15930** (Estándares PDF/X-1a y PDF/X-4), **ISO/IEC 15420** (especificaciones GS1 para códigos de barras) y las recomendaciones del **Ghent Workgroup (GWG)**.

---

```
========================================================================================
                          FIN DEL MANUAL DE USUARIO
           IntelliPrint · CPIFP Salesianos Urnieta · CIFP Mendizabala LHII
                       Departamento de Educación · Eusko Jaurlaritza
========================================================================================
```

