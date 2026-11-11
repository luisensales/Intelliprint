# Revisión de IntelliPrint — 11 de noviembre de 2026

Se confirmaron **11 problemas**, seis de prioridad alta (P1) y cinco de prioridad media (P2). **Los once están corregidos en el código local**, empezando por los seis de prioridad alta. Se conservan debajo el diagnóstico y las reproducciones originales. No se ha publicado ningún despliegue.

Las correcciones vinculan la autorización y los derivados al PDF actual, descartan respuestas de correcciones de otra selección, verifican el espacio real de los perfiles ICCBased, reciben las subidas con un plazo de 30 segundos antes de adquirir el turno de procesamiento y validan imágenes inline también en Forms anidados. Los PPF se regeneran con el origen y los parámetros solicitados. Los pliegos anteriores deben regenerarse cuando cambia el PDF; los pliegos antiguos sin identidad de origen tampoco se consideran vigentes.

También se añadieron identificadores de trabajo a los nombres del ZIP, restauración de controles mediante `finally`, criterios de resolución y color procedentes del informe, instrucciones sRGB para destinos RGB y un perfil de respaldo al eliminar el seleccionado.

## Validación realizada

- Validación final de las correcciones: **205 de 205 pruebas Python pasan**.
- JavaScript: **38 de 38 pruebas pasan**, incluidas las nuevas reproducciones de autorización, respuestas tardías, controles y perfiles.
- `pip check`: sin dependencias instaladas incompatibles.
- `git diff --check`: sin errores de espacios.
- Además de las pruebas existentes, se ejecutaron reproducciones específicas de interfaz, peticiones ASGI y API, conservación de pliegos/PPF y sobreimpresión con color ICCBased.

Que las pruebas existentes pasen no cubre los casos nuevos descritos debajo. No se realizó una comprobación externa del despliegue ni un análisis actualizado de vulnerabilidades de las dependencias.

## 1. P1 — La interfaz puede mostrar la autorización de otro PDF

**Código:** `static/index.html:3104`, `static/index.html:3610`, `static/index.html:3615`.

`renderResults()` actualiza el trabajo y oculta el panel firmado cuando corresponde, pero no actualiza `badgeRelease` ni `descRelease` con `triple_result.release`. Esos campos solo se actualizan en la respuesta de autorizar.

**Reproducción:** autorizar A y cargar B pendiente, o corregir A después de autorizarlo. La reproducción de las funciones en Node conserva `AUTHORIZED` y «Firmado por A» aunque el informe entrante esté pendiente y el servidor haya invalidado la firma.

**Impacto:** el operador ve una autorización verde que no corresponde al documento actual.

**Corrección propuesta:** derivar siempre ambos indicadores del informe actual y restablecerlos al iniciar otro análisis. La autorización debe corresponder a la huella del PDF actual.

## 2. P1 — Una respuesta tardía cambia el trabajo activo

**Código:** `static/index.html:4481`, `static/index.html:4491`, `static/index.html:3067`.

Varias correcciones individuales llaman a `renderResults()` al recibir la respuesta sin comprobar si el usuario sigue trabajando con el mismo `jobId`. El render vuelve a asignar `currentJobId`.

**Reproducción:** iniciar conversión CMYK de A, seleccionar B y resolver después la respuesta de A. La reproducción con una promesa controlada termina con `currentJobId=A` y `currentReport=A`.

**Impacto:** resultados, acciones y descargas vuelven a otro PDF sin que el usuario lo haya elegido. Batch y códigos de barras ya tienen protecciones que no cubren estas otras acciones.

**Corrección propuesta:** capturar identificador y generación de selección al iniciar cada operación; descartar la actualización de pantalla si cambiaron. Restaurar el botón de la operación aunque su respuesta ya no sea aplicable.

## 3. P1 — Se descargan pliegos y datos CIP3 anteriores a una corrección

**Código:** `app.py:745`, `app.py:2788`, `app.py:2813`, `app.py:2914`, `app.py:2996`.

Cambiar el PDF acumulado invalida la autorización, pero no invalida `imposed_pdf_path`, `last_imposition_plan` ni `last_cip3_calculation`. Las descargas comprueban la existencia del archivo, o su firma de formato PPF, sin vincularlo a la huella del PDF de origen. El nombre del PPF tampoco incorpora la tirada.

**Reproducción API:** subir un PDF, generar imposición y PPF de 16 zonas con tirada 1.000, convertir el PDF a CMYK y descargar otra vez. La huella del PDF actual cambia, pero el pliego devuelve HTTP 200 con exactamente los bytes anteriores. Pedir el PPF con `run_length=2500` devuelve también el archivo anterior y `/CIP3AdmPrintVolume 1000 def`.

**Impacto:** se puede imprimir una versión anterior o utilizar una tirada/preajuste que no corresponde a lo solicitado.

**Corrección propuesta:** vincular los derivados a la huella del origen y a todos sus parámetros; invalidarlos o regenerarlos al cambiar el PDF, la imposición o esos parámetros.

## 4. P1 — La sobreimpresión de objetos ICCBased puede dar un falso «CUMPLE»

**Código:** `pdf_graphics.py:23`, especialmente la resolución del espacio de color en las líneas 29–39; consumidores en `preflight_engine.py` y correctores de sobreimpresión.

El resolvedor no interpreta los canales o el espacio alternativo de un color ICCBased. Las comprobaciones de blanco y negro reconocen los espacios DeviceCMYK/DeviceRGB/DeviceGray, pero no su equivalente ICCBased.

**Reproducción:** PDF sin fuentes con un vector blanco definido mediante un espacio ICCBased de cuatro canales, sobreimpresión activada y OutputIntent CMYK válido. El preflight devuelve `PASS`, sin errores ni avisos. El equivalente DeviceCMYK detecta `WHITE_OVERPRINT`.

**Impacto:** una incidencia de impresión real queda fuera del dictamen y de las correcciones asociadas.

**Corrección propuesta:** resolver ICCBased a través de su perfil, número de canales y espacio alternativo, con tratamiento explícito de los espacios que no puedan verificarse. Añadir equivalencias de pruebas para blanco, negro puro y negro compuesto.

## 5. P1 — Una subida sin terminar ocupa el único turno de procesamiento

**Código:** `security_limits.py:146`, `security_limits.py:150`, `security_limits.py:170`.

El middleware adquiere el semáforo global de PDF antes de recibir el cuerpo completo. La lectura de `receive()` no tiene un plazo de terminación.

**Reproducción ASGI:** iniciar `POST /api/check` con un cuerpo de un byte declarado y mantenerlo sin terminar. El único semáforo queda adquirido aunque todavía no se haya alcanzado el manejador de análisis.

**Impacto:** un cliente lento o una conexión abierta puede bloquear el resto de las operaciones PDF hasta desconectarse.

**Corrección propuesta:** limitar el tiempo de recepción del cuerpo y adquirir el turno de procesamiento después de completar y validar la recepción, manteniendo un límite separado para las subidas concurrentes.

## 6. P1 — El límite de imágenes no cubre las imágenes inline

**Código:** `security_limits.py:62`, `security_limits.py:80`.

La validación de megapíxeles recorre imágenes XObject y sus máscaras, pero no los operadores de imagen inline del contenido de la página.

**Reproducción:** un PDF de 782 bytes con una imagen inline comprimida de 5.000 × 5.000 píxeles pasa `validate_pdf_resources()`. `get_image_info()` confirma los 25 megapíxeles, por encima del límite configurado de 20. No se rasterizó el documento para esta prueba.

**Impacto:** se elude un límite previo a la decodificación, permitiendo que documentos comprimidos pequeños lleguen a operaciones de mayor consumo de memoria.

**Corrección propuesta:** aplicar el mismo presupuesto a imágenes inline, incluidas las que estén en Forms anidados, antes de decodificar o renderizar.

## 7. P2 — La exportación ZIP pierde la distinción entre trabajos con el mismo nombre

**Código:** `hotfolder_engine.py:646`, `hotfolder_engine.py:653`, `hotfolder_engine.py:663`.

Los nombres internos del ZIP usan el nombre del PDF sin el identificador del trabajo.

**Reproducción:** dos trabajos distintos llamados `arte.pdf` producen dos entradas `PDFs_Listos_Impresion/arte_CORREGIDO.pdf`. Leer o extraer por ese nombre conserva únicamente uno de los documentos, aunque el manifiesto contiene los dos trabajos. El mismo patrón afecta a sus informes.

**Corrección propuesta:** incorporar el `jobId` a las rutas del ZIP o crear una carpeta independiente por trabajo.

## 8. P2 — Algunas correcciones dejan sus botones bloqueados tras un éxito

**Código:** `static/index.html:4250`, `static/index.html:4257`, `static/index.html:3683`, `static/index.html:4524`.

Marcas, sobreimpresión y barniz retornan después de recibir `data.report`, antes de restaurar el botón deshabilitado. El render no restablece todos esos controles.

**Reproducción Node:** una respuesta normal de marcas deja `disabled=true` y «Inyectando marcas…». El estado también puede persistir al cargar otro PDF.

**Corrección propuesta:** restaurar los controles en `finally`, con independencia de que la respuesta se muestre o se descarte.

## 9. P2 — El inventario usa un umbral de resolución distinto al del perfil

**Código:** `static/index.html:3503`.

El umbral se calcula mediante tres identificadores conocidos en lugar de leer `job_summary.target_dpi`.

**Reproducción Node:** perfil personalizado de 600 ppp e imagen CMYK de 400 ppp; la fila aparece verde como «Óptima para tirada». También se usan 300 ppp para perfiles de periódico o gran formato que exigen 200 o 150.

**Corrección propuesta:** utilizar los criterios del informe verificado, sin reconstruirlos a partir del nombre del perfil.

## 10. P2 — Se recomienda convertir a CMYK cuando el destino exige RGB

**Código:** `static/index.html:3142`, `static/index.html:3207`, `static/index.html:3517`; `client_report_generator.py:234`.

La regla `SOURCE_COLOR_DIAGNOSTIC` sirve para ambas direcciones de conversión. La interfaz y la tarjeta pedagógica la interpretan siempre como imágenes RGB que deben convertirse a CMYK.

**Reproducción:** perfil `PANTALLA_RGB` con una imagen CMYK y recomendación del motor de usar sRGB. La interfaz ofrece convertir a CMYK y la guía afirma «Imágenes en Modo de Color RGB (0 detectadas)», con instrucciones para CMYK. Una imagen RGB correcta también recibe una indicación de conversión inapropiada en el inventario.

**Corrección propuesta:** usar `required_color_family` y el color real del objeto para generar el texto y ofrecer únicamente acciones compatibles con el destino.

## 11. P2 — Eliminar el perfil seleccionado rompe el siguiente análisis

**Código:** `static/index.html:2767`, `static/index.html:2770`, `static/index.html:2994`, `static/index.html:7320`.

La recarga intenta conservar el identificador del perfil eliminado, por lo que ningún radio queda seleccionado. El inicio del análisis accede a `.value` sobre `null` antes del bloque `try`.

**Reproducción:** seleccionar un perfil personalizado, eliminarlo en el gestor y pulsar analizar sin seleccionar otro. Se produce una excepción de JavaScript y no se inicia el análisis.

**Corrección propuesta:** seleccionar un perfil de respaldo existente tras eliminar o recargar el catálogo y validar la selección antes de leer su valor.

## Orden sugerido

Primero: coherencia de autorización, identidad de pliegos/PPF y cambio accidental de trabajo. A continuación: falsos pases ICCBased y límites de subida/decodificación. Después: ZIP, criterios del perfil y estados de los controles.

Los cambios previos del repositorio se han conservado. Las pruebas confirman las reproducciones indicadas, pero no constituyen una garantía de ausencia de otros defectos.
