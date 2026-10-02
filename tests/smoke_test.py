"""
Prueba rápida de ProjectBuilder con los datos de tests/data (no necesita internet).

Uso (consola de Python de QGIS 3 o QGIS 4):
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\smoke_test.py", encoding="utf-8").read())

Crea proyectos en carpetas temporales y comprueba capas, SRC, estilos, ficheros, búsqueda
y selección de capas sueltas de un GeoPackage. No abre ventanas: los avisos se muestran en la consola.
"""
import os
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsProject
from qgis.PyQt.QtCore import Qt

qgis.utils.reloadPlugin('project_builder')
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data').replace('\\', '/')
avisos = []
dock_module.ProjectBuilderDockWidget.warn = lambda self, msg: avisos.append(msg)  # sin ventanas emergentes


def _items(item):
    """Todos los elementos que cuelgan de item (sin QTreeWidgetItemIterator, que puede cerrar QGIS 4)."""
    for i in range(item.childCount()):
        yield item.child(i)
        yield from _items(item.child(i))


def _crear(marcar, nombre):
    """Crea un proyecto marcando los elementos del árbol cuyo texto esté en 'marcar'. Devuelve (proyecto, ficheros, panel)."""
    tmp = tempfile.mkdtemp(prefix="pb_test_").replace('\\', '/')
    dw = dock_module.ProjectBuilderDockWidget(qgis.utils.iface)
    dw.pathFolder.setText(DATA)
    dw.load_tree(DATA)
    for item in list(_items(dw.treeWidget.invisibleRootItem())):
        if item.text(0) in marcar:
            item.setCheckState(0, Qt.CheckState.Checked)  # se marca la casilla, como haría el usuario
    dw.pathFolderProject.setText(tmp)
    dw.nameProject.setText(nombre)
    dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
    dw.create_project(background=False)  # sin segundo plano para comprobar el resultado al momento
    p = QgsProject()
    p.read(f"{tmp}/{nombre}.qgz")
    ficheros = sorted(os.path.relpath(os.path.join(d, f), tmp) for d, _, fs in os.walk(tmp) for f in fs)
    return p, ficheros, dw


# 1. Proyecto completo
p, ficheros, dw = _crear(("multicapa.gpkg", "zonas_4326.shp", "puntos_23030.shp", "MAYUSCULAS_4326.TIF"), "prueba")
capas = list(p.mapLayers().values())
zonas_shp = [lyr for lyr in capas if lyr.source().replace('\\', '/').endswith('zonas_4326.shp')]
gpkg_item = [it for it in _items(dw.treeWidget.invisibleRootItem()) if it.text(0) == 'multicapa.gpkg'][0]

# 2. Búsqueda en el árbol
dw.filterBox.setText("PUNTOS")  # en mayúsculas a propósito: la búsqueda no distingue
visibles = [it.text(0) for it in _items(dw.treeWidget.invisibleRootItem()) if not it.isHidden() and it.childCount() == 0]
dw.filterBox.clear()
todas_visibles = all(not it.isHidden() for it in _items(dw.treeWidget.invisibleRootItem()))
dw.deleteLater()

# 3. Solo una capa interna del GeoPackage
p2, _, dw2 = _crear(("lineas_25830",), "parcial")
capas2 = sorted(lyr.name() for lyr in p2.mapLayers().values())
dw2.deleteLater()

checks = {
    "proyecto .qgz se abre": bool(capas),
    "sin avisos": not avisos,
    "5 capas (2 del GeoPackage)": len(capas) == 5,
    "todas válidas": all(lyr.isValid() for lyr in capas),
    "todas en EPSG:25830": all(lyr.crs().authid() == 'EPSG:25830' for lyr in capas),
    "estilo naranja en zonas_4326.shp": bool(zonas_shp) and zonas_shp[0].renderer().symbol().color().name() == '#ff7f00',
    ".qml copiado": 'vectorial' + os.sep + 'zonas_4326.qml' in ficheros,
    "sin ficheros sueltos (.qgs~, attachments)": not any(f.endswith(('.qgs~', '_attachments.zip', '.qgs')) for f in ficheros),
    "rutas relativas en el proyecto": p.filePathStorage() == Qgis.FilePathType.Relative,
    "services.json leído (3 WMS)": len(dw.services) == 3,
    "GeoPackage muestra sus 2 capas en el árbol": gpkg_item.childCount() == 2,
    "búsqueda 'PUNTOS' deja solo puntos_23030.shp": visibles == ['puntos_23030.shp'],
    "al borrar la búsqueda se ve todo": todas_visibles,
    "GeoPackage parcial: solo lineas_25830": capas2 == ['lineas_25830'],
}

print("=" * 60)
print("QGIS", Qgis.version())
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if avisos:
    print("Avisos:", avisos)
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
