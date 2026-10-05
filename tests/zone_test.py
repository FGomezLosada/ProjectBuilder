"""
Prueba de la zona de trabajo (mejora 4.4) con los datos de tests/data (no necesita internet).

Uso (consola de Python de QGIS 3 o QGIS 4):
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\zone_test.py", encoding="utf-8").read())

Recorta por un rectángulo (mitad oeste de los datos), por una capa con elementos seleccionados y margen,
y en los tres formatos de salida. Comprueba que las geometrías se cortan por el borde, que las capas
sin datos en la zona no se añaden y que la zona queda arriba del todo en el proyecto.
"""
import os
import tempfile

import qgis.utils
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt

qgis.utils.reloadPlugin('project_builder')
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data').replace('\\', '/')
WGS84 = QgsCoordinateReferenceSystem('EPSG:4326')
OESTE = -3.876  # la zona de prueba llega hasta esta longitud (los datos van de -3.905 a -3.845)
avisos, vacias = [], []
PASOS = os.path.join(tempfile.gettempdir(), 'pb_zone_pasos.txt')  # si QGIS se cerrara, aquí queda el último paso hecho
open(PASOS, 'w', encoding='utf-8').close()


def paso(texto):
    with open(PASOS, 'a', encoding='utf-8') as f:
        f.write(texto + "\n")
        f.flush()
        os.fsync(f.fileno())


dock_module.ProjectBuilderDockWidget.warn = lambda self, msg: avisos.append(msg)  # sin ventanas emergentes
dock_module.ProjectBuilderDockWidget.load_project_layers = lambda self, *a: None  # sin el bloque del proyecto abierto: no depende de lo que tenga abierto el usuario
_exito = dock_module.ProjectBuilderDockWidget.show_success
_revision = dock_module.ProjectBuilderDockWidget.start_health_check
dock_module.ProjectBuilderDockWidget.start_health_check = lambda self, force=False: None  # sin revisar servicios por internet
paneles = []  # se cierran al final, después de quitar la capa de prueba
dock_module.ProjectBuilderDockWidget.show_success = lambda self, ruta, empty=(), *a, **k: vacias.append(list(empty))


def _items(item):
    for i in range(item.childCount()):
        yield item.child(i)
        yield from _items(item.child(i))


def _crear(nombre, modo='single', zona=None, margen=0, seleccion=False, capa=None, añadir=True):
    """Crea un proyecto con todo tests/data recortado por la zona. Devuelve (proyecto, carpeta)."""
    tmp = tempfile.mkdtemp(prefix="pb_zona_").replace('\\', '/')
    dw = dock_module.ProjectBuilderDockWidget(qgis.utils.iface)
    for carpeta in (DATA + '/vectorial', DATA + '/raster'):
        dw.add_source_folder(carpeta)
    for i in range(dw.treeWidget.topLevelItemCount()):
        dw.treeWidget.topLevelItem(i).setCheckState(0, Qt.CheckState.Checked)
    dw.pathFolderProject.setText(tmp)
    dw.nameProject.setText(nombre)
    dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
    dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
    dw.groupZone.setChecked(True)
    if capa is not None:
        dw.zoneByLayer.setChecked(True)
        dw.zoneLayer.setLayer(capa)
        dw.zoneSelected.setChecked(seleccion)
    else:
        dw.zoneByExtent.setChecked(True)
        dw.zoneExtent.setOutputExtentFromUser(zona, WGS84)
    dw.zoneMargin.setValue(margen)
    dw.zoneAddLayer.setChecked(añadir)
    dw.update_summary()
    resumen = dw.summaryLabel.text()
    paso(f"{nombre}: creando")
    dw.create_project(background=False)
    paso(f"{nombre}: creado")
    paneles.append(dw)
    p = QgsProject()
    p.read(f"{tmp}/{nombre}.qgz")
    return p, tmp, resumen


def _xmax(lyr):
    """
    Longitud máxima (en grados, EPSG:4326) de los elementos de la capa. Se pasan las geometrías a grados una a una:
    pasar solo el rectángulo de la extensión lo agrandaría y parecería que hay datos fuera de la zona.
    En los ráster se usa su extensión (con un pequeño margen de tolerancia en la comprobación).
    """
    t = QgsCoordinateTransform(lyr.crs(), WGS84, QgsProject.instance())
    if isinstance(lyr, QgsRasterLayer):
        return t.transformBoundingBox(lyr.extent()).xMaximum()
    xs = []
    for f in lyr.getFeatures():
        g = QgsGeometry(f.geometry())
        g.transform(t)
        xs.append(g.boundingBox().xMaximum())
    return max(xs) if xs else None


def _por_nombre(p):
    return {lyr.name(): lyr for lyr in p.mapLayers().values()}


rect = QgsRectangle(-3.91, 36.72, OESTE, 36.79)

paso("inicio")
# 1. Rectángulo, un solo GeoPackage
p1, tmp1, resumen1 = _crear("rect", zona=rect)
c1 = _por_nombre(p1)
vacias1 = vacias[-1] if vacias else None
primera1 = p1.layerTreeRoot().children()[0]
vect1 = [lyr for n, lyr in c1.items() if isinstance(lyr, QgsVectorLayer) and lyr.isSpatial() and n != 'zona_trabajo']
rast1 = [lyr for lyr in c1.values() if isinstance(lyr, QgsRasterLayer)]
def _area_25830(capa):
    """Superficie total de una capa en m² (EPSG:25830), para comparar antes y después del recorte."""
    t = QgsCoordinateTransform(capa.crs(), QgsCoordinateReferenceSystem("EPSG:25830"), QgsProject.instance())
    total = 0
    for f in capa.getFeatures():
        g = QgsGeometry(f.geometry())
        g.transform(t)
        total += g.area()
    return total


area_original = _area_25830(QgsVectorLayer(DATA + "/vectorial/zonas_4326.shp", "o", "ogr"))
area_zonas1 = _area_25830(QgsVectorLayer(f"{tmp1}/rect.gpkg|layername=zonas_4326_2", "z", "ogr"))

# 2. Capa con un elemento seleccionado + 500 m de margen, un GeoPackage por capa
memoria = QgsVectorLayer("Polygon?crs=EPSG:4326", "municipios_prueba", "memory")
for wkt in ("POLYGON((-3.91 36.72, -3.885 36.72, -3.885 36.79, -3.91 36.79, -3.91 36.72))",
            "POLYGON((-3.86 36.72, -3.84 36.72, -3.84 36.79, -3.86 36.79, -3.86 36.72))"):
    f = QgsFeature()
    f.setGeometry(QgsGeometry.fromWkt(wkt))
    memoria.dataProvider().addFeatures([f])
QgsProject.instance().addMapLayer(memoria, False)
memoria.selectByIds([1])
p2, tmp2, _ = _crear("capa", modo='convert', capa=memoria, seleccion=True, margen=500)
zona2 = QgsVectorLayer(f"{tmp2}/zona_trabajo.gpkg|layername=zona_trabajo", "z", "ogr")
xmax_zona2 = _xmax(zona2) if zona2.isValid() else None
vect2 = [lyr for n, lyr in _por_nombre(p2).items() if isinstance(lyr, QgsVectorLayer) and lyr.isSpatial() and n != 'zona_trabajo']

# 3. Conservar el formato original, sin añadir la zona al proyecto
p3, tmp3, _ = _crear("conservar", modo='keep', zona=rect, añadir=False)
c3 = _por_nombre(p3)
shp3 = QgsVectorLayer(f"{tmp3}/vectorial/zonas_4326.shp", "s", "ogr")

paso("comprobaciones 1-3 leídas")
# 4. Errores: zona por capa sin elementos seleccionados
memoria.removeSelection()
avisos.clear()
_crear("error", capa=memoria, seleccion=True)
aviso_sel = list(avisos)
paso("error comprobado")
for dw in paneles:
    dw.zoneLayer.setLayer(None)  # los paneles dejan de usar la capa antes de quitarla del proyecto
QgsProject.instance().removeMapLayer(memoria.id())
paso("capa de prueba quitada")
dock_module.ProjectBuilderDockWidget.show_success = _exito
dock_module.ProjectBuilderDockWidget.start_health_check = _revision
for dw in paneles:
    dw.deleteLater()

checks = {
    "[rect] resumen indica el recorte": "recortadas a la zona" in resumen1,
    "[rect] zona_trabajo arriba del todo y visible": primera1.name() == 'zona_trabajo' and primera1.itemVisibilityChecked(),
    "[rect] zona_trabajo dentro de rect.gpkg con contorno rojo": 'zona_trabajo' in c1
        and c1['zona_trabajo'].source().startswith(f"{tmp1}/rect.gpkg")
        and c1['zona_trabajo'].renderer().symbol().symbolLayer(0).color().name() == '#e31a1c',
    "[rect] lugares_4326 (fuera de la zona) no se añade y se avisa": 'lugares_4326' not in c1 and vacias1 == ['lugares_4326'],
    "[rect] vectoriales cortados por el borde": bool(vect1) and all(_xmax(lyr) <= OESTE + 1e-6 for lyr in vect1 if _xmax(lyr) is not None),
    "[rect] polígonos cortados (menos superficie)": 0 < area_zonas1 < area_original * 0.9,
    "[rect] rásteres recortados": len(rast1) == 3 and all(_xmax(lyr) <= OESTE + 0.002 for lyr in rast1),
    "[rect] vista inicial en la zona": not p1.viewSettings().defaultViewExtent().isNull(),
    "[capa] zona = elemento seleccionado + 500 m": xmax_zona2 is not None and -3.885 + 0.004 < xmax_zona2 < -3.885 + 0.007,
    "[capa] vectoriales dentro de la zona": bool(vect2) and all(_xmax(lyr) <= xmax_zona2 + 1e-6 for lyr in vect2),
    "[conservar] shapefile recortado": shp3.isValid() and _xmax(shp3) <= OESTE + 1e-6,
    "[conservar] sin capa de zona si no se pide": 'zona_trabajo' not in c3 and not os.path.exists(f"{tmp3}/zona_trabajo.gpkg"),
    "[error] avisa si no hay elementos seleccionados": aviso_sel == ["No hay elementos seleccionados en la capa de la zona"],
}

paso("checks calculados")
print("=" * 60)
print("QGIS", Qgis.version(), "· zona de trabajo")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if avisos and avisos != aviso_sel:
    print("Avisos:", avisos)
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
paso("fin")
