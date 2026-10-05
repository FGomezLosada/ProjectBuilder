# ProjectBuilder

**QGIS plugin that builds a ready-to-use QGIS project from a selection of local layers and web services.**
*Plugin de QGIS que crea un proyecto listo para trabajar a partir de una selección de capas y servicios web.*

![QGIS 3.34+ | 4.x](https://img.shields.io/badge/QGIS-3.34%2B%20%7C%204.x-589632) ![License GPL v2+](https://img.shields.io/badge/license-GPL%20v2%2B-blue)

[English](#english) · [Español](#español)

---

## English

ProjectBuilder creates a QGIS project (`.qgz`) in a few clicks:

- **Layers of the open QGIS project** (same groups, current styles), **PostGIS / SpatiaLite tables** from your QGIS connections and **local layers** from one or more folders (Shapefile, GeoPackage, GeoJSON, KML, GML, FlatGeobuf, DXF, GPX, GeoTIFF, ECW, JPEG2000, ASCII Grid…), copied into **a single GeoPackage**, one GeoPackage per layer or their original format, optionally **reprojected** to the project CRS. Source folders become layer groups and `.qml` styles are kept.
- **Work area**: clip every layer to a polygon layer (or its selected features) or a rectangle, with an optional buffer in metres.
- **Web services** (WMS, WMTS, WFS): your favourites, your QGIS connections and a built-in, automatically checked catalogue of Spanish public services (IGN, Cadastre, IGME, regional SDIs).
- **Print layouts** from the open project or from `.qpt` templates, with their maps centred on the work area.
- **Layers report**: before creating the project, see each layer's type, feature count, area or length, CRS and size (clipped to the work area); save it as PDF, HTML or CSV.
- **Self-contained projects**: SVG icons used by the styles are copied into an `iconos/` folder; styles stored inside GeoPackages are kept.
- **Drag and drop** folders and layer files from the file explorer or the QGIS Browser; hover a layer for its CRS, feature count and size, and double-click it to see it on the map.
- **Saved configurations** to repeat the same kind of project with one click.
- Messages and a final report (layers, size, time, problems) inside the panel, without pop-ups.
- Runs in the background, with progress and cancel. No external dependencies.

The user interface is in Spanish. Install it from *Plugins → Manage and Install Plugins* (search for *ProjectBuilder*) or download the ZIP from [Releases](https://github.com/FGomezLosada/ProjectBuilder/releases) and use *Install from ZIP*.
Bug reports and ideas are welcome in [Issues](https://github.com/FGomezLosada/ProjectBuilder/issues).

---

## Español

![Panel de ProjectBuilder](docs/captura_panel.png)

### Qué hace
- Compatible con **QGIS 3.34+ y QGIS 4.x**, en Windows, Linux y macOS. Sin dependencias externas.
- **Capas del proyecto abierto en QGIS**, con sus mismos grupos y su estilo actual (los servicios web se añaden tal cual).
- **Tablas de PostGIS, SpatiaLite y GeoPackage** de tus conexiones de QGIS (botón *Añadir base de datos*), por esquemas; se descarga solo lo que cae en la zona de trabajo y se conserva el estilo guardado en la base de datos.
- **Capas locales** de varias carpetas a la vez; cada carpeta se convierte en un grupo del proyecto y se conservan los estilos `.qml`.
  - Vectoriales: Shapefile, GeoPackage, SpatiaLite, GeoJSON, KML, GML, FlatGeobuf, MapInfo, DXF y GPX.
  - Ráster: GeoTIFF, ECW, JPEG2000, ASCII Grid, IMG, VRT, PNG/JPG georreferenciados y MrSID.
- **Formato de salida**: un solo GeoPackage + GeoTIFF (recomendado), un GeoPackage por capa o conservar el original. Reproyección al SRC del proyecto opcional.
- **Zona de trabajo**: recorta todas las capas por una capa de polígonos (o sus elementos seleccionados) o un rectángulo, con margen en metros.
- **Servicios web** WMS, WMTS y WFS: tus **favoritos**, tus **conexiones de QGIS** y un **catálogo** de servicios oficiales (IGN, Catastro, IGME, comunidades autónomas) que se revisa solo.
- **Composiciones de impresión** del proyecto abierto o de plantillas `.qpt`, con los mapas centrados en la zona.
- **Informe de capas**: antes de crear el proyecto, cada capa con su tipo, elementos, superficie o longitud, SRC y tamaño (ya recortada a la zona). Se guarda en PDF, HTML o CSV, o se copia para Excel o Word.
- **Iconos SVG de los estilos** copiados a la carpeta `iconos/` del proyecto: se puede mover o enviar la carpeta y los iconos se siguen viendo. Se conservan también los estilos guardados dentro de los GeoPackage.
- **Configuraciones guardadas** para repetir un tipo de proyecto con un clic.
- Exportación en segundo plano, con progreso y cancelación. Las capas se añaden ocultas para que el proyecto abra rápido.

### Instalación
- Desde QGIS: *Complementos → Administrar e instalar complementos*, busca **ProjectBuilder**.
- O descarga el ZIP de [Releases](https://github.com/FGomezLosada/ProjectBuilder/releases) y usa *Instalar a partir de ZIP*.

### Uso
**Configuración** (arriba): elige una configuración guardada para rellenar el panel, o guarda la actual con 💾.

1. **Capas**: arriba del árbol aparecen las capas del **proyecto abierto en QGIS**; márcalas igual que las de las carpetas. Pulsa *Añadir carpeta…* (tantas veces como orígenes necesites) y marca las capas o carpetas (☑). También puedes **arrastrar carpetas o ficheros** al panel desde el Explorador o el Navegador de QGIS (los ficheros sueltos entran ya marcados). Al pasar el ratón por una capa ves su SRC, elementos y tamaño; con **doble clic** (o clic derecho → *Ver en el mapa*) el mapa va a ella. La caja de búsqueda filtra; los GeoPackage se despliegan para elegir capas sueltas. Elige el **formato de salida**.
2. **Servicios web** (opcional): activa la sección y marca las capas. Despliega un servicio para ver sus capas; **★** guarda una capa en Favoritos y **+** crea una conexión nueva en QGIS.

   ![Servicios web](docs/captura_servicios.png)
3. **Zona de trabajo** (opcional): elige una capa de polígonos (o solo sus elementos seleccionados) o un rectángulo (extensión del mapa, de una capa o dibujado), y un margen en metros. Todo se recorta por esa zona y el proyecto se abre en ella.
4. **Proyecto**: nombre, carpeta de destino (se crea si no existe; no puede ser ninguna de las de origen ni estar dentro de ellas), SRC y composiciones de impresión. En el cajetín puedes usar `[% @project_title %]`: se rellena con el nombre del proyecto.
5. Revisa el resumen (o pulsa **Informe de capas…** para ver el detalle de cada capa) y pulsa **Crear proyecto**. Al terminar, el panel muestra qué se ha creado, cuánto ocupa y cuánto ha tardado, con botones para **abrir el proyecto**, **abrir su carpeta** o ver el **informe** completo. Los avisos salen en esa misma barra, sin ventanas. **Limpiar** vacía el formulario y **?** abre esta guía.

### Servicios siempre al día
El plugin comprueba sus servicios una vez por semana (en segundo plano): los que no responden se desactivan temporalmente (⛔), corrige los cambios de dirección más habituales y descarga el catálogo más reciente de este repositorio.
Para ampliar el catálogo, edita `services.json` (grupos con `nombre` y `servicios`; cada servicio con `name`, `url`, `type` y opcionalmente `layer`) o propón uno en [Issues](https://github.com/FGomezLosada/ProjectBuilder/issues).

### Desarrollo
Ver [`docs/DESARROLLO.md`](docs/DESARROLLO.md) y el [historial de versiones](CHANGELOG.md). Pruebas: doble clic en `tools\probar.bat` (las lanza todas en QGIS 3.40 y 4, cada una en un QGIS sin ventana).
El ZIP para publicar se genera con `python tools/package.py`.

### Autor y licencia
Francisco Gómez Losada · pgomezlosada@gmail.com · [GNU GPL v2 o posterior](LICENSE).
Origen: Trabajo Fin de Máster (2023).
