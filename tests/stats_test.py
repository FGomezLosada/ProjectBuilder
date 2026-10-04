"""
Prueba del informe de capas (mejora 4.6) con los datos de tests/data (no necesita internet).

Uso: tools\\probar.bat stats_test.py   (o en la consola de Python de QGIS:)
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\stats_test.py", encoding="utf-8").read())

Calcula el informe de capas (botón «Informe de capas…») con una zona de trabajo, crea el proyecto y comprueba
que lo calculado antes coincide con lo que hay después; prueba también guardar (PDF, HTML, CSV) y copiar.
"""
import os
import tempfile
from collections import Counter

import qgis.utils
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsDistanceArea,
    QgsLayerTreeLayer,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QApplication

qgis.utils.reloadPlugin('project_builder')
import project_builder.core.stats as stats  # noqa: E402
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data').replace('\\', '/')
TMP = tempfile.mkdtemp(prefix="pb_informe_").replace('\\', '/')
Clase = dock_module.ProjectBuilderDockWidget
avisos, ventanas, destinos = [], [], []
_originales = {n: getattr(Clase, n) for n in ('warn', 'start_health_check', 'show_success', 'show_report_dialog',
                                               'load_project_layers', 'ask_save_path')}
Clase.warn = lambda self, msg: avisos.append(msg)
Clase.start_health_check = lambda self, force=False: None
Clase.show_success = lambda self, ruta, empty=(): None
Clase.show_report_dialog = lambda self, contenido, filas=(): ventanas.append((contenido, filas))
Clase.load_project_layers = lambda self, *a: None  # sin el bloque del proyecto abierto
Clase.ask_save_path = lambda self, propuesta: destinos.pop(0) if destinos else ''


def _panel(nombre, zona=True):
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
    return dw


def _resumen(filas):
    """Lo comparable entre antes y después: (tipo, elementos) de cada capa vectorial y superficie/longitud totales."""
    vectoriales = [f for f in filas if f['elementos'] and f['tipo'] in ('Puntos', 'Líneas', 'Polígonos')]
    return Counter((f['tipo'], f['elementos']) for f in vectoriales), stats.totals(filas)


# 1. Informe de capas con zona de trabajo (ventana)
dw = _panel("con_zona")
dw.show_layers_report()
contenido, previas = ventanas[0] if ventanas else ('', [])

# 2. Guardar en los tres formatos y copiar
destinos += [f"{TMP}/informe.pdf", f"{TMP}/informe.html", f"{TMP}/informe.csv"]
guardados = [dw.save_layers_report(contenido, previas) for _ in range(3)]
csv = open(f"{TMP}/informe.csv", encoding='utf-8-sig').read() if os.path.isfile(f"{TMP}/informe.csv") else ''
dw.copy_layers_report(previas)
portapapeles = QApplication.clipboard().mimeData()
copiado_texto = portapapeles.text() if portapapeles else ''
copiado_html = portapapeles.html() if portapapeles else ''

# 3. Se crea el proyecto: lo que hay en él coincide con lo calculado antes
dw.create_project(background=False)
p = QgsProject()
p.read(f"{TMP}/con_zona/con_zona.qgz")
finales = [stats.layer_stats(nodo.layer(), ellipsoid=p.ellipsoid()) for nodo in p.layerTreeRoot().findLayers()
           if isinstance(nodo, QgsLayerTreeLayer) and nodo.layer() is not None and nodo.layer().name() != 'zona_trabajo']
antes, total_antes = _resumen(previas)
despues, total_despues = _resumen(finales)
ficheros = os.listdir(f"{TMP}/con_zona")

# 4. Superficie sin zona, comparada con un cálculo independiente sobre el elipsoide
dw2 = _panel("sin_zona", zona=False)
filas2 = {f['nombre']: f for f in dw2.preview_rows()}
zonas = QgsVectorLayer(DATA + "/vectorial/zonas_4326.shp", "z", "ogr")
medidor = QgsDistanceArea()
medidor.setSourceCrs(zonas.crs(), QgsProject.instance().transformContext())
medidor.setEllipsoid('EPSG:7030')
esperada = sum(medidor.measureArea(f.geometry()) for f in zonas.getFeatures()) / 10000

for panel in (dw, dw2):
    panel.zoneLayer.setLayer(None)
    panel.deleteLater()
for nombre, funcion in _originales.items():
    setattr(Clase, nombre, funcion)

checks = {
    "ventana «Informe de capas» con las capas": "Informe de capas · con_zona" in contenido and "zonas_4326" in contenido,
    "superficie de la zona en la cabecera": "Superficie de la zona" in contenido,
    "guarda en PDF, HTML y CSV": guardados == [f"{TMP}/informe.pdf", f"{TMP}/informe.html", f"{TMP}/informe.csv"]
        and all(os.path.getsize(r) > 500 for r in guardados if r),
    "CSV para Excel (columnas con ';' y coma decimal)": csv.startswith("Capa;Grupo;Tipo;Elementos") and "zonas_4326" in csv
        and any(',' in linea.split(';')[4] for linea in csv.splitlines()[1:] if len(linea.split(';')) > 4 and linea.split(';')[4]),
    "copiar: celdas para Excel y tabla para Word": copiado_texto.startswith("Capa\tGrupo") and "<table" in copiado_html,
    "mismos elementos antes y después de crear": bool(antes) and antes == despues,
    "misma superficie antes y después (±1 %)": total_antes['superficie_ha'] > 0
        and abs(total_antes['superficie_ha'] - total_despues['superficie_ha']) <= total_antes['superficie_ha'] * 0.01,
    "misma longitud antes y después (±1 %)": total_antes['longitud_km'] > 0
        and abs(total_antes['longitud_km'] - total_despues['longitud_km']) <= total_antes['longitud_km'] * 0.01,
    "superficie en hectáreas reales (elipsoide)": abs(filas2['zonas_4326']['superficie_ha'] - esperada) < 1e-6 * max(esperada, 1),
    "rásteres con tamaño y resolución": any(f['tipo'] == 'Ráster' and 'px' in f['detalle'] for f in previas),
    "ya no se crea un informe automático": not any(f.startswith('informe') for f in ficheros),
    "sin avisos": not avisos,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· informe de capas")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if avisos:
    print("Avisos:", avisos)
if not checks["mismos elementos antes y después de crear"]:
    print("Antes:", sorted(antes.items()), "\nDespués:", sorted(despues.items()))
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
