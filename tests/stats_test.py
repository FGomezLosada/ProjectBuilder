"""
Prueba de las estadísticas e informe (mejora 4.6) con los datos de tests/data (no necesita internet).

Uso (consola de Python de QGIS 3 o QGIS 4):
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\stats_test.py", encoding="utf-8").read())

Calcula las estadísticas previas (botón «Estadísticas…») con una zona de trabajo, crea el proyecto y comprueba
que el informe HTML existe y que lo calculado antes coincide con lo que hay después en el proyecto.
"""
import os
import tempfile
from collections import Counter

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsDistanceArea, QgsProject, QgsRectangle, QgsVectorLayer
from qgis.PyQt.QtCore import Qt

qgis.utils.reloadPlugin('project_builder')
import project_builder.core.stats as stats  # noqa: E402
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data').replace('\\', '/')
TMP = tempfile.mkdtemp(prefix="pb_estadisticas_").replace('\\', '/')
Clase = dock_module.ProjectBuilderDockWidget
avisos, ventanas, informes = [], [], []
_originales = {n: getattr(Clase, n) for n in ('warn', 'start_health_check', 'show_success', 'show_report_dialog', 'load_project_layers')}
Clase.warn = lambda self, msg: avisos.append(msg)
Clase.start_health_check = lambda self, force=False: None
Clase.show_success = lambda self, ruta, empty=(), report=None: informes.append(report)
Clase.show_report_dialog = lambda self, contenido: ventanas.append(contenido)
Clase.load_project_layers = lambda self, *a: None  # sin el bloque del proyecto abierto


def _panel(nombre, zona=True, informe=True):
    dw = Clase(qgis.utils.iface)
    for carpeta in (DATA + '/vectorial', DATA + '/raster'):
        dw.add_source_folder(carpeta)
    for i in range(dw.treeWidget.topLevelItemCount()):
        dw.treeWidget.topLevelItem(i).setCheckState(0, Qt.CheckState.Checked)
    dw.nameProject.setText(nombre)
    dw.pathFolderProject.setText(f"{TMP}/{nombre}")
    dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
    if zona:
        dw.groupZone.setChecked(True)
        dw.zoneByExtent.setChecked(True)
        dw.zoneExtent.setOutputExtentFromUser(QgsRectangle(-3.91, 36.72, -3.876, 36.79), QgsCoordinateReferenceSystem('EPSG:4326'))
    dw.statsCheck.setChecked(informe)
    return dw


def _resumen(filas):
    """Lo comparable entre antes y después: (tipo, elementos) de cada capa vectorial y superficie/longitud totales."""
    vectoriales = [f for f in filas if f['elementos'] and f['tipo'] in ('Puntos', 'Líneas', 'Polígonos')]
    return Counter((f['tipo'], f['elementos']) for f in vectoriales), stats.totals(filas)


# 1. Estadísticas previas con zona de trabajo
dw = _panel("con_informe")
dw.show_preview_stats()
previas = dw.preview_rows()
ventana_ok = len(ventanas) == 1 and "Estadísticas previas" in ventanas[0] and "zonas_4326" in ventanas[0]

# 2. Se crea el proyecto: informe HTML con las capas ya copiadas
dw.create_project(background=False)
finales = getattr(dw, 'last_report_rows', [])
informe = f"{TMP}/con_informe/informe_con_informe.html"
texto = open(informe, encoding='utf-8').read() if os.path.isfile(informe) else ''
antes, total_antes = _resumen(previas)
despues, total_despues = _resumen(finales)

# 3. Superficie de una capa sin zona, comparada con un cálculo independiente sobre el elipsoide
dw2 = _panel("sin_zona", zona=False, informe=False)
filas2 = {f['nombre']: f for f in dw2.preview_rows()}
zonas = QgsVectorLayer(DATA + "/vectorial/zonas_4326.shp", "z", "ogr")
medidor = QgsDistanceArea()
medidor.setSourceCrs(zonas.crs(), QgsProject.instance().transformContext())
medidor.setEllipsoid('EPSG:7030')
esperada = sum(medidor.measureArea(f.geometry()) for f in zonas.getFeatures()) / 10000
dw2.create_project(background=False)
sin_informe = not os.path.exists(f"{TMP}/sin_zona/informe_sin_zona.html")

for panel in (dw, dw2):
    panel.zoneLayer.setLayer(None)
    panel.deleteLater()
for nombre, funcion in _originales.items():
    setattr(Clase, nombre, funcion)

checks = {
    "ventana de estadísticas previas": ventana_ok,
    "informe HTML junto al proyecto": bool(texto) and "Informe del proyecto con_informe" in texto,
    "el mensaje final ofrece el informe": informes and informes[0] and informes[0].replace('\\', '/').endswith("informe_con_informe.html"),
    "informe con la zona y sus hectáreas": "Superficie de la zona" in texto and " ha" in texto,
    "informe con capas sin datos en la zona": "Capas sin datos en la zona de trabajo" in texto and "lugares_4326" in texto,
    "mismos elementos antes y después de crear": bool(antes) and antes == despues,
    "misma superficie antes y después (±1 %)": total_antes['superficie_ha'] > 0
        and abs(total_antes['superficie_ha'] - total_despues['superficie_ha']) <= total_antes['superficie_ha'] * 0.01,
    "misma longitud antes y después (±1 %)": total_antes['longitud_km'] > 0
        and abs(total_antes['longitud_km'] - total_despues['longitud_km']) <= total_antes['longitud_km'] * 0.01,
    "superficie en hectáreas reales (elipsoide)": abs(filas2['zonas_4326']['superficie_ha'] - esperada) < 1e-6 * max(esperada, 1),
    "rásteres con tamaño y resolución": any(f['tipo'] == 'Ráster' and 'px' in f['detalle'] for f in finales),
    "sin informe si la casilla está desmarcada": sin_informe,
    "sin avisos": not avisos,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· estadísticas e informe")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if avisos:
    print("Avisos:", avisos)
if not checks["mismos elementos antes y después de crear"]:
    print("Antes:", sorted(antes.items()), "\nDespués:", sorted(despues.items()))
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
