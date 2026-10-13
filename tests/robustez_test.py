"""
Prueba de robustez: casos límite que un usuario real se puede encontrar (revisión previa a la publicación).
Cada caso es independiente: si uno falla, los demás se siguen comprobando.

Uso: tools\\probar.bat (o tools\\run_tests.py robustez_test.py robustez_fondo_test.py)
"""
import faulthandler
import os
import shutil
import sys
import tempfile
import time
import traceback

import qgis.utils
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsRasterLayer,
    QgsTask,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QCoreApplication, Qt

qgis.utils.reloadPlugin('project_builder')
import project_builder.core.exporter as exporter  # noqa: E402
import project_builder.core.icons as icons  # noqa: E402
import project_builder.core.open_project as open_project  # noqa: E402
import project_builder.core.scanner as scanner  # noqa: E402
import project_builder.core.services as svc_module  # noqa: E402
import project_builder.core.stats as stats  # noqa: E402
import project_builder.core.task as task_module  # noqa: E402
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402
from project_builder.core import configs  # noqa: E402
from project_builder.core.clip import geometry_from_extent, write_zone  # noqa: E402

faulthandler.enable(file=sys.stdout, all_threads=True)  #Diagnóstico si QGIS se cerrara
PERFIL = tempfile.mkdtemp(prefix="pb_perfil_")
svc_module.profile_dir = lambda: PERFIL
svc_module.favorites_path = lambda: PERFIL + "/favoritos.json"
svc_module.health_path = lambda: PERFIL + "/estado_servicios.json"
DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data')
TMP = tempfile.mkdtemp(prefix="pb_robustez_")
Clase = dock_module.ProjectBuilderDockWidget
avisos = []
_originales = {n: getattr(Clase, n) for n in ('warn', 'start_health_check', 'show_success', 'load_project_layers')}
Clase.warn = lambda self, msg: avisos.append(msg)
Clase.start_health_check = lambda self, force=False: None
Clase.show_success = lambda self, ruta, empty=(), errors=(), *a, **k: avisos.extend(errors)
Clase.load_project_layers = lambda self, *a: None
paneles = []
resultados = {}
detalles = {}


GRUPO = os.environ.get('PB_ROBUSTEZ', 'base')  #'base' (este fichero) o 'fondo' (robustez_fondo_test.py)


def prueba(nombre, grupo='base'):
    """
    Decorador: ejecuta el caso y anota OK/FALLO (y la excepción, si la hay).
    Los casos con exportación en segundo plano van en su propio QGIS (grupo 'fondo'): muchas pruebas seguidas en un mismo
    proceso acumulan objetos y pueden cerrar QGIS, como ya pasó con la batería completa.
    """
    def envolver(funcion):
        if grupo != GRUPO:
            return funcion
        saltar = [s for s in os.environ.get('PB_SALTAR', '').split(';') if s]
        if any(s.lower() in nombre.lower() for s in saltar):  #Diagnóstico: saltar casos por una parte de su nombre
            return funcion
        print(f"[inicio] {nombre}", flush=True)  #Si QGIS se cerrara, se sabría en qué caso
        try:
            ok, detalle = funcion()
        except Exception:  # noqa: BLE001
            ok, detalle = False, traceback.format_exc(limit=4)
        print(f"[fin] {nombre}: {'OK' if ok else 'FALLO'}", flush=True)
        resultados[nombre] = bool(ok)
        if not ok:
            detalles[nombre] = detalle
        return funcion
    return envolver


def _panel():
    dw = Clase(qgis.utils.iface)
    paneles.append(dw)
    return dw


def _items(item):
    for i in range(item.childCount()):
        yield item.child(i)
        yield from _items(item.child(i))


def _poligonos(ruta, geometrias, crs='EPSG:4326', driver='ESRI Shapefile', capa=None):
    """Crea una capa de polígonos con esas geometrías (WKT)."""
    memoria = QgsVectorLayer(f"Polygon?crs={crs}" if crs else "Polygon", 'tmp', 'memory')
    elementos = []
    for wkt in geometrias:
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        elementos.append(f)
    memoria.dataProvider().addFeatures(elementos)
    opciones = QgsVectorFileWriter.SaveVectorOptions()
    opciones.driverName = driver
    if capa:
        opciones.layerName = capa
    error = QgsVectorFileWriter.writeAsVectorFormatV3(memoria, ruta, QgsProject.instance().transformContext(), opciones)[0]
    assert error == QgsVectorFileWriter.WriterError.NoError, error
    return ruta


ZONA = write_zone(*geometry_from_extent(QgsVectorLayer(DATA + '/vectorial/zonas_4326.shp', 'z', 'ogr').extent(),
                                        QgsCoordinateReferenceSystem('EPSG:4326')))
CENTRO_X, CENTRO_Y = -3.874, 36.755  #Dentro de la zona de los datos de prueba
PAJARITA = (f"POLYGON(({CENTRO_X - 0.01} {CENTRO_Y - 0.01},{CENTRO_X + 0.01} {CENTRO_Y + 0.01},"
            f"{CENTRO_X + 0.01} {CENTRO_Y - 0.01},{CENTRO_X - 0.01} {CENTRO_Y + 0.01},{CENTRO_X - 0.01} {CENTRO_Y - 0.01}))")
CUADRADO = (f"POLYGON(({CENTRO_X - 0.005} {CENTRO_Y - 0.005},{CENTRO_X + 0.005} {CENTRO_Y - 0.005},"
            f"{CENTRO_X + 0.005} {CENTRO_Y + 0.005},{CENTRO_X - 0.005} {CENTRO_Y + 0.005},{CENTRO_X - 0.005} {CENTRO_Y - 0.005}))")


@prueba("geometría inválida (pajarita) con zona de trabajo: se exporta igualmente")
def _():
    origen = _poligonos(os.path.join(TMP, 'invalida.shp'), [PAJARITA, CUADRADO])
    destino = os.path.join(TMP, 'salida_invalida', 'invalida.gpkg')
    exporter.export_layer(origen, destino, None, zone=ZONA)
    n = QgsVectorLayer(destino, 'x', 'ogr').featureCount()
    return n >= 2, f"elementos exportados: {n}"


@prueba("carpeta con apóstrofo, tildes y espacios (GeoPackage común)")
def _():
    gpkg = os.path.join(TMP, "L'Alfàs del Pi", "Señalización vial", "proyecto.gpkg")
    exporter.export_to_shared_geopackage(DATA + '/vectorial/zonas_4326.shp', gpkg, {'zonas_4326': 'zonas'},
                                         QgsCoordinateReferenceSystem('EPSG:25830'))
    capa = QgsVectorLayer(f"{gpkg}|layername=zonas", 'x', 'ogr')
    return capa.isValid() and capa.featureCount() == 3, f"válida={capa.isValid()} elementos={capa.featureCount()}"


@prueba("capa sin SRC (shapefile sin .prj): se copia sin reproyectar ni recortar, con aviso")
def _():
    carpeta = os.path.join(TMP, 'sin_src')
    os.makedirs(carpeta)
    for ext in ('.shp', '.shx', '.dbf'):
        shutil.copy2(DATA + '/vectorial/zonas_4326' + ext, os.path.join(carpeta, 'zonas' + ext))
    tarea = task_module.ExportTask([task_module.Job(os.path.join(carpeta, 'zonas.shp'),
                                                    os.path.join(TMP, 'salida_sin_src', 'zonas.gpkg'), ('g',))],
                                   QgsCoordinateReferenceSystem('EPSG:25830'), ZONA)
    ok = tarea.run()
    capa = QgsVectorLayer(os.path.join(TMP, 'salida_sin_src', 'zonas.gpkg'), 'x', 'ogr')
    return (ok and capa.featureCount() == 3 and any('SRC' in e for e in tarea.errors)
            and abs(capa.extent().xMinimum() + 3.895) < 0.001), f"errores={tarea.errors} n={capa.featureCount()} ext={capa.extent().toString()}"


@prueba("capa sin SRC en el modo recomendado (un solo GeoPackage común)")
def _():
    carpeta = os.path.join(TMP, 'sin_src_comun')
    os.makedirs(carpeta)
    for ext in ('.shp', '.shx', '.dbf'):
        shutil.copy2(DATA + '/vectorial/zonas_4326' + ext, os.path.join(carpeta, 'zonas' + ext))
    gpkg = os.path.join(TMP, 'salida_comun', 'proyecto.gpkg')
    exporter.export_to_shared_geopackage(DATA + '/vectorial/lugares_4326.geojson', gpkg, {'lugares_4326': 'lugares'},
                                         QgsCoordinateReferenceSystem('EPSG:25830'))
    notas = []
    exporter.export_to_shared_geopackage(os.path.join(carpeta, 'zonas.shp'), gpkg, {'zonas': 'zonas'},
                                         QgsCoordinateReferenceSystem('EPSG:25830'), zone=ZONA, notes=notas)
    zonas = QgsVectorLayer(f"{gpkg}|layername=zonas", 'z', 'ogr')
    lugares = QgsVectorLayer(f"{gpkg}|layername=lugares", 'l', 'ogr')
    return (zonas.featureCount() == 3 and lugares.featureCount() == 3 and notas), \
        f"zonas={zonas.featureCount()} lugares={lugares.featureCount()} notas={notas}"


@prueba("zona de trabajo dibujada con autointersecciones (pajarita)")
def _():
    from project_builder.core.clip import geometry_from_layer
    capa = QgsVectorLayer(_poligonos(os.path.join(TMP, 'zona_pajarita.shp'), [PAJARITA]), 'zona', 'ogr')
    geometria, crs = geometry_from_layer(capa)
    return (geometria.type() == Qgis.GeometryType.Polygon and geometria.area() > 0 and geometria.isGeosValid()
            and write_zone(geometria, crs)), f"tipo={geometria.wkbType()} área={geometria.area()}"


@prueba("contraseñas fuera también en servicios web y configuraciones copiadas a mano")
def _():
    wms = "contextualWMSLegend=0&crs=EPSG:25830&format=image/png&layers=a&password=secreto&username=pepe&styles=&url=https://x.es/wms"
    limpia = configs.strip_credentials(wms)
    os.makedirs(configs.configs_dir(), exist_ok=True)
    with open(os.path.join(configs.configs_dir(), 'copiada_a_mano.json'), 'w', encoding='utf-8') as f:
        f.write('{"version": 1, "capas": {}}')
    nombres = [n for n, _ in configs.list_configs()]
    ruta = configs.config_path('copiada_a_mano')
    configs.delete_config('copiada_a_mano')
    return ('secreto' not in limpia and 'pepe' not in limpia and 'url=https://x.es/wms' in limpia
            and 'copiada_a_mano' in nombres and ruta.endswith('copiada_a_mano.json')
            and not os.path.isfile(ruta)), f"{limpia} {nombres} {ruta}"


@prueba("un error inesperado en una capa no aborta la tarea (se anota y sigue)")
def _():
    original = task_module.export_layer
    llamadas = []

    def falla(origen, *a, **k):
        llamadas.append(origen)
        if len(llamadas) == 1:
            raise OSError("disco lleno (simulado)")
        return original(origen, *a, **k)
    task_module.export_layer = falla
    try:
        jobs = [task_module.Job(DATA + '/vectorial/lugares_4326.geojson', os.path.join(TMP, 's1', 'a.gpkg'), ()),
                task_module.Job(DATA + '/vectorial/limites_4326.kml', os.path.join(TMP, 's1', 'b.gpkg'), ())]
        tarea = task_module.ExportTask(jobs, None)
        ok = tarea.run()
    finally:
        task_module.export_layer = original
    return ok and len(tarea.outputs) == 1 and any('disco lleno' in e for e in tarea.errors), f"ok={ok} errores={tarea.errors}"


@prueba("cancelar durante la última capa cancela de verdad")
def _():
    original = task_module.export_layer
    tarea = task_module.ExportTask([task_module.Job(DATA + '/vectorial/lugares_4326.geojson', os.path.join(TMP, 's2', 'a.gpkg'), ())], None)

    def cancela(*a, **k):
        tarea.cancel()
        return original(*a, **k)
    task_module.export_layer = cancela
    try:
        ok = tarea.run()
    finally:
        task_module.export_layer = original
    return ok is False, f"run() devolvió {ok}"


@prueba("origen y destino iguales: nunca se sobrescribe el origen")
def _():
    carpeta = os.path.join(TMP, 'mismo')
    os.makedirs(carpeta)
    for ext in ('.shp', '.shx', '.dbf', '.prj'):
        shutil.copy2(DATA + '/vectorial/zonas_4326' + ext, os.path.join(carpeta, 'zonas' + ext))
    ruta = os.path.join(carpeta, 'zonas.shp')
    try:
        exporter.export_layer(ruta, ruta, QgsCoordinateReferenceSystem('EPSG:25830'))
        lanzo = False
    except exporter.ExportError:
        lanzo = True
    return lanzo and QgsVectorLayer(ruta, 'x', 'ogr').featureCount() == 3, f"lanzó error={lanzo}"


@prueba("carpeta sin permiso dentro de una carpeta de capas: se salta y se ve el resto")
def _():
    carpeta = os.path.join(TMP, 'con_bloqueada')
    os.makedirs(os.path.join(carpeta, 'bloqueada'))
    shutil.copy2(DATA + '/vectorial/lugares_4326.geojson', carpeta)
    original = scanner.os.listdir

    def listdir(ruta):
        if os.path.basename(os.path.normpath(ruta)) == 'bloqueada':
            raise PermissionError(13, "Acceso denegado", ruta)
        return original(ruta)
    scanner.os.listdir = listdir
    try:
        nombres = [e.name for e in scanner.scan_folder(carpeta)]
        dw = _panel()
        dw.add_source_folder(carpeta)
        arbol = [it.text(0) for it in _items(dw.treeWidget.invisibleRootItem())]
    finally:
        scanner.os.listdir = original
    return 'lugares_4326.geojson' in nombres and 'lugares_4326.geojson' in arbol, f"{nombres} {arbol}"


@prueba("nombres reservados de Windows (CON, NUL, AUX...) no se usan como fichero")
def _():
    return all(open_project.safe_name(n).upper() not in ('CON', 'NUL', 'AUX', 'PRN', 'COM1', 'LPT1')
               for n in ('CON', 'nul', 'Aux', 'PRN', 'com1', 'LPT1')), [open_project.safe_name(n) for n in ('CON', 'nul')]


@prueba("la configuración exportada no lleva contraseñas")
def _():
    fuente = "dbname='sig' host=localhost port=5432 user='pepe' password='secreto' sslmode=disable table=\"public\".\"t\" (geom)"
    limpia = configs.strip_credentials(fuente)
    return 'secreto' not in limpia and "dbname='sig'" in limpia and 'table=' in limpia, limpia


@prueba("favoritos.json estropeado (lista, ANSI, sin nombre) no rompe el panel")
def _():
    casos = [b'[1, 2, 3]', 'Señal'.encode('latin-1'), b'{"favoritos": [{"url": "http://x"}]}', b'{"favoritos": 5}']
    ok, fallidos = True, []
    try:
        for contenido in casos:
            with open(svc_module.favorites_path(), 'wb') as f:
                f.write(contenido)
            try:
                svc_module.load_favorites()
                ok = False  #Debería avisar
                fallidos.append(contenido)
            except svc_module.ServicesError:
                pass
        dw = _panel()  #Con un fichero estropeado el panel también debe abrirse, y apartar el fichero (sin borrarlo)
        apartado = os.path.isfile(svc_module.favorites_path() + '.estropeado') and not os.path.isfile(svc_module.favorites_path())
    finally:
        for f in (svc_module.favorites_path(), svc_module.favorites_path() + '.estropeado'):
            if os.path.isfile(f):
                os.remove(f)
    return ok and apartado and dw.favorites == [], f"sin aviso: {fallidos} apartado={apartado}"


@prueba("un icono que no se puede copiar no impide guardar el proyecto")
def _():
    svg = os.path.join(TMP, 'icono.svg')
    with open(svg, 'w') as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="4"/></svg>')
    from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer, QgsSvgMarkerSymbolLayer
    capa = QgsVectorLayer("Point?crs=EPSG:4326", "puntos", "memory")
    simbolo = QgsMarkerSymbol()
    simbolo.changeSymbolLayer(0, QgsSvgMarkerSymbolLayer(svg))
    capa.setRenderer(QgsSingleSymbolRenderer(simbolo))
    proyecto = QgsProject()
    proyecto.addMapLayer(capa)
    original = icons.shutil.copy2

    def bloqueado(*a, **k):
        raise PermissionError(13, "El archivo está en uso", svg)
    icons.shutil.copy2 = bloqueado
    try:
        _cambiadas, faltan = icons.localize(proyecto, os.path.join(TMP, 'proy_iconos'), layers=[capa])
    finally:
        icons.shutil.copy2 = original
    return any('icono.svg' in i for _, i in faltan), f"faltan={faltan}"


@prueba("estadísticas de una capa sin SRC: sin superficies absurdas")
def _():
    sin = _poligonos(os.path.join(TMP, 'sin_src_utm.shp'),
                     ["POLYGON((400000 4000000,401000 4000000,401000 4001000,400000 4001000,400000 4000000))"], crs=None)
    fila = stats.layer_stats(QgsVectorLayer(sin, 'x', 'ogr'))
    return fila['superficie_ha'] is None or abs(fila['superficie_ha'] - 100) < 1, f"superficie={fila['superficie_ha']}"


@prueba("composición con «:» en el nombre (Plano 1:5000)")
def _():
    import project_builder.core.layouts as layouts
    from qgis.core import QgsPrintLayout
    proyecto = QgsProject()
    composicion = QgsPrintLayout(proyecto)
    composicion.initializeDefaults()
    composicion.setName("Plano 1:5000 / norte?")
    proyecto.layoutManager().addLayout(composicion)
    ruta = layouts.snapshot_layout(proyecto, "Plano 1:5000 / norte?")
    return os.path.isfile(ruta) and os.path.getsize(ruta) > 100, ruta


@prueba("WMTS cuyo conjunto de teselas no se llama como un SRC («UTM30N»)")
def _():
    from project_builder.core.capabilities import parse_capabilities
    xml = b"""<?xml version="1.0"?><Capabilities xmlns="http://www.opengis.net/wmts/1.0" xmlns:ows="http://www.opengis.net/ows/1.1">
    <Contents><Layer><ows:Identifier>orto</ows:Identifier><ows:Title>Ortofoto</ows:Title><Format>image/jpeg</Format>
    <TileMatrixSetLink><TileMatrixSet>UTM30N</TileMatrixSet></TileMatrixSetLink></Layer>
    <TileMatrixSet><ows:Identifier>UTM30N</ows:Identifier><ows:SupportedCRS>urn:ogc:def:crs:EPSG::25830</ows:SupportedCRS></TileMatrixSet>
    </Contents></Capabilities>"""
    capa = parse_capabilities(xml, 'wmts')[0]
    servicio = svc_module.Service('Orto', 'https://ejemplo.es/wmts', layer=capa['layer'], type='wmts', format=capa['format'],
                                  style=capa['style'], tilematrixset=capa['tilematrixset'], crs_list=capa['crs'])
    from urllib.parse import unquote
    uri = unquote(servicio.uri())
    return 'crs=EPSG:25830' in uri and 'tileMatrixSet=UTM30N' in uri, uri


def _crear_panel(carpetas, marcar, destino, nombre="robustez"):
    dw = _panel()
    for c in carpetas:
        dw.add_source_folder(c)
    for it in list(_items(dw.treeWidget.invisibleRootItem())):
        if it.text(0) in marcar:
            it.setCheckState(0, Qt.CheckState.Checked)
    dw.pathFolderProject.setText(destino)
    dw.nameProject.setText(nombre)
    dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
    return dw


@prueba("destino que CONTIENE una carpeta de capas: se rechaza (protege los datos)")
def _():
    padre = os.path.join(TMP, 'datos_padre')
    shutil.copytree(DATA + '/vectorial', os.path.join(padre, 'capas'))
    dw = _crear_panel([os.path.join(padre, 'capas')], {'zonas_4326.shp'}, padre)
    error = dw.validate()
    return error is not None, f"validate()={error!r}"


@prueba("nombre de proyecto con caracteres no válidos o carpeta relativa: se avisa")
def _():
    dw = _crear_panel([DATA + '/vectorial'], {'zonas_4326.shp'}, os.path.join(TMP, 'p'), nombre='obra:1/a')
    e1 = dw.validate()
    dw.nameProject.setText('obra1')
    dw.pathFolderProject.setText('proyectos\\obra1')
    e2 = dw.validate()
    return e1 is not None and e2 is not None, f"{e1!r} {e2!r}"


@prueba("un error en las comprobaciones no borra el GeoPackage del proyecto anterior")
def _():
    destino = os.path.join(TMP, 'repetido')
    dw = _crear_panel([DATA + '/vectorial'], {'zonas_4326.shp'}, destino)
    dw.create_project(background=False)
    gpkg = os.path.join(destino, 'robustez.gpkg')
    antes = os.path.isfile(gpkg)
    dw.groupZone.setChecked(True)
    dw.zoneByLayer.setChecked(True)
    dw.zoneLayer.setLayer(None)  #Zona activada pero sin capa: ZoneError
    avisos.clear()
    dw.create_project(background=False)
    return antes and os.path.isfile(gpkg) and avisos, f"antes={antes} después={os.path.isfile(gpkg)} avisos={avisos}"


@prueba("ráster del proyecto abierto con extensión poco común (.gtiff)")
def _():
    raro = os.path.join(TMP, 'mdt_raro.gtiff')
    shutil.copy2(DATA + '/raster/mdt_4326.tif', raro)
    capa = QgsRasterLayer(raro, 'mdt_raro')
    QgsProject.instance().addMapLayer(capa)
    try:
        dw = _panel()
        Clase.load_project_layers = _originales['load_project_layers']
        dw.load_project_layers()
        for item in dw._project_leaves():
            item.setCheckState(0, Qt.CheckState.Checked)
        dw.pathFolderProject.setText(os.path.join(TMP, 'proy_raro'))
        dw.nameProject.setText('raro')
        avisos.clear()
        dw.create_project(background=False)
        tif = os.path.join(TMP, 'proy_raro', 'mdt_raro.tif')
        valido = QgsRasterLayer(tif, 'x').isValid()
    finally:
        Clase.load_project_layers = lambda self, *a: None
        QgsProject.instance().removeMapLayer(capa.id())
    return valido and not avisos, f"tif válido={valido} avisos={avisos}"


@prueba("cambiar el formulario mientras se exporta no cambia el proyecto que se está creando", grupo='fondo')
def _():
    destino = os.path.join(TMP, 'fondo')
    dw = _crear_panel([DATA + '/vectorial'], {'zonas_4326.shp', 'lugares_4326.geojson'}, destino, nombre='original')
    dw.create_project(background=True)
    dw.nameProject.setText('cambiado')  #El usuario sigue tocando el panel
    dw.pathFolderProject.setText(os.path.join(TMP, 'otra'))
    limite = time.time() + 60
    while dw.task is not None and time.time() < limite:
        QCoreApplication.processEvents()
        time.sleep(0.05)
    return os.path.isfile(os.path.join(destino, 'original.qgz')), f"ficheros={os.listdir(destino) if os.path.isdir(destino) else None}"


@prueba("al recargar el plugin con una exportación en marcha, se cancela", grupo='fondo')
def _():
    from project_builder.project_builder import ProjectBuilder
    plugin = ProjectBuilder(qgis.utils.iface)
    plugin.initGui()
    plugin.run()
    dw = plugin.dockwidget
    for c in (DATA + '/vectorial',):
        dw.add_source_folder(c)
    for it in list(_items(dw.treeWidget.invisibleRootItem())):
        if it.text(0) == 'zonas_4326.shp':
            it.setCheckState(0, Qt.CheckState.Checked)
    dw.pathFolderProject.setText(os.path.join(TMP, 'recarga'))
    dw.nameProject.setText('recarga')
    dw.create_project(background=True)
    tarea = dw.task
    plugin.unload()
    limite = time.time() + 30
    fin = (QgsTask.TaskStatus.Complete, QgsTask.TaskStatus.Terminated)
    while tarea is not None and tarea.status() not in fin and time.time() < limite:
        QCoreApplication.processEvents()
        time.sleep(0.05)
    return tarea is not None and tarea.isCanceled(), f"estado={tarea.status() if tarea else None}"


for nombre, funcion in _originales.items():
    setattr(Clase, nombre, funcion)
for dw in paneles:
    dw.deleteLater()

print("=" * 60)
print("QGIS", Qgis.version(), f"· robustez (casos límite, grupo {GRUPO})")
for nombre, ok in resultados.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
for nombre, detalle in detalles.items():
    print("--", nombre, "\n", str(detalle)[:700])
print("RESULTADO:", "TODO CORRECTO" if all(resultados.values()) else "HAY FALLOS")
print("=" * 60)
