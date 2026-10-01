"""
Prueba rápida de ProjectBuilder con los datos de tests/data.

Uso (consola de Python de QGIS 3 o QGIS 4):
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\smoke_test.py", encoding="utf-8").read())

Crea un proyecto en una carpeta temporal y comprueba capas, SRC, estilos y ficheros.
No abre ventanas: los avisos se recogen y se muestran en la consola.
"""
import os
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsProject
from qgis.PyQt.QtWidgets import QTreeWidgetItemIterator

qgis.utils.reloadPlugin('project_builder')
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data').replace('\\', '/')
SELECCION = ("multicapa.gpkg", "zonas_4326.shp", "puntos_23030.shp", "MAYUSCULAS_4326.TIF")
ESPERADO = {  # nombre de capa -> color esperado (None = cualquiera)
    'lineas_25830': None, 'zonas_4326': None, 'puntos_23030': None, 'MAYUSCULAS_4326': None,
}

avisos = []
dock_module.ProjectBuilderDockWidget.warn = lambda self, msg: avisos.append(msg)  # sin ventanas emergentes

tmp = tempfile.mkdtemp(prefix="pb_test_").replace('\\', '/')
dw = dock_module.ProjectBuilderDockWidget(qgis.utils.iface)
dw.pathFolder.setText(DATA)
dw.load_tree(DATA)
it = QTreeWidgetItemIterator(dw.treeWidget)
while it.value():
    if it.value().text(0) in SELECCION:
        it.value().setSelected(True)
    it += 1
dw.pathFolderProject.setText(tmp)
dw.nameProject.setText("prueba")
dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
dw.create_project(background=False)  # sin segundo plano para poder comprobar el resultado al momento
dw.deleteLater()

p = QgsProject()
ok_read = p.read(tmp + "/prueba.qgz")
capas = list(p.mapLayers().values())
ficheros = sorted(os.path.relpath(os.path.join(d, f), tmp) for d, _, fs in os.walk(tmp) for f in fs)
zonas_shp = [l for l in capas if l.source().replace('\\', '/').endswith('zonas_4326.shp')]

checks = {
    "proyecto .qgz se abre": ok_read,
    "sin avisos": not avisos,
    "5 capas (2 del GeoPackage)": len(capas) == 5,
    "todas válidas": all(l.isValid() for l in capas),
    "todas en EPSG:25830": all(l.crs().authid() == 'EPSG:25830' for l in capas),
    "estilo naranja en zonas_4326.shp": bool(zonas_shp) and zonas_shp[0].renderer().symbol().color().name() == '#ff7f00',
    ".qml copiado": 'vectorial' + os.sep + 'zonas_4326.qml' in ficheros,
    "sin ficheros sueltos (.qgs~, attachments)": not any(f.endswith(('.qgs~', '_attachments.zip', '.qgs')) for f in ficheros),
    "rutas relativas en el proyecto": p.filePathStorage() == Qgis.FilePathType.Relative,
}

print("=" * 60)
print("QGIS", Qgis.version(), "| carpeta:", tmp)
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if avisos:
    print("Avisos:", avisos)
for l in capas:
    print("   -", l.name(), "|", l.crs().authid(), "| válida:", l.isValid())
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
