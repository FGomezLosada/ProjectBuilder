"""
Prueba rápida de ProjectBuilder con los datos de tests/data (no necesita internet).

Uso (consola de Python de QGIS 3 o QGIS 4):
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\smoke_test.py", encoding="utf-8").read())

Usa DOS carpetas de origen (tests/data/vectorial y tests/data/raster) y prueba los tres formatos de salida,
la búsqueda, la selección de capas sueltas de un GeoPackage y quitar una carpeta del árbol.
No abre ventanas: los avisos se muestran en la consola.
"""
import os
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsLayerTreeGroup, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import Qt

qgis.utils.reloadPlugin('project_builder')
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data').replace('\\', '/')
CARPETAS = (DATA + '/vectorial', DATA + '/raster')
TODAS = ("multicapa.gpkg", "zonas_4326.shp", "puntos_23030.shp", "MAYUSCULAS_4326.TIF",
         "lugares_4326.geojson", "limites_4326.kml", "pendientes_4326.asc")
SINGLE, CONVERT, KEEP = 'single', 'convert', 'keep'
avisos = []
dock_module.ProjectBuilderDockWidget.warn = lambda self, msg: avisos.append(msg)  # sin ventanas emergentes


def _items(item):
    """Todos los elementos que cuelgan de item (sin QTreeWidgetItemIterator, que puede cerrar QGIS 4)."""
    for i in range(item.childCount()):
        yield item.child(i)
        yield from _items(item.child(i))


def _panel():
    dw = dock_module.ProjectBuilderDockWidget(qgis.utils.iface)
    for carpeta in CARPETAS:
        dw.add_source_folder(carpeta)
    return dw


def _crear(marcar, nombre, modo=SINGLE, reproyectar=True):
    """Crea un proyecto marcando los elementos cuyo texto esté en 'marcar'. Devuelve (proyecto, ficheros, carpeta)."""
    tmp = tempfile.mkdtemp(prefix="pb_test_").replace('\\', '/') + "/carpeta_nueva/proyecto"  # aún no existe: el plugin debe crearla
    dw = _panel()
    for item in list(_items(dw.treeWidget.invisibleRootItem())):
        if item.text(0) in marcar:
            item.setCheckState(0, Qt.CheckState.Checked)  # se marca la casilla, como haría el usuario
    dw.pathFolderProject.setText(tmp)
    dw.nameProject.setText(nombre)
    dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
    dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
    dw.reprojectCheck.setChecked(reproyectar)
    dw.create_project(background=False)  # sin segundo plano para comprobar el resultado al momento
    dw.deleteLater()
    p = QgsProject()
    p.read(f"{tmp}/{nombre}.qgz")
    ficheros = sorted(os.path.relpath(os.path.join(d, f), tmp).replace('\\', '/') for d, _, fs in os.walk(tmp) for f in fs)
    return p, ficheros, tmp


def _grupos(nodo, ruta=()):
    """Rutas de todos los grupos del árbol de capas del proyecto."""
    out = []
    for c in nodo.children():
        if isinstance(c, QgsLayerTreeGroup):
            out.append('/'.join((*ruta, c.name())))
            out += _grupos(c, (*ruta, c.name()))
    return out


def _color(lyr):
    return lyr.renderer().symbol().color().name() if hasattr(lyr.renderer(), 'symbol') else None


# 1. Un solo GeoPackage (por defecto)
p, ficheros, tmp = _crear(TODAS, "prueba")
capas = list(p.mapLayers().values())
zonas_shp = [lyr for lyr in capas if lyr.name() == 'zonas_4326_2']  # la del shapefile (la del GeoPackage se llama zonas_4326)
estilo_en_gpkg = _color(QgsVectorLayer(f"{tmp}/prueba.gpkg|layername=zonas_4326_2", "x", "ogr"))
grupos = _grupos(p.layerTreeRoot())

# 2. Árbol: varias carpetas, búsqueda y quitar carpeta
dw = _panel()
for _i in range(dw.treeWidget.topLevelItemCount()):
    dw.treeWidget.topLevelItem(_i).setCheckState(0, Qt.CheckState.Checked)
dw.update_summary()
resumen = dw.summaryLabel.text()
for _i in range(dw.treeWidget.topLevelItemCount()):
    dw.treeWidget.topLevelItem(_i).setCheckState(0, Qt.CheckState.Unchecked)
raices = [dw.treeWidget.topLevelItem(i).text(0) for i in range(dw.treeWidget.topLevelItemCount())]
multi = [it.childCount() for it in _items(dw.treeWidget.invisibleRootItem()) if it.text(0) == 'multicapa.gpkg']  # se guarda el número, no el elemento
dw.filterBox.setText("PUNTOS")  # en mayúsculas a propósito: la búsqueda no distingue
visibles = [it.text(0) for it in _items(dw.treeWidget.invisibleRootItem()) if not it.isHidden() and it.childCount() == 0]
dw.filterBox.clear()
dw.add_source_folder(DATA)  # contiene a las otras dos: debe rechazarse
rechazo = len(avisos) == 1
avisos.clear()
dw.treeWidget.setCurrentItem(dw.treeWidget.topLevelItem(1).child(0))  # una capa de la carpeta raster
dw.remove_current_folder()
tras_quitar = [dw.treeWidget.topLevelItem(i).text(0) for i in range(dw.treeWidget.topLevelItemCount())]
dw.nameProject.setText("x")
dw.addWMS.setChecked(True)
dw.reset_form()
limpio = dw.treeWidget.topLevelItemCount() == 0 and not dw.nameProject.text() and not dw.addWMS.isChecked()
dw.deleteLater()

# 3. Solo una capa interna del GeoPackage
p2, ficheros2, _ = _crear(("lineas_25830",), "parcial")
capas2 = sorted(lyr.name() for lyr in p2.mapLayers().values())

# 3b. Sin reproyectar: cada capa conserva su SRC original
p5, _, _ = _crear(("puntos_23030.shp", "mdt_4326.tif"), "sin_reproyectar", SINGLE, reproyectar=False)
src5 = sorted((lyr.name(), lyr.crs().authid()) for lyr in p5.mapLayers().values())

# 4. Un GeoPackage por capa
p3, ficheros3, _ = _crear(TODAS, "porcapa", CONVERT)
capas3 = list(p3.mapLayers().values())

# 5. Conservar el formato original
p4, ficheros4, _ = _crear(TODAS, "conservar", KEEP)
capas4 = list(p4.mapLayers().values())
ext4 = sorted({os.path.splitext(f)[1].lower() for f in ficheros4 if not f.endswith(('.qgz', '.qml', '.prj', '.dbf', '.shx', '.cpg', '.xml'))})

checks = {
    "sin avisos": not avisos,
    "crea la carpeta del proyecto si no existe": os.path.isfile(f"{tmp}/prueba.qgz"),
    "[1 GPKG] 8 capas válidas en EPSG:25830": len(capas) == 8 and all(lyr.isValid() and lyr.crs().authid() == 'EPSG:25830' for lyr in capas),
    "[1 GPKG] solo prueba.qgz, prueba.gpkg y los .tif": all(f in ('prueba.qgz', 'prueba.gpkg') or f.endswith(('.tif', '.aux.xml')) for f in ficheros)
        and 'raster/pendientes_4326.tif' in ficheros,
    "[1 GPKG] 6 tablas vectoriales dentro de prueba.gpkg": sum(lyr.source().startswith(f"{tmp}/prueba.gpkg") for lyr in capas) == 6,
    "[1 GPKG] nombres repetidos con sufijo (zonas_4326_2)": len(zonas_shp) == 1,
    "[1 GPKG] estilo naranja en el proyecto": bool(zonas_shp) and _color(zonas_shp[0]) == '#ff7f00',
    "[1 GPKG] estilo naranja guardado dentro del GeoPackage": estilo_en_gpkg == '#ff7f00',
    "[1 GPKG] grupos = carpetas de origen": {'vectorial', 'vectorial/subcarpeta', 'vectorial/multicapa', 'raster'} <= set(grupos),
    "[1 GPKG] rutas relativas": p.filePathStorage() == Qgis.FilePathType.Relative,
    "[árbol] dos carpetas de origen": raices == ['vectorial', 'raster'],
    "[árbol] GeoPackage con sus 2 capas": multi == [2],
    "[árbol] búsqueda 'PUNTOS' deja solo puntos_23030.shp": visibles == ['puntos_23030.shp'],
    "[árbol] rechaza una carpeta que contiene a otras": rechazo,
    "[árbol] quitar carpeta": tras_quitar == ['vectorial'],
    "[árbol] botón Limpiar vacía el formulario": limpio,
    "[panel] resumen '9 capas · un solo GeoPackage' (carpetas enteras)": resumen.startswith("9 capas · un solo GeoPackage"),
    "[sin reproyectar] cada capa en su SRC y el proyecto en 25830": src5 == [('mdt_4326', 'EPSG:4326'), ('puntos_23030', 'EPSG:23030')]
        and p5.crs().authid() == 'EPSG:25830',
    "[parcial] solo lineas_25830": capas2 == ['lineas_25830'] and 'parcial.gpkg' in ficheros2,
    "[por capa] 8 capas válidas, .gpkg y .tif": len(capas3) == 8 and all(lyr.isValid() for lyr in capas3)
        and all(lyr.source().split('|')[0].lower().endswith(('.gpkg', '.tif')) for lyr in capas3),
    "[por capa] estructura de carpetas conservada": 'vectorial/subcarpeta/puntos_23030.gpkg' in ficheros3,
    "[conservar] 8 capas válidas": len(capas4) == 8 and all(lyr.isValid() for lyr in capas4),
    "[conservar] .shp .geojson .kml .asc .tif se mantienen": ext4 == ['.asc', '.geojson', '.gpkg', '.kml', '.shp', '.tif'],
    "[conservar] estilo naranja en zonas_4326.shp": [_color(lyr) for lyr in capas4 if lyr.source().split('|')[0].endswith('zonas_4326.shp')] == ['#ff7f00'],
    "services.json leído (3 WMS)": len(dock_module.load_services()) == 3,
}

print("=" * 60)
print("QGIS", Qgis.version())
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if avisos:
    print("Avisos:", avisos)
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
