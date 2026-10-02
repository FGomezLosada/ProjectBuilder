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
| Rama de trabajo | `fase4` (v0.4.0 publicada en `main` con etiqueta) |

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

Probado OK en QGIS 3.40.13 y QGIS 4.2.2 (fases 1-3, v0.4.0).

## Entorno de pruebas
- Repo: `%USERPROFILE%\Documents\dev\ProjectBuilder` (rama `qgis4`)
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
project_builder_dockwidget.py(.ui)  interfaz
core/          lógica sin interfaz: formats, scanner, exporter, project, task, services
services.json  servicios WMS
tests/         datos de prueba y scripts para la consola de QGIS
```

## Formatos admitidos (core/formats.py)
- Vectoriales: shp, gpkg, sqlite, geojson/json, kml, gml, fgb, tab/mif, dxf, gpx
- Ráster: tif/tiff, ecw, jp2, asc, img, vrt, png, jpg, sid
- Para añadir uno: incluir su extensión en VECTOR_EXTENSIONS/RASTER_EXTENSIONS (y en KEEP_* si GDAL lo escribe)

## Datos de prueba
`tests/data/` (ver `LEEME.txt`). Pruebas: `tests/smoke_test.py` (sin internet) y `tests/background_test.py` (segundo plano + WMS). También vía MCP de QGIS 3.40.
Comprobación de estilo: `ruff check .` (configuración en `pyproject.toml`).

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
| 4.3 | Catálogo amplio de WMS agrupado por ámbito (estatal y comunidades) + WFS/WMTS | TFM + petición |
| 4.4 | Recorte previo por capa, buffer o BBOX | TFM |
| 4.5 | Plantilla de composición `.qpt` | TFM |
| 4.6 | Estadísticas de las capas seleccionadas | TFM |
| 4.7 | Conexión a base de datos (PostGIS) como origen de capas | TFM |
| 4.8 | Estilos `.qml` con símbolos SVG (pendiente de definir) | Word de mejoras |
| 4.9 | Plantillas de configuración: guardar/cargar en `.json` carpetas, capas marcadas, WMS, SRC y modo (p. ej. "Proyecto municipal Nerja") | Idea aprobada |
| 4.10 | Origen "capas del proyecto abierto en QGIS" (además de carpetas y BBDD) | Idea |

### Mejoras visuales y de uso (propuestas, por priorizar)
| # | Mejora | Qué aporta |
|---|---|---|
| V1 | Panel en 3 secciones plegables (1 Capas · 2 Servicios · 3 Proyecto) en lugar de pestañas | Todo a la vista y en orden de uso; los WMS dejan de estar "escondidos" |
| V2 | Resumen en vivo junto al botón: "7 capas · 2 WMS · un solo GeoPackage" | Saber qué se va a generar antes de pulsar |
| V3 | Iconos de QGIS según geometría y tipo (punto/línea/polígono, ráster, GeoPackage, carpeta) | Árbol más legible y con el aspecto nativo de QGIS (y de su tema oscuro) |
| V4 | Información al pasar el ratón por una capa: ruta, SRC, nº de elementos, tamaño | Elegir sin abrir las capas |
| V5 | "Ver en el mapa": resaltar la extensión de la capa al hacer clic | Comprobar de un vistazo dónde cae cada capa |
| V6 | Avisos dentro del propio panel (barra de mensajes) en lugar de ventanas emergentes | Menos interrupciones |
| V7 | Informe final: capas exportadas, tamaño, tiempo, problemas, botones "Abrir proyecto" y "Abrir carpeta" | Cierre claro del proceso |
| V8 | Arrastrar carpetas o ficheros desde el Explorador de Windows al árbol | Añadir orígenes más rápido |
| V9 | Icono nuevo en SVG y botón de ayuda que abre el README | Imagen más profesional |

