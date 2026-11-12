# Manual de usuario de IntelliPrint

**Edición 2026.11.2 · Actualizado el 12 de noviembre de 2026**

Guía de operación para preimpresión, taller gráfico y Formación Profesional.

CPIFP Salesianos Urnieta LHIPI · CIFP Mendizabala LHII · Departamento de Educación del Gobierno Vasco.

Este manual explica cómo preparar un PDF, elegir las condiciones de producción, interpretar el informe y utilizar cada opción de la aplicación. Incluye los controles de color, las correcciones, la imposición, los tinteros CIP3, los códigos de barras, el margen de seguridad, la cola de trabajos y las actividades de FP. Las versiones web, Markdown, Word y PDF comparten el mismo contenido.

La decisión de imprimir corresponde al responsable del trabajo. Un resultado favorable de las comprobaciones disponibles debe completarse con la revisión visual, las condiciones acordadas con el cliente y las comprobaciones del RIP y de la máquina que correspondan. Una pantalla oscura, una simulación de papel o un perfil ICC incrustado no constituyen por sí solos una certificación de impresión.

## 1 Uso del manual y conceptos de trabajo

*Itinerarios según perfil: Diseñador / Creativo (Caps. 1, 2, 3, 4, 8), Técnico de Taller (Caps. 1, 2, 3, 4, 5, 6, 8), Docente de FP (Caps. 1, 2, 3, 7, 8) y Alumno de FP (Caps. 1, 4, 5, 7, 8, 9).*

### Introducción general para todos los usuarios

IntelliPrint es una plataforma integral de preflight técnico, control de calidad editorial y preparación para artes gráficas y medios digitales. Su diseño responde tanto a las exigencias de un taller gráfico profesional de producción como a las necesidades formativas de los centros de Formación Profesional de Artes Gráficas.

Cualquiera que sea tu perfil de uso, existen cuatro premisas fundamentales en IntelliPrint:
1. El archivo PDF original nunca se destruye ni se sobreescribe en el servidor; cada corrección genera una variante derivada identificada.
2. Un perfil de preflight determina qué tolerancias técnicas se exigen, mientras que el perfil ICC define cómo se interpreta o convierte el espacio de color.
3. Un informe favorable no reemplaza la revisión humana experta del responsable ni las condiciones contractuales acordadas con el cliente.
4. Las correcciones automáticas de taller deben aplicarse con criterio selectivo, resolviendo únicamente las anomalías que impidan la tirada real.

### Perfiles de usuario y rutas recomendadas de lectura

Para obtener el máximo rendimiento según tu responsabilidad técnica, el manual ofrece cuatro itinerarios específicos:

| Perfil de usuario | Enfoque principal | Capítulos recomendados |
| --- | --- | --- |
| Diseñador / Creativo | Preparación de arte final, interpretación pedagógica del informe y Visto Bueno digital. | Capítulos 1, 2, 3, 4 y 8 |
| Técnico de Taller | Preflight GWG profundo, correcciones en 1 clic, imposición de pliegos y curvas CIP3. | Capítulos 1, 2, 3, 4, 5, 6 y 8 |
| Docente de FP | Planificación de retos formativos, diseño de perfiles a medida y rúbricas de taller. | Capítulos 1, 2, 3, 7 y 8 |
| Alumno de FP | Metodología de resolución de retos, entrenamiento con cuestionario y simulador de máquina. | Capítulos 1, 4, 5, 7, 8 y 9 |

#### Perfil 1: Diseñador gráfico, creativo y cliente

Este itinerario está concebido para profesionales del diseño (InDesign, Illustrator, Photoshop, Canva) y clientes que preparan o aprueban artes finales para imprenta o soportes digitales.

- **Preparación previa:** Configura el sangrado perimetral (habitualmente 3 mm en folletos y revistas) y respeta las cajas de corte (TrimBox) y sangrado (BleedBox). En trabajos para offset o digital comercial, evita textos en negro enriquecido de 4 tintas y trabaja en CMYK; en trabajos para pantallas o web, utiliza el espacio estándar sRGB.
- **Interpretación del informe:** Consulta la *Guía de Arte Final* simplificada. No necesitas descifrar curvas técnicas complejas: el sistema resume el estado en cuatro áreas clave (Geometría, Color, Fuentes y Cobertura) con indicaciones pedagógicas de cómo corregir en tu programa de maquetación si fuera necesario.
- **Portal de Visto Bueno digital:** Revisa en pantalla la prueba acumulativa generada, valida que los textos, paginación y colores correspondan al encargo y firma digitalmente la orden de impresión o describe los cambios requeridos.

#### Perfil 2: Técnico de preimpresión y taller gráfico

Este itinerario se dirige a los responsables de preimpresión y operarios de taller que reciben artes finales heterogéneos y deben garantizar una entrada limpia y sin paradas en máquina.

- **Validación rigurosa GWG:** Comprobación estricta de estándares Ghent Workgroup según el soporte de salida: Offset comercial (300 % TAC), Impresión digital (200 % TAC), Prensa / Periódico (240 % TAC), Envase y packaging en cartoncillo y Gran Formato.
- **Taller en 1 Clic:** Corrección de incidencias sin tener que devolver el archivo al cliente: generación geométrica de sangrado por efecto espejo perimetral, incrustación de tipografías del sistema, vectorización de fuentes problemáticas y limitación de cobertura excesiva TAC mediante algoritmos UCR/GCR conservando el canal negro (K).
- **Módulos de producción:** Generación de imposición de pliegos normalizados (cabeza con cabeza, signaturas, marcas de corte y tiras de control FOGRA ISO 12647-2) y cálculo de curvas de apertura de tinteros CIP3 (formato PPF) para su carga directa en la mesa de control de la máquina de imprimir.

#### Perfil 3: Docente de Formación Profesional

Este itinerario está diseñado para el profesorado de los ciclos formativos de Grado Medio (Preimpresión Digital, Impresión Gráfica) y Grado Superior (Diseño y Gestión de la Producción Gráfica).

- **Catálogo de 20 retos formativos:** Banco estructurado de escenarios didácticos clasificados por nivel de dificultad (Básico, Intermedio, Avanzado) con fallos reales de imprenta preparados para el aula: desde problemas geométricos elementales hasta trampas complejas de sobreimpresión, tintas planas no convertidas y perfiles cruzados.
- **Perfiles de preflight personalizados:** Editor integrado para crear especificaciones de examen o de prácticas de taller con tolerancias a medida (resolución mínima, TAC límite, sangrado requerido, fuentes trazadas).
- **Rúbricas y seguimiento pedagógico:** Pautas para evaluar la capacidad diagnóstica del alumnado, diferenciando la detección analítica del problema frente a la corrección mecánica no justificada.

#### Perfil 4: Alumnado y estudiantes de artes gráficas

Este itinerario acompaña al estudiante en su proceso de aprendizaje técnico y desarrollo de competencias profesionales de preimpresión.

- **Metodología de resolución:** Aprende a interpretar el diagnóstico antes de pulsar botones de corrección. Identifica qué causa cada aviso o error y cómo afectaría al proceso de tirada en máquina.
- **Cuestionario técnico y simuladores:** Módulo de autoevaluación interactivo con preguntas de taller, retroalimentación inmediata sobre la respuesta correcta y simulador gráfico de defectos de impresión (repintado por exceso de tinta, corte con filete blanco por falta de sangrado, fuera de registro por holguras mecánicas).
- **Glosario y buenas prácticas:** Vocabulario técnico de la industria gráfica (ISO 12647, GWG, OutputIntent, UCR, GCR, tramado, ganancia de punto) para dominar el lenguaje del taller.

### Qué hace IntelliPrint

IntelliPrint analiza documentos PDF y genera un informe con tres partes independientes: estado técnico, revisión editorial y autorización de salida. También ofrece herramientas para modificar una copia del documento y preparar determinados entregables del taller. Se accede desde [la aplicación web](https://intelliprint.onrender.com/) o desde una instalación local administrada por el centro.

El perfil de preflight establece las condiciones que se comprueban. El perfil ICC describe una condición de reproducción de color. El primero responde a «qué requisitos tiene este trabajo»; el segundo, a «cómo se declara o transforma su color». Elegir Offset 300 % no convierte automáticamente todas las imágenes en CMYK. Elegir un ICC CMYK tampoco crea sangrado, incrusta fuentes ni mejora una imagen de baja resolución.

### Orden recomendado de operación

1. Conserva fuera de la aplicación el PDF recibido y, si existe, el archivo de diseño original.
2. Carga el PDF, selecciona el perfil de preflight y decide si se conserva o se cambia el ICC documental.
3. Ejecuta la verificación y lee los errores, avisos y métricas antes de corregir.
4. Revisa el texto antes de trazar fuentes. Aplica únicamente las correcciones necesarias para el destino real.
5. Comprueba las separaciones, el comparador y los márgenes. Revisa de nuevo las incidencias que permanecen.
6. Genera la imposición, CIP3 u otros entregables que necesite el trabajo.
7. Registra la decisión del responsable y descarga el PDF final y los informes que deban archivarse.

### Unidades y resultados

| Término | Cómo interpretarlo |
| --- | --- |
| mm | Tamaños de página, sangrado, calles de corte y márgenes. |
| pt | Grosor de trazos y tamaño tipográfico. Un punto equivale aproximadamente a 0,353 mm. |
| ppp o DPI | Resolución efectiva de una imagen al tamaño colocado. No equivale a cambiar su etiqueta de resolución. |
| C M Y K | Porcentajes o canales de cian, magenta, amarillo y negro. |
| TAC | Suma de las cuatro tintas de proceso en una zona. Puede llegar a 400 %. |
| Error | Incidencia técnica que impide que el informe dé el trabajo por conforme. |
| Aviso | Situación que requiere una decisión o revisión, aunque no siempre impida producir. |
| No medido | No existe una medición disponible; no debe interpretarse como cero ni como conformidad. |

### Límites que conviene conocer antes de empezar

La aplicación comprueba las reglas que tiene implementadas; no sustituye una validación completa de cualquier variante PDF/X, una prueba contractual de color ni una verificación certificada de códigos. La estimación TAC combina las muestras de imágenes CMYK con una composición de página hasta 72 ppp y resolución de render limitada. Un detalle vectorial muy pequeño o un comportamiento específico del RIP requiere comprobación adicional.

La conversión automática RGB a CMYK trabaja sobre imágenes embebidas. No es una conversión general de todos los textos, vectores, patrones y transparencias del documento. El limitador TAC modifica imágenes CMYK y conserva el canal K; una cobertura excesiva que proceda de otros objetos puede seguir apareciendo en el informe. Estas limitaciones explican por qué una acción puede completarse y quedar todavía un dictamen «NO CUMPLE».

## 2 Acceso y navegación de la interfaz

*Perfiles recomendados: Diseñador / Creativo, Técnico de Taller, Docente de FP.*

<!-- ui-controls: pdfFileInput -->

### Acceso y primera pantalla

Abre la dirección de la aplicación en un navegador actual con JavaScript habilitado. La primera pantalla contiene el archivo de entrada, el perfil de verificación y la selección ICC. En un servicio gratuito puede haber una espera inicial al reactivarse el servidor. Espera a que se carguen los catálogos antes de iniciar el análisis.

El botón de inicio y el logotipo de IntelliPrint llevan a la aplicación. Los logotipos institucionales enlazan a las webs de los centros y del departamento de educación; no son herramientas de análisis. El indicador «Motor Activo» identifica la interfaz disponible, pero no acredita que un documento concreto haya superado su revisión.

### Botones de la cabecera

La barra superior de IntelliPrint agrupa las herramientas por bloques de trabajo (**Flujo**, **Taller**, **Aula FP**, **Entorno** y **Acceso Taller**):

| Opción | Uso y efecto |
| --- | --- |
| Acceso Taller | Abre el panel de autenticación de usuarios y roles (RBAC), las cuentas demo de taller y el registro individual con código de grupo FP. |
| Nuevo PDF | Limpia la selección y el informe mostrado para comenzar otro trabajo. Descarga antes los resultados que quieras conservar. No equivale a borrar los archivos del servidor. |
| Trabajos | Abre el gestor de trabajos activos con filtros de búsqueda, estado de caducidad (24 h), recarga rápida de sesiones y descarga de Paquetes de Producción ZIP. |
| Perfiles | Abre la lista de perfiles y su editor personalizado (crear, copiar, modificar, importar y exportar en JSON). También se llega desde Gestionar Perfiles. |
| Orden Producción | Conecta el documento con recetas reales de producto, máquina, papel y acabados para calcular pliegos y emitir el Job Ticket oficial en PDF. |
| Validación GWG | Lanza la auditoría normativa contra estándares GWG 2015 / ISO PDF/X sobre el PDF acumulado actual y descarga su certificado pericial. |
| Simulador FP | Abre el módulo didáctico: catálogo de 20 retos prácticos, 4 simuladores físicos de máquina, autoevaluación y ficha del alumno PDF. |
| Panel Docente | Abre el aula virtual de FP: gestión de grupos, códigos de clase, prácticas, evaluación por rúbricas ponderadas, gráficas de evolución, exportación CSV y administración de cuentas. |
| Manual (PDF) | Abre este manual en el lector web interactivo con filtro por perfil y permite descargar el manual oficial en PDF. |
| Cabina D50 | Cambia al tema oscuro antirreflejo de cabina de prensa y vuelve al modo de oficina al pulsarlo de nuevo. La elección se recuerda en ese navegador. |
| Pantalla Completa | Solicita el modo kiosko o pantalla completa del navegador. Se sale con el mismo control o con la tecla Esc cuando el navegador lo permite. |

El modo Cabina D50 reduce el brillo visual de la interfaz para pupitres de prensa. No calibra el monitor, no instala un perfil de pantalla ni controla la iluminación física D50. Para juzgar color hay que disponer de un monitor y unas condiciones de observación adecuados.

### Acceso Taller, roles del sistema y sesión única

El botón **Acceso Taller** permite identificarse mediante usuario o correo electrónico y contraseña, acceder mediante **cuentas demo** rápidas (*Jefe Taller*, *CTP / Preimpresión*, *Profesor FP*, *Diseñadora*, *Alumno FP* y *Admin*) o crear una cuenta individual en la pestaña **Crear Cuenta (Email)**.

| Rol del sistema | Permisos y responsabilidades principales |
| --- | --- |
| `admin` | Acceso completo al sistema, gestión de usuarios, aprobación de solicitudes de rol y auditoría general. |
| `responsable` | Jefe de taller: autorización final de pase a producción, gestión de perfiles, control del Hot-Folder y versiones. |
| `preimpresion` | Técnico CTP / preimpresión: correcciones en 1 clic, imposición de pliegos, curvas CIP3, órdenes de producción, validación GWG y enlaces de Visto Bueno cliente. |
| `docente` | Profesorado FP: creación de grupos y códigos de clase, publicación de prácticas, evaluación con rúbricas y seguimiento del alumnado. |
| `diseñador` | Creativo o cliente: subida de archivos, preflight, lectura de informes pedagógicos y entrega de trabajos. |
| `alumno` | Estudiante de FP: matriculación mediante código de clase, resolución de retos, simuladores, cuestionario y entregas al docente. |

El registro individual activa al instante las cuentas básicas (*Alumno/a FP* y *Diseñador/a*). Si durante el alta el estudiante introduce un **Código de Grupo FP** válido, queda matriculado automáticamente en ese grupo. Las solicitudes de roles sensibles (*Docente*, *Preimpresión* o *Responsable*) quedan pendientes hasta su validación administrativa. Por seguridad, el sistema aplica una política de **sesión única activa** por cuenta: al iniciar sesión desde un nuevo navegador se cierra la sesión anterior de esa misma cuenta.

### Herramientas después de analizar

La zona superior del informe organiza las operaciones del documento activo en cuatro bloques diferenciados:

1. **1. Correcciones:** Acceso directo a **Taller en 1 Clic** para aplicar correcciones acumuladas en lote sobre el PDF activo.
2. **2. Geometría & Códigos:** Abre los inspectores de **Códigos & QR** y **Margen & Lomo**.
3. **3. Validación y Entrega:** Reúne **Validar GWG**, **VºBº Cliente** (enlace seguro de aprobación externa), **Entregar a FP** (envío de práctica de alumno) y **Hot-Folder**.
4. **4. Pliego & Salida:** Incluye **Imposición**, **Tinteros CIP3**, **Hoja Máquina**, descarga de **Paquete ZIP** completo y accesos directos a **Ficha**, **Inf. Cliente** y **JSON**.

Inmediatamente debajo figura la **Línea Temporal de Versiones**, que muestra la versión activa (`v0001`, `v0002`, etc.) y ofrece controles de **Deshacer**, **Rehacer**, **Comparar Versiones** y descarga de **PDF Aprobado**. Las ventanas modales se cierran con su botón Cerrar o la cruz de la cabecera; cerrar un panel no deshace una corrección ya terminada. Si una acción está procesándose, espera su resultado antes de lanzar otra sobre el mismo trabajo.

### Dos recorridos breves

Para un folleto offset: carga el PDF, selecciona Offset Comercial 300 %, conserva el ICC si es el acordado con la imprenta y verifica. Revisa resolución, fuentes y sangrado. Corrige lo necesario, compara y prepara la imposición. Autoriza solo después de revisar la versión final.

Para un documento de pantalla: selecciona Web, Pantalla y Documento Digital RGB. El perfil no exige sangrado y utiliza una referencia de 96 ppp. No conviertas imágenes a CMYK ni añadas marcas de imprenta simplemente porque esos botones estén disponibles. Conserva la legibilidad y la utilidad del PDF para su destino digital.

## 3 Archivo de entrada perfiles e ICC

*Perfiles recomendados: Diseñador / Creativo, Técnico de Taller, Docente de FP.*

### Subir y comprobar un PDF

Arrastra un archivo a la zona de carga o pulsa para seleccionarlo. La aplicación muestra su nombre y permite retirarlo antes de analizar. El archivo debe ser un PDF legible con páginas y debe poder abrirse sin contraseña. Cambiar la extensión de otro formato a .pdf no lo convierte en PDF.

La inspección preliminar muestra tamaño del archivo, páginas, dimensiones de la primera página, imágenes detectadas y datos del OutputIntent. Esta inspección orienta la selección; no sustituye al preflight completo. Comprueba que las dimensiones corresponden a la pieza esperada, especialmente si el documento contiene páginas de distintos tamaños.

Después de escoger perfil e ICC, pulsa **Iniciar Verificación Preflight**. Durante el procesamiento se muestra un estado de carga. Si hay un fallo, conserva el original y revisa el mensaje. Un PDF cifrado, dañado, vacío o demasiado costoso para los recursos disponibles puede necesitar una nueva exportación desde la aplicación de diseño.

No se establece aquí un tamaño máximo universal: la viabilidad depende de las páginas, resolución de las imágenes, transparencias y memoria disponible. Para trabajos pesados, utiliza una copia optimizada de forma controlada o una instalación local adecuada. No reduzcas resolución de producción únicamente para obtener un informe rápido.

### Los seis perfiles estándar

<!-- ui-controls: name:profile -->
<!-- ui-values: name:profile=OFFSET_300,DIGITAL_200,PANTALLA_RGB,PERIODICO_TAC240,PACKAGING_CARTONCILLO,GRAN_FORMATO -->

| Perfil | Resolución sangre y TAC | Otras referencias del perfil |
| --- | --- | --- |
| Offset Comercial 300 % | 300 ppp; 3 mm; TAC máximo 300 %. | CMYK; filete mínimo 0,25 pt; zona de seguridad guardada 3 mm; admite tintas directas; exige fuentes incrustadas. |
| Impresión Digital Estándar | 200 ppp; 3 mm; TAC máximo 320 %. | CMYK; filete 0,25 pt; seguridad 3 mm; admite directas; exige fuentes incrustadas. |
| Web Pantalla y Documento Digital RGB | 96 ppp; 0 mm; referencia TAC 400 %, no evaluada como condición de impresión CMYK. | RGB; filete 0,50 pt; seguridad guardada 0 mm; no admite directas; exige fuentes incrustadas. |
| Prensa y Papel Periódico | 200 ppp; 2 mm; TAC máximo 240 %. | CMYK; filete 0,30 pt; seguridad 4 mm; no admite directas; exige fuentes incrustadas. |
| Packaging y Cartoncillo | 300 ppp; 5 mm; TAC máximo 300 %. | CMYK; filete 0,25 pt; seguridad 4 mm; admite directas; exige fuentes incrustadas. |
| Gran Formato y Cartelería | 150 ppp; 5 mm; TAC máximo 320 %. | CMYK; filete 0,35 pt; seguridad 5 mm; admite directas; exige fuentes incrustadas. |

Estos valores son los perfiles incluidos en la aplicación, no una receta válida para todas las prensas o soportes. Acuerda con el taller el ICC, la cobertura, la resolución y la geometría reales. El sangrado se comprueba analizando las zonas de corte mediante detección de contenido en los bordes: si el diseño tiene fondo blanco limpio y ningún elemento cromático o gráfico toca los márgenes, el motor no exige sangre innecesariamente.

La zona de seguridad guardada en un perfil sirve de referencia de configuración. El inspector **Margen & Lomo** dispone de sus propios campos de corte y medianil: comprueba y ajusta allí los valores que quieras inspeccionar. No supongas que cambiar un perfil mueve textos o aplica automáticamente ese margen en el diseño.

### Conservar o seleccionar el ICC documental

<!-- ui-controls: name:icc_option iccCatalogSelect -->
<!-- ui-values: name:icc_option=preserve,custom_selection -->

**Conservar el perfil embebido** es la selección inicial. Mantiene la declaración de color que tenga el PDF. Si no existe un OutputIntent válido, conservar no lo crea. El informe puede seguir señalando ausencia de ICC.

**Seleccionar perfil del catálogo** habilita el desplegable y declara ese ICC en la copia de trabajo. El catálogo depende de los archivos válidos instalados. Se admiten perfiles del catálogo, no rutas de archivos del ordenador ni direcciones arbitrarias. Elegirlo modifica la declaración documental; no transforma por sí solo todos los colores del PDF.

| ICC incluido | Uso de referencia y diferencia práctica |
| --- | --- |
| ISO Coated v2 300 % FOGRA39 | Destino CMYK estucado con referencia nominal de cobertura del 300 %. |
| ISO Coated v2 ECI FOGRA39 | Otra variante CMYK del catálogo. No se debe confundir su nombre con la variante de 300 %. |
| PSO Coated v3 FOGRA51 | Destino CMYK para la condición estucada correspondiente. |
| PSO Uncoated v3 FOGRA52 | Destino CMYK para la condición no estucada correspondiente. |
| sRGB IEC61966 2 1 | Espacio RGB para pantalla y flujos que lo requieran. |
| Adobe RGB 1998 | Espacio RGB de gama más amplia; requiere un flujo de color que lo interprete correctamente. |

No elijas un perfil por parecer más reciente o tener más gama. El correcto es el acordado para el destino del trabajo. La compatibilidad se basa en el archivo ICC válido y su familia de color; el nombre de una opción no garantiza que todos los objetos de la página hayan sido convertidos a esa condición.

### Crear editar copiar y eliminar perfiles

<!-- ui-controls: pmNameInput pmDestinationInput pmDpiInput pmBleedInput pmTacInput pmHairlineInput pmSafetyInput pmColorFamilySelect pmAllowSpotsCheck pmRequireFontsCheck importProfileFileInput -->
<!-- ui-values: pmColorFamilySelect=CMYK,RGB,GRAY -->

Abre **Perfiles Preflight**. Selecciona un perfil para ver sus valores o pulsa **Nuevo Perfil**. Si partes de uno estándar, cambia los campos y guarda una copia personalizada: los perfiles estándar no se sobrescriben ni se eliminan desde este editor. Los perfiles personalizados se guardan en el servidor y aparecen en el selector principal.

| Campo del editor | Qué introduce el usuario | Valores y uso |
| --- | --- | --- |
| Nombre del perfil | Un nombre reconocible para el taller o ejercicio. | Obligatorio. Por ejemplo, Revista offset no estucada. El servidor admite hasta 200 caracteres. |
| Destino o descripción | Prensa, soporte, acabado o propósito del perfil. | Texto que ayuda a elegirlo correctamente; no configura físicamente la máquina. |
| Resolución objetivo DPI | Resolución efectiva mínima. | El control ofrece 72 a 600, con paso 10; valor inicial 300. |
| Sangrado mínimo mm | Extensión requerida cuando haya elementos al corte. | De 0 a 15, paso 0,5; inicial 3. El cero se conserva. |
| TAC máximo porcentaje | Límite de referencia para la condición CMYK. | El control ofrece 200 a 400, paso 10; inicial 300. |
| Línea mínima CTP pt | Grosor de filete que debe revisarse. | De 0,10 a 1,00, paso 0,05; inicial 0,25. |
| Zona de seguridad mm | Referencia del perfil para los elementos vivos. | De 0 a 15, paso 0,5; inicial 3. Configura además el inspector Margen & Lomo. |
| Espacio de color | Familia de destino. | CMYK o RGB son los destinos admitidos al guardar en esta edición. La opción Escala de Grises puede aparecer en el selector, pero no es un destino de perfil guardable. |
| Permitir tintas directas Pantone | Autoriza o prohíbe separaciones adicionales. | Activado inicialmente. Desactivarlo hace que las tintas directas detectadas se señalen como no admitidas. |
| Exigir fuentes 100 % incrustadas | Controla la obligatoriedad de la incrustación. | Activado inicialmente. Desactivarlo no incrusta fuentes ni garantiza que el receptor tenga la tipografía. |

Pulsa **Guardar Perfil** para validar y guardar. **Cancelar** o **Cerrar** cierran el editor; no convierten los cambios pendientes en una configuración guardada. **Eliminar** solo está disponible para un perfil personalizado: afecta al catálogo compartido del servidor, no modifica retroactivamente los PDFs ya descargados.

Los rangos que muestra el formulario son los recomendados por esa interfaz. El servidor también valida los perfiles importados: exige valores numéricos finitos, DPI entre 1 y 9600, sangre y seguridad entre 0 y 100 mm, TAC entre 100 y 400 %, filete entre 0,01 y 10 pt, familia CMYK o RGB y casillas booleanas. No utilices estos rangos más amplios para sustituir las especificaciones de producción del taller.

### Exportar e importar perfiles

**Exportar JSON** descarga los perfiles personalizados. No es el informe JSON de un trabajo ni un archivo ICC. Guarda una copia antes de modificar o eliminar un catálogo importante.

**Importar JSON** permite escoger un archivo del catálogo personalizado. La importación valida el lote completo antes de escribir: un registro inválido o dos identificadores duplicados dentro del archivo producen un rechazo sin importar parcialmente el conjunto. Un identificador que ya exista en el catálogo no se duplica. Para actualizar un perfil existente, utiliza el editor.

Los perfiles creados por la aplicación llevan un identificador personalizado. Un JSON inventado sin identificador, con una familia no admitida o con valores fuera de rango no es una importación válida. Ante un rechazo, corrige una copia del JSON exportado y conserva el respaldo original.

## 4 Lectura y revisión del informe

*Perfiles recomendados: Diseñador / Creativo, Técnico de Taller, Docente de FP, Alumno de FP.*

### Los tres estados independientes

El bloque **Técnico** muestra CUMPLE, CUMPLE CON AVISOS o NO CUMPLE, junto con los contadores. CUMPLE significa que no quedan incidencias de las comprobaciones ejecutadas, no que se hayan medido todas las condiciones posibles de una tirada.

La **revisión editorial** indica si quedan sugerencias pendientes. La **autorización** identifica la decisión registrada por el responsable. Un archivo puede estar técnicamente conforme y pendiente de autorización, o tener avisos que el responsable debe estudiar. Corregir el PDF obliga a revisar de nuevo el resultado y vuelve a dejar pendiente la autorización de la copia corregida.

### Pestaña Incidencias técnicas

Cada tarjeta contiene categoría, página, título y explicación. Lee la explicación antes de pulsar el botón de corrección. Algunos avisos tienen una herramienta contextual; otros requieren volver a InDesign, Illustrator u otra aplicación de origen. No todas las incidencias son corregibles automáticamente.

Cuando un hallazgo dispone del botón **Ver en PDF**, al pulsarlo se abre el **Visor de incidencias** sobre la página real del documento acumulado. Este visor permite recorrer las páginas afectadas y resalta visualmente la ubicación exacta de los objetos detectados (o la zona geométrica correspondiente) para agilizar la localización del problema.

| Hallazgo habitual | Qué revisar y qué herramienta puede ayudar |
| --- | --- |
| Imagen RGB en destino CMYK | Confirmar intención y apariencia; convertir imágenes con el ICC acordado si procede. |
| Resolución insuficiente | Conseguir otra imagen o reducir su tamaño colocado en el diseño. Convertir color no añade detalle. |
| Fuente no incrustada | Incrustar desde el origen o trazar con revisión visual. Comprobar que la tipografía original es la correcta. |
| OutputIntent ausente o incompatible | Declarar un ICC válido para el destino y comprobar el color de los objetos. |
| Sangrado insuficiente | Revisar cajas y contenido real. Expandir cajas no dibuja automáticamente la parte que falta. |
| Blanco en sobreimpresión | Revisar la reserva o el texto blanco y la herramienta de sobreimpresión. Puede desaparecer en plancha. |
| Negro enriquecido pequeño o negro en calado | Examinar el tamaño, los canales y la sobreimpresión del texto. |
| Barniz o tinta técnica en calado | Confirmar el acabado y aplicar sobreimpresión técnica cuando corresponda. |
| Filete demasiado fino | Comparar con el umbral del perfil; engrosar y revisar detalle, códigos y tramas. |
| Exceso de TAC | Identificar si procede de imágenes o de otros objetos. El limitador de imágenes puede no resolver toda la página. |
| Tinta directa no admitida | Revisar el destino y convertir únicamente las tintas que deban ser cuatricromía. |

Los contadores pueden representar imágenes, operaciones de texto u objetos, según la regla. No deben leerse automáticamente como un número de palabras, glifos, planchas o páginas defectuosas. La severidad de una incidencia puede depender del perfil y de sus umbrales.

### Pestaña Revisión editorial

La revisión editorial propone posibles erratas a partir del texto extraíble del PDF y del diccionario técnico disponible. No realiza OCR de fotografías ni garantiza que un texto convertido en curvas pueda revisarse como texto. Nombres propios, siglas, marcas y vocabulario de una especialidad deben valorarse manualmente.

| Acción de una sugerencia | Resultado real |
| --- | --- |
| Aceptar | Registra que se acepta la recomendación editorial. No sustituye automáticamente el texto dentro del PDF. |
| Ignorar | Resuelve esa sugerencia para la revisión actual sin incorporarla como palabra al glosario. |
| Añadir al glosario | Guarda la palabra como vocabulario admitido para evitar ciertas advertencias futuras en ese servidor. |

Si aceptas una errata, corrígela en el archivo de diseño y exporta de nuevo cuando sea necesario. Resolver todas las sugerencias cambia el estado editorial, no el contenido físico del PDF. Revisa la ortografía antes de trazar fuentes y antes de firmar la salida. No añadas al glosario una errata solo para eliminar un aviso.

### Pestaña Métricas y Sobreimpresión

Consulta páginas, imágenes, fuentes, sangrado y perfiles detectados. La tabla de imágenes relaciona página, espacio de color, resolución efectiva, dimensiones en píxeles y tamaño colocado. Una imagen de 1200 píxeles de ancho puede tener resolución suficiente en una tarjeta e insuficiente en un cartel grande: importa su tamaño final.

Los bloques de sobreimpresión distinguen negro 100 % K, negros oscuros, blancos, negro enriquecido y tintas técnicas cuando el análisis los identifica. Los botones **Sobreimprimir 100 % K**, **Sobreimprimir barnices**, **Convertir a CMYK** y otros accesos contextualizados ejecutan acciones; consultar la tabla no cambia el PDF.

El TAC se calcula como estimación y queda registrado en el informe. Si no puede estimarse, se comunica como no medido y requiere revisión adicional. Esta edición no incorpora un mapa de calor TAC seleccionable como herramienta independiente. No debe confundirse un resumen de cobertura o el visor de color con ese mapa.

### Convertir imágenes desde las métricas

<!-- ui-controls: cmykProfileChoice -->
<!-- ui-values: cmykProfileChoice=embedded,ISOcoated_v2_300_bas.icc,ISOcoated_v2_eci.icc,PSOcoated_v3.icc,PSOuncoated_v3_FOGRA52.icc -->

Pulsa **Convertir a CMYK** para desplegar el panel. **Perfil destino** ofrece el perfil embebido en el PDF y cuatro destinos concretos: ISO Coated v2 300 % FOGRA39, ISO Coated v2 ECI, PSO Coated v3 FOGRA51 y PSO Uncoated v3 FOGRA52. La selección inicial es el embebido. Si no se encuentra un destino embebido utilizable, la operación aplica su alternativa disponible y debe revisarse el perfil informado en el resultado.

Pulsa **Convertir imágenes RGB a CMYK** y espera. El informe se vuelve a analizar; una imagen de baja resolución seguirá generando su incidencia aunque su color ya sea CMYK. Los textos y vectores RGB no se convierten por esta herramienta. Revisa pieles, colores corporativos, degradados y transparencias con especial atención.

### Pestaña Previsualización de Separaciones

<!-- ui-controls: sepPageInput sepSimProfileSelect sepChanC sepChanM sepChanY sepChanK sepSimulatePaperChk sepPaperTypeSelect sepSimulateBlackInkChk sepViewMode -->
<!-- ui-values: sepSimProfileSelect=default,PSOuncoated_v3_FOGRA52.icc,PSOcoated_v3.icc,ISOcoated_v2_300_bas.icc,ISOcoated_v2_eci.icc -->
<!-- ui-values: sepPaperTypeSelect=uncoated,coated,newsprint,kraft -->
<!-- ui-values: sepViewMode=color,grayscale -->

El visor ayuda a comprobar qué ocurre al activar o desactivar canales y cómo cambia la apariencia simulada. Trabaja sobre el documento disponible del trabajo, incluida su versión corregida cuando existe. Es una previsualización rasterizada; no es una prueba contractual ni una medida de densidad tomada en una prensa.

| Control | Opciones y uso |
| --- | --- |
| Página | Escribe un número válido o usa las flechas anterior y siguiente. La numeración visible comienza en 1. |
| Perfil de simulación | Según selección inicial, PSO Uncoated v3 FOGRA52, PSO Coated v3 FOGRA51, ISO Coated v2 300 % FOGRA39 o ISO Coated v2 ECI. Cambia la simulación visual, no convierte el archivo. |
| Cian Magenta Amarillo Negro | Cuatro casillas inicialmente activadas. Desactiva una para examinar la contribución de esa plancha. |
| Tintas directas | Casillas generadas para las tintas detectadas. Sirven para estudiar la previsualización; apagarlas no elimina la separación del PDF descargado. |
| Todas CMYK | Activa los cuatro canales de proceso. |
| Sin Negro CMY | Desactiva K. Ayuda a localizar contribuciones CMY y a revisar un supuesto negro puro. |
| Solo Plancha K | Aísla el canal negro. Resulta útil para textos y códigos. |
| Solo Cian | Aísla C para inspeccionar esa contribución. Para M o Y, usa las casillas. |
| Modo de vista | Simulación Color o Película RIP Gris. La vista en gris de una sola plancha representa su intensidad de tinta. No genera una película certificada de producción. |

La familia del perfil de simulación debe ser CMYK. Una selección inicial RGB puede requerir una alternativa CMYK para poder mostrar una simulación de imprenta. La apariencia del monitor y el procesamiento del visor influyen en lo que se ve; comprueba el resultado de producción con el flujo de color real.

### Simulación del soporte y de la tinta negra

Activa **Simular papel** para desplegar los ajustes de prueba visual. Puedes escoger Offset no estucado o natural, Estucado brillante o semimate, Papel prensa o periódico y Papel Kraft o cartoncillo reciclado. La opción no estucada figura inicialmente en el selector; al cambiar el perfil de simulación, la interfaz puede ajustar el soporte relacionado.

**Simular tinta negra** está activada inicialmente dentro de las opciones del soporte. Modifica la representación del negro del modelo de visualización. Cambiar soporte o negro simulado no modifica las tintas del PDF ni mide el papel físico que se empleará.

La lectura orientativa bajo el cursor deriva de la previsualización mostrada. No es una lectura espectrofotométrica ni debe emplearse como aceptación densitométrica de una tirada. Los acabados, tintas opacas, metalizados, DeviceN y ciertas combinaciones complejas requieren una revisión especializada; no debe asumirse equivalencia completa con cualquier RIP.

### Tintas planas desde el visor

**Convertir tintas planas a CMYK** actúa sobre el PDF; las casillas de las planchas actúan sobre la vista. Esta diferencia es esencial. La conversión general preserva las tintas identificadas como técnicas, por ejemplo barnices o troqueles. No deduzcas que una tinta se ha eliminado por dejar de verla en la pantalla: comprueba las separaciones y el informe posterior.

### Pestaña Comparador Antes y Después

<!-- ui-controls: compDpiSelect compPageInput compSliderInput -->
<!-- ui-values: compDpiSelect=100,130,160 -->

El comparador superpone dos imágenes de página y permite desplazar su división. **Antes** corresponde a la copia de entrada utilizada en el análisis; si se aplicó un ICC en la configuración inicial, esa copia puede incluir ya la declaración elegida. **Después** corresponde al PDF acumulado disponible tras las correcciones.

| Control | Uso |
| --- | --- |
| Página y flechas | Cambia la página comparada entre 1 y el total disponible. |
| Resolución | 100 DPI Rápido, 130 DPI Estándar o 160 DPI Alta nitidez. Inicialmente 130. Cambia la imagen de pantalla, no la resolución del archivo. |
| Deslizador | De 0 a 100, inicialmente 50. Desplaza la división para revelar ambas versiones. También puede arrastrarse sobre la zona prevista por el visor. |
| Actualizar | Solicita nuevamente las imágenes después de una corrección o ante una vista anterior. |
| Corregir en 1 Clic | Abre las opciones del taller para el trabajo actual. No ejecuta una corrección por sí solo. |

Si no hay correcciones registradas, se informa de vista idéntica o de ausencia de cambios. Una coincidencia visual no demuestra que no hayan cambiado fuentes, perfiles o sobreimpresiones. Del mismo modo, una diferencia de tamaño o posición puede deberse a nuevas cajas, sangrado o marcas: revisa la geometría y las dimensiones además de la apariencia.

### Línea temporal y comparador visual de versiones

Bajo los bloques de herramientas del informe se encuentra la **Línea Temporal de Versiones**, que registra cada cambio realizado (`v0001` original, `v0002` tras cada corrección) junto con su descripción.

- **Deshacer (`Ctrl+Z`) y Rehacer (`Ctrl+Y`):** Permiten retroceder o avanzar en la cadena de correcciones sin perder el historial de análisis. El panel de nodos cronológicos expandible permite restaurar cualquier versión intermedia guardada.
- **Comparar Versiones:** Abre el comparador avanzado de versiones, donde puedes elegir cualquier par de versiones (`v0001` frente a `v0003`, por ejemplo) para inspeccionarlas en modo lado a lado o activar el **mapa visual de diferencias (Diff)** y verificar alteraciones de píxeles o geometría.
- **PDF Aprobado:** Cuando existe una autorización válida para producción, se habilita la descarga directa de la entrega oficial aprobada.

### Pestaña Autorización de Salida

<!-- ui-controls: operatorNameInput releaseDecisionSelect releaseNotesInput -->
<!-- ui-values: releaseDecisionSelect=approved,approved_with_warnings,rejected -->

Introduce el **Nombre del Operario o Responsable**, escoge una **Decisión de Salida** y escribe, cuando proceda, las **Observaciones técnicas**. Pulsa el botón de firmar o registrar la autorización del panel para guardar la decisión y generar sus enlaces de salida.

| Decisión | Cuándo utilizarla |
| --- | --- |
| Autorizar paso a producción Aprobado | El responsable ha revisado la versión final y considera que cumple las condiciones acordadas. |
| Autorizar con excepciones aceptadas | Deben quedar documentadas las excepciones y su aceptación. No borra las incidencias técnicas ni las convierte en mediciones superadas. |
| Rechazar archivo Requiere nuevo arte final | El PDF necesita otra exportación, contenido nuevo o una corrección que no puede aprobarse en el estado actual. |

El registro contiene nombre, decisión, fecha y notas. Es una constancia operativa de la aplicación, no una firma electrónica criptográfica que certifique la identidad del firmante. Tras modificar el PDF, revisa y autoriza la copia corregida. La ficha del maquinista necesita un estado técnico compatible y autorización registrada para presentarlo como listo para impresión.

Para comunicar los resultados al cliente o diseñador sin tecnicismos de RIP, utiliza el enlace **Inf. Cliente (Guía de Arte Final)**, que genera un informe pedagógico de una página adaptado automáticamente al destino elegido: para imprenta muestra el estado **LISTO PARA IMPRESIÓN** bajo estándar ISO 12647-2 (CMYK, +3 mm de sangrado y límite TAC); para documentos de pantalla (**Web, Pantalla y Documento Digital RGB**) muestra **LISTO PARA PANTALLA** bajo estándar **Pantalla / Documento Digital (sRGB)** validando la legibilidad digital sin exigir CMYK ni sangrado.

## 5 Correcciones y Taller en 1 Clic

*Perfiles recomendados: Técnico de Taller, Alumno de FP.*

### Cómo se acumulan las correcciones

Cada corrección parte de la versión disponible más reciente del trabajo. El botón principal de descarga permite recuperar el PDF acumulado. Evita trabajar con una descarga antigua y asumir que incorpora cambios posteriores. Conserva una copia identificada del original y otra del resultado que finalmente autorices.

Después de una acción, revisa el informe actualizado y no solo el mensaje de operación terminada. El éxito de una herramienta significa que pudo ejecutar su operación; pueden permanecer otros errores. Si una operación falla o no puede conservar las propiedades requeridas, revisa el mensaje y vuelve al origen cuando corresponda.

### Sobreimpresión del negro blancos y negro enriquecido

**Sobreimprimir 100 % K** revisa textos negros destinados a sobreimprimir. El flujo también trata blancos en sobreimpresión y negros enriquecidos pequeños cuando se identifican. Un blanco que sobreimprime puede desaparecer; un texto pequeño de varias tintas puede producir halos por desajuste.

Usa la herramienta en el contexto de la impresión prevista. No debe aplicarse sobreimpresión indiscriminadamente a cualquier color o acabado. Los efectos especiales, reservas intencionadas, tintas opacas y trabajos con planchas técnicas deben revisarse con el taller. Una sobreimpresión de negro no es un cálculo general de reventado o trapping entre todos los colores del diseño.

Comprueba el resultado aislando K y usando Sin Negro CMY. Revisa que los elementos blancos sigan siendo reservas visibles y que los textos pequeños no hayan cambiado de apariencia de forma inaceptable. Si la fuente no estaba incrustada, verifica también la tipografía antes de autorizar.

### Sobreimpresión de barnices y tintas técnicas

**Sobreimprimir barnices** identifica tintas técnicas por su denominación y configuración. Puede ayudar a evitar que una capa de barniz cale la cuatricromía que hay debajo. Los nombres coherentes de separaciones son importantes para que el sistema pueda clasificarlas.

Antes de usarla, confirma con el impresor qué plancha debe existir y cómo debe combinarse. Barniz, troquel, estampación y tinta blanca no son intercambiables. Después, revisa que se conserve la separación y que el área cubierta siga siendo la prevista. La clasificación automática por nombres no sustituye esa comprobación.

### Convertir imágenes RGB a CMYK

La conversión utiliza un destino ICC CMYK y sustituye los datos de las imágenes que puede procesar. No aumenta su resolución, no recupera detalle perdido por compresión y no implica que todos los objetos del documento sean CMYK. Usa el panel de métricas si necesitas escoger uno de los perfiles disponibles en lugar del contexto automático de una incidencia.

Al terminar, consulta cuántas imágenes se han convertido y revisa el inventario. Una imagen omitida puede no necesitar conversión; un error durante el proceso requiere una revisión del documento. No aceptes un resultado únicamente porque el aspecto global parezca similar. Compara los colores sensibles y las zonas con transparencias.

### Convertir tintas planas a cuatricromía

Esta acción es adecuada cuando una tinta comercial debe imprimirse con CMYK y el taller lo ha acordado. Un color directo puede quedar fuera de la gama disponible y cambiar de apariencia. Conserva las planchas de acabados o corte que sí sean necesarias.

El botón general de la interfaz convierte las tintas comerciales tratables; no utiliza las casillas de visibilidad como lista de selección de conversión. Antes y después, consulta los nombres de las separaciones. Si un nombre técnico no se reconoce o la tinta debe conservarse, detén el flujo y corrige su definición desde el origen.

### Engrosar líneas finas

El corrector eleva los trazos que identifica por debajo del umbral a un grosor seguro, teniendo en cuenta la referencia del perfil cuando corresponde. La referencia habitual es 0,30 pt; perfiles más exigentes pueden necesitar más grosor. No modifica una trama completa ni garantiza conservar la estética de un patrón delicado.

Examina guillochés, planos, tablas pequeñas y elementos de precisión. Un filete que ya forma parte de una imagen raster no se convierte en un trazo vectorial mediante esta herramienta. Si el aviso permanece, puede requerirse una modificación del diseño o una comprobación más específica de las transformaciones del objeto.

### Trazar fuentes a curvas

El trazado convierte el texto de las páginas afectadas en formas y utiliza un motor PDF que conserva las propiedades de impresión comprobadas. Mantiene la geometría y el perfil documental en las condiciones admitidas. Si no puede preservar las separaciones o completar el trazado, debe revisarse el fallo en lugar de asumir que el archivo está reparado.

El texto trazado deja de funcionar como texto editable o buscable en esas páginas. Por eso la revisión editorial debe hacerse antes. El trazado tampoco puede recuperar una tipografía original que nunca estuvo incrustada: si el documento ya se visualiza con una sustitución, convertir esa sustitución a curvas no restaura la fuente del diseñador.

El botón contextual puede limitar la acción a una página señalada. El taller automático selecciona las páginas con incidencias de fuentes. En una instalación local, el trazado seguro requiere Ghostscript disponible; en el despliegue Docker se instala como dependencia. El usuario debe comparar las páginas resultantes antes de dar la tipografía por correcta.

### Ajustar cajas y sangrado geométrico

La normalización define o ajusta MediaBox, TrimBox y BleedBox respetando el contenido del documento. Si ya existe un TrimBox, trata de conservar el formato neto. Si el lienzo parece incluir el sangrado de un tamaño estándar, puede calcular el corte hacia dentro; en otros casos expande el espacio exterior.

Esto no dibuja ilustración nueva en un borde vacío. Un PDF puede tener una BleedBox formalmente correcta y seguir sin contenido que llegue hasta ella. Revisa los cuatro bordes, las medidas de corte y el informe posterior. En formatos personalizados, verifica que la inferencia geométrica no haya cambiado el tamaño final esperado.

### Generar sangre reflejada

**Extender el fondo al sangrado (reflejo)** prolonga las franjas del borde mediante copias reflejadas del contenido PDF original. Conserva las tintas, los vectores y las coordenadas del diseño; no reduce la pieza para hacer sitio a la sangre. Utiliza la medida de sangrado del perfil, que habitualmente es 3 mm, y conserva el contenido de sangre real que ya exista. Es una ayuda para casos determinados, no una reconstrucción del diseño original. En líneas diagonales, rostros, textos pegados al borde o elementos repetitivos puede producir reflejos o continuidades artificiales.

Comprueba el resultado al tamaño de producción y con el comparador. Para un encargo sensible, la solución preferible suele ser ampliar correctamente el fondo en el archivo de diseño. La sangre reflejada no desplaza los textos hacia dentro ni crea por sí sola margen de seguridad.

### Añadir Marcas FOGRA

**Marcas FOGRA**, también denominada **Añadir pautas de corte y registro** en el taller, añade marcas de corte, registro, tira de control y datos exteriores. Las pautas se alinean con el TrimBox y empiezan fuera de la zona de sangre. El área exterior aumenta para alojarlas, mientras el tamaño de corte y el diseño mantienen sus medidas. Se conserva el fondo extendido; no se encaja la página completa dentro del corte. Revisa siempre las marcas y el contenido útil.

La tira es un elemento gráfico de control. Imprimirla no calibra una prensa ni acredita conformidad con una norma. Sus parches deben medirse con el instrumento y procedimiento adecuados. La lámina FOGRA descargable es una guía independiente: descargarla no añade marcas al trabajo.

Si el PDF ya contiene marcas, evita duplicarlas sin motivo. El motor de imposición también puede añadir marcas y una tira: decide dónde deben generarse dentro del flujo del taller.

### Limitar TAC

**Limitar TAC** reduce la suma de C, M e Y de las imágenes CMYK que superen el límite, conservando K. El límite se toma del contexto del perfil cuando se usa el control correspondiente; un valor nominal de 300 % en un texto de ayuda no debe sustituir la comprobación del destino real.

El limitador admite límites entre 100 y 400 %. No es una conversión integral de color a un perfil con un GCR o UCR específico de la imprenta. Puede cambiar el equilibrio visual de una imagen y no corrige automáticamente cualquier relleno vectorial, transparencia, tinta directa o acumulación de objetos. Si el nuevo informe sigue indicando exceso, identifica su origen en el diseño.

La medición TAC posterior es estimada. Utiliza los resultados como diagnóstico y confirma los casos críticos en el RIP. Un campo sin medición debe mostrarse y tratarse como no medido, no como un valor favorable por defecto.

### Opciones de Taller en 1 Clic

<!-- ui-controls: batchChkTrapping batchChkHairlines batchChkFonts batchChkGeometry batchChkMirrorBleed batchChkCmyk batchChkSpots batchChkIcc batchChkTac batchChkMarks -->

Este panel corrige **un trabajo**, con sus opciones seleccionadas. No es la cola de varios PDFs. Abre el taller, revisa las diez casillas, pulsa **Aplicar correcciones seleccionadas** y espera el informe del lote de acciones. Cerrar el panel no revierte las operaciones que ya hayan terminado.

| Casilla | Estado inicial | Qué incluye o qué debe comprobarse |
| --- | --- | --- |
| Trapping y sobreimpresión | Activada | Tratamientos de blanco, negro enriquecido, negro 100 % K y tintas técnicas del flujo disponible. No equivale a un trapping general del documento. |
| Líneas finas | Activada | Engrosamiento según los umbrales aplicables. Revisar detalles de precisión. |
| Fuentes | Activada | Trazado de páginas con incidencias de fuentes; se omite el trabajo pesado si no hace falta. |
| Geometría y cajas | Activada | Normalización de corte y espacio de sangrado. No crea por sí sola contenido exterior. |
| Extender el fondo al sangrado | Activada en perfiles de imprenta con sangre mayor que cero | Reflejo de los bordes sin reducir el diseño ni cambiar sus tintas. Revisar imágenes y elementos cercanos al corte. |
| Imágenes RGB a CMYK | Activada | Conversión de imágenes en los destinos CMYK; no es conversión de todos los objetos. |
| Tintas planas a CMYK | Desactivada | Descomposición de tintas comerciales tratables preservando las técnicas identificadas. |
| OutputIntent ICC | Activada | Declaración ICC de destino del flujo. Revisar cuál queda informado en el resultado. |
| Limitación TAC | Activada | Limitación de imágenes CMYK según el perfil. No garantiza que desaparezca cualquier exceso vectorial. |
| Pautas de corte y registro | Activada en perfiles CMYK de imprenta | Marcas fuera de la sangre, conservando el tamaño de corte. Desactivar si el destino no requiere marcas en la pieza individual. |

Al abrir el taller por primera vez para un trabajo de imprenta se proponen la extensión del fondo y las pautas. En un perfil RGB de pantalla se dejan desmarcadas y el flujo no añade marcas de imprenta. Puedes desmarcar cualquiera de las opciones propuestas; al volver a abrir el panel del mismo trabajo se conserva tu elección. Para otro trabajo se vuelven a proponer las opciones de su perfil.

El flujo sigue un orden de correcciones; no ejecuta necesariamente las casillas en el orden en que las pulsas. Normalizar cajas define espacio; Extender el fondo lo llena con contenido reflejado y Pautas de corte coloca las marcas por fuera. Revisa los pasos aplicados, errores pendientes, avisos y dictamen final. **Lote completado** indica que terminó el procesamiento, no una autorización de salida.

## 6 Módulos de producción

*Perfiles recomendados: Técnico de Taller.*

### Imposición de pliegos

<!-- ui-controls: name:impMode impSheetSize impOrientation impGapXSelect impGapYSelect impBleedSelect impMarksChk impRegChk impColorBarChk impSlugChk -->
<!-- ui-values: name:impMode=step_and_repeat,booklet -->
<!-- ui-values: impSheetSize=SRA3,500x700,A3,A4,B3,SRA4 -->
<!-- ui-values: impOrientation=auto,landscape,portrait -->
<!-- ui-values: impGapXSelect=4.0,0.0,2.0,3.0,5.0,6.0,8.0,10.0 -->
<!-- ui-values: impGapYSelect=4.0,0.0,2.0,3.0,5.0,6.0,8.0,10.0 -->
<!-- ui-values: impBleedSelect=2.0,3.0,0.0 -->

Abre **Imposición Pliego** después de revisar el PDF. La imposición prepara otro archivo de pliegos; no sustituye la edición del diseño. Observa la cuadrícula calculada, tamaño de pose, orientación, número de pliegos y avisos antes de generar.

| Control | Opciones disponibles |
| --- | --- |
| Modo | Paso y repetición o Cuadernillo grapado. El primero es el inicial. Una sola página se repite; un documento de varias páginas se distribuye según el plan. |
| Formato de pliego | SRA3 320 × 450 mm inicial; 500 × 700 mm B2 Offset; A3 297 × 420 mm; A4 210 × 297 mm; B3 350 × 500 mm; SRA4 225 × 320 mm. |
| Orientación de pliego | Auto Máximo poses inicial; Horizontal Apaisado; Vertical. Auto busca aprovechamiento, no conoce las restricciones reales de pinza o fibra de la máquina. |
| Calle horizontal X | 0, 2, 3, 4, 5, 6, 8 o 10 mm. Inicial 4. Separa columnas. |
| Calle vertical Y | Los mismos valores, independiente de X. Inicial 4. Separa filas. |
| Sangrado por pose | 2 mm inicial; 3 mm estándar; 0 mm corte neto. Seleccionar 3 no crea contenido que falte en el PDF de origen. |
| Marcas de corte | Activadas inicialmente. Generan referencias de corte en el pliego. |
| Cruces de registro | Activadas inicialmente. Añaden referencias para el registro de impresión. |
| Tira o barra de control | Activada inicialmente. Añade el elemento de control de color previsto. |
| Slug o información | Activado inicialmente. Añade información exterior del trabajo y los elementos asociados del generador. |

Una calle de 0 mm es corte compartido y exige que la producción lo permita. No la elijas solo para obtener una pose más si puede aparecer contaminación entre piezas o faltar espacio para el sangrado. X e Y permiten calles diferentes para adaptar el corte; ninguna de las dos configura físicamente una guillotina.

La vista previa se recalcula al cambiar parámetros. **Generar Pliego PDF** crea el archivo descargable con esos valores. Consulta después el número de páginas del resultado, las marcas, los bordes y el orden real. Si cambias opciones tras generar, vuelve a generar antes de descargar el resultado definitivo; una vista previa nueva no reescribe por sí sola un PDF ya generado.

### Cuadernillo y geometrías de origen

En **Cuadernillo grapado**, el motor organiza parejas de páginas para doblado y grapado y completa el múltiplo de cuatro con posiciones en blanco cuando haga falta. Verifica portada, contraportada, caras y secuencia con una maqueta doblada. El plan no resuelve automáticamente todas las necesidades de compensación de lomo, creep, tipos de encuadernación o alimentación de una prensa concreta.

El motor distingue PDFs sin sangre, con sangre y con una zona de marcas ya incluida. La detección se basa en las cajas y sus dimensiones. No sustituye la revisión de un PDF mal definido, con páginas de tamaños diferentes o con marcas que formen parte del contenido de la pieza. En esos casos revisa página a página y normaliza desde el origen si es necesario.

El aprovechamiento calculado es geométrico. No incluye por sí mismo restricciones de fibra, pinzas, contrapinzas, zonas no imprimibles, orden de acabados o puesta en máquina. Confirma estas condiciones antes de utilizar un pliego para producción.

### Tinteros CIP3 y cálculo de consumo

<!-- ui-controls: cip3NumZones cip3RunLength cip3PaperType -->
<!-- ui-values: cip3NumZones=32,24,16 -->
<!-- ui-values: cip3PaperType=coated,uncoated,carton,newspaper -->

Abre **Tinteros CIP3** para calcular coberturas por franjas y preparar archivos de preajuste. Si existe un pliego de imposición disponible, el flujo automático puede utilizarlo; en otro caso se calcula sobre el PDF del trabajo. Comprueba la fuente y dimensiones que devuelve el módulo. El cálculo se realiza para la página de referencia del documento utilizado; no es una suma automática de todas las caras de cualquier publicación.

| Control | Opciones y significado |
| --- | --- |
| Número de zonas o llaves | 32 inicial, 24 o 16. Escoge el número que corresponda a la configuración real de la prensa y al flujo de importación. |
| Tirada en pliegos | Inicial 1000; el control ofrece 100 a 1 000 000, paso 500. Influye en la estimación de consumo. |
| Tipo de papel o soporte | Estucado comercial, Offset no estucado, Cartoncillo packaging o Papel prensa. Selecciona el modelo que se aproxime al trabajo. |
| Calcular Zonas | Recalcula el gráfico, la tabla y los archivos con la configuración actual. |
| Filtro de canal | Todos CMYK, Cian, Magenta, Amarillo o Negro. Cambia la representación de barras, no la configuración física de la máquina. |

Los coeficientes visibles junto a los soportes —1,20; 0,95; 1,30 y 0,85 g/m²— se utilizan como referencias del modelo de consumo de tinta. No representan el gramaje del papel que hay que comprar. Los resultados en gramos y kilogramos son estimaciones basadas en cobertura, superficie y tirada; deben ajustarse con experiencia de máquina, tinta, maculatura y condiciones reales.

La tabla relaciona zona, posición transversal, coberturas CMYK y apertura orientativa. La cobertura es el porcentaje de área analizada; la apertura es una propuesta de preajuste. No son dos maneras equivalentes de medir densidad. Las señales de posible fricción seca o desequilibrio de zonas requieren valoración del operario.

### Descargar y utilizar PPF y ficha de tinteros

Después de calcular, utiliza los enlaces de **PPF CIP3** y **Ficha de tinteros PDF**. Cambiar el número de zonas o la tirada requiere recalcular antes de obtener un entregable coherente con los nuevos valores.

El archivo PPF es un entregable para un flujo que lo admita; descargarlo no envía órdenes a la prensa. Verifica compatibilidad, orientación, lado de máquina, dimensiones y asignación de llaves en el sistema receptor. La ficha PDF sirve para revisión y comunicación del ajuste, no como sustituto de la puesta a punto real.

### Inspector y corrector de códigos de barras y QR

Abre **Códigos & QR** para inspeccionar el PDF acumulado. El módulo muestra los códigos que sus detectores consiguen reconocer, el tipo, contenido leído, página, dimensiones y observaciones sobre color o zona de silencio. En ciertos códigos lineales puede comprobar el dígito de control cuando el formato se identifica.

**Corregir Todos a 100 % K** actúa sobre los hallazgos tratables. Las tarjetas pueden ofrecer **Corregir** de forma individual. El flujo utiliza una captura del código, una reserva blanca y una reconstrucción del negro puro, y comprueba que se conserve la lectura. No es necesario inventar un contenido nuevo ni teclear otro código para esta acción.

La zona de silencio es el espacio libre que permite distinguir el símbolo. La reserva puede cubrir contenido cercano: revisa su tamaño y los textos o imágenes que rodean al código. La reconstrucción puede rasterizar esa región; no la consideres una reedición vectorial del símbolo original.

Que no se encuentre un código no demuestra que no exista. Códigos pequeños, dañados, inclinados, compuestos por ciertas simbologías o con poca calidad pueden no reconocerse. Comprueba la lectura del PDF final y de una muestra impresa con los lectores y requisitos de verificación del destino. Un QR legible en pantalla no acredita por sí solo el grado de calidad de un código comercial impreso.

### Inspector Margen y Lomo

<!-- ui-controls: smBindingModeSelect smSafetyMarginInput smGutterMarginInput smPageSelect -->
<!-- ui-values: smBindingModeSelect=auto,single_leaf,bound_publication -->
<!-- ui-values: smPageSelect=0 -->

Abre **Margen & Lomo** para estudiar la proximidad de los elementos vivos al corte y al medianil. Este módulo inspecciona y representa riesgos; no recoloca automáticamente textos, imágenes ni páginas.

| Control | Valores y uso |
| --- | --- |
| Tipo de pieza o encuadernación | Auto-detectar inicial; Hoja suelta o tarjeta sin lomo; Publicación encuadernada con lomo o medianil. Escoge manualmente si la deducción no corresponde al trabajo. |
| Margen de seguridad de corte | Inicial 3 mm; control entre 1 y 10 mm, paso 0,5. Es una distancia hacia dentro desde la línea de corte. |
| Margen de lomo o medianil | Inicial 8 mm; control entre 4 y 25 mm, paso 0,5. Se utiliza cuando el modo considera que hay lomo. |
| Página | Lista de páginas con indicaciones de incidencias y lado del lomo cuando corresponde. Cambia la página representada. |

El modo automático trata documentos de menos de cuatro páginas como piezas sin lomo. En documentos mayores también considera las dimensiones para reconocer tarjetas pequeñas. Esta regla es una ayuda, no una identificación de todos los tipos de encuadernación. Un juego de tarjetas puede tener muchas páginas y no llevar lomo; una pieza especial puede requerir otro criterio.

Consulta la lista de **Elementos Fuera de Margen** y la leyenda: corte, seguridad, medianil y zonas de peligro. Los elementos muy próximos al corte pueden tener un riesgo mayor que los que solo invaden una referencia preventiva. Corrige las posiciones en el diseño y exporta nuevamente cuando corresponda.

### Cola de Lotes Multi PDF

<!-- ui-controls: batchInputFiles -->

Abre **Hot-Folder** y selecciona la pestaña **Cola de Lotes Multi-PDF**. Arrastra varios PDFs o utiliza el selector múltiple. La carga utiliza el contexto de perfil e ICC de la pantalla principal; revisa esas selecciones antes de añadir el conjunto. No debe usarse un único perfil por comodidad si los trabajos tienen destinos distintos.

La tabla muestra nombre, páginas, tamaño, estado e incidencias. **Ver** abre el informe del trabajo de la fila. **Corregir Todo el Lote** ejecuta la cadena masiva; los resultados individuales pueden ser conformes, mantener avisos, seguir rechazados o fallar. Revisa las filas y no supongas que todas quedan aprobadas por haber terminado la petición general.

**Descargar Todo en ZIP** reúne los PDFs e informes disponibles. Comprueba que el ZIP contiene los trabajos esperados y que sus documentos corresponden al estado final revisado. **Limpiar cola** limpia la lista de esa sesión de interfaz; no es una orden de borrado seguro de los archivos temporales del servidor.

La cola masiva y Taller en 1 Clic cumplen funciones diferentes. La primera maneja varios trabajos con una cadena de procesamiento; el segundo permite elegir diez acciones para el trabajo actualmente abierto. No esperes que las casillas de un panel se conviertan automáticamente en opciones individualizadas de cada fila del otro.

### Carpeta Caliente Hot Folder

La pestaña **Carpeta Caliente** consulta un servicio que vigila carpetas del servidor. No vigila una carpeta del ordenador del navegador. En una instalación local, las carpetas pertenecen al equipo que ejecuta IntelliPrint; en Render pertenecen al contenedor del servicio.

| Control o zona | Función |
| --- | --- |
| Iniciar Demonio | Activa el servicio de vigilancia cuando no está ejecutándose. |
| Detener Demonio | Solicita detener la vigilancia. No debe interpretarse como deshacer un archivo ya procesado. |
| Escanear Ahora | Solicita un procesamiento de los candidatos disponibles sin esperar el siguiente ciclo. |
| Contadores y registro | Muestran cola y salidas, con eventos de aprobado, rechazado o error. Revisa los mensajes individuales. |
| Descargar Aprobados ZIP | Empaqueta la salida disponible de esa categoría, incluidos los documentos generados allí. |
| Descargar Rechazados ZIP | Permite recuperar la salida rechazada para estudiar sus incidencias o corregir el origen. |

Las carpetas de trabajo son hotfolder/in, processing, out_aprobados y out_rechazados. El administrador debe depositar los PDFs en la entrada mediante un mecanismo de acceso al servidor. La pestaña de carga múltiple no equivale a instalar un vigilante de carpetas o un cliente FTP en el ordenador del usuario.

El servicio incluido parte de un perfil y una cadena predeterminados. La interfaz de esta edición ofrece iniciar, detener y escanear; no incluye un editor completo de rutas, perfil, horario, reglas de enrutamiento o credenciales FTP. Una instalación permanente requiere que el administrador prepare almacenamiento y operación adecuados.

### Ficha del maquinista y trazabilidad QR

**Ficha Maquinista** abre una vista de producción asociada al identificador del trabajo. Permite consultar el estado técnico y de autorización, archivo, ICC declarado, tintas, datos de sangrado, TAC disponible y enlaces de informes. Los elementos que no se hayan medido no deben tratarse como comprobaciones favorables.

Los generadores de pliegos pueden incorporar un QR que conduce a esa ficha. Escanéalo con una cámara o lector con acceso al servidor. El QR identifica una dirección de consulta: no contiene dentro todo el PDF ni todo el historial del trabajo y no es una autorización independiente para imprimir.

La ficha necesita que el trabajo siga existiendo en el servidor. Para un archivo de producción duradero, conserva los PDFs e informes descargados; no dependas únicamente del QR. Comprueba la vigencia de los datos después de corregir, generar una nueva versión o registrar una nueva decisión.

### Orden de producción y hoja de ruta de taller

El módulo **Orden Producción** conecta el documento PDF con los parámetros reales de fabricación del taller gráfico para calcular recetas de tirada y emitir una hoja de ruta técnica (**Job Ticket**).

- **Selección de parámetros:** Permite definir tirada de ejemplares, tipo de producto (folleto, díptico, revista, tarjeta, cartel o envase), prensa o máquina de impresión, formato de pliego, papel/gramaje, tipo de impresión (1 o 2 caras), juego de tintas y acabados (plegado, grapado, troquelado o barnizado).
- **Cálculo y vinculación:** Calcula automáticamente el aprovechamiento del pliego, poses por cara y pliegos brutos necesarios (incluyendo merma estimada de puesta en marcha) y puede vincularse al preflight e imposición del trabajo activo.
- **Hoja de ruta PDF:** Genera y descarga el **Job Ticket PDF** con las instrucciones completas para preimpresión, máquina de imprimir y postimpresión.

### Validación de producción GWG 2015 e ISO PDF/X

**Validación GWG** (accesible desde la cabecera o desde el botón **Validar GWG** del bloque de validación) ejecuta una auditoría pericial independiente sobre la **versión acumulada más reciente** del trabajo activo (incorporando todas las correcciones realizadas).

- **Estándares disponibles:** Evalúa conforme a las especificaciones del Ghent Workgroup y normas ISO: GWG 2015 Offset Comercial (`Sheetfed Offset`), Impresión Digital, Prensa (`Newspaper`), Packaging o variantes **PDF/X-1a** y **PDF/X-4**.
- **Evidencias y certificado:** Presenta el listado de reglas evaluadas con evidencia técnica, número real de páginas verificadas e impacto en máquina. Si cumple o tras documentar su estado, permite descargar el **Certificado Oficial de Validación GWG** en formato PDF.

### Portal de visto bueno del cliente

Desde el bloque **3. Validación y Entrega**, el botón **VºBº Cliente** genera un enlace único e infalsificable para enviar al cliente o diseñador, sin necesidad de que el destinatario tenga usuario ni contraseña en IntelliPrint.

- **Revisión fiel de la versión corregida:** El portal muestra en pantalla la **versión acumulada más reciente corregida** del PDF junto con su conteo real de páginas y botón de descarga directa para revisión final.
- **Decisión documentada:** El cliente introduce su nombre/empresa, su correo electrónico opcional (para justificante) y observaciones de tirada. Puede pulsar **Dar Visto Bueno (OK para Imprimir)** para aprobar la entrada en máquina o **Solicitar Cambios / Rechazar** registrando qué debe modificarse antes de producir.

## 7 Modo didáctico para Formación Profesional

*Perfiles recomendados: Docente de FP, Alumno de FP.*

### Aula virtual de FP: grupos, códigos de clase y rúbricas

El módulo docente de IntelliPrint (**Panel Docente** en la cabecera o **Entregar a FP** desde un trabajo activo) permite gestionar el flujo completo de enseñanza y aprendizaje en el taller de Artes Gráficas:

1. **Creación de grupos y códigos de matrícula:** Desde la pestaña **Grupos y Prácticas**, el profesor define sus módulos y grupos (por ejemplo, *2º GS Preimpresión Digital*). El sistema genera de forma automática un código de matrícula único con el formato `FP-XXXX` (letras y dígitos aleatorios).
2. **Matriculación ágil del alumnado:** El profesor comunica el código al grupo. Durante el registro individual en la aplicación o desde la pestaña **Mis Prácticas (Alumno)**, el estudiante introduce dicho código en la casilla correspondiente, quedando matriculado al instante en el grupo de su profesor.
3. **Publicación y entrega directa de prácticas:** El docente puede asignar ejercicios vinculados a cualquiera de los 20 retos formativos del catálogo o proponer prácticas libres sobre PDFs reales de imprenta, definiendo el perfil técnico objetivo. El alumno resuelve el PDF en IntelliPrint y pulsa **Entregar a FP** para enviar automáticamente tanto su diagnóstico inicial como la versión corregida final y sus operaciones registradas.
4. **Evaluación mediante rúbricas ponderadas:** Cada práctica incorpora una rúbrica de evaluación técnica con criterios ponderados sobre 10 puntos (diagnóstico inicial 20 %, criterio en correcciones 30 %, calidad técnica final 30 % y preparación para taller 20 %). Al recibir la entrega del alumno, el motor compara el PDF inicial con el corregido y propone una nota automática justificada. El docente revisa la comparativa, ajusta la puntuación de cada criterio y aporta observaciones pedagógicas.
5. **Informes, evolución, CSV y administración:** El docente puede descargar un **Informe PDF de Evaluación** individual por entrega, exportar el libro completo de calificaciones en **CSV**, analizar la evolución gráfica de sus grupos y (si cuenta con rol de administrador o responsable) aprobar cuentas docentes/técnicas pendientes y asignar roles desde la pestaña **Usuarios y Roles**.

### Las cuatro pestañas de Alumnos FP

**Retos Prácticos FP** abre casos preparados. **Simulador Físico de Taller** permite variar modelos visuales. **Autoevaluación FP** presenta preguntas con corrección comentada. **Ficha Alumno PDF** genera una hoja de práctica con los datos introducidos y el resultado de cuestionario disponible.

Los simuladores son actividades ilustrativas. No aplican correcciones al PDF activo ni constituyen una simulación calibrada de una prensa real. El cuestionario evalúa respuestas; no califica automáticamente todos los aspectos de un arte final producido por el alumno.

### Buscar y cargar un reto

Utiliza los filtros **Todos 20**, **Iniciación 7**, **Intermedio 7** y **Avanzado 6**. Cada tarjeta presenta nivel, tipo de documento, errores intencionados, objetivos de aprendizaje y referencias técnicas del ejercicio.

**Cargar Reto en IntelliPrint** crea o recupera el trabajo de práctica y abre su informe. Puede sustituir el trabajo que se muestra en pantalla; descarga antes un resultado propio que quieras conservar. **Descargar PDF Real para Práctica** recupera el PDF de entrada del caso para estudiarlo en otras herramientas. El PDF del reto y el PDF corregido del informe no son necesariamente la misma versión.

### Catálogo de los veinte retos

#### Iniciación

| Reto | Problema y objetivo de práctica |
| --- | --- |
| Reto 1: Tarjeta Corporativa con Rich Black y Sin Sangrado | Texto de 6 pt en 4 tintas (CMYK) con grave riesgo de descalce de registro en máquina. Comprender la diferencia entre 100% K puro y Negro Enriquecido en tipografía menuda. |
| Reto 2: Flyer Nocturno en Espacio de Color RGB sin Separación | Imágenes en espacio de color RGB (sRGB IEC61966-2.1) sin separación a CMYK. Dominar la conversión de color con perfil estandarizado (ISO Coated v2 / FOGRA39). |
| Reto 3: Tríptico Envolvente con Fondos al Corte y Cajas al Ras | Cero milímetros de sangrado en los 4 bordes perimetrales (0 mm BleedBox). Añadir +3 mm de sangrado perimetral en documentos plegados. |
| Reto 4: Cartel Promocional con Imágenes Web a 72 DPI | Resolución efectiva de 72 DPI (muy inferior al estándar de 300 DPI en offset). Calcular la resolución efectiva en función de la escala de colocación. |
| Reto 5: Marcapáginas Cultural con Tipografías No Incrustadas | Tipografías no incrustadas en el archivo PDF (fuentes referenciadas externamente). Comprobar que todas las fuentes estén incrustadas como subconjunto (Subset). |
| Reto 6: Adhesivo Promocional sin Cajas de Página (TrimBox/BleedBox) | Ausencia de TrimBox y BleedBox normalizados en la estructura del PDF. Conocer la jerarquía de cajas PDF: MediaBox, CropBox, BleedBox y TrimBox. |
| Reto 7: Cupón Descuento con Texto Legal en Gris Tramado al 40% | Texto de cuerpo pequeño (4.5 pt) tramado con punto de semitono al 40% K. Reconocer por qué las letras menores de 7 pt deben ser trazo continuo (100% K). |

#### Intermedio

| Reto | Problema y objetivo de práctica |
| --- | --- |
| Reto 8: Folleto Promocional con TAC 365% y Líneas Pelo (CTP) | Exceso extremo de cobertura de tinta (TAC 365% vs límite de 300%-320%). Comprender los límites de absorción del papel estucado según ISO 12647-2. |
| Reto 9: Catálogo Comercial con 5 Tintas Planas Pantone Directas | 5 colores directos Pantone en un trabajo presupuestado para 4 tintas CMYK. Identificar y convertir tintas planas a CMYK usando tablas LAB oficiales. |
| Reto 10: Dossier Corporativo con Blanco en Sobreimpresión (White Overprint) | Elemento vectorial blanco con sobreimpresión activada (/OP true). Comprender la diferencia entre Calado (Knockout) y Sobreimpresión (Overprint). |
| Reto 11: Carta de Menú con Texto Amarillo sobre Azul sin Reventado (Trapping) | Falta de reventado (trapping) en colores adyacentes de alta luminancia. Aprender la teoría del reventado: ensanchar el color más claro sobre el más oscuro. |
| Reto 12: Orla de Diploma con Filetes Guilloche de 0.08 pt y TAC Elevado | Trazos ornamentales de 0.08 pt por debajo del umbral mínimo de plancha CTP (0.25 pt). Ajustar el grosor mínimo de filete según la resolución CTP y soporte de impresión. |
| Reto 13: Manual de Taller con Texto 100% K en Calado (Knockout) | Texto negro 100% K configurado en calado (knockout) sobre fondos de color. Comprender la regla de oro de preimpresión: Texto 100% K debe sobreimprimir siempre. |
| Reto 14: Calendario de Sobremesa con Descompensación de Tinteros CIP3 | Desequilibrio lateral extremo de entintado entre zonas adyacentes de tintero. Calcular los perfiles zonales de apertura de tintero CIP3 / PPF. |

#### Avanzado

| Reto | Problema y objetivo de práctica |
| --- | --- |
| Reto 15: Estuche Packaging con Código de Barras EAN-13 en 4 Tintas | Código de barras EAN-13 tramado en cuatricromía (provoca rechazo en escáneres ópticos). Conocer las especificaciones GS1 para códigos de barras comerciales (100% K y quiet zone). |
| Reto 16: Portada y Pliegos de Revista con Textos en el Medianil/Lomo | Textos e información crítica ubicados dentro de la zona de hendido del lomo (8 mm). Calcular la reserva de medianil y lomo según el tipo de encuadernación (grapa vs rústica). |
| Reto 17: Etiqueta de Vino con Barniz UVI Calando en vez de Sobreimprimir | Tinta especial de barniz serigráfico calando las tintas de cuatricromía subyacentes. Configurar las tintas de acabado técnico (Barniz, Stamping, Golpe seco) en sobreimpresión obligatoria. |
| Reto 18: Prospecto Farmacéutico con Código QR en 4 Tintas sobre Papel Fino | Código QR de alta densidad compuesto en 4 tintas (Rich Black 300%). Generar códigos 2D bidimensionales (QR, DataMatrix) estrictamente en 100% K puro. |
| Reto 19: Pliego de Imposición SRA3 sin Calles de Corte ni Marcas de Taller | Ausencia de calles de corte y sangre intermedia entre poses (gutter 0 mm). Utilizar el motor de imposición paramétrica de taller en vez de montaje manual. |
| Reto 20: Envase Alimentario con Masa de Tinta y Barniz en la Solapa de Pegado | Masa de tinta y barniz cubriendo la solapa de encolado (Glue Flap de 15 mm). Diseñar reservas en blanco obligatorias en las solapas de pegado de packaging. |


### Simulador Descalce de Registro

<!-- ui-controls: rngShift -->

El control de desajuste ofrece valores de 1 a 10, inicialmente 4. La interfaz representa cada unidad con una referencia visual de 0,05 mm: el valor inicial se muestra como +0,20 mm. Mueve el deslizador para comparar cómo se separan los canales en un texto de negro enriquecido frente a uno de negro puro.

Se trata de un modelo pedagógico. El valor mostrado no mide el registro de una prensa ni el archivo activo. La conclusión práctica es revisar la composición de tintas y la sensibilidad del texto pequeño al desajuste, no reproducir exactamente ese desplazamiento en cualquier máquina.

### Simulador Repintado en Pila

<!-- ui-controls: rngTac -->

El deslizador TAC permite 260 a 380 %, con paso 10; inicialmente 360 %. Compara la representación del riesgo de transferencia o maculado en pila al aumentar la cobertura. Consulta también el texto de explicación y el riesgo de taller que acompaña la imagen.

No existe un porcentaje universal que prediga por sí solo el secado: influyen tinta, soporte, carga, velocidad y condiciones de apilado. Utiliza el ejercicio para entender el motivo de limitar tinta y de respetar la condición acordada, no como ensayo de laboratorio.

### Simulador Guillotina y Sangre

<!-- ui-controls: chkHasBleed rngCut -->

La casilla **El documento incluye +3 mm de Sangre** está inicialmente desactivada. Actívala para comparar la tolerancia visual al corte con y sin extensión exterior. El deslizador de deriva de corte ofrece 0,2 a 2,5 mm, paso 0,1; inicialmente 1,5 mm.

Observa el filete blanco que puede aparecer cuando el fondo termina en el corte neto. La actividad no modifica el TrimBox del trabajo abierto y no añade sangre a ese PDF. Para corregir un archivo, utiliza las herramientas del capítulo de correcciones o vuelve al diseño original.

### Simulador Plancha CTP

<!-- ui-controls: rngStroke -->

El grosor del trazo puede variar de 0,04 a 0,40 pt, paso 0,02; inicialmente 0,08 pt. Estudia la representación de pérdida de líneas finas y compárala con el grosor que exija el perfil de producción.

La imagen ayuda a comprender por qué conviene revisar filetes y detalles. No modela todas las resoluciones de filmación, curvas, lineaturas, planchas o condiciones de revelado. El texto de riesgo explica el objetivo del ejercicio; la validación real corresponde al flujo CTP del taller.

### Autoevaluación FP

<!-- ui-controls: quiz -->

Marca una respuesta por pregunta. **Calificar Autoevaluación** envía las respuestas elegidas y devuelve nota sobre 10, aciertos, nivel y una explicación por pregunta. Es posible enviar una parte del cuestionario, pero las no contestadas no equivalen a respuestas correctas; conviene completarlo antes de emitir una ficha.

Lee la justificación y las referencias después de corregir. El botón **Reiniciar Cuestionario** permite comenzar otro intento en la interfaz. No confundas ese reinicio con borrar un PDF de ficha ya descargado o con modificar un informe técnico del trabajo.

El resultado disponible en la sesión se puede incorporar a la ficha del alumno. Si cierras o recargas la página, comprueba de nuevo que el resultado sigue seleccionado antes de generar la hoja. La aplicación no presenta aquí un libro de calificaciones permanente ni una gestión completa de identidades de alumnos.

### Ficha Alumno PDF

<!-- ui-controls: wsStudentName wsSchoolName wsScenarioSelect -->

Introduce **Nombre Completo del Estudiante**, revisa **Centro Educativo** y selecciona el **Reto o Caso de Taller Asociado**. El centro tiene un texto inicial con los centros participantes, pero puede editarse para la ficha. Revisa los datos antes de emitirla.

**Generar Ficha Oficial PDF A4** crea la hoja y habilita su descarga. Si existe un resultado de cuestionario disponible, se incluye; si no, no debe presentarse como una calificación obtenida. El nombre introducido es un dato de la ficha, no una autenticación de la persona ni una firma digital.

Descarga la ficha y entrégala según el procedimiento del docente. Para documentar una práctica completa, adjunta cuando proceda el PDF de entrada, la versión corregida, su informe y una breve justificación de las decisiones. La ficha de actividad, el certificado técnico y la autorización de producción cumplen funciones distintas.

## 8 Descargas archivo de trabajos y manuales

*Perfiles recomendados: Diseñador / Creativo, Técnico de Taller, Docente de FP, Alumno de FP.*

### Qué entrega cada documento

| Entregable | Contenido y momento de uso |
| --- | --- |
| PDF del trabajo | La versión disponible del documento. Descarga la acumulada después de revisar las correcciones. |
| Certificado o ficha técnica de preflight PDF | Resumen técnico, incidencias y datos de la decisión de salida cuando se ha registrado. No es por sí solo una certificación externa de conformidad. |
| Informe pedagógico para cliente o diseñador PDF | Guía de Arte Final que explica problemas y recomendaciones para comunicar qué debe corregirse y por qué, adaptada a imprenta o pantalla sRGB. |
| Certificado de validación GWG PDF | Auditoría normativa sobre estándares GWG 2015 o ISO PDF/X con evidencias de cumplimiento y conteo real de páginas. |
| Hoja de ruta de taller Job Ticket PDF | Orden de producción calculada con parámetros de máquina, pliegos brutos, papel, tintas y acabados. |
| Paquete de producción ZIP completo | Archivo consolidado con el PDF final, ficha técnica, certificado GWG, informe cliente, pliego de imposición, CIP3 PPF y manifiesto JSON. |
| Informe JSON | Datos estructurados del análisis y metadatos del trabajo; útil para archivo técnico o integración. No equivale a un catálogo de perfiles. |
| Pliego de imposición PDF | Montaje generado con los parámetros de imposición. Revisa caras, marcas y medidas. |
| PPF CIP3 | Datos para un flujo de preajuste compatible. Requiere cálculo previo y validación en el receptor. |
| Ficha de tinteros PDF | Coberturas y valores de preajuste para revisión del operario. |
| Lámina técnica FOGRA PDF | Material de consulta sobre la tira de control. No altera el trabajo abierto. |
| Ficha del alumno PDF o Informe evaluación FP | Hoja de práctica del estudiante o informe detallado por rúbrica ponderada emitido por el docente. |
| ZIP de lote o de hotfolder | Recopilación de archivos disponibles de la cola o categoría correspondiente. Revisar su contenido al recibirlo. |

Una descarga de una acción concreta puede identificar ese resultado de corrección. Si después se realizan más acciones, utiliza el botón principal o el entregable final revisado para evitar enviar una versión antigua. Asigna nombres de archivo o carpetas que distingan entrada, corrección, imposición y versión autorizada.

### Gestión de trabajos activos y paquete de producción ZIP

Desde el botón **Trabajos** de la cabecera se accede al listado de documentos procesados actualmente en el servidor:

- **Búsqueda y estado:** Permite filtrar por nombre o identificador, consultar el estado técnico y de autorización, y ver el contador regresivo hasta la caducidad automática (24 h).
- **Recarga de sesión:** Permite reabrir cualquier trabajo activo en pantalla con su historial completo de versiones y seguir aplicando herramientas sin volver a subir el PDF.
- **Paquete ZIP completo:** Desde el gestor de trabajos o desde el bloque de salida del informe principal se puede descargar en un solo clic el **Paquete de Producción ZIP** con todos los entregables generados para ese trabajo.

### Las cuatro versiones del manual

**Manual web** permite leer y navegar por capítulos dentro de la aplicación o en su página propia, incorporando un filtro interactivo para resaltar los capítulos recomendados según tu perfil (*Diseñador*, *Taller*, *Docente* o *Alumno*). **Markdown** es la fuente de texto canónica consultable y editable. **Word DOCX** es la edición ofimática. **PDF** es la edición de lectura e impresión. Todas comparten el contenido de esta edición y se mantienen sincronizadas.

En la aplicación web actual (botón **Manual (PDF)** y página web `/manual`), se ofrece exclusivamente la lectura interactiva y el enlace **Descargar PDF** (junto al botón **Imprimir**). Las versiones fuente en Markdown y Word DOCX se mantienen en el repositorio técnico del proyecto. La lámina FOGRA tiene su propio enlace y no es una versión de este manual.

Utiliza el índice, el selector por perfil de lectura y la búsqueda del navegador, del lector PDF o de Word para localizar un control por su nombre visible. En Word, el panel de navegación utiliza los títulos del documento. La fecha de edición distingue este contenido ampliado de una copia antigua que se haya quedado en Descargas o en la caché del navegador.

### Conservación temporal y reinicios

Los trabajos se conservan durante 24 horas desde la última modificación de los archivos del trabajo. La limpieza automática se ejecuta aproximadamente cada hora y elimina los trabajos que han superado ese plazo.

Un reinicio o un despliegue en un almacenamiento efímero también puede eliminar trabajos. Los retos incluidos pueden recargarse desde su banco de prácticas; eso no significa que cualquier PDF de un usuario pueda recuperarse. Un QR puede dejar de encontrar su trabajo después de una limpieza o reinicio.

Descarga a tiempo los archivos importantes y guárdalos en el sistema de archivo del centro o empresa. Incluye el PDF final, el informe, la decisión del responsable y los datos de producción que correspondan. La huella SHA-256 mostrada identifica el archivo de referencia registrado; no la confundas sin comprobarlo con una huella calculada de cada derivado posterior.

### Instalación local y tareas del administrador

La instalación necesita Python y las dependencias del proyecto. El iniciador de Windows incluido arranca el servicio local según su configuración; el navegador consulta ese servicio. El trazado seguro de fuentes requiere Ghostscript disponible, y la configuración avanzada permite indicar su ejecutable con GHOSTSCRIPT_BIN. No basta con abrir index.html directamente como un archivo local.

El administrador gestiona almacenamiento, catálogo ICC, copias de perfiles, dependencias y publicación. Los perfiles personalizados y el glosario se guardan en ese servidor y pueden perderse si el almacenamiento no es persistente. Exporta los catálogos importantes y define una política de respaldo fuera del contenedor.

Hay rutas de diagnóstico y documentación de API para uso técnico. No sustituyen los controles explicados en este manual ni convierten una instalación pública en un sistema de gestión de usuarios, archivo seguro o control físico de una prensa. Coordina con el administrador las restricciones y el acceso adecuados para el centro.

## 9 Preguntas frecuentes y verificación final

*Perfiles recomendados: Alumno de FP, Técnico de Taller.*

### He terminado una corrección y el archivo sigue rechazado

Lee las incidencias restantes. Una conversión de color no repara la resolución; una caja de sangrado no amplía el dibujo; trazar fuentes no cambia el tamaño de una imagen. El informe posterior vuelve a comprobar el PDF. La operación puede estar bien ejecutada y el trabajo seguir necesitando otra corrección.

Si el problema necesita contenido que no existe, como una imagen de más calidad o un fondo original más amplio, vuelve al diseño. No encadenes operaciones al azar hasta obtener un aspecto aceptable en pantalla.

### El PDF se ve bien pero falta el ICC o hay RGB

Muchos lectores muestran un PDF con valores genéricos o suposiciones de color. Eso no equivale a tener un OutputIntent CMYK correcto. Revisa el perfil documental y los espacios de los objetos. Declarar un ICC y convertir los datos son operaciones diferentes.

Si eliges un perfil de pantalla, que aparezca una recomendación distinta no implica que debas convertir a CMYK. Decide primero el destino y después la acción. Conserva el original para comparar y para volver a exportar si se ha declarado una condición equivocada.

### Convertir a CMYK ha cambiado los colores

Puede ocurrir por diferencias de gama, perfiles de origen, intención de reproducción y condición de destino. Verifica que se ha utilizado el ICC acordado. Una tinta directa intensa o un RGB muy saturado puede no reproducirse igual en CMYK.

No uses la simulación de sustrato como solución a un perfil de conversión incorrecto. Pide una revisión de color o una prueba adecuada cuando el encargo tenga colores críticos.

### La opción Escala de Grises no se guarda como perfil

La validación de perfiles de esta edición admite CMYK y RGB. La presencia de la opción visual de grises no convierte GRAY en un destino admitido al guardar. Si el trabajo es monocromo, acuerda su composición con el taller y utiliza un perfil admitido y una comprobación de canales apropiada.

Un negro RGB, una imagen gris y un negro puro K no son necesariamente equivalentes en una prensa de cuatricromía. La vista Solo Plancha K ayuda a revisar la contribución del negro, pero no transforma por sí misma los datos.

### He aceptado una errata y sigue apareciendo en el PDF

Aceptar resuelve la sugerencia de revisión, no edita el texto físico del archivo. Corrige el documento de origen y vuelve a exportar cuando proceda. Si el texto ya está en curvas o en una imagen, no tendrá las mismas posibilidades de extracción y revisión editorial.

### Después de trazar fuentes ya no puedo buscar el texto

Es una consecuencia del trazado: los glifos se convierten en formas. Conserva una versión editable y realiza antes la revisión editorial. Si el objetivo es accesibilidad o lectura digital con búsqueda, evalúa si corresponde incrustar la fuente en lugar de trazar.

### El límite TAC aplicado no elimina todos los excesos

El corrector modifica imágenes CMYK y conserva K. Un relleno vectorial, una transparencia o una superposición puede seguir excediendo la referencia. Consulta el nuevo informe y revisa el origen del exceso en una herramienta que permita examinar esos objetos o en el RIP.

El resultado de cobertura es una estimación. Una cifra favorable en la previsualización no sustituye el tratamiento de color de producción y las comprobaciones requeridas por la imprenta.

### He añadido sangre y todavía aparece un borde blanco

Comprueba si solo se han ampliado cajas o si existe contenido real fuera del corte. Examina los cuatro lados y las esquinas. La sangre reflejada puede resolver algunos bordes, pero puede crear reflejos visibles en otros.

No confíes únicamente en la cifra de BleedBox. Un fondo que termina en el corte neto seguirá siendo insuficiente aunque haya espacio exterior para sangrar.

### La imposición tiene menos poses de las esperadas

Revisa formato, orientación, dimensiones reales, sangre y calles X e Y. Las marcas o el área exterior incluida en el documento pueden influir en la detección. Auto busca un resultado geométrico dentro de sus condiciones; no conoce todas las restricciones de una máquina.

No reduzcas calles o sangre por debajo de lo admisible solo para aumentar el aprovechamiento. Comprueba con el operario el tamaño imprimible y el esquema de corte.

### El PPF no funciona en la prensa

Verifica primero el flujo receptor: compatibilidad, número de llaves, orientación, dimensiones y página usada. El módulo genera un archivo de preajuste, pero no garantiza un dialecto o una configuración de importación de cada fabricante.

Utiliza la ficha PDF para contrastar los valores y consulta al responsable de la prensa. No interpretes cobertura, apertura orientativa y densidad medida como una misma magnitud.

### El inspector no encuentra un código que sí está en la página

Puede depender de tamaño, simbología, contraste, rotación, calidad o capacidades del detector. Revisa el código en el diseño y con un lector apropiado. No encontrarlo no significa que sea correcto ni que esté ausente.

Después de corregir, comprueba que se conserva el contenido leído y que la reserva no ha cubierto información vecina. Para requisitos comerciales de calidad, verifica una muestra impresa con el procedimiento adecuado.

### El hotfolder no ve la carpeta de mi ordenador

El servicio vigila el sistema de archivos del servidor que ejecuta IntelliPrint. Una web abierta desde otro ordenador no obtiene acceso a sus carpetas locales. Usa la cola de carga múltiple para subir archivos desde el navegador o pide al administrador un mecanismo de entrada al servidor.

### La ficha del maquinista indica que no está listo

Comprueba el estado técnico y la autorización. Un trabajo pendiente de firma o con un error no debe interpretarse como listo porque exista un QR. Si se ha corregido después de una autorización, revisa la copia nueva y registra otra decisión.

Si faltan datos o el trabajo ya no existe, recupera los archivos que se hayan archivado o vuelve a cargar el PDF. No reinterpretes una ficha incompleta como un permiso de impresión.

### No encuentro un trabajo o su QR devuelve un error

Puede haberse limpiado o perdido en un reinicio del servicio. Descarga y archiva antes de que termine la sesión de trabajo. Los enlaces temporales no son un sistema de conservación permanente.

### El análisis tarda mucho o aparece un fallo de conexión

Espera si hay una operación en curso y evita lanzar varias correcciones simultáneas. Los archivos con imágenes grandes, muchas páginas o transparencias pueden necesitar más recursos. Si la página se ha recargado o el servidor se ha reiniciado, puede ser necesario cargar de nuevo el original.

Conserva el mensaje y el identificador del trabajo para el administrador. Antes de reenviar un resultado al cliente, comprueba que has descargado el archivo completo y que corresponde a la última operación terminada.

### Lista de verificación antes de entregar

1. El destino y el perfil de preflight son los acordados para este trabajo.
2. Las medidas de corte, el sangrado real y los márgenes se han revisado.
3. Las imágenes tienen resolución efectiva adecuada y el tratamiento de color previsto.
4. Las fuentes y el contenido editorial se han comprobado antes de cualquier trazado.
5. Se conservan las separaciones necesarias y se han revisado blanco, negro y sobreimpresión.
6. El TAC y sus límites se han interpretado con sus condiciones de medición y las comprobaciones del RIP.
7. Los códigos mantienen su contenido y se han comprobado con el procedimiento requerido.
8. La imposición, los datos CIP3 y los acabados corresponden a la versión final y a la máquina real.
9. El responsable ha registrado la decisión y las excepciones que procedan.
10. El PDF final y los informes se han guardado fuera del almacenamiento temporal de la aplicación.

### Glosario de consulta

| Concepto | Definición práctica |
| --- | --- |
| Preflight | Verificación previa de determinadas condiciones del documento. |
| Arte final | Archivo preparado para el destino de producción acordado. |
| MediaBox | Límite físico de la página PDF; puede incluir zonas exteriores. |
| TrimBox | Formato neto de corte declarado. |
| BleedBox | Área de sangrado declarada. No demuestra por sí sola que exista dibujo exterior. |
| CropBox | Área que un lector puede utilizar para mostrar o recortar la página. |
| OutputIntent | Declaración documental de una condición de salida, normalmente con un ICC incrustado. |
| ICC | Perfil que describe una condición o espacio de reproducción de color. |
| RGB | Composición con rojo, verde y azul, habitual en pantalla. |
| CMYK | Composición de proceso con cian, magenta, amarillo y negro. |
| Tinta directa | Separación adicional identificada, por ejemplo un color comercial o una plancha técnica. |
| Sobreimpresión | Comportamiento por el que un objeto no reserva ciertas tintas inferiores. |
| Calado | Reserva que retira contribuciones inferiores para colocar el objeto. |
| Negro enriquecido | Negro compuesto con K y contribuciones adicionales de C, M o Y. |
| TAC | Cobertura total de las tintas de proceso en una zona. |
| Sangrado | Extensión del contenido más allá del corte para tolerar la variación de guillotina. |
| Margen de seguridad | Separación interior de textos y otros elementos vivos respecto al corte. |
| Medianil | Zona interior asociada a lomo o encuadernación que puede requerir más reserva. |
| Pose | Una posición de una pieza o página dentro de un pliego impuesto. |
| Calle | Espacio entre poses para sangre y operaciones de corte. |
| Slug | Área exterior con información y elementos de taller. |
| CIP3 PPF | Formato de intercambio para datos de producción, utilizado aquí para preajuste de tinteros. |
| Zona de silencio | Espacio limpio alrededor de un código necesario para su lectura. |
| RIP | Sistema que interpreta el documento para generar la salida de impresión. |
| CTP | Proceso de producción de planchas a partir de datos digitales. |
| Trazado de fuentes | Conversión de glifos de texto en formas; afecta a edición y búsqueda. |
| Soft proof | Simulación visual de una condición de reproducción; requiere interpretar sus límites. |
| SHA 256 | Huella calculada a partir de los bytes de un archivo de referencia. |
| GWG 2015 / PDF/X | Especificaciones internacionales del Ghent Workgroup e ISO 15930 para intercambio fiable en artes gráficas. |
| Job Ticket | Hoja de ruta técnica u orden de producción con especificaciones de máquina, soporte, pliegos y acabados. |
| Rúbrica FP | Matriz ponderada de evaluación por competencias utilizada en el aula virtual docente. |
| Diff visual | Comparación píxel a píxel entre dos versiones del documento para localizar modificaciones o desplazamientos. |
| RBAC | Control de acceso basado en roles de taller y docencia (diseñador, alumno, preimpresión, responsable, docente y administrador). |

**Fin del manual · Edición 2026.11.2**
