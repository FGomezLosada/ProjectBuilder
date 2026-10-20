# Changelog / Historial de versiones

## 1.0.1 (2026-10-20) · plan de pruebas por herramienta
- **Plan de pruebas** (`docs/PLAN_PRUEBAS.md`): cada herramienta del panel tiene su batería de casos (124 casos nuevos en 12
  baterías: uso normal, límite, absurdos y mensajes), que pasa en QGIS 3.40 y 4.2. En todos los casos se vigila que no salga
  ningún error de Python ni ninguna ventana, y que cada aviso diga qué pasa y qué hacer.
- **Ningún error imprevisto abre la ventana de error de Python**: sale un aviso en el panel y el detalle queda en el Registro
  de mensajes (pestaña ProjectBuilder) para poder enviarlo.
- **Avisos que dicen qué hacer**; los errores de Windows, GDAL y PostgreSQL se explican en palabras del usuario.
- **Se comprueba antes de empezar**: capas movidas o borradas después de añadirlas, capas en edición con cambios sin guardar
  (antes se copiaban sin esos cambios), rutas demasiado largas para Windows, unidades desconectadas, carpetas sin permiso,
  SRC sin elegir y carpetas pegadas entre comillas («Copiar como ruta de acceso», ahora se aceptan).
- **Zona de trabajo**: si se quita de QGIS la capa de la zona, el desplegable ya no salta solo a otra capa (se podía recortar
  por la zona equivocada); se queda vacío y se avisa.
- **«Conservar el formato»**: los shapefiles ya no pierden las tildes (todo se escribe en UTF-8), los GeoJSON con extensión
  `.json` se guardan como `.geojson` (antes salía un fichero que QGIS no abría) y los MapInfo `.mif` se convierten a GeoPackage.
- **Un solo GeoPackage**: las capas del proyecto abierto conservan su nombre (p. ej. «Plano 1:5000»).
- Las tablas internas de SpatiaLite (KNN2, data_licenses) ya no aparecen como capas. Los logos e imágenes de las
  composiciones se copian al proyecto. «Ver en el mapa» de una capa vacía avisa en lugar de llevar el mapa a 0,0.
- Ficheros dañados (favoritos, estado de los servicios, configuraciones editadas a mano, plantillas .qpt) ya no dan errores:
  se ignora lo que no sirve y se avisa. Una carpeta enorme (C:\, Documentos) ya no deja QGIS parado: se corta y se explica.
- Pruebas: arrancan QGIS con una organización propia (QGIS 4.2 se quedaba parado si el registro tenía muchas claves de otras
  baterías) y dejan `tests/data` como estaba.

## 1.0.0 (2026-10-05) · primera versión estable
- **Revisión de robustez antes de publicar** (19 casos límite nuevos en `tests/robustez_test.py` y `robustez_fondo_test.py`):
  - Nunca se sobrescriben los datos de origen: se rechaza una carpeta de destino que contiene carpetas de capas, y la exportación se niega a escribir sobre su propio fichero de origen.
  - Las capas con geometrías no válidas se reparan al recortarlas por la zona (antes fallaban), y la zona de trabajo admite polígonos con autointersecciones.
  - Las capas sin SRC (p. ej. un shapefile sin `.prj`) se copian sin reproyectar ni recortar, con aviso.
  - Rutas con apóstrofos, tildes, espacios o de red (`\\servidor\...`) en el GeoPackage común.
  - Rásteres del proyecto abierto con extensiones poco comunes; se comprueba que GDAL ha escrito de verdad cada fichero.
  - Un error imprevisto en una capa ya no aborta todo el proyecto (se anota y se sigue), y cancelar durante la última capa cancela de verdad.
  - Lo que hay en el panel al pulsar *Crear* es lo que se crea: el formulario queda bloqueado mientras se exporta. El GeoPackage de un proyecto anterior solo se sustituye cuando todo está comprobado.
  - Se avisa de nombres de proyecto no válidos o carpetas incompletas; los nombres reservados de Windows (CON, NUL…) no se usan como fichero.
  - Carpetas sin permiso, accesos directos y ficheros dañados se saltan al recorrer las carpetas.
  - Las configuraciones exportadas no incluyen usuarios ni contraseñas de bases de datos o servicios.
  - Un `favoritos.json` dañado ya no impide abrir el panel (se aparta como copia). Iconos bloqueados o en OneDrive no impiden guardar el proyecto.
  - WMTS con conjuntos de teselas de nombre propio («UTM30N») usan el SRC que declara el servicio.
  - Al recargar o desinstalar el plugin se cancelan las tareas en marcha; la revisión semanal de servicios se puede cancelar al momento.
  - `tools\\run_tests.py` guarda el detalle completo de cada prueba que falla en `tests\\detalle_<prueba>_qgis<versión>.txt`.
- **Manual de uso** completo, con capturas de cada función (`docs/MANUAL.md`); el botón **?** del panel lo abre.
- **Compartir configuraciones**: importar y exportar ficheros `.json` (también arrastrándolos al panel), y abrir la carpeta donde se guardan.
- Corrige el tamaño del informe final: medía toda la carpeta de destino (p. ej. *Descargas*) en lugar de solo los ficheros del proyecto.
- **Avisos dentro del panel**, en una barra encima de los botones, en lugar de ventanas emergentes. Los avisos largos muestran la primera línea y el resto con «Más».
- **Informe final** al crear el proyecto: capas, tamaño de la carpeta y tiempo, con los problemas si los hay, y botones «Abrir proyecto», «Abrir carpeta» e «Informe…» (cada capa del proyecto con sus elementos, superficie y tamaño; se guarda en PDF, HTML o CSV).
- **Icono nuevo** (SVG, nítido a cualquier tamaño) y botón de **ayuda** (?) que abre la guía de uso.
- **Arrastrar al panel** carpetas y ficheros de capas desde el Explorador de Windows o el Navegador de QGIS (también capas sueltas de un GeoPackage y plantillas `.qpt`). Un fichero suelto aparece bajo su carpeta, ya marcado, sin recorrer el resto de la carpeta; un shapefile con todos sus ficheros cuenta como una capa. Se guarda en las configuraciones.
- Al añadir una carpeta que contiene otra que ya estaba en el árbol, se integra en ella sin perder lo marcado (antes se rechazaba).
- **Información al pasar el ratón** por una capa: ruta, SRC, geometría y número de elementos (o píxeles y bandas), y tamaño; en carpetas y GeoPackages, cuántas capas tienen.
- **Ver en el mapa** (clic derecho o doble clic en una capa): lleva el mapa a la capa y hace parpadear su extensión. El menú también permite abrir la carpeta o quitarla del árbol.
- **Iconos de los estilos**: los SVG e imágenes que usan las capas se copian a la carpeta `iconos/` del proyecto, que queda autónomo (se puede mover o enviar y los iconos se siguen viendo). Si la ruta guardada en el estilo ya no existe (por ejemplo, viene de otro ordenador), el icono se busca por su nombre en las carpetas de capas y sus subcarpetas, en la carpeta del proyecto abierto y en las carpetas SVG de QGIS. Avisa de los que siguen sin encontrarse.
- Se conservan los **estilos guardados dentro de un GeoPackage de origen** (antes solo se usaba el `.qml` junto al fichero).
- **Bases de datos PostGIS, SpatiaLite y GeoPackage conectados** como origen: botón «Añadir base de datos» con las conexiones de QGIS; esquemas y tablas (también vistas) en el árbol; se descargan en segundo plano, solo lo que cae en la zona de trabajo, y conservan el estilo guardado en la base de datos.
- **Informe de capas**: botón que muestra al instante, antes de crear el proyecto, cada capa con su tipo, elementos, superficie o longitud (en metros reales), SRC y tamaño, ya recortada a la zona de trabajo. Se guarda en PDF, HTML o CSV, o se copia para pegar en Excel o Word.
- Pruebas automáticas aisladas: `tools\\probar.bat` las lanza en QGIS 3.40 y 4, cada una en un QGIS sin ventana.
- **Capas del proyecto abierto** como origen: mismo árbol de grupos y estilo actual de cada capa. Las de fichero, base de datos o temporales se copian (respetando su filtro); los servicios web se añaden tal cual. La lista se actualiza sola.

## 0.6.1 (2026-10-02)
- Preparado para el repositorio oficial de QGIS: descripción en inglés, licencia GPL (`LICENSE`), README bilingüe, este historial y generación automática del ZIP (`tools/package.py` y GitHub Action).

## 0.6.0 (2026-10-02)
- **Zona de trabajo**: recorte de todas las capas por una capa de polígonos (o sus elementos seleccionados) o un rectángulo, con margen en metros. Los vectoriales se cortan por el borde y los ráster por máscara; las capas sin datos en la zona se avisan. El proyecto se abre en la zona (y los WFS solo descargan esa zona).
- **Composiciones de impresión**: copia composiciones del proyecto abierto, de plantillas `.qpt` de cualquier carpeta o del perfil de QGIS, con los mapas centrados en la zona y en el SRC del proyecto.
- **Configuraciones guardadas**: guarda el panel (carpetas, capas, servicios, SRC, formato, zona y composiciones) y recupéralo con un clic.
- Corrige un cierre de QGIS 4 al quitar capas con el panel abierto.

## 0.5.0 (2026-10-02)
- Salida a un **GeoPackage único** (por defecto), uno por capa o formato original. Más formatos (GeoJSON, KML, FlatGeobuf, ASC…). Varias carpetas de origen. Reproyección opcional.
- Panel con secciones plegables, filtro, resumen en vivo e iconos nativos de QGIS.
- **Servicios WMS, WMTS y WFS**: favoritos, conexiones de QGIS y catálogo con 71 servicios públicos españoles.
- Revisión automática semanal de los servicios y catálogo actualizable desde GitHub; revisión mensual en GitHub con aviso por email.

## 0.4.0
- Lógica separada en `core/`, exportación en segundo plano con progreso, árbol con casillas, proyecto `.qgz` con rutas relativas, botón para abrir el proyecto, servicios en `services.json` y proyectos solo con WMS.

## 0.3.0
- Correcciones: reproyección vectorial real, protección de los datos de origen, GeoPackage multicapa, extensiones en mayúsculas, selección en el árbol y copia de estilos `.qml`.

## 0.2.0
- Compatibilidad con QGIS 3.34+ y QGIS 4 (Qt6). Renombrado interno a `project_builder`.

## 0.1 (2023)
- Versión inicial (Trabajo Fin de Máster).
