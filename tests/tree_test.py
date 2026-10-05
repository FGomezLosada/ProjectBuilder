"""
Prueba del árbol de capas: arrastrar carpetas y ficheros (V8), información al pasar el ratón (V4) y «Ver en el mapa» (V5).
Usa copias de tests/data en una carpeta temporal (no necesita internet).

Uso: tools\\probar.bat (o tools\\run_tests.py tree_test.py)
"""
import os
import shutil
import tempfile

import qgis.utils
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsMimeDataUtils,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from qgis.PyQt.QtGui import QDropEvent, QHelpEvent

qgis.utils.reloadPlugin('project_builder')
import project_builder.core.info as info  # noqa: E402
import project_builder.core.services as svc_module  # noqa: E402
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

PERFIL = tempfile.mkdtemp(prefix="pb_perfil_")
svc_module.profile_dir = lambda: PERFIL
svc_module.favorites_path = lambda: PERFIL + "/favoritos.json"
svc_module.health_path = lambda: PERFIL + "/estado_servicios.json"
DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data')
Clase = dock_module.ProjectBuilderDockWidget
avisos = []
_originales = {n: getattr(Clase, n) for n in ('warn', 'start_health_check', 'show_success', 'load_project_layers')}
Clase.warn = lambda self, msg: avisos.append(msg)
Clase.start_health_check = lambda self, force=False: None
Clase.show_success = lambda self, *a, **k: None
Clase.load_project_layers = lambda self, *a: None
paneles = []
N = os.path.normpath


def _panel():
    dw = Clase(qgis.utils.iface)
    paneles.append(dw)
    return dw


def _items(item):
    for i in range(item.childCount()):
        yield item.child(i)
        yield from _items(item.child(i))


def _hijos(item):
    return [item.child(i).text(0) for i in range(item.childCount())]


def _raices(dw):
    return [dw.treeWidget.topLevelItem(i).text(0) for i in range(dw.treeWidget.topLevelItemCount())]


def _item(dw, texto):
    return next((it for it in _items(dw.treeWidget.invisibleRootItem()) if it.text(0) == texto), None)


def _info(panel, texto):
    item = _item(panel, texto)
    return panel.item_info(item) if item is not None else ''


# Datos: un «escritorio» con capas sueltas y una carpeta «datos» con una subcarpeta
TMP = tempfile.mkdtemp(prefix="pb_arbol_")
ESCRITORIO = os.path.join(TMP, "escritorio")
GRANDE = os.path.join(ESCRITORIO, "grande")
DATOS = os.path.join(TMP, "datos")
SUB = os.path.join(DATOS, "sub")
for carpeta in (GRANDE, SUB):
    os.makedirs(carpeta)
for ext in ('.shp', '.shx', '.dbf', '.prj', '.cpg', '.qml'):
    shutil.copy2(os.path.join(DATA, 'vectorial', 'zonas_4326' + ext), ESCRITORIO)
shutil.copy2(os.path.join(DATA, 'vectorial', 'multicapa.gpkg'), ESCRITORIO)
shutil.copy2(os.path.join(DATA, 'raster', 'mdt_4326.tif'), ESCRITORIO)
shutil.copy2(os.path.join(DATA, 'vectorial', 'lugares_4326.geojson'), GRANDE)
shutil.copy2(os.path.join(DATA, 'vectorial', 'limites_4326.kml'), SUB)
shutil.copy2(os.path.join(DATA, 'vectorial', 'lugares_4326.geojson'), os.path.join(DATOS, 'suelto.geojson'))
for nombre in ('notas.txt', 'huerfano.dbf'):
    with open(os.path.join(ESCRITORIO, nombre), 'w') as f:
        f.write("x")

dw = _panel()

# 1. Shapefile arrastrado con todos sus ficheros: aparece una vez, marcado, sin recorrer toda la carpeta
r1 = dw.add_dropped([os.path.join(ESCRITORIO, n) for n in ('zonas_4326.shp', 'zonas_4326.dbf', 'zonas_4326.prj', 'zonas_4326.qml')])
raiz = dw.treeWidget.topLevelItem(0)
paso1 = (r1 == [] and _raices(dw) == ['escritorio'] and _hijos(raiz) == ['zonas_4326.shp']
         and raiz.data(0, dock_module.PARTIAL_ROLE) is True
         and _item(dw, 'zonas_4326.shp').checkState(0) == Qt.CheckState.Checked)

# 2. Un fichero que no es una capa avisa; un acompañante sin su capa se ignora
r2 = dw.add_dropped([os.path.join(ESCRITORIO, 'notas.txt'), os.path.join(ESCRITORIO, 'huerfano.dbf')])
paso2 = len(r2) == 1 and 'notas.txt' in r2[0] and _hijos(raiz) == ['zonas_4326.shp']

# 3. Una carpeta arrastrada dentro de la carpeta a medias: con todo su contenido
r3 = dw.add_dropped([GRANDE])
paso3 = r3 == [] and _hijos(raiz) == ['grande', 'zonas_4326.shp'] and _hijos(_item(dw, 'grande')) == ['lugares_4326.geojson']

# 4. Una capa de un GeoPackage arrastrada desde el Navegador de QGIS: solo esa capa marcada
gpkg = os.path.join(ESCRITORIO, 'multicapa.gpkg')
internas = [s.name() for s in dock_module.vector_sublayers(gpkg)]
uri = QgsMimeDataUtils.Uri()
uri.layerType, uri.providerKey, uri.name = 'vector', 'ogr', internas[0]
uri.uri = f"{gpkg}|layername={internas[0]}"
rutas_navegador = dw.drop_paths(QgsMimeDataUtils.encodeUriList([uri]))
dw.add_dropped(rutas_navegador)
item_gpkg = _item(dw, 'multicapa.gpkg')
marcadas_gpkg = [item_gpkg.child(i).text(0) for i in range(item_gpkg.childCount())
                 if item_gpkg.child(i).checkState(0) == Qt.CheckState.Checked]
paso4 = (rutas_navegador == [(gpkg, internas[0])] and marcadas_gpkg == [internas[0]] and len(internas) > 1)

# 5. Las capas del panel Capas de QGIS no se aceptan (ya están en «Proyecto abierto»)
del_panel_capas = QMimeData()
del_panel_capas.setData(dock_module.LAYER_TREE_MIME, b'x')
paso5 = dw.drop_paths(del_panel_capas) is None

# 6. Soltar de verdad un fichero del Explorador sobre el panel (evento de Qt)
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(os.path.join(ESCRITORIO, 'mdt_4326.tif'))])
evento = QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, mime, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
dw.dropEvent(evento)  #Lo que hace Qt al soltar sobre el panel
pendientes = list(dw.pending_drops)
dw.process_drops()  #En QGIS se lanza solo justo después de soltar
paso6 = evento.isAccepted() and _item(dw, 'mdt_4326.tif') is not None \
    and _item(dw, 'mdt_4326.tif').checkState(0) == Qt.CheckState.Checked

# 7. Se guarda en una configuración y se recupera igual (solo lo arrastrado, no toda la carpeta)
datos = dw.config_to_dict()
b = _panel()
avisos_b = b.apply_config(datos)
paso7 = (avisos_b == [] and b.config_to_dict()['capas'] == datos['capas'] and _raices(b) == ['escritorio']
         and _hijos(b.treeWidget.topLevelItem(0)) == _hijos(raiz)
         and {N(r) for r in datos['capas']['sueltos']} == {N(os.path.join(ESCRITORIO, n)) for n in
                                                          ('grande', 'multicapa.gpkg', 'mdt_4326.tif', 'zonas_4326.shp')})

# 8. Arrastrar después la carpeta entera: se muestra todo y no se pierde nada de lo marcado
antes = sorted(dw._leaf_checks([raiz]))
dw.add_dropped([ESCRITORIO])
raiz = dw.treeWidget.topLevelItem(0)
paso8 = (_raices(dw) == ['escritorio'] and not raiz.data(0, dock_module.PARTIAL_ROLE)
         and sorted(dw._leaf_checks([raiz])) == antes and 'notas.txt' not in _hijos(raiz)
         and dw.config_to_dict()['capas']['sueltos'] == [])

# 9. Un fichero de una carpeta que contiene otra ya añadida entera: la añadida pasa a colgar de ella
c = _panel()
c.add_source_folder(SUB)
_item(c, 'limites_4326.kml').setCheckState(0, Qt.CheckState.Checked)
c.add_dropped([os.path.join(DATOS, 'suelto.geojson')])
datos_c = c.config_to_dict()
d = _panel()
avisos_d = d.apply_config(datos_c)
paso9 = (_raices(c) == ['datos'] and _hijos(c.treeWidget.topLevelItem(0)) == ['sub', 'suelto.geojson']
         and _item(c, 'limites_4326.kml').checkState(0) == Qt.CheckState.Checked
         and {N(r) for r in datos_c['capas']['sueltos']} == {N(SUB), N(os.path.join(DATOS, 'suelto.geojson'))}
         and datos_c['capas']['carpetas'] == [] and avisos_d == [] and d.config_to_dict()['capas'] == datos_c['capas'])

# 10. El proyecto puede ir en la carpeta de un fichero arrastrado (pero no dentro de lo arrastrado)
c.nameProject.setText("arrastrado")
c.pathFolderProject.setText(os.path.join(DATOS, 'proyecto'))
valido = c.validate()
c.pathFolderProject.setText(os.path.join(SUB, 'proyecto'))
dentro = c.validate()
c.pathFolderProject.setText(os.path.join(DATOS, 'proyecto'))
c.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
c.create_project(background=False)
proyecto = QgsProject()
proyecto.read(os.path.join(DATOS, 'proyecto', 'arrastrado.qgz'))
nombres = sorted(lyr.name() for lyr in proyecto.mapLayers().values())
paso10 = valido is None and dentro is not None and any(n.startswith('suelto') for n in nombres) \
    and any(n.startswith('limites') for n in nombres) and not avisos

# 11. Información al pasar el ratón
texto_shp = _info(b, 'zonas_4326.shp')
texto_gpkg = _info(b, 'multicapa.gpkg')
texto_tif = _info(b, 'mdt_4326.tif')
texto_carpeta = b.item_info(b.treeWidget.topLevelItem(0))
paso11 = ('EPSG:4326' in texto_shp and 'elemento' in texto_shp and 'Tamaño' in texto_shp
          and f"{len(internas)} capas dentro" in texto_gpkg and 'píxeles' in texto_tif
          and 'capas' in texto_carpeta and 'arrastrado' in texto_carpeta)
vista = b.treeWidget.viewport()
b.treeWidget.expandAll()
rect = b.treeWidget.visualItemRect(_item(b, 'zonas_4326.shp') or b.treeWidget.topLevelItem(0))
ayuda = QHelpEvent(QEvent.Type.ToolTip, rect.center(), vista.mapToGlobal(rect.center()))
recuadro = b.eventFilter(vista, ayuda)
vacio = QHelpEvent(QEvent.Type.ToolTip, QPoint(5, vista.height() - 3), vista.mapToGlobal(QPoint(5, vista.height() - 3)))
recuadro_vacio = b.eventFilter(vista, vacio)
paso11b = recuadro is True and recuadro_vacio is True

# 12. «Ver en el mapa» y menú del clic derecho
lienzo = qgis.utils.iface.mapCanvas()
b.show_on_map(_item(b, 'zonas_4326.shp'))  #Con None no hace nada
extension_vista = lienzo.extent()
paso12 = (getattr(b, 'last_map_extent', None) is not None and extension_vista.contains(b.last_map_extent))
puntos = QgsVectorLayer(os.path.join(DATA, 'vectorial', 'subcarpeta', 'puntos_23030.shp'), 'p', 'ogr')
en_4326 = info.map_extent([puntos], QgsCoordinateReferenceSystem('EPSG:4326'))
paso12b = en_4326 is not None and -10 < en_4326.xMinimum() < 5 and 35 < en_4326.yMinimum() < 45
acciones = [a.text() for a in b.tree_menu(_item(b, 'zonas_4326.shp')).actions() if not a.isSeparator()] if _item(b, 'zonas_4326.shp') else []
acciones_vacio = [a.text() for a in b.tree_menu(None).actions()]
paso12c = (acciones == ['Ver en el mapa', 'Abrir la carpeta', 'Quitar «escritorio» del árbol']
           and acciones_vacio == ['Añadir carpeta…'])

# 13. Tamaños legibles
paso13 = (info.human_size(850) == '850 B' and info.human_size(12698) == '12,4 KB'
          and info.file_size(os.path.join(ESCRITORIO, 'zonas_4326.shp')) > os.path.getsize(os.path.join(ESCRITORIO, 'zonas_4326.shp')))

for nombre, funcion in _originales.items():
    setattr(Clase, nombre, funcion)
for panel in paneles:
    panel.deleteLater()

checks = {
    "shapefile arrastrado con sus ficheros: una vez, marcado y sin recorrer la carpeta": paso1,
    "avisa de un fichero que no es una capa e ignora acompañantes sueltos": paso2,
    "carpeta arrastrada: con todo su contenido": paso3,
    "capa de un GeoPackage desde el Navegador de QGIS: solo esa capa": paso4,
    "no acepta capas del panel Capas de QGIS": paso5,
    "soltar un fichero del Explorador sobre el panel": paso6,
    "lo arrastrado se guarda y recupera en una configuración": paso7,
    "arrastrar luego la carpeta entera conserva lo marcado": paso8,
    "una carpeta ya añadida pasa a colgar de la de un fichero arrastrado": paso9,
    "crea el proyecto con lo arrastrado (y valida la carpeta destino)": paso10,
    "información de capas, GeoPackage, ráster y carpetas": paso11,
    "recuadro al pasar el ratón (también en la zona vacía)": paso11b,
    "«Ver en el mapa» lleva el mapa a la capa": paso12,
    "extensión reproyectada al SRC del mapa": paso12b,
    "menú del clic derecho": paso12c,
    "tamaños legibles (con ficheros acompañantes)": paso13,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· árbol de capas (arrastrar, información, ver en el mapa)")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'pendientes': pendientes, 'sueltos': datos['capas']['sueltos'], 'r1': r1, 'r2': r2, 'r3': r3, 'hijos': _hijos(dw.treeWidget.topLevelItem(0)), 'rutas_navegador': rutas_navegador,
                        'marcadas_gpkg': marcadas_gpkg, 'avisos': avisos, 'avisos_b': avisos_b, 'avisos_d': avisos_d,
                        'raices_c': _raices(c), 'datos_c': datos_c['capas'], 'valido': valido, 'nombres': nombres,
                        'texto_shp': texto_shp, 'texto_gpkg': texto_gpkg, 'texto_tif': texto_tif, 'texto_carpeta': texto_carpeta,
                        'recuadro': (recuadro, recuadro_vacio), 'acciones': acciones, 'en_4326': en_4326 and en_4326.toString(),
                        'vista': extension_vista.toString(), 'capa': getattr(b, 'last_map_extent', None) and b.last_map_extent.toString()})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
