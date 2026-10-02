"""
Prueba de las composiciones de impresión (mejora 4.5) con los datos de tests/data (no necesita internet).

Uso (consola de Python de QGIS 3 o QGIS 4):
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\layout_test.py", encoding="utf-8").read())

Crea una composición en el proyecto abierto y una plantilla .qpt, las añade a un proyecto nuevo recortado
por una zona de trabajo y comprueba los mapas (SRC y extensión), el título del cajetín y la leyenda.
No toca la lista de plantillas del usuario. Al terminar quita del proyecto abierto la composición de prueba.
"""
import os
import tempfile

import qgis.utils
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsPrintLayout,
    QgsProject,
    QgsReadWriteContext,
    QgsRectangle,
)
from qgis.PyQt.QtCore import Qt

qgis.utils.reloadPlugin('project_builder')
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data').replace('\\', '/')
TMP = tempfile.mkdtemp(prefix="pb_composicion_").replace('\\', '/')
Clase = dock_module.ProjectBuilderDockWidget
avisos, plantillas = [], []
_originales = {n: getattr(Clase, n) for n in ('warn', 'start_health_check', '_layout_files', '_set_layout_files', 'show_success')}
Clase.warn = lambda self, msg: avisos.append(msg)
Clase.start_health_check = lambda self, force=False: None
Clase._layout_files = staticmethod(lambda: list(plantillas))  # lista de plantillas en memoria: no se toca la del usuario
Clase._set_layout_files = staticmethod(lambda rutas: plantillas.__setitem__(slice(None), rutas))
Clase.show_success = lambda self, ruta, empty=(): None
WGS84 = QgsCoordinateReferenceSystem('EPSG:4326')


def _composicion(proyecto, nombre):
    """Composición A4 sencilla: mapa, título con expresión y leyenda."""
    layout = QgsPrintLayout(proyecto)
    layout.initializeDefaults()
    layout.setName(nombre)
    mapa = QgsLayoutItemMap(layout)
    mapa.attemptSetSceneRect(mapa.rect().adjusted(0, 0, 200, 150))
    layout.addLayoutItem(mapa)
    titulo = QgsLayoutItemLabel(layout)
    titulo.setText("[% @project_title %]")
    layout.addLayoutItem(titulo)
    leyenda = QgsLayoutItemLegend(layout)
    leyenda.setLinkedMap(mapa)
    layout.addLayoutItem(leyenda)
    return layout


# Una composición en el proyecto abierto en QGIS y una plantilla .qpt en una carpeta cualquiera
abierta = _composicion(QgsProject.instance(), "PB prueba (proyecto abierto)")
QgsProject.instance().layoutManager().addLayout(abierta)
qpt = TMP + "/cajetin_prueba.qpt"
_composicion(QgsProject.instance(), "x").saveAsTemplate(qpt, QgsReadWriteContext())
no_qpt = TMP + "/no_es_plantilla.qpt"
with open(no_qpt, 'w', encoding='utf-8') as f:
    f.write("esto no es una plantilla")

dw = Clase(qgis.utils.iface)
bloques = [dw.layoutsTree.topLevelItem(i).text(0) for i in range(dw.layoutsTree.topLevelItemCount())]
dw.add_layout_file(qpt)  # como si se eligiera con el botón «Añadir plantilla .qpt…»
dw.check_layouts([('proyecto', "PB prueba (proyecto abierto)"), ('fichero', qpt)])
marcadas = dw.selected_layouts()
dw.add_source_folder(DATA + '/vectorial')
for i in range(dw.treeWidget.topLevelItemCount()):
    dw.treeWidget.topLevelItem(i).setCheckState(0, Qt.CheckState.Checked)
dw.nameProject.setText("con_composicion")
dw.pathFolderProject.setText(TMP + "/proyecto")
dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
dw.groupZone.setChecked(True)
dw.zoneByExtent.setChecked(True)
zona = QgsRectangle(-3.89, 36.74, -3.87, 36.76)
dw.zoneExtent.setOutputExtentFromUser(zona, WGS84)
dw.update_summary()
resumen = dw.summaryLabel.text()
configuracion = dw.config_to_dict()['composiciones']
dw.create_project(background=False)

p = QgsProject()
p.read(TMP + "/proyecto/con_composicion.qgz")
nuevas = {lyt.name(): lyt for lyt in p.layoutManager().printLayouts()}
zona_25830 = QgsCoordinateTransform(WGS84, p.crs(), p).transformBoundingBox(zona)


def _mapa(lyt):
    return next(i for i in lyt.items() if isinstance(i, QgsLayoutItemMap))


def _texto(lyt):
    return next(i for i in lyt.items() if isinstance(i, QgsLayoutItemLabel)).currentText()


def _leyenda(lyt):
    return next(i for i in lyt.items() if isinstance(i, QgsLayoutItemLegend))


# Plantilla estropeada: avisa y el proyecto se crea igual
avisos.clear()
dw.add_layout_file(no_qpt)
dw.check_layouts([('fichero', no_qpt)])
dw.nameProject.setText("con_error")
dw.create_project(background=False)
aviso_mala = list(avisos)

QgsProject.instance().layoutManager().removeLayout(abierta)
for nombre, funcion in _originales.items():
    setattr(Clase, nombre, funcion)
dw.zoneLayer.setLayer(None)
dw.deleteLater()

checks = {
    "lista: composición del proyecto abierto": "Del proyecto abierto" in bloques,
    "lista: plantilla .qpt añadida y marcada": marcadas == [('proyecto', "PB prueba (proyecto abierto)"), ('fichero', qpt)],
    "resumen indica 2 composiciones": "2 composiciones" in resumen,
    "se guardan en la configuración": configuracion == [['proyecto', "PB prueba (proyecto abierto)"], ['fichero', qpt]],
    "proyecto nuevo con las 2 composiciones": sorted(nuevas) == ["PB prueba (proyecto abierto)", "cajetin_prueba"],
    "mapas en el SRC del proyecto": all(_mapa(lyt).crs().authid() == 'EPSG:25830' for lyt in nuevas.values()),
    "mapas centrados en la zona de trabajo": all(_mapa(lyt).extent().contains(zona_25830)
                                                 and _mapa(lyt).extent().width() < zona_25830.width() * 3
                                                 for lyt in nuevas.values()),
    "mapas con las capas del proyecto (no fijas)": all(not _mapa(lyt).keepLayerSet() for lyt in nuevas.values()),
    "título del cajetín = nombre del proyecto": all(_texto(lyt) == "con_composicion" for lyt in nuevas.values()),
    "leyenda con las capas del proyecto": all(_leyenda(lyt).autoUpdateModel() for lyt in nuevas.values()),
    "plantilla estropeada: avisa y crea el proyecto": len(aviso_mala) == 1 and "no_es_plantilla" in aviso_mala[0]
        and os.path.isfile(TMP + "/proyecto/con_error.qgz"),
}

print("=" * 60)
print("QGIS", Qgis.version(), "· composiciones")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if avisos and not checks["plantilla estropeada: avisa y crea el proyecto"]:
    print("Avisos:", avisos)
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
