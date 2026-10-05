"""
Prueba de los iconos de los estilos (mejora 4.8) con datos creados al vuelo (no necesita internet).

Uso: tools\\probar.bat icons_test.py   (o en la consola de Python de QGIS:)
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\icons_test.py", encoding="utf-8").read())

Crea una carpeta de capas cuyos estilos usan SVG de una carpeta de iconos «del cliente» (dos con el mismo nombre y
distinto dibujo, uno que no existe y uno de serie de QGIS), crea el proyecto, lo mueve a otra carpeta y comprueba
que los iconos se siguen viendo.
"""
import glob
import os
import shutil
import tempfile
import zipfile

import qgis.utils
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerLineSymbolLayer,
    QgsMarkerSymbol,
    QgsProject,
    QgsRenderContext,
    QgsSingleSymbolRenderer,
    QgsSvgMarkerSymbolLayer,
    QgsSVGFillSymbolLayer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt

qgis.utils.reloadPlugin('project_builder')
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data').replace('\\', '/')
TMP = tempfile.mkdtemp(prefix="pb_iconos_").replace('\\', '/')
Clase = dock_module.ProjectBuilderDockWidget
avisos = []
_originales = {n: getattr(Clase, n) for n in ('warn', 'start_health_check', 'show_success', 'load_project_layers')}
Clase.warn = lambda self, msg: avisos.append(msg)
Clase.start_health_check = lambda self, force=False: None
Clase.show_success = lambda self, ruta, empty=(): None
Clase.load_project_layers = lambda self, *a: None

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="{r}" fill="#2a2"/></svg>'

# 1. Datos de origen: capas + carpeta de iconos del cliente (fuera de la carpeta de capas, como suele llegar)
ORIGEN, ICONOS = f"{TMP}/capas", f"{TMP}/iconos_cliente"
os.makedirs(ORIGEN)
os.makedirs(f"{ICONOS}/otra_serie")
with open(f"{ICONOS}/arbol.svg", 'w') as f:
    f.write(SVG.format(r=4))
with open(f"{ICONOS}/otra_serie/arbol.svg", 'w') as f:  # mismo nombre, distinto dibujo
    f.write(SVG.format(r=2))
for patron in ("zonas_4326.*", "subcarpeta/puntos_23030.*"):
    for fichero in glob.glob(f"{DATA}/vectorial/{patron}"):
        if not fichero.endswith('.qml'):
            shutil.copy2(fichero, ORIGEN)
serie = next((s for s in glob.glob(os.path.join(QgsApplication.pkgDataPath(), 'svg', '**', '*.svg'), recursive=True)), None)

puntos = QgsVectorLayer(f"{ORIGEN}/puntos_23030.shp", "puntos", "ogr")
marcador = QgsMarkerSymbol()
marcador.changeSymbolLayer(0, QgsSvgMarkerSymbolLayer(f"{ICONOS}/arbol.svg", 6))
if serie:
    marcador.appendSymbolLayer(QgsSvgMarkerSymbolLayer(serie, 3))  # icono de serie de QGIS: no se copia
puntos.setRenderer(QgsSingleSymbolRenderer(marcador))
puntos.saveNamedStyle(f"{ORIGEN}/puntos_23030.qml")

zonas = QgsVectorLayer(f"{ORIGEN}/zonas_4326.shp", "zonas", "ogr")
relleno = QgsFillSymbol()
relleno.changeSymbolLayer(0, QgsSVGFillSymbolLayer(f"{ICONOS}/otra_serie/arbol.svg", 8, 0))
zonas.setRenderer(QgsSingleSymbolRenderer(relleno))
zonas.saveNamedStyle(f"{ORIGEN}/zonas_4326.qml")

shutil.copy2(f"{DATA}/vectorial/multicapa.gpkg", f"{ORIGEN}/lineas.gpkg")
lineas = QgsVectorLayer(f"{ORIGEN}/lineas.gpkg|layername=lineas_25830", "lineas", "ogr")
linea = QgsLineSymbol()
marcas = QgsMarkerLineSymbolLayer()
marcas.setSubSymbol(QgsMarkerSymbol([QgsSvgMarkerSymbolLayer(f"{ICONOS}/no_existe.svg", 4)]))
linea.changeSymbolLayer(0, marcas)
lineas.setRenderer(QgsSingleSymbolRenderer(linea))
lineas.saveStyleToDatabase("default", "", True, "")  # estilo dentro del GeoPackage de origen
del puntos, zonas, lineas


def _crear(nombre, modo):
    dw = Clase(qgis.utils.iface)
    dw.add_source_folder(ORIGEN)
    dw.treeWidget.topLevelItem(0).setCheckState(0, Qt.CheckState.Checked)
    dw.nameProject.setText(nombre)
    dw.pathFolderProject.setText(f"{TMP}/{nombre}")
    dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
    dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
    avisos.clear()
    dw.create_project(background=False)
    dw.deleteLater()
    return list(avisos)


def _rutas(proyecto):
    """Rutas de los iconos SVG de cada capa del proyecto: {capa: [rutas]}."""
    return {capa.name(): _rutas_capa(capa) for capa in proyecto.mapLayers().values()}


def _rutas_capa(capa):
    """Rutas de los iconos SVG que usa una capa (también los de sus subsímbolos)."""
    rutas = []
    for simbolo in capa.renderer().symbols(QgsRenderContext()):
        pila = list(simbolo.symbolLayers())
        while pila:
            nivel = pila.pop()
            if isinstance(nivel, QgsSvgMarkerSymbolLayer):
                rutas.append(nivel.path())
            elif isinstance(nivel, QgsSVGFillSymbolLayer):
                rutas.append(nivel.svgFilePath())
            if nivel.subSymbol() is not None:
                pila += list(nivel.subSymbol().symbolLayers())
    return rutas


# 2. Un solo GeoPackage
avisos1 = _crear("unico", 'single')
iconos1 = sorted(os.listdir(f"{TMP}/unico/iconos")) if os.path.isdir(f"{TMP}/unico/iconos") else []
with zipfile.ZipFile(f"{TMP}/unico/unico.qgz") as z:
    qgs = z.read(next(n for n in z.namelist() if n.endswith('.qgs'))).decode('utf-8')
capa_gpkg = QgsVectorLayer(f"{TMP}/unico/unico.gpkg|layername=puntos_23030", "puntos_23030", "ogr")  # con su estilo guardado dentro
rutas_gpkg = _rutas_capa(capa_gpkg)
del capa_gpkg  # se cierra el GeoPackage antes de mover la carpeta

# 3. Se mueve la carpeta del proyecto entera a otro sitio: los iconos se siguen encontrando
shutil.move(f"{TMP}/unico", f"{TMP}/movido")
p = QgsProject()
p.read(f"{TMP}/movido/unico.qgz")
rutas_movido = _rutas(p)
propios = [r for rs in rutas_movido.values() for r in rs if 'iconos' in r.replace('\\', '/').split('/')[-2:-1]]

# 4. Un GeoPackage por capa
avisos2 = _crear("por_capa", 'convert')
iconos2 = sorted(os.listdir(f"{TMP}/por_capa/iconos")) if os.path.isdir(f"{TMP}/por_capa/iconos") else []

for nombre, funcion in _originales.items():
    setattr(Clase, nombre, funcion)

checks = {
    "iconos usados copiados a iconos/ (dos con el mismo nombre)": iconos1 == ['arbol.svg', 'arbol_2.svg'],
    "el icono de serie de QGIS no se copia": serie is None or os.path.basename(serie) not in iconos1,
    "el proyecto guarda rutas relativas a iconos/": "iconos/arbol.svg" in qgs and "iconos/arbol_2.svg" in qgs
        and f"{ICONOS}/arbol.svg" not in qgs and f"{ICONOS}/otra_serie/arbol.svg" not in qgs,
    "el estilo dentro del GeoPackage apunta a la copia": any(r.replace('\\', '/').endswith('/unico/iconos/arbol.svg') for r in rutas_gpkg),
    "proyecto movido: los iconos se siguen encontrando": len(propios) == 2 and all(os.path.isfile(r) for r in propios),
    "aviso del icono que no existe": any('no_existe.svg' in a for a in avisos1),
    "[por capa] también copia los iconos": iconos2 == ['arbol.svg', 'arbol_2.svg'],
    "[por capa] mismo aviso": any('no_existe.svg' in a for a in avisos2),
}

print("=" * 60)
print("QGIS", Qgis.version(), "· iconos de los estilos")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("iconos:", iconos1, "| rutas movido:", rutas_movido, "| gpkg:", rutas_gpkg, "| avisos:", avisos1)
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
