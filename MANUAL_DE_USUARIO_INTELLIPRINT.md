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
2. [PRIMEROS PASOS Y ACCESO A LA APLICACIÓN](#2-primeros-pasos-y-acceso-a-la-aplicación)
   - 2.1. Acceso a la Plataforma Web
   - 2.2. Requisitos de Archivo (Formatos Admitidos)
   - 2.3. Estructura de la Interfaz Principal
   - 2.4. Modo Cabina de Máquina D50 (Dark Theme Antirreflejo) y Modo Kiosko / Pantalla Completa
3. [CONFIGURACIÓN Y ANÁLISIS DE ENTRADA](#3-configuración-y-análisis-de-entrada)
   - 3.1. Carga de Archivos (Arrastrar y Soltar / Selección)
   - 3.2. Inspección Rápida Preliminar
   - 3.3. Selección de Perfiles de Verificación Estándar
   - 3.4. Gestión de Espacios de Color y Perfiles ICC (Output Intent)
   - 3.5. Creador y Editor de Perfiles de Preflight Personalizados (Custom Profiles Editor)
4. [EL INFORME DE VERIFICACIÓN (PREFLIGHT REPORT)](#4-el-informe-de-verificación-preflight-report)
   - 4.1. Semáforo de Producción y Calificación Global
   - 4.2. Pestaña 1: Hallazgos e Incidencias Técnicas (Findings)
   - 4.3. Pestaña 2: Corrector Ortográfico Editorial y Glosario
   - 4.4. Pestaña 3: Métricas de Producción y Heatmap de TAC
   - 4.5. Pestaña 4: Visor Densitométrico de Separaciones CMYK
   - 4.6. Pestaña 5: Comparador Visual Antes / Después (Slider)
   - 4.7. Pestaña 6: Hoja de Aprobación y Firma de Producción (Release)
   - 4.8. Barra de Herramientas Ergonómica (Prensa, Ajustes Técnicos y Entregables)
5. [SUITE DE HERRAMIENTAS Y CORRECCIONES EN 1 CLIC](#5-suite-de-herramientas-y-correcciones-en-1-clic)
   - 5.1. "Taller en 1 Clic" (Batch Auto-Fix)
   - 5.2. Corrección de Espacio de Color (RGB a CMYK con Perfil ICC)
   - 5.3. Conversión de Tintas Planas (Spot / Pantone a CMYK)
   - 5.4. Corrección de Sobreimpresión (K100% Overprint, Blanco Knockout, Tintas Técnicas)
   - 5.5. Corrección de Líneas Finas (Hairlines a 0.30 pt)
   - 5.6. Vectorización de Tipografías (Font Outlining)
   - 5.7. Normalización de Geometría y Cajas PDF (TrimBox / BleedBox)
   - 5.8. Generador de Sangre Reflejada (+3 mm Mirror Bleed)
   - 5.9. Tira de Control Normalizada FOGRA / ISO 12647-2 y Balance de Grises
   - 5.10. Limitador de Cobertura Total de Tinta (TAC 300%)
6. [MÓDULOS AVANZADOS DE PRODUCCIÓN](#6-módulos-avanzados-de-producción)
   - 6.1. Motor de Imposición de Pliegos (Imposition Engine N-Up)
   - 6.2. Exportación de Datos CIP3 / PPF v3.0 & Preajuste de Tinteros por Zonas
   - 6.3. Inspector y Corrector de Códigos de Barras y QR (100% K)
   - 6.4. Procesamiento por Lote y Carpeta Caliente (Batch & Hot-Folder)
   - 6.5. Inspector de Margen de Seguridad y Lomo / Medianil
   - 6.6. Trazabilidad de Taller y Ficha para el Maquinista (Código QR en Pliego)
7. [MODO DIDÁCTICO Y SIMULADOR DE TALLER FP](#7-modo-didáctico-y-simulador-de-taller-fp)
   - 7.1. Banco de Retos Prácticos Reales (Casos de Estudio FP)
   - 7.2. Simulador Físico de Consecuencias en Taller (Efectos Reales en Máquina)
   - 7.3. Cuestionario de Autoevaluación Técnica (Quiz FP)
   - 7.4. Emisión de Ficha Oficial de Práctica y Evaluación (PDF A4)
8. [DOCUMENTACIÓN DE SALIDA Y ENTREGABLES](#8-documentación-de-salida-y-entregables)
   - 8.1. Certificado Técnico de Preflight Oficial (PDF A4)
   - 8.2. Guía Pedagógica para el Cliente / Diseñador (PDF A4)
   - 8.3. Reporte de Datos en Formato JSON
   - 8.4. Ficha de Tinteros CIP3 y Lámina Técnica FOGRA (PDF A4)
9. [PREGUNTAS FRECUENTES Y SOLUCIÓN DE PROBLEMAS (FAQ)](#9-preguntas-frecuentes-y-solución-de-problemas-faq)

---

## 1. ¿QUÉ ES INTELLIPRINT?

### 1.1. Misión y Filosofía de Taller Gráfico
**IntelliPrint** es una plataforma integral de ingeniería de software gráfico diseñada para auditar, normalizar, corregir e imponer documentos PDF antes de su entrada a las prensas de impresión offset y digital, así como para la validación de publicaciones digitales interactivas y web.

Nacida en el entorno productivo y educativo de la Formación Profesional de Artes Gráficas del País Vasco (desarrollada conjuntamente por [**CPIFP Salesianos Urnieta LHIPI**](https://salesianosurnieta.com/) y [**CIFP Mendizabala LHII**](https://www.mendizabala.eus/), con respaldo del [**Departamento de Educación del Gobierno Vasco / Eusko Jaurlaritza**](https://www.euskadi.eus/gobierno-vasco/departamento-educacion/)), su filosofía radica en el concepto de **"Cero Errores y Cero Desperdicio"**.

En la industria gráfica tradicional, más del 70% de las incidencias en máquina (repintados, paradas de tirada por descalce de texto fino, filetes blancos por falta de sangre, códigos de barras ilegibles en supermercados o amputación de textos por guillotina) se originan por fallos en los artes finales suministrados por agencias y diseñadores externos. IntelliPrint actúa como un cortafuegos inteligente entre el diseño y la máquina de imprimir.

### 1.2. Identidad Visual y Logotipo Corporativo
La identidad visual de IntelliPrint refleja la unión entre la precisión de la preimpresión técnica y la innovación educativa:
- **Monograma Simbólico "iP":** Ícono vanguardista de diseño plano estilizado que integra el punto de la 'i' en amarillo proceso (`#FFD700`), el fuste vertical blanco puro (`#FFFFFF`) y el bucle descendente de la 'p' en un degradado armónico de cian proceso (`#00A3FF`) y magenta (`#E6007E`), evocando la síntesis sustractiva de la cuatricromía.
- **Logotipo Tipográfico de Alto Contraste:** Composición equilibrada formada por la palabra `Intelli` en peso fino tipográfico (*Light 300*) en blanco puro y `Print` en peso sólido (*Heavy 700*) en cian de proceso (`#00A3FF`).
- **Navegación e Interactividad Institucional:** Todos los logotipos presentes en la interfaz web, fichas móviles de taller y certificados PDF incorporan hipervínculos interactivos a los portales oficiales de las instituciones colaboradoras y a la página de inicio.

### 1.2. Objetivos de Producción y Formación Profesional
1. **Reducción de Maculatura y Desperdicio:** Minimizar el consumo inútil de papel, tinta, planchas CTP y energía, reduciendo el impacto medioambiental.
2. **Validación Rápida:** Reducir el tiempo medio de revisión técnica de archivos a menos de 1 minuto por trabajo.
3. **Didáctica y Transferencia del Conocimiento:** Ofrecer no solo una herramienta industrial, sino un entorno pedagógico donde alumnos de FP y operarios comprendan la física del taller gráfico.
4. **Trazabilidad Total y Automatización:** Enlazar la preimpresión con el maquinista mediante códigos QR dinámicos impresos en el pliego de máquina y archivos de tinteros CIP3.

### 1.3. Arquitectura del Sistema
IntelliPrint combina un potente backend en **Python (FastAPI, PyMuPDF, PikePDF, OpenCV, NumPy, Pillow)** con un frontend web reactivo y de alta velocidad en **HTML5, Tailwind CSS y JavaScript moderno**, sin dependencias pesadas de cliente. Puede ejecutarse localmente en redes de taller o desplegarse en la nube mediante contenedores Docker.

---

## 2. PRIMEROS PASOS Y ACCESO A LA APLICACIÓN

### 2.1. Acceso a la Plataforma Web
Para comenzar a utilizar IntelliPrint:
1. Abra su navegador web habitual (Google Chrome, Mozilla Firefox, Microsoft Edge o Safari recomendados).
2. Introduzca la dirección del servidor (en local habitualmente `http://localhost:8000` o la URL en la nube).
3. Verificará que el sistema está operativo si en la cabecera superior derecha aparece el indicador verde: `● Motor Activo`.

### 2.2. Requisitos de Archivo (Formatos Admitidos)
- **Formato:** Archivos `.pdf` (versiones 1.3 a 2.0, PDF/X-1a, PDF/X-3, PDF/X-4).
- **Tamaño recomendado:** Hasta 500 MB por archivo.
- **Tipos de documento:** Tarjetas de visita, folletos, flyers, cartelería, revistas, packaging troquelado, papelería corporativa o catálogos editoriales completos.

### 2.3. Estructura de la Interfaz Principal
La pantalla principal se divide en tres grandes zonas:
1. **Cabecera Institucional:** Muestra los logos oficiales de Salesianos Urnieta, Mendizabala y Eusko Jaurlaritza, junto a los accesos directos al **Modo Didáctico FP**, **Manual**, **Editor de Perfiles**, **Modo Cabina D50** y botón de **Nuevo PDF**.
2. **Zona de Carga y Configuración:** Área de arrastre del PDF, selector de perfiles de taller y catálogo de perfiles ICC de salida.
3. **Panel de Resultados y Herramientas (Workspace):** Se despliega automáticamente tras analizar el archivo, ofreciendo el semáforo de producción, las pestañas de diagnóstico y la botonera de corrección rápida organizada en bloques temáticos.

### 2.4. Modo Cabina de Máquina D50 (Dark Theme Antirreflejo) y Modo Kiosko
En los pupitres de control de prensas offset y digitales, la iluminación estándar según la norma **ISO 3664** es de **D50 (5000 K)**:
- **Botón `[ 🌙 Cabina D50 ]`:** Conmuta a un tema oscuro antirreflejo de alto contraste calibrado para absorber la luz directa de la visera del pupitre y evitar que el brillo blanco de la pantalla deslumbre al maquinista o altere su adaptación cromática al medir pliegos. La preferencia se guarda automáticamente en `localStorage`.
- **Botón `[ ⛶ ]`:** Activa el modo de Pantalla Completa nativo (*Kiosk Mode*), aislando la aplicación de las barras del sistema operativo en monitores táctiles industriales de máquina.

---

## 3. CONFIGURACIÓN Y ANÁLISIS DE ENTRADA

### 3.1. Carga de Archivos
- **Método 1 (Arrastrar y Soltar):** Arrastre el archivo PDF desde el explorador de archivos y suéltelo dentro de la caja discontinua azul con el icono de subida.
- **Método 2 (Explorador):** Haga clic en la caja para examinar y seleccionar el archivo en sus carpetas locales.

### 3.2. Inspección Rápida Preliminar
Nada más seleccionar el archivo, el sistema realiza una lectura instantánea sin bloqueo, informando de:
- Nombre del documento y peso en megabytes.
- Número total de páginas.
- Dimensiones físicas exactas de corte (en milímetros).
- Cantidad de imágenes rasterizadas embebidas.
- Perfil de salida (*OutputIntent*) detectado en el PDF original.

### 3.3. Selección de Perfiles de Verificación Estándar (Paso 2)
En el bloque **"2. PERFIL DE DESTINO (INTELLIPRINT)"**, elija el estándar técnico con el que desea auditar el archivo. El catálogo oficial incluye 6 perfiles predeterminados:
1. **Offset Comercial (ISO Coated v2 / 300% TAC):** Para folletos, catálogos, revistas y papelería corporativa de alta calidad en papel estucado brillante o mate según ISO 12647-2 (≥300 DPI, 3.0 mm de sangre, TAC ≤300%, espacio CMYK).
2. **Impresión Digital Estándar:** Para tiradas cortas bajo demanda en prensas digitales láser/tóner o inkjet de producción continua (≥200 DPI, 2.0 mm de sangre, TAC ≤320%, espacio CMYK).
3. **Prensa y Papel Periódico:** Para rotativa y publicaciones en papel prensa de alta porosidad y absorción rápida (≥170 DPI, 2.0 mm de sangre, TAC ≤240%, espacio CMYK).
4. **Packaging y Cartoncillo:** Para estuches, envases cosméticos, cajas plegables y productos con troquel complejo (≥300 DPI, 5.0 mm de sangrado mínimo, TAC ≤280%, espacio CMYK).
5. **Gran Formato y Cartelería:** Para lonas publicitarias, vallas, vinilos, displays y roll-ups donde la mayor distancia de visualización admite densidades reducidas (≥150 DPI, 5.0 mm de sangrado, TAC ≤320%, espacio CMYK).
6. **Web, Pantalla y Documento Digital (RGB):** Para catálogos interactivos, memorias corporativas para web, e-books o presentaciones digitales. A diferencia de los perfiles de imprenta, **este perfil exige estrictamente 0.0 mm de sangrado exterior**, admite y prioriza el espacio de color **RGB (sRGB)**, sitúa la resolución óptima en **96 DPI / ppp** y desactiva restricciones de TAC de tinta física (hasta 400%).

### 3.4. Gestión de Espacios de Color y Perfiles ICC (Paso 3)
En el bloque **"3. PERFIL DE COLOR (ICC)"**, configure la intención de salida colorimétrica (*Output Intent*):
- **Conservar perfil del documento:** Respeta el diccionario de salida (*OutputIntent*) que traía embebido originalmente el PDF. Recomendado cuando el archivo ya ha sido exportado correctamente desde maquetación.
- **Elegir de icc_profiles/:** Asigna forzosamente un perfil ICC físico del catálogo (*ISO Coated v2 300% ECI*, *PSO Coated v3 FOGRA51*, *PSO Uncoated v3 FOGRA52*, *sRGB2014.icc*, etc.). Este perfil será el que se incruste en el documento al ejecutar las herramientas de normalización o "Taller en 1 Clic".

> [!IMPORTANT]
> **¿Qué diferencia existe entre el Paso 2 y el Paso 3?**
> - **El Paso 2 (Perfil de Destino)** es el **inspector o baremo normativo**. Establece las reglas y tolerancias para buscar fallos (resolución mínima, sangrado requerido, límite de TAC, hairlines o espacios no permitidos). **El Paso 2 NO incrusta ni altera ningún perfil dentro del PDF**.
> - **El Paso 3 (Perfil de Color ICC)** es la **declaración física de salida**. Determina qué perfil de color específico (`.icc`) viajará incrustado como *OutputIntent* en el archivo resultante cuando se ejecute la conversión cromática o la reparación en un clic.

### 3.5. Creador y Editor de Perfiles de Preflight Personalizados (Custom Profiles Editor)
Pulsando el botón **`[ ⚙️ Gestionar Perfiles ]`** o **`[ + Crear Perfil Personalizado ]`**, los docentes y jefes de taller pueden definir criterios de inspección exactos para su parque de maquinaria:
- **Parámetros configurables:**
  - *Nombre y destino:* ej. "Packaging Mendizabala 5mm" o "Digital Salesianos Ricoh".
  - *Resolución mínima (DPI):* Umbral de alerta para imágenes.
  - *Sangrado mínimo requerido (mm):* ej. 5.0 mm en estuchería frente a 3.0 mm comercial.
  - *Límite de Cobertura Total de Tinta (TAC %):* ej. 280% para cartoncillo o 240% para prensa.
  - *Grosor mínimo de trazo (Hairline en pt):* Umbral de seguridad contra pérdida en CTP.
  - *Margen de seguridad interior (mm):* Distancia mínima admisible de textos al corte.
  - *Espacio de color requerido:* CMYK, RGB o Escala de Grises.
  - *Reglas booleanas:* Permitir tintas planas (Pantone) y exigir tipografías 100% incrustadas.
- **Persistencia e Intercambio:** Los perfiles se guardan en el servidor (`custom_profiles.json`) y disponen de botones para **`[ Exportar JSON ]`** e **`[ Importar JSON ]`**, facilitando el envío de pautas técnicas entre aulas y puestos de trabajo.

---

## 4. EL INFORME DE VERIFICACIÓN (PREFLIGHT REPORT)

### 4.1. Semáforo de Producción y Calificación Global
En la parte superior se presentan tres tarjetas resumen:
1. **1. Resultado Técnico:**
   - `✓ CUMPLE` en verde si el PDF es apto para filmación e impresión.
   - `⚠ CUMPLE CON AVISOS` en ámbar si contiene advertencias menores tolerables.
   - `✕ NO CUMPLE` en rojo si contiene errores críticos que causarían maculatura o parada de máquina.
2. **2. Resultado de Contenido:** Indica el estado de la revisión ortográfica y posibles erratas detectadas.
3. **3. Resultado de Salida:** Muestra la condición de visto bueno para el pase a máquina.

### 4.2. Pestaña 1: Hallazgos e Incidencias Técnicas (Findings)
Agrupa todas las reglas comprobadas, clasificadas por colores de severidad:
- **Rojo (Crítico):** Líneas finas (*hairlines* < 0.25 pt) que desaparecerán en CTP, exceso de TAC que provocará repintado, textos negros pequeños en cuatricromía (*Rich Black*) que generarán descalce, ausencia de sangrado en fondos al corte.
- **Ámbar (Advertencia):** Imágenes de resolución subóptima, fuentes no incrustadas, espacios de color RGB en procesos offset.
- **Verde (Aprobado):** Reglas conformes con la norma ISO.

### 4.3. Pestaña 2: Corrector Ortográfico Editorial y Glosario
IntelliPrint cuenta con un motor lingüístico integrado con más de 85.000 términos y un glosario técnico de Artes Gráficas:
- Detecta erratas en titulares, textos legales y créditos de página.
- Permite **Aceptar sugerencia**, **Ignorar** o **Añadir al Glosario Técnico del Taller** para que no vuelva a marcar términos técnicos del sector (p. ej. *FOGRA*, *CTP*, *pantone*, *troquel*).

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

### 4.8. Barra de Herramientas Ergonómica Segmentada
Para optimizar el flujo de trabajo sin saturar la pantalla, la botonera de resultados se organiza en tres bloques lógicos:
1. **Acciones Principales:** `[ ⚡ Taller en 1 Clic ]` (reparación integral), `[ 📄 Descargar PDF ]`, `[ 🛡️ Ficha Técnica ]` y `[ 🔄 Nuevo PDF ]`.
2. **Prensa & Taller:** `[ 📐 Imposición Pliego ]`, `[ 🖨️ Tinteros CIP3 ]` y `[ 📱 Ficha Maquinista ]`.
3. **Ajustes Técnicos & Entregables:** `[ ✂️ Marcas FOGRA ]`, `[ 💧 Limitar TAC ]`, `[ 🏷️ Códigos & QR ]`, `[ 📏 Margen & Lomo ]`, `[ 📁 Hot-Folder ]`, `[ 👤 Informe Cliente ]` y `[ 💻 JSON ]`.

---

## 5. SUITE DE HERRAMIENTAS Y CORRECCIONES EN 1 CLIC

### 5.1. "Taller en 1 Clic" (Batch Auto-Fix)
Aplica en secuencia no destructiva las correcciones estándar recomendadas para entrar a imprenta:
1. Normalización de cajas PDF (MediaBox y TrimBox).
2. Generación de sangre reflejada de +3 mm si faltaba.
3. Conversión de imágenes RGB a CMYK con el perfil de color elegido.
4. Activación de sobreimpresión automática en textos negros (100% K).
5. Corrección de líneas pelo inferiores a 0.25 pt elevándolas a 0.30 pt.
6. Vectorización de tipografías conflictivas.

### 5.2. Corrección de Espacio de Color (RGB a CMYK)
Convierte todas las fotografías y objetos en espacio RGB al perfil CMYK seleccionado mediante transformaciones colorimétricas directas, evitando las desviaciones de tono en máquina.

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

### 5.9. Tira de Control Normalizada FOGRA / ISO 12647-2 y Balance de Grises
Sustituye la antigua barra de colores genérica por una **tira de control espectrofotométrica profesional** calculada y dibujada directamente en espacio nativo `/DeviceCMYK`:
- **Sólidos Primarios (100% CMYK):** Para control de densidad máxima ($D_{\max}$) y espesor de capa de tinta.
- **Escalas Tonales y Ganancia de Punto (TVI):** Medios tonos (50%), altas luces CTP críticas (3% y 5%) y sombras profundas (95% y 98%).
- **Sobreimpresiones y Trapping:** Rojo (M+Y), Verde (C+Y), Azul (C+M) y Tricromía (C+M+Y) para calibración de aceptación de tintas según la fórmula Preucil.
- **Tríada de Balance de Grises ISO 12647-2:** Comparación de neutros tricromáticos frente a negro puro:
  - *Altas luces:* CMY25 (C:25%, M:19%, Y:19%) vs REF25 (K:25%).
  - *Medios tonos:* **CMY50 (C:50%, M:40%, Y:40%) vs REF50 (K:50%)** con doble recuadro de alineación.
  - *Sombras:* CMY75 (C:75%, M:64%, Y:64%) vs REF75 (K:75%).
- **Miras Vernier Slur & Doubling:** Filamentos ultrafinos (0.25 pt) verticales y horizontales para diagnosticar arrastre de papel y doblado de mantilla en prensa offset.

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
  - *Caso B (Con sangre):* Imposición de BleedBox completo y marcas de corte interiores indicando el corte exacto.
  - *Caso C (Marcas previas):* Recorte selectivo al TrimBox descartando marcas antiguas del cliente.
- Incluye cálculo en vivo de poses por pliego, porcentaje de aprovechamiento del papel y descarga del pliego con tira FOGRA y código QR de trazabilidad.

### 6.2. Exportación de Datos CIP3 / PPF v3.0 & Preajuste de Tinteros por Zonas
Permite enviar los datos de cobertura del pliego a las consolas de máquina (Heidelberg Prinect, Komori, Roland, KBA):
- **Cálculo de Cobertura Zonal:** Divide el ancho del pliego en **16, 24 o 32 zonas longitudinales** de tintero en espacio nativo DeviceCMYK.
- **Curva de Apertura de Llave (% Opening):** Determina la apertura estimada de cada cuchilla con una base lubricante mínima del 2.5% para prevenir desgaste mecánico.
- **Estimación de Consumo de Tinta:** Calcula los kilogramos y gramos de Cian, Magenta, Amarillo y Negro necesarios según la tirada (ej. 1.000 a 100.000 pliegos) y el tipo de papel (estucado, no estucado, cartoncillo o prensa).
- **Alerta de Fricción Seca:** Identifica zonas sin aporte de tinta adyacentes a zonas cargadas, avisando al maquinista para aplicar gel protector en los rodillos.
- **Descargas Disponibles:** Archivo estándar `.ppf` (PostScript CIP3 v3.0) y Ficha Técnica de Tinteros en PDF A4 apaisado para el pupitre de máquina.

### 6.3. Inspector y Corrector de Códigos de Barras y QR
- **Detección Morfológica Inteligente:** Localiza códigos EAN-13, EAN-8, UPC, Code 128 y Códigos QR en cualquier página mediante filtrado morfológico y gradientes direccionales Scharr en OpenCV.
- **Validación Aritmética GS1:** Comprueba el dígito de control (módulo 10).
- **Muestreo Cromático Nativo:** Analiza si las barras están formadas por **Negro 100% Puro (K)** o por **Negro Enriquecido (Rich Black a 4 tintas CMYK)**.
- **Corrector en 1 Clic:** Re-genera el código como elemento vectorial a 300 DPI en **100% K puro sobreimpreso** e inyecta la zona muda perimetral (*quiet zone*) opaca en blanco para garantizar su lectura en cualquier escáner comercial.

### 6.4. Procesamiento por Lote y Carpeta Caliente (Batch & Hot-Folder)
Diseñado para entornos de alta producción:
- **Subida Masiva:** Arrastre 20 o 50 PDFs a la vez en la cola de trabajo. IntelliPrint los analiza en paralelo mediante subprocesos multihilo.
- **Acciones Colectivas:** Botones para "Corregir Todo el Lote" y "Descargar Todo en ZIP Normalizado".
- **Hot-Folder Automatizado (Daemon de Fondo):**
  - Monitoriza la carpeta del sistema `hotfolder/in/`.
  - Cuando un diseñador o cliente deposita un archivo, el sistema comprueba la estabilidad de escritura (*file lock*), ejecuta el preflight y aplica las correcciones automáticas.
  - Si el archivo cumple los criterios, se mueve a `hotfolder/out_aprobados/` acompañado de su Certificado Técnico.
  - Si presenta errores irreparables, se desvía a `hotfolder/out_rechazados/` junto con la Guía Pedagógica explicativa para el cliente.

### 6.5. Inspector de Margen de Seguridad y Lomo / Medianil
Audita la proximidad de los elementos críticos respecto a los bordes de corte y plegado:
- **Detección Automática de Tipo de Impreso:**
  - *Hoja suelta (Single Leaf):* Tarjetas de visita (85 × 55 mm), folletos simples y flyers. Aplica margen de seguridad de 3 mm y lomo de 0 mm.
  - *Publicación encuadernada (Bound Publication):* Documentos de 4 o más páginas. Aplica margen de seguridad de 3 mm en cortes y reserva especial de **8 mm en el lomo/medianil** (alternando izquierda/derecha según páginas pares e impares).
- **Visor con Capas de Inspección:** Dibuja sobre el diseño la línea roja de corte (TrimBox), la línea verde de zona de seguridad, la franja morada del lomo y cajas de alerta rojas sobre los textos que invaden las zonas de riesgo.

### 6.6. Trazabilidad de Taller y Ficha para el Maquinista
- **Inyección de QR en el Pliego:** Tanto en la imposición de pliegos como al añadir marcas de imprenta, el sistema estampa en el margen técnico inferior un código QR en negro 100% K de $9 \times 9\text{ mm}$ junto al texto de cabecera.
- **Ficha Móvil de Verificación (`/verify/{job_id}`):**
  - El maquinista enfoca el QR con su teléfono o tablet a pie de máquina y accede al instante a una pantalla optimizada de taller.
  - Visualiza el semáforo de producción: `✓ LISTO PARA IMPRESIÓN` o `⚠ REQUIERE AJUSTES`.
  - Consulta los parámetros de máquina: perfil ICC de salida, cuerpos de tinta que debe preparar en batería (CMYK + Pantones), valor máximo de TAC, verificación de sangre, estado de códigos de barras y dimensiones del pliego.
  - Dispone de botones táctiles para descargar el certificado, la guía del cliente, los datos CIP3 o el pliego de imposición.

---

## 7. MODO DIDÁCTICO Y SIMULADOR DE TALLER FP

Accediendo desde el botón superior **`[ 🎓 Alumnos FP ]`**, se abre el entorno educativo diseñado específicamente para la formación de futuros técnicos en preimpresión y producción gráfica:

```
[ 🎯 1. Retos Prácticos FP ] [ ⚙️ 2. Simulador Físico ] [ 📝 3. Autoevaluación FP ] [ 📄 4. Ficha Alumno PDF ]
```

### 7.1. Banco de Retos Prácticos Reales (20 Casos de Estudio FP)
IntelliPrint incorpora un catálogo ampliado de **20 retos prácticos oficiales** basados en incidencias reales extraídas de talleres gráficos y de packaging, distribuidos en tres niveles pedagógicos progresivos:

#### A. Categoría 1: Iniciación FP (Grado Medio / 1º Grado Superior) · 7 Retos
1. **Reto 1: Tarjeta Corporativa con Rich Black y Sin Sangrado:** Tarjeta 85x55 mm con tipografía de 6 pt en 4 tintas (Rich Black 300%) y fondos al corte con 0 mm de sangre.
2. **Reto 2: Flyer Nocturno en Espacio de Color RGB sin Separación:** Flyer publicitario A6 con fotografías sRGB sin convertir y colores saturados fuera de gamut offset.
3. **Reto 3: Tríptico Envolvente con Fondos al Corte y Cajas al Ras:** Folleto A4 plegado con 0 mm de sangre y cajas de texto invadiendo las líneas de plegado.
4. **Reto 4: Cartel Promocional con Imágenes Web a 72 DPI:** Cartel A3 con imagen descargada de internet escalada al 400% y pixelado visible.
5. **Reto 5: Marcapáginas Cultural con Tipografías No Incrustadas:** Archivo con fuentes referenciadas externamente que disparan riesgo de reflow y sustitución en RIP.
6. **Reto 6: Adhesivo Promocional sin Cajas de Página (TrimBox/BleedBox):** PDF con solo MediaBox, carente de cajas geométricas de corte para mesa Kongsberg.
7. **Reto 7: Cupón Descuento con Texto Legal en Gris Tramado al 40%:** Textos legales minúsculos de 4.5 pt rotos por trama de semitono dispersa.

#### B. Categoría 2: Intermedio FP (Taller de Impresión Offset / Digital) · 7 Retos
8. **Reto 8: Folleto Promocional con TAC 365% y Líneas Pelo CTP:** Fondo nocturno saturado con TAC extremo (365%) y filetes dorados ultrafinos de 0.06 pt.
9. **Reto 9: Catálogo Comercial con 5 Tintas Planas Pantone Directas:** Catálogo presupuestado para 4 colores que incluye 5 tintas directas no convertidas.
10. **Reto 10: Dossier Corporativo con Blanco en Sobreimpresión (White Overprint):** Logotipo blanco con atributo `/OP true` que desaparece al calar en CTP.
11. **Reto 11: Carta de Menú con Texto Amarillo sobre Azul sin Reventado (Trapping):** Tipografía amarilla sobre fondo azul oscuro propensa a filetes blancos por vibración.
12. **Reto 12: Orla de Diploma con Filetes Guilloche de 0.08 pt y TAC Elevado:** Trazos de seguridad ultrafinos y masa de tinta del 330% sobre papel verjurado absorbente.
13. **Reto 13: Manual de Taller con Texto 100% K en Calado (Knockout):** Textos negros que calan las masas de color de fondo dejando huecos en CMY.
14. **Reto 14: Calendario de Sobremesa con Descompensación de Tinteros CIP3:** Gran masa oscura en el lateral izquierdo y blanco puro en el derecho con riesgo de emulsión agua-tinta.

#### C. Categoría 3: Avanzado FP (Packaging, Imposición y Acabados) · 6 Retos
15. **Reto 15: Estuche Packaging con Código de Barras EAN-13 en 4 Tintas:** Código de barras comercial tramado en cuatricromía y textos legales a 1.2 mm del troquel.
16. **Reto 16: Portada y Pliegos de Revista con Textos en el Medianil/Lomo:** Publicación grapada con textos dentro de la zona de grapa (8 mm) sin compensar la trepa.
17. **Reto 17: Etiqueta de Vino con Barniz UVI Calando en vez de Sobreimprimir:** Capa de barniz serigráfico selectivo con calado que perfora la tinta inferior.
18. **Reto 18: Prospecto Farmacéutico con Código QR en 4 Tintas sobre Papel Fino:** Código QR denso en Rich Black sobre papel biblia de 45 g/m² que empasta los módulos.
19. **Reto 19: Pliego de Imposición SRA3 sin Calles de Corte ni Marcas de Taller:** Montaje artesanal con 8 tarjetas pegadas a corte cero sin marcas ni tira de calibración.
20. **Reto 20: Envase Alimentario con Masa de Tinta y Barniz en la Solapa de Pegado:** Solapa de encolado (*Glue Flap*) saturada de tinta y barniz que destruye la adherencia de cola PUR.

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

Desde la botonera de resultados o la ficha de verificación, IntelliPrint genera las siguientes modalidades de salida documental:

### 8.1. Certificado Técnico de Preflight Oficial (PDF A4)
- Documento técnico riguroso de una página A4 para el jefe de taller y el archivo de producción.
- Incorpora sellos institucionales, código SHA-256 de integridad del archivo, datos densitométricos, geometría de cajas, perfil ICC de salida y veredicto formal de tirada.

### 8.2. Guía Pedagógica para el Cliente / Diseñador (PDF A4)
- Informe visual, cordial y didáctico redactado sin jerga hostil.
- Explica de forma gráfica al diseñador qué incidencias se encontraron en su arte final y **cómo corregirlas paso a paso en Adobe InDesign, Adobe Illustrator o Photoshop** antes de reenviar el PDF.

### 8.3. Reporte de Datos en Formato JSON
- Archivo estructurado con todas las métricas, árboles de objetos, perfiles y reglas evaluadas para su integración automática con sistemas ERP / MIS de imprenta (como Prinect, Pace o sistemas de gestión gráfica).

### 8.4. Ficha de Tinteros CIP3 y Lámina Técnica FOGRA (PDF A4)
- **Ficha de Tinteros CIP3:** Tabla densitométrica y gráfica de apertura de tornillos de tintero para colocar en la consola de máquina offset.
- **Lámina Técnica Tira FOGRA ISO 12647-2:** Póster de calibración espectrofotométrica con la tira a escala 1:1 y macroexplicación del balance de grises y trapping.

---

## 9. PREGUNTAS FRECUENTES Y SOLUCIÓN DE PROBLEMAS (FAQ)

**1. ¿Por qué el preflight marca error crítico en un texto negro si en pantalla se ve perfectamente negro?**
> En monitor, un texto compuesto por C=70 M=60 Y=50 K=90 se muestra negro oscuro. Sin embargo, en la imprenta requiere cuatro planchas de impresión distintas. Si el texto es menudo (6 u 8 pt), cualquier vibración mínima de máquina provocará un descalce con halos de color. Pulse "Taller en 1 Clic" o "Sobreimpresión" para convertirlo automáticamente a 100% K puro sobreimpreso.

**2. ¿El generador de sangre reflejada modifica el contenido original del diseño?**
> No. La sangre reflejada solo toma una franja de 3 mm del borde exterior y la proyecta simétricamente hacia afuera (más allá de la línea de corte TrimBox). La zona visible final del impreso permanece 100% inalterada.

**3. ¿Qué diferencia hay entre la Ficha Técnica para el Maquinista y el Certificado de Preflight?**
> El Certificado es un informe administrativo y de calidad en PDF A4. La Ficha del Maquinista (`/verify/{job_id}`) es una consola web móvil ultra-rápida pensada para abrirse en segundos a pie de máquina escaneando el código QR impreso en el pliego, mostrando solo los parámetros operativos esenciales (tintas, perfiles, TAC y riesgos).

**4. ¿Cómo se utiliza el archivo CIP3 (.ppf) en la máquina de imprimir?**
> Copie el archivo `.ppf` descargado a la unidad USB o carpeta compartida conectada al pupitre de control (ej. Heidelberg CP2000 o Komori KHS). La consola leerá las 32 zonas y regulará automáticamente los servomotores de los tinteros antes de iniciar el entintado de la batería.

**5. ¿Cumple IntelliPrint con las normas internacionales de Artes Gráficas?**
> Sí. Todas las tolerancias y reglas de comprobación y corrección están parametrizadas con base en las normas **ISO 12647-2** (Offset en pliegos y tiras de control), **ISO 15930** (Estándares PDF/X-1a y PDF/X-4), **ISO/IEC 15420** (especificaciones GS1 para códigos de barras), **CIP3/CIP4 PPF v3.0** y las especificaciones del **Ghent Workgroup (GWG)**.

**6. ¿Qué diferencia real hay entre el Paso 2 (Perfil de Destino) y el Paso 3 (Perfil ICC)? ¿El Paso 2 ya incrusta un perfil?**
> **No.** El Paso 2 actúa estrictamente como el **conjunto de reglas y tolerancias de inspección** (DPI mínimo admisible, sangrado obligatorio, límite de TAC, hairlines y espacios cromáticos admitidos). El Paso 2 no modifica ni incrusta nada en el PDF original. La incrustación de un perfil físico de color solo ocurre en el **Paso 3**, donde el usuario elige conservar el perfil nativo del documento o forzar la asignación de un archivo `.icc` del catálogo al ejecutar procesos de normalización o corrección ("Taller en 1 Clic", "Convertir a CMYK", etc.).

**7. ¿Por qué el perfil 'Web, Pantalla y Documento Digital (RGB)' no exige sangrado exterior?**
> Los documentos diseñados para visualización digital, navegación web, tablets o presentaciones en pantalla no atraviesan una fase de plegado o corte con guillotina mecánica en taller. Por tanto, exigir sangrado exterior generaría márgenes indeseados en los visores PDF. En este perfil, el sangrado requerido es de exactamente **0.0 mm**, se aceptan y recomiendan imágenes en espacio **sRGB / RGB**, la resolución base se ajusta a **96 ppp** y el TAC no está restringido a la absorción del papel físico.

---

```
========================================================================================
                          FIN DEL MANUAL DE USUARIO
           IntelliPrint · CPIFP Salesianos Urnieta · CIFP Mendizabala LHII
                       Departamento de Educación · Eusko Jaurlaritza
========================================================================================
```
