# ProjectBuilder · Guía de desarrollo

Documento vivo. Léelo al empezar cada sesión de trabajo (también sirve de contexto para Claude).

## Qué es
Plugin de QGIS que crea un proyecto `.qgs` a partir de una selección de capas locales
(se copian y reproyectan a la carpeta del proyecto) y servicios WMS. Origen: TFM (2023).

## Decisiones tomadas
| Tema | Decisión |
|---|---|
| Versiones soportadas | QGIS 3.34 LTR+ y QGIS 4.x (Qt5 y Qt6) con el mismo código |
| Nombre interno | `project_builder` (antes `carto_base`) |
| Autor / email | Francisco Gómez Losada · pgomezlosada@gmail.com |
| Capas al crear el proyecto | Se añaden **ocultas** (carga rápida del proyecto) |
| Formato del proyecto | `.qgz`, rutas relativas, guardado una sola vez |
| Formato de salida | Selector: **Un solo GeoPackage + GeoTIFF** (por defecto; estilos guardados dentro del GeoPackage), **Un GeoPackage por capa** o **Conservar** (si GDAL no puede escribirlo, se convierte) |
| Orígenes de capas | Varias carpetas a la vez (raíces del árbol). Cada carpeta de origen es un grupo del proyecto; en los modos de ficheros sueltos, también una subcarpeta |
| Valores recordados entre sesiones | Últimas carpetas de capas y de proyecto, último SRC (QSettings, prefijo `project_builder/`) |
| SRC | Casilla "Reproyectar todas las capas a este SRC" (marcada por defecto). Desmarcada: cada capa conserva su SRC original y el proyecto reproyecta al vuelo |
| Servicios web | Árbol con ★ Favoritos (perfil del usuario: `<perfil QGIS>/project_builder/favoritos.json`), Mis conexiones de QGIS (solo lectura, agrupadas por tipo) y Catálogo (`services.json`, con grupos). Las capas de un servicio se piden al desplegarlo (GetCapabilities asíncrono, 20 s máx.) |
| Rama de trabajo | `main` (una sola rama; cada versión publicada lleva su etiqueta `vX.Y.Z`) |

## Convenciones de código
- Importar Qt **siempre** desde `qgis.PyQt` (nunca `PyQt5`/`PyQt6` directamente).
- Enums de Qt con nombre completo: `Qt.ItemDataRole.UserRole`, no `Qt.UserRole`.
- Nada de `import *`.
- Lógica separada de la interfaz: `core/` no importa widgets.
- Mensajes al usuario: barra de mensajes de QGIS; errores técnicos: `QgsMessageLog`.
- Comentarios en español y abundantes: se conservan siempre (ayudan a entender el código). Solo se corrigen si quedan desactualizados.
- Nombres: `snake_case` funciones/variables, `PascalCase` clases.

## Flujo de trabajo
1. Cambios con Buscar/Reemplazar (`Ctrl+H`) en VS Code. Un cambio pequeño cada vez → probar en QGIS (recargar plugin) → commit.
2. Mensajes de commit convencionales: `feat:`, `fix:`, `refactor:`, `chore:`, `docs:`.
3. Fases: 0 limpieza · 1 migración QGIS 4 · 2 errores · 3 reestructuración · 4 mejoras.

## Checklist de migración a QGIS 4 / Qt6
- [x] Imports `PyQt5` → `qgis.PyQt`
- [x] Enums Qt cortos → completos
- [x] `exec_()` → `exec()` (no se usaba)
- [x] `Qgis.Success` → `Qgis.MessageLevel.Success`
- [x] `QgsCoordinateReferenceSystem(int, EpsgCrsId)` → `QgsCoordinateReferenceSystem.fromEpsgId()` o el objeto CRS
- [x] Quitar `resources.py` (pyrcc5 no existe en Qt6) → rutas de fichero
- [x] `metadata.txt`: `qgisMinimumVersion=3.34`, `supportsQt6=True`
- [x] En los `.ui`, todo `spacer` necesita `sizeHint` (Qt6/PyQt6 falla sin él; Qt5 lo tolera)
- [x] **Nunca usar un enum de Qt directamente en un `if`**: en PyQt6 todos valen `True` (p. ej. `QNetworkReply.NetworkError.NoError`). Comparar siempre: `if reply.error() != QNetworkReply.NetworkError.NoError:`
- Comprobar un `.ui` con Qt6 sin abrir QGIS 4: cargarlo con `PyQt6.uic.loadUiType` (simulando `qgis.gui`)

Probado OK en QGIS 3.40.13 y QGIS 4.2.2 (fases 1-3, v0.4.0).

## Entorno de pruebas
- Repo: `%USERPROFILE%\Documents\dev\ProjectBuilder` (rama `main`)
- Enlazado (`mklink /J`) como `project_builder` en `%APPDATA%\QGIS\QGIS3\...\plugins` y `QGIS4\...\plugins` (perfil `default`)
- Recargar con Plugin Reloader o reiniciando QGIS

## Errores conocidos (fase 2 completada, v0.3.0)
1. ~~Reproyección vectorial con `+proj=noop`: no transforma coordenadas.~~ ✅
2. ~~Carpeta destino = origen (o dentro) → sobrescribe datos.~~ ✅
3. ~~GeoPackage multicapa: solo exporta la primera capa.~~ ✅
4. ~~`.ecw` listado pero no exportable; `ext in ('.tif')` es comparación de cadena.~~ ✅
5. ~~SRC no EPSG se pierde (`postgisSrid`).~~ ✅
6. ~~`selectTreeChilds`: `==` en lugar de `=`; selección de hijos errónea.~~ ✅
7. ~~Extensiones sensibles a mayúsculas; `.qml` sin comprobar ni copiar.~~ ✅
8. ~~`closingPlugin` se conecta en cada ejecución; `unload` no elimina el panel.~~ ✅
9. ~~Interfaz bloqueada durante la exportación; el proyecto no se abre al terminar.~~ ✅ (fase 3)

## Estructura
```
__init__.py / project_builder.py    entrada del plugin (menú, botón, panel)
project_builder_dockwidget.py(.ui)  interfaz (el .ui se edita con Qt Designer: secciones plegables QgsCollapsibleGroupBox)
core/          lógica sin interfaz: formats, scanner, exporter, project, task, services, capabilities
services.json  servicios WMS
tests/         datos de prueba y scripts para la consola de QGIS
```

## Formatos admitidos (core/formats.py)
- Vectoriales: shp, gpkg, sqlite, geojson/json, kml, gml, fgb, tab/mif, dxf, gpx
- Ráster: tif/tiff, ecw, jp2, asc, img, vrt, png, jpg, sid
- Para añadir uno: incluir su extensión en VECTOR_EXTENSIONS/RASTER_EXTENSIONS (y en KEEP_* si GDAL lo escribe)

## Cómo pasar las pruebas (recomendado)
Doble clic en `tools\probar.bat` (o `tools\probar.bat zone_test.py` para una sola desde CMD): lanza todas las pruebas
en QGIS 3.40 y en QGIS 4.2, **cada una en un QGIS propio sin ventana** (`tools/run_tests.py`), con la configuración de pruebas
de QGIS (no toca favoritos, plantillas ni configuraciones del usuario). Resultado en `tests/resultados_qgis<versión>.txt`.
Así las pruebas no se contaminan entre sí: lanzar muchas seguidas en el mismo QGIS (con recargas del plugin y decenas de paneles
creados y destruidos) acababa confundiendo objetos de Python y cerrando QGIS, aunque cada prueba por separado pasara.
Si cambia la versión de QGIS instalada, actualizar las dos rutas de `tools\probar.bat`.

## Datos de prueba
`tests/data/` (ver `LEEME.txt`). Pruebas: `tests/smoke_test.py` (sin internet), `tests/zone_test.py` (zona de trabajo, sin internet), `tests/config_test.py` (configuraciones guardadas, sin internet), `tests/layout_test.py` (composiciones, sin internet), `tests/open_project_test.py` (capas del proyecto abierto, sin internet), `tests/stats_test.py` (informe de capas, sin internet), `tests/background_test.py` (segundo plano + WMS/WMTS/WFS reales) y
`tests/check_catalog.py` (comprueba que los 71 servicios del catálogo responden y que sus capas existen; ejecutarlo de vez en cuando). También vía MCP de QGIS 3.40.
Si una prueba larga se lanza por el MCP, conviene hacerlo con `QTimer.singleShot` y guardar la salida en un fichero:
así la llamada no espera a que termine (el MCP corta a los 60 s).
Varias pruebas seguidas: encadenarlas (cada una programa la siguiente al terminar), NUNCA varios `singleShot` a la vez:
Processing/GDAL atienden eventos mientras trabajan, la siguiente prueba arranca dentro de la anterior, recarga el plugin
en mitad y QGIS se cierra (0xc0000374, memoria corrompida). Para diagnosticar cierres: `faulthandler.enable(fichero)`
con el fichero dentro de la carpeta del proyecto (`pb_crash.txt`, ignorado por git).
Señales: conectar a métodos, no a `lambda` que usen `self` (un lambda puede ejecutarse con el panel ya destruido: cierre en QGIS 4).
Ráster + zona: recortar y reproyectar en un solo gdalwarp crea un ráster gigantesco (aplica la resolución en grados
como si fueran metros); por eso se recorta primero en el SRC original y después se reproyecta.
Comprobación de estilo: `ruff check .` (configuración en `pyproject.toml`).

## Mantenimiento automático de los servicios
1. **En el plugin** (`core/health.py`): al abrir el panel, como mucho cada 7 días, comprueba en segundo plano el catálogo y los
   favoritos. Los caídos se desactivan (⛔) hasta la siguiente comprobación; si responden con `https` o sin `/wms.aspx`, se usa esa
   dirección. Avisa si falla algún favorito. ⟳ fuerza la comprobación. Resultado en `<perfil>/project_builder/estado_servicios.json`.
2. **Catálogo desde GitHub**: el plugin descarga `services.json` de la rama `main` (`REMOTE_CATALOG_URL`) y lo usa si su campo
   `"version"` es más reciente que el del plugin. **Al cambiar el catálogo, subir siempre `"version"` (fecha AAAA-MM-DD).**
3. **Revisión mensual en GitHub** (`.github/workflows/revisar-catalogo.yml` + `tools/check_catalog_ci.py`, sin QGIS): el día 1 de
   cada mes; si falla algún servicio abre o actualiza la incidencia "Catálogo: servicios que no responden" (aviso por email).
   Se puede lanzar a mano desde la pestaña *Actions*.

## Notas sobre servicios
- Las cadenas de conexión WMS/WMTS se construyen con `QgsDataSourceUri` (protege URLs con `?` y `&`).
- En WMTS, QGIS necesita la URL completa de GetCapabilities (`?SERVICE=WMTS&REQUEST=GetCapabilities`).
- MITECO (`wms.mapama.gob.es`): en octubre de 2026 su servidor WMS devuelve un error interno a cualquier petición. Fuera del catálogo hasta que vuelva.
- Pendiente de añadir al catálogo: Galicia, Asturias, Cantabria, Extremadura, Ceuta y Melilla (no se encontraron servicios que respondieran).

## Hoja de ruta

### Fase 3 · Base técnica (v0.4.0) ✅
1. Lógica separada en `core/` (escaneo, exportación, construcción del proyecto) ✅
2. Exportación en segundo plano (`QgsTask`) con barra de progreso ✅
3. Árbol con casillas ☑ (marcar carpeta = marcar contenido) ✅
4. Proyecto `.qgz`, guardado una sola vez, rutas relativas, opción de abrirlo al terminar ✅
5. Servicios en `services.json` (sin tocar código) ✅
6. Limpieza (ruff, nombres homogéneos) conservando comentarios ✅

### Fase 4 · Mejoras (memoria TFM, apdo. 4) → v1.0.0
| # | Mejora | Origen |
|---|---|---|
| 4.1 ✅ | Búsqueda/filtrado en el árbol + capas internas de GeoPackage como hijos | TFM + prueba QGIS 4 |
| 4.2 ✅ | Más formatos, formato de salida a elegir (incl. un solo GeoPackage) y varias carpetas de origen | TFM + petición |
| 4.3 ✅ | Servicios web: ★ Favoritos + conexiones de QGIS + catálogo (17 grupos, 71 servicios comprobados); WMS, WMTS y WFS; aviso ⚠ en servicios pesados | TFM + petición |
| 4.4 ✅ | Zona de trabajo: recorte por capa (o elementos seleccionados) o rectángulo, con margen en metros; vectoriales cortados por el borde, ráster por máscara, capas vacías avisadas, vista inicial en la zona | TFM |
| 4.5 ✅ | Composiciones de impresión: las del proyecto abierto, plantillas `.qpt` de cualquier carpeta y las del perfil de QGIS; mapas centrados en la zona, en el SRC del proyecto; título del proyecto = nombre (`[% @project_title %]`). Sin plantilla propia del plugin | TFM + petición |
| 4.6 ✅ | Informe de capas: botón «Informe de capas…» que muestra al instante tipo, elementos, superficie/longitud (elipsoide), SRC y tamaño de cada capa (recortada a la zona); se guarda en PDF/HTML/CSV o se copia para Excel/Word | TFM |
| 4.7 | Conexión a base de datos (PostGIS) como origen de capas | TFM |
| 4.8 | Estilos `.qml` con símbolos SVG (pendiente de definir) | Word de mejoras |
| 4.9 ✅ | Configuraciones guardadas: un `.json` por configuración en el perfil (carpetas, capas marcadas, servicios, SRC, formato y zona de trabajo); se elige en un desplegable arriba del panel | Idea aprobada |
| 4.10 ✅ | Capas del proyecto abierto como origen: mismo árbol de grupos, estilo actual de cada capa; las de fichero/BBDD/temporales se copian (con filtro), los servicios web se enlazan; se actualiza solo | Idea |

### Mejoras visuales y de uso (propuestas, por priorizar)
| # | Mejora | Qué aporta |
|---|---|---|
| V1 ✅ | Panel en 3 secciones plegables (1 Capas · 2 Servicios · 3 Proyecto) en lugar de pestañas | Todo a la vista y en orden de uso; los WMS dejan de estar "escondidos" |
| V2 ✅ | Resumen en vivo junto al botón: "7 capas · 2 WMS · un solo GeoPackage" | Saber qué se va a generar antes de pulsar |
| V3 ✅ | Iconos de QGIS según geometría y tipo (punto/línea/polígono, ráster, GeoPackage, carpeta) | Árbol más legible y con el aspecto nativo de QGIS (y de su tema oscuro) |
| V4 | Información al pasar el ratón por una capa: ruta, SRC, nº de elementos, tamaño | Elegir sin abrir las capas |
| V5 | "Ver en el mapa": resaltar la extensión de la capa al hacer clic | Comprobar de un vistazo dónde cae cada capa |
| V6 | Avisos dentro del propio panel (barra de mensajes) en lugar de ventanas emergentes | Menos interrupciones |
| V7 | Informe final: capas exportadas, tamaño, tiempo, problemas, botones "Abrir proyecto" y "Abrir carpeta" | Cierre claro del proceso |
| V8 | Arrastrar carpetas o ficheros desde el Explorador de Windows al árbol | Añadir orígenes más rápido |
| V9 | Icono nuevo en SVG y botón de ayuda que abre el README | Imagen más profesional |

## Publicación de una versión
1. Subir `version=` y añadir la línea del `changelog` en `metadata.txt` (y en `CHANGELOG.md`).
2. Pasar las pruebas (`tests/*_test.py`) en QGIS 3.40 y QGIS 4.
3. `git commit`, `git tag vX.Y.Z`, `git push && git push --tags`.
4. La GitHub Action `publicar-version.yml` genera el ZIP (`tools/package.py`) y crea la *Release* de GitHub con él.
5. Subir ese ZIP a https://plugins.qgis.org/ (con el OSGeo ID): *My plugins* → la del plugin → *Add version*.
El ZIP solo lleva lo necesario para el plugin (lista en `tools/package.py`): nada de tests, docs, .git ni __pycache__.

