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
| Rama de trabajo | `qgis4` → se fusiona a `main` al terminar la migración |

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

Probado OK en QGIS 3.40.13 y QGIS 4.2.2 (fase 1, v0.2.0).

## Entorno de pruebas
- Repo: `%USERPROFILE%\Documents\dev\ProjectBuilder` (rama `qgis4`)
- Enlazado (`mklink /J`) como `project_builder` en `%APPDATA%\QGIS\QGIS3\...\plugins` y `QGIS4\...\plugins` (perfil `default`)
- Recargar con Plugin Reloader o reiniciando QGIS

## Errores conocidos (fase 2)
1. ~~Reproyección vectorial con `+proj=noop`: no transforma coordenadas.~~ ✅
2. ~~Carpeta destino = origen (o dentro) → sobrescribe datos.~~ ✅
3. GeoPackage multicapa: solo exporta la primera capa.
4. `.ecw` listado pero no exportable; `ext in ('.tif')` es comparación de cadena.
5. SRC no EPSG se pierde (`postgisSrid`).
6. `selectTreeChilds`: `==` en lugar de `=`; selección de hijos errónea.
7. Extensiones sensibles a mayúsculas; `.qml` sin comprobar ni copiar.
8. `closingPlugin` se conecta en cada ejecución; `unload` no elimina el panel.
9. Interfaz bloqueada durante la exportación; el proyecto no se abre al terminar.

## Mejoras futuras (fase 4, del TFM)
- Más formatos vectoriales y ráster
- Filtro/búsqueda en el árbol de capas
- Más WMS (en fichero de configuración) y servicios WFS
- Estilos: copiar `.qml` y los SVG que usen (pendiente de definir)
- Plantilla de composición `.qpt`
- Recorte previo por capa, buffer o BBOX
- Conexión a base de datos (PostGIS)
- Estadísticas de capas seleccionadas
