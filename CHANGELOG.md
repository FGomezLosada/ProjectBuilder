# Changelog / Historial de versiones

## Próxima versión
- **Iconos de los estilos**: los SVG e imágenes que usan las capas se copian a la carpeta `iconos/` del proyecto, que queda autónomo (se puede mover o enviar y los iconos se siguen viendo). Avisa de los iconos que no se encuentran.
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
