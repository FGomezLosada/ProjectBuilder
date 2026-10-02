"""
Prueba de la creación EN SEGUNDO PLANO (como al pulsar el botón), con GeoPackage + 2 WMS.
Necesita internet (los WMS se consultan al crear el proyecto).

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
avisos = []
dock_module.ProjectBuilderDockWidget.warn = lambda self, msg: avisos.append(msg)

tmp = tempfile.mkdtemp(prefix="pb_bg_").replace('\\', '/')
dw = dock_module.ProjectBuilderDockWidget(qgis.utils.iface)
dw.pathFolder.setText(DATA)
dw.load_tree(DATA)


def _marcar(item):
    if item.text(0) == "multicapa.gpkg":
        item.setCheckState(0, Qt.CheckState.Checked)
    for i in range(item.childCount()):
        _marcar(item.child(i))


for _i in range(dw.treeWidget.topLevelItemCount()):
    _marcar(dw.treeWidget.topLevelItem(_i))
dw.addWMS.setChecked(True)
dw.wmsComboBox.setCheckedItems(list(dw.services.keys())[:2])
dw.pathFolderProject.setText(tmp)
dw.nameProject.setText("prueba")
dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))

_tarea = None
dw.create_project()  # en segundo plano, como el botón
_tarea = dw.task
_t0 = time.time()
while dw.task is not None and time.time() - _t0 < 60:  # espera a que termine la tarea
    QCoreApplication.processEvents()
    time.sleep(0.05)

p = QgsProject()
p.read(tmp + "/prueba.qgz")
print("=" * 60)
print("QGIS", Qgis.version(), "| carpeta:", tmp)
print("Errores de la tarea:", _tarea.errors if _tarea else "sin tarea")
print("Exportadas:", [os.path.basename(x) for x in _tarea.exported] if _tarea else "-")
print("Avisos:", avisos)
print("Árbol del proyecto:", [n.name() for n in p.layerTreeRoot().children()])
print("Capas:", sorted(lyr.name() for lyr in p.mapLayers().values()))
print("Ficheros:", sorted(os.path.relpath(os.path.join(d, f), tmp) for d, _, fs in os.walk(tmp) for f in fs))
print("=" * 60)
