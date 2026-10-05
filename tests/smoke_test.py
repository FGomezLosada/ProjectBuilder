"""
Prueba rápida de ProjectBuilder con los datos de tests/data (no necesita internet).

Uso (consola de Python de QGIS 3 o QGIS 4):
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\smoke_test.py", encoding="utf-8").read())

Usa DOS carpetas de origen (tests/data/vectorial y tests/data/raster) y prueba los tres formatos de salida,
la búsqueda, la selección de capas sueltas de un GeoPackage y quitar una carpeta del árbol.
No abre ventanas: los avisos se muestran en la consola.
"""
import os
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsLayerTreeGroup, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import Qt

qgis.utils.reloadPlugin('project_builder')
import project_builder.core.services as svc_module  # noqa: E402
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

import datetime  # noqa: E402
import json  # noqa: E402

def _escribir(ruta, datos):
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(datos, f)


PERFIL = tempfile.mkdtemp(prefix="pb_perfil_")  # perfil de prueba: no se tocan los ficheros del usuario
FAVORITOS = PERFIL + "/favoritos.json"
svc_module.favorites_path = lambda: FAVORITOS
svc_module.health_path = lambda: PERFIL + "/estado_servicios.json"
svc_module.profile_dir = lambda: PERFIL
_cat = {s.name: s for _, lista in svc_module.load_catalog() for s in lista}
_escribir(PERFIL + "/estado_servicios.json", {'fecha': datetime.date.today().isoformat(), 'servicios': {  # comprobación "de hoy": no se lanza otra por red
    _cat['Catastro'].key(): {'ok': False, 'url': _cat['Catastro'].url, 'detalle': 'no responde (prueba)'},
    _cat['Curvas de nivel'].key(): {'ok': True, 'url': 'https://ejemplo.org/mdt-nuevo', 'detalle': 'dirección actualizada'},
}})

DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data').replace('\\', '/')
CARPETAS = (DATA + '/vectorial', DATA + '/raster')
TODAS = ("multicapa.gpkg", "zonas_4326.shp", "puntos_23030.shp", "MAYUSCULAS_4326.TIF",
         "lugares_4326.geojson", "limites_4326.kml", "pendientes_4326.asc")
SINGLE, CONVERT, KEEP = 'single', 'convert', 'keep'
avisos = []
dock_module.ProjectBuilderDockWidget.warn = lambda self, msg: avisos.append(msg)  # sin ventanas emergentes
dock_module.ProjectBuilderDockWidget.load_project_layers = lambda self, *a: None  # sin el bloque del proyecto abierto: no depende de lo que tenga abierto el usuario


def _items(item):
    """Todos los elementos que cuelgan de item (sin QTreeWidgetItemIterator, que puede cerrar QGIS 4)."""
    for i in range(item.childCount()):
        yield item.child(i)
        yield from _items(item.child(i))


def _panel():
    dw = dock_module.ProjectBuilderDockWidget(qgis.utils.iface)
    for carpeta in CARPETAS:
        dw.add_source_folder(carpeta)
    return dw


def _crear(marcar, nombre, modo=SINGLE, reproyectar=True):
    """Crea un proyecto marcando los elementos cuyo texto esté en 'marcar'. Devuelve (proyecto, ficheros, carpeta)."""
    tmp = tempfile.mkdtemp(prefix="pb_test_").replace('\\', '/') + "/carpeta_nueva/proyecto"  # aún no existe: el plugin debe crearla
    dw = _panel()
    for item in list(_items(dw.treeWidget.invisibleRootItem())):
        if item.text(0) in marcar:
            item.setCheckState(0, Qt.CheckState.Checked)  # se marca la casilla, como haría el usuario
    dw.pathFolderProject.setText(tmp)
    dw.nameProject.setText(nombre)
    dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
    dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
    dw.reprojectCheck.setChecked(reproyectar)
    dw.create_project(background=False)  # sin segundo plano para comprobar el resultado al momento
    dw.deleteLater()
    p = QgsProject()
    p.read(f"{tmp}/{nombre}.qgz")
    ficheros = sorted(os.path.relpath(os.path.join(d, f), tmp).replace('\\', '/') for d, _, fs in os.walk(tmp) for f in fs)
    return p, ficheros, tmp


def _grupos(nodo, ruta=()):
    """Rutas de todos los grupos del árbol de capas del proyecto."""
    out = []
    for c in nodo.children():
        if isinstance(c, QgsLayerTreeGroup):
            out.append('/'.join((*ruta, c.name())))
            out += _grupos(c, (*ruta, c.name()))
    return out


def _color(lyr):
    return lyr.renderer().symbol().color().name() if hasattr(lyr.renderer(), 'symbol') else None


# 1. Un solo GeoPackage (por defecto)
p, ficheros, tmp = _crear(TODAS, "prueba")
capas = list(p.mapLayers().values())
zonas_shp = [lyr for lyr in capas if lyr.name() == 'zonas_4326_2']  # la del shapefile (la del GeoPackage se llama zonas_4326)
estilo_en_gpkg = _color(QgsVectorLayer(f"{tmp}/prueba.gpkg|layername=zonas_4326_2", "x", "ogr"))
grupos = _grupos(p.layerTreeRoot())

# 2. Árbol: varias carpetas, búsqueda y quitar carpeta
dw = _panel()
for _i in range(dw.treeWidget.topLevelItemCount()):
    dw.treeWidget.topLevelItem(_i).setCheckState(0, Qt.CheckState.Checked)
dw.update_summary()
resumen = dw.summaryLabel.text()
for _i in range(dw.treeWidget.topLevelItemCount()):
    dw.treeWidget.topLevelItem(_i).setCheckState(0, Qt.CheckState.Unchecked)
raices = [dw.treeWidget.topLevelItem(i).text(0) for i in range(dw.treeWidget.topLevelItemCount())]
multi = [it.childCount() for it in _items(dw.treeWidget.invisibleRootItem()) if it.text(0) == 'multicapa.gpkg']  # se guarda el número, no el elemento
dw.filterBox.setText("PUNTOS")  # en mayúsculas a propósito: la búsqueda no distingue
visibles = [it.text(0) for it in _items(dw.treeWidget.invisibleRootItem()) if not it.isHidden() and it.childCount() == 0]
dw.filterBox.clear()
avisos.clear()
dw.treeWidget.setCurrentItem(dw.treeWidget.topLevelItem(1).child(0))  # una capa de la carpeta raster
dw.remove_current_folder()
tras_quitar = [dw.treeWidget.topLevelItem(i).text(0) for i in range(dw.treeWidget.topLevelItemCount())]
[it for it in _items(dw.treeWidget.topLevelItem(0)) if it.text(0) == 'zonas_4326.shp'][0].setCheckState(0, Qt.CheckState.Checked)
dw.add_source_folder(DATA)  # contiene a 'vectorial': la integra, sin perder lo marcado
integra = (not avisos and [dw.treeWidget.topLevelItem(i).text(0) for i in range(dw.treeWidget.topLevelItemCount())] == ['data']
           and [it.checkState(0) for it in _items(dw.treeWidget.topLevelItem(0)) if it.text(0) == 'zonas_4326.shp']
           == [Qt.CheckState.Checked])
avisos.clear()
# Servicios web: tres bloques, catálogo y favoritos
raices_serv = [dw.servicesTree.topLevelItem(i).text(0) for i in range(dw.servicesTree.topLevelItemCount())]
capas_cat = [it for it in dw._service_leaves() if it.text(0) == 'Mapa base IGN']
dw.servicesTree.setCurrentItem(capas_cat[0])
dw.toggle_favorite()  # ★ añadir
fav_guardado = [s.name for s in svc_module.load_favorites(FAVORITOS)]
fav_arbol = [dw.servicesTree.topLevelItem(0).child(i).text(0) for i in range(dw.servicesTree.topLevelItem(0).childCount())]
for it in dw._service_leaves():
    if it.text(0) in ('Mapa base IGN', 'Ortofoto PNOA máxima actualidad'):
        it.setCheckState(0, Qt.CheckState.Checked)  # 'Mapa base IGN' está dos veces (favorito y catálogo): cuenta una
catastro = [it for it in dw._service_leaves() if it.text(0).replace('⛔', '').strip() == 'Catastro']
catastro_ok = bool(catastro) and catastro[0].isDisabled() and catastro[0].text(0).startswith('⛔')  # se calcula ya: el árbol se reconstruye
curvas = [svc_module.Service.from_dict(it.data(0, dock_module.SERVICE_ROLE)).url for it in dw._service_leaves() if it.text(0) == 'Curvas de nivel']
marcados = [s.name for s in dw.selected_services()]
dw.servicesTree.setCurrentItem(dw.servicesTree.topLevelItem(0).child(0))
dw.toggle_favorite()  # ★ quitar
fav_quitado = svc_module.load_favorites(FAVORITOS)
dw.nameProject.setText("x")
dw.addWMS.setChecked(True)
dw.reset_form()
limpio = dw.treeWidget.topLevelItemCount() == 0 and not dw.nameProject.text() and not dw.addWMS.isChecked() and not dw.selected_services()
dw.deleteLater()

# Catálogo descargado de GitHub: se usa solo si su versión es más reciente
_remoto = PERFIL + "/services_remoto.json"
_escribir(_remoto, {'version': '2000-01-01', 'grupos': []})
catalogo_viejo = svc_module.best_catalog_path()
_escribir(_remoto, {'version': '2999-01-01', 'grupos': [{'nombre': 'Remoto', 'servicios': []}]})
catalogo_nuevo = svc_module.best_catalog_path()
os.remove(_remoto)

# 3. Solo una capa interna del GeoPackage
p2, ficheros2, _ = _crear(("lineas_25830",), "parcial")
capas2 = sorted(lyr.name() for lyr in p2.mapLayers().values())

# 3b. Sin reproyectar: cada capa conserva su SRC original
p5, _, _ = _crear(("puntos_23030.shp", "mdt_4326.tif"), "sin_reproyectar", SINGLE, reproyectar=False)
src5 = sorted((lyr.name(), lyr.crs().authid()) for lyr in p5.mapLayers().values())

# 4. Un GeoPackage por capa
p3, ficheros3, _ = _crear(TODAS, "porcapa", CONVERT)
capas3 = list(p3.mapLayers().values())

# 5. Conservar el formato original
p4, ficheros4, _ = _crear(TODAS, "conservar", KEEP)
capas4 = list(p4.mapLayers().values())
ext4 = sorted({os.path.splitext(f)[1].lower() for f in ficheros4 if not f.endswith(('.qgz', '.qml', '.prj', '.dbf', '.shx', '.cpg', '.xml', '.html'))})

checks = {
    "sin avisos": not avisos,
    "crea la carpeta del proyecto si no existe": os.path.isfile(f"{tmp}/prueba.qgz"),
    "[1 GPKG] 8 capas válidas en EPSG:25830": len(capas) == 8 and all(lyr.isValid() and lyr.crs().authid() == 'EPSG:25830' for lyr in capas),
    "[1 GPKG] solo prueba.qgz, prueba.gpkg y los .tif": all(f in ('prueba.qgz', 'prueba.gpkg', 'informe_prueba.html') or f.endswith(('.tif', '.aux.xml', '.gpkg-wal', '.gpkg-shm')) for f in ficheros)
        and 'raster/pendientes_4326.tif' in ficheros,
    "[1 GPKG] 6 tablas vectoriales dentro de prueba.gpkg": sum(lyr.source().startswith(f"{tmp}/prueba.gpkg") for lyr in capas) == 6,
    "[1 GPKG] nombres repetidos con sufijo (zonas_4326_2)": len(zonas_shp) == 1,
    "[1 GPKG] estilo naranja en el proyecto": bool(zonas_shp) and _color(zonas_shp[0]) == '#ff7f00',
    "[1 GPKG] estilo naranja guardado dentro del GeoPackage": estilo_en_gpkg == '#ff7f00',
    "[1 GPKG] grupos = carpetas de origen": {'vectorial', 'vectorial/subcarpeta', 'vectorial/multicapa', 'raster'} <= set(grupos),
    "[1 GPKG] rutas relativas": p.filePathStorage() == Qgis.FilePathType.Relative,
    "[árbol] dos carpetas de origen": raices == ['vectorial', 'raster'],
    "[árbol] GeoPackage con sus 2 capas": multi == [2],
    "[árbol] búsqueda 'PUNTOS' deja solo puntos_23030.shp": visibles == ['puntos_23030.shp'],
    "[árbol] una carpeta que contiene a otra la integra, sin perder lo marcado": integra,
    "[árbol] quitar carpeta": tras_quitar == ['vectorial'],
    "[árbol] botón Limpiar vacía el formulario": limpio,
    "[panel] resumen '9 capas · un solo GeoPackage' (carpetas enteras)": resumen.startswith("9 capas · un solo GeoPackage"),
    "[sin reproyectar] cada capa en su SRC y el proyecto en 25830": src5 == [('mdt_4326', 'EPSG:4326'), ('puntos_23030', 'EPSG:23030')]
        and p5.crs().authid() == 'EPSG:25830',
    "[parcial] solo lineas_25830": capas2 == ['lineas_25830'] and 'parcial.gpkg' in ficheros2,
    "[por capa] 8 capas válidas, .gpkg y .tif": len(capas3) == 8 and all(lyr.isValid() for lyr in capas3)
        and all(lyr.source().split('|')[0].lower().endswith(('.gpkg', '.tif')) for lyr in capas3),
    "[por capa] estructura de carpetas conservada": 'vectorial/subcarpeta/puntos_23030.gpkg' in ficheros3,
    "[conservar] 8 capas válidas": len(capas4) == 8 and all(lyr.isValid() for lyr in capas4),
    "[conservar] .shp .geojson .kml .asc .tif se mantienen": ext4 == ['.asc', '.geojson', '.gpkg', '.kml', '.shp', '.tif'],
    "[conservar] estilo naranja en zonas_4326.shp": [_color(lyr) for lyr in capas4 if lyr.source().split('|')[0].endswith('zonas_4326.shp')] == ['#ff7f00'],
    "[servicios] tres bloques (Favoritos, Mis conexiones, Catálogo)": raices_serv == ['★ Favoritos', 'Mis conexiones de QGIS', 'Catálogo ProjectBuilder'],
    "[servicios] catálogo con grupos (estatal y comunidades)": len(svc_module.load_catalog()) >= 10,
    "[servicios] ★ añade a favoritos y se guarda": fav_guardado == ['Mapa base IGN'] and fav_arbol == ['Mapa base IGN'],
    "[servicios] una capa marcada dos veces cuenta una": sorted(marcados) == ['Mapa base IGN', 'Ortofoto PNOA máxima actualidad'],
    "[comprobación] servicio caído desactivado con ⛔": catastro_ok,
    "[comprobación] usa la dirección corregida": curvas == ['https://ejemplo.org/mdt-nuevo'],
    "[comprobación] variantes de URL (https, sin /wms.aspx)": svc_module.url_variants('http://a.es/sig/x/wms.aspx')[-1] == 'https://a.es/sig/x',
    "[servicios] ★ quita de favoritos": fav_quitado == [],
    "[catálogo] usa el de GitHub solo si es más reciente": catalogo_viejo == svc_module.SERVICES_FILE
        and os.path.normpath(catalogo_nuevo) == os.path.normpath(_remoto),
}

print("=" * 60)
print("QGIS", Qgis.version())
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if avisos:
    print("Avisos:", avisos)
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
