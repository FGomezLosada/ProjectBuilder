"""
Prueba de la creación EN SEGUNDO PLANO (como al pulsar el botón), con un GeoPackage y servicios web
del catálogo: un WMS, un WMTS y un WFS. Necesita internet.

Uso (consola de Python de QGIS 3 o QGIS 4):
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\background_test.py", encoding="utf-8").read())
"""
import os
import tempfile
import time

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsProject
from qgis.PyQt.QtCore import QCoreApplication, Qt

qgis.utils.reloadPlugin('project_builder')
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data').replace('\\', '/')
SERVICIOS = ('Unidades administrativas', 'Mapa base IGN (teselas, más rápido)', 'Unidades administrativas (WFS, vectorial)')
avisos = []
dock_module.ProjectBuilderDockWidget.warn = lambda self, msg: avisos.append(msg)

tmp = tempfile.mkdtemp(prefix="pb_bg_").replace('\\', '/')
dw = dock_module.ProjectBuilderDockWidget(qgis.utils.iface)
dw.add_source_folder(DATA)


def _marcar(item):
    if item.text(0) == "multicapa.gpkg":
        item.setCheckState(0, Qt.CheckState.Checked)
    for i in range(item.childCount()):
        _marcar(item.child(i))


for _i in range(dw.treeWidget.topLevelItemCount()):
    _marcar(dw.treeWidget.topLevelItem(_i))
dw.addWMS.setChecked(True)
catalogo = dw.servicesTree.topLevelItem(2)
for it in dw._service_leaves(catalogo):
    if it.text(0) in SERVICIOS:
        it.setCheckState(0, Qt.CheckState.Checked)
dw.pathFolderProject.setText(tmp)
dw.nameProject.setText("prueba")
dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))

dw.create_project()  # en segundo plano, como el botón
_t0 = time.time()
while dw.task is not None and time.time() - _t0 < 60:  # espera a que termine la tarea
    QCoreApplication.processEvents()
    time.sleep(0.05)

p = QgsProject()
p.read(tmp + "/prueba.qgz")
capas = {lyr.name(): (lyr.providerType(), lyr.isValid()) for lyr in p.mapLayers().values()}
print("=" * 60)
print("QGIS", Qgis.version(), "| carpeta:", tmp)
print("Avisos:", avisos)
print("Árbol del proyecto:", [n.name() for n in p.layerTreeRoot().children()])
for nombre, (proveedor, valida) in sorted(capas.items()):
    print(f"   - {nombre} [{proveedor}] válida: {valida}")
ok = not avisos and all(nombre in capas and capas[nombre][1] for nombre in SERVICIOS) and 'lineas_25830' in capas
print("RESULTADO:", "TODO CORRECTO" if ok else "HAY FALLOS")
print("=" * 60)
