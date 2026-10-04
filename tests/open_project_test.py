"""
Prueba de las capas del proyecto abierto como origen (mejora 4.10), con los datos de tests/data (no necesita internet).

Uso (consola de Python de QGIS 3 o QGIS 4):
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\open_project_test.py", encoding="utf-8").read())

Añade al proyecto abierto un grupo de prueba con: un Shapefile con un estilo cambiado, una capa temporal (en memoria),
una capa de GeoPackage con filtro, un ráster y una capa XYZ (servicio web). Crea proyectos en dos formatos de salida
y comprueba grupos, estilos, filtros y capas enlazadas. Al terminar quita el grupo de prueba del proyecto abierto.
"""
import os
import tempfile

import qgis.utils
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsLayerTreeGroup,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

qgis.utils.reloadPlugin('project_builder')
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data').replace('\\', '/')
TMP = tempfile.mkdtemp(prefix="pb_abierto_").replace('\\', '/')
Clase = dock_module.ProjectBuilderDockWidget
avisos = []
_originales = {n: getattr(Clase, n) for n in ('warn', 'start_health_check', 'show_success')}
Clase.warn = lambda self, msg: avisos.append(msg)
Clase.start_health_check = lambda self, force=False: None
Clase.show_success = lambda self, ruta, empty=(), report=None: None
GRUPO = "PB prueba proyecto abierto"

# 1. Capas en el proyecto abierto: grupo de prueba > subgrupo Catastro
proyecto = QgsProject.instance()
grupo = proyecto.layerTreeRoot().insertGroup(0, GRUPO)
catastro = grupo.addGroup("Catastro")
zonas = QgsVectorLayer(DATA + "/vectorial/zonas_4326.shp", "zonas estilo propio", "ogr")
zonas.renderer().symbol().setColor(QColor('#123456'))  # estilo cambiado en el proyecto (distinto de su .qml naranja)
memoria = QgsVectorLayer("Point?crs=EPSG:4326&field=nombre:string", "puntos temporales", "memory")
elementos = []
for x, y in ((-3.88, 36.75), (-3.87, 36.755)):
    f = QgsFeature(memoria.fields())
    f.setAttributes(["p"])
    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
    elementos.append(f)
memoria.dataProvider().addFeatures(elementos)
lineas = QgsVectorLayer(DATA + "/vectorial/multicapa.gpkg|layername=lineas_25830", "lineas filtradas", "ogr")
lineas.setSubsetString("fid = 1")
mdt = QgsRasterLayer(DATA + "/raster/mdt_4326.tif", "mdt")
xyz = QgsRasterLayer("type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0", "OSM", "wms")
for capa, destino in ((zonas, catastro), (memoria, grupo), (lineas, grupo), (mdt, grupo), (xyz, grupo)):
    proyecto.addMapLayer(capa, False)
    destino.addLayer(capa)


def _items(item):
    for i in range(item.childCount()):
        yield item.child(i)
        yield from _items(item.child(i))


def _crear(nombre, modo):
    dw = Clase(qgis.utils.iface)
    raiz = dw._project_root()
    prueba = next(it for it in _items(raiz) if it.text(0) == GRUPO)
    prueba.setCheckState(0, Qt.CheckState.Checked)  # se marca el grupo entero
    dw.nameProject.setText(nombre)
    dw.pathFolderProject.setText(f"{TMP}/{nombre}")
    dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
    dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
    dw.update_summary()
    datos = (raiz.text(0), dw.summaryLabel.text(), len(dw.selected_project_layers()), dw.config_to_dict()['proyecto_abierto'])
    dw.create_project(background=False)
    paneles.append(dw)
    p = QgsProject()
    p.read(f"{TMP}/{nombre}/{nombre}.qgz")
    return p, datos


def _grupos(nodo, ruta=()):
    out = []
    for c in nodo.children():
        if isinstance(c, QgsLayerTreeGroup):
            out.append('/'.join((*ruta, c.name())))
            out += _grupos(c, (*ruta, c.name()))
    return out


paneles = []
p1, (titulo, resumen, n_marcadas, en_config) = _crear("abierto_unico", 'single')
c1 = {lyr.name(): lyr for lyr in p1.mapLayers().values()}
p2, _ = _crear("abierto_por_capa", 'convert')
c2 = {lyr.name(): lyr for lyr in p2.mapLayers().values()}

# Actualización automática: una capa nueva en el proyecto abierto aparece en el árbol
dw = paneles[-1]
nueva = QgsVectorLayer("Polygon?crs=EPSG:4326", "capa nueva", "memory")
proyecto.addMapLayer(nueva, False)
grupo.addLayer(nueva)
programado = dw.projectTimer.isActive()  # el aviso de QGIS pone en marcha la actualización (con un pequeño retardo)
dw.load_project_layers()
aparece = any(it.text(0) == "capa nueva" for it in _items(dw._project_root()))
sigue_marcada = all(it.checkState(0) == Qt.CheckState.Checked for it in _items(dw._project_root()) if it.text(0) == "mdt")

# Limpieza: los paneles dejan de usar las capas y se quita el grupo de prueba del proyecto abierto
for panel in paneles:
    panel.zoneLayer.setLayer(None)
for capa in (zonas, memoria, lineas, mdt, xyz, nueva):
    proyecto.removeMapLayer(capa.id())
proyecto.layerTreeRoot().removeChildNode(grupo)
for nombre, funcion in _originales.items():
    setattr(Clase, nombre, funcion)
for panel in paneles:
    panel.deleteLater()


def _color(lyr):
    return lyr.renderer().symbol().color().name() if lyr is not None and hasattr(lyr.renderer(), 'symbol') else None


checks = {
    "bloque «Proyecto abierto en QGIS» arriba del árbol": titulo == "Proyecto abierto en QGIS",
    "marcar el grupo marca sus 5 capas": n_marcadas == 5 and "5 capas" in resumen,
    "se guardan en la configuración": len(en_config) == 5,
    "[GPKG] mismos grupos que el proyecto abierto": {GRUPO, f"{GRUPO}/Catastro"} <= set(_grupos(p1.layerTreeRoot())),
    "[GPKG] 5 capas válidas": len(c1) == 5 and all(lyr.isValid() for lyr in c1.values()),
    "[GPKG] estilo del proyecto abierto (no el .qml)": _color(c1.get("zonas estilo propio")) == '#123456',
    "[GPKG] capa temporal copiada con sus 2 elementos": c1.get("puntos temporales") is not None
        and c1["puntos temporales"].featureCount() == 2 and "abierto_unico.gpkg" in c1["puntos temporales"].source(),
    "[GPKG] filtro respetado (1 línea)": c1.get("lineas filtradas") is not None and c1["lineas filtradas"].featureCount() == 1,
    "[GPKG] ráster copiado a GeoTIFF": c1.get("mdt") is not None and c1["mdt"].source().endswith(".tif")
        and c1["mdt"].source().startswith(f"{TMP}/abierto_unico"),
    "[GPKG] servicio web añadido tal cual": c1.get("OSM") is not None and c1["OSM"].providerType() == 'wms'
        and 'tile.openstreetmap.org' in c1["OSM"].source(),
    "[por capa] ficheros en subcarpetas = grupos": os.path.isfile(f"{TMP}/abierto_por_capa/{GRUPO}/Catastro/zonas estilo propio.gpkg"),
    "[por capa] estilo del proyecto abierto": _color(c2.get("zonas estilo propio")) == '#123456',
    "la lista se actualiza sola al añadir una capa": programado and aparece,
    "al actualizar se conserva lo marcado": sigue_marcada,
    "sin avisos": not avisos,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· capas del proyecto abierto")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if avisos:
    print("Avisos:", avisos)
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
