"""
Plan de pruebas · H14 Formatos y datos de entrada: todo lo que el usuario puede traer en sus carpetas (cada formato
admitido, textos con tildes en cualquier codificación, geometrías 3D, curvas, tablas sin geometría, ráster VRT y
multibanda, una capa grande). Ver docs/PLAN_PRUEBAS.md.
Uso: tools\\probar.bat (o tools\\run_tests.py casos_formatos_test.py)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import caso, panel  # noqa: E402

from osgeo import gdal  # noqa: E402
from qgis.core import (  # noqa: E402
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsProject,
    QgsRasterLayer,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant  # noqa: E402

TEXTO = 'Málaga, Cañada «ñ» €'  #Tildes, eñe, comillas españolas y euro: lo que más se estropea al cambiar de formato
MODOS = ('single', 'convert', 'keep')
# Polígonos alrededor de los datos de prueba (Málaga): el de la izquierda queda dentro de la zona y el otro fuera
DENTRO = 'POLYGON((-3.875 36.745,-3.865 36.745,-3.865 36.755,-3.875 36.755,-3.875 36.745))'
FUERA = 'POLYGON((-3.80 36.70,-3.79 36.70,-3.79 36.71,-3.80 36.71,-3.80 36.70))'
ZONA = 'POLYGON((-3.89 36.73,-3.85 36.73,-3.85 36.77,-3.89 36.77,-3.89 36.73))'


def _escribir(ruta, driver, geometria='Polygon', wkts=(DENTRO, FUERA), capa=None, opciones=None, campos=True, crs='EPSG:4326',
              anadir=False, fuente=None, codificacion='UTF-8'):
    """Escribe una capa de prueba con GDAL (el mismo camino que cualquier programa) y devuelve la ruta."""
    memoria = QgsVectorLayer(f"{geometria}?crs={crs}" if crs else geometria, 'tmp', 'memory')
    if campos:
        memoria.dataProvider().addAttributes([QgsField('nombre', QVariant.String), QgsField('n', QVariant.Int)])
        memoria.updateFields()
    elementos = []
    for i, wkt in enumerate(wkts):
        f = QgsFeature(memoria.fields())
        if wkt:
            f.setGeometry(QgsGeometry.fromWkt(wkt))
        if campos:
            f.setAttributes([f"{TEXTO} {i}", i])
        elementos.append(f)
    memoria.dataProvider().addFeatures(elementos)
    o = QgsVectorFileWriter.SaveVectorOptions()
    o.driverName = driver
    o.fileEncoding = codificacion
    if capa:
        o.layerName = capa
    if opciones:
        o.layerOptions = opciones
    if fuente:
        o.datasourceOptions = fuente
    if anadir:
        o.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
    error, mensaje = QgsVectorFileWriter.writeAsVectorFormatV3(memoria, ruta, QgsProject.instance().transformContext(), o)[:2]
    assert error == QgsVectorFileWriter.WriterError.NoError, (ruta, mensaje)
    return ruta


def _crear(carpeta_origen, nombre, modo, zona=False, marcadas=None, background=False):
    """Crea un proyecto con todo lo de carpeta_origen. Devuelve (resultado, panel)."""
    dw = panel()
    dw.add_source_folder(carpeta_origen)
    raiz = dw.treeWidget.topLevelItem(dw.treeWidget.topLevelItemCount() - 1)
    if marcadas:
        comun.marcar(dw, *marcadas)
    else:
        raiz.setCheckState(0, comun.Qt.CheckState.Checked)
    dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
    dw.pathFolderProject.setText(comun.carpeta(f'dest_{nombre}_{modo}'))
    dw.nameProject.setText(nombre)
    if zona:
        capa = QgsVectorLayer('Polygon?crs=EPSG:4326', 'zona_formatos', 'memory')
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromWkt(ZONA))
        capa.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(capa)
        dw.groupZone.setChecked(True)
        dw.zoneByLayer.setChecked(True)
        dw.zoneLayer.setLayer(capa)
        dw.zoneAddLayer.setChecked(False)  #Así las capas del proyecto son solo las del usuario
    if background:
        dw.last_result = None
        dw.create_project(background=True)
        limite = time.time() + 300
        while dw.task is not None and time.time() < limite:
            comun.procesar_eventos(0.05)
        comun.procesar_eventos()
        resultado = dw.last_result
    else:
        resultado = comun.crear(dw)
    if zona:
        QgsProject.instance().removeMapLayer(capa.id())
    return resultado, dw


def _capas(resultado):
    """{nombre de capa: (válida, nº de elementos o None, textos del campo «nombre»)} del proyecto creado."""
    if not resultado:
        return {}
    p = QgsProject()
    p.read(resultado['proyecto'])
    capas = {}
    for c in p.mapLayers().values():
        if c.name() == 'zona_trabajo':
            continue
        textos = []
        if isinstance(c, QgsVectorLayer) and c.isValid() and c.fields().indexOf('nombre') >= 0:
            textos = [f['nombre'] for f in c.getFeatures()]
        capas[c.name()] = (c.isValid(), c.featureCount() if isinstance(c, QgsVectorLayer) else None, textos)
    p.clear()
    return capas


# ---------------------------------------------------------------------------------------------------------------- Casos
@caso('F10', 'Todos los formatos vectoriales admitidos, en los tres formatos de salida: ninguna capa se pierde ni se rompe')
def _():
    origen = comun.carpeta('formatos')
    _escribir(os.path.join(origen, 'shape.shp'), 'ESRI Shapefile')
    _escribir(os.path.join(origen, 'geo.geojson'), 'GeoJSON')
    os.replace(_escribir(os.path.join(comun.carpeta('json_temporal'), 'geo_json.geojson'), 'GeoJSON'),
               os.path.join(origen, 'geo_json.json'))  #GDAL añadiría «.geojson» al nombre: se renombra después
    _escribir(os.path.join(origen, 'google.kml'), 'KML')
    _escribir(os.path.join(origen, 'gml.gml'), 'GML')
    _escribir(os.path.join(origen, 'flat.fgb'), 'FlatGeobuf')
    _escribir(os.path.join(origen, 'mapinfo.tab'), 'MapInfo File')
    gdal.VectorTranslate(os.path.join(origen, 'mapinfo_mif.mif'), _escribir(os.path.join(comun.carpeta('tab_para_mif'), 'm.tab'),
                         'MapInfo File'), format='MapInfo File', datasetCreationOptions=['FORMAT=MIF'])
    _escribir(os.path.join(origen, 'cad.dxf'), 'DXF', campos=False)
    _escribir(os.path.join(origen, 'gps.gpx'), 'GPX', geometria='Point', wkts=('POINT(-3.87 36.75)', 'POINT(-3.79 36.705)'),
              campos=False)
    _escribir(os.path.join(origen, 'spatialite.sqlite'), 'SQLite', fuente=['SPATIALITE=YES'])
    _escribir(os.path.join(origen, 'paquete.gpkg'), 'GPKG', capa='parcelas')
    fallos = []
    for modo in MODOS:
        resultado, _dw = _crear(origen, 'formatos', modo)
        capas = _capas(resultado)
        malas = [n for n, (valida, _, _) in capas.items() if not valida]
        # Las capas vacías del usuario se copian (pueden ser plantillas para dibujar); las del GPX son su estructura fija
        sin_datos = [n for n, (valida, cuenta, _) in capas.items() if valida and cuenta == 0
                     and n not in ('routes', 'tracks', 'route_points', 'track_points')]
        internas = [n for n in capas if n.lower() in ('knn', 'knn2', 'data_licenses')]  #Tablas internas de SpatiaLite
        problemas = [p for p in (resultado or {}).get('problemas', []) if 'cad.dxf no tiene SRC' not in p]  #El DXF no lo guarda
        if not resultado or len(capas) < 12 or malas or sin_datos or internas or problemas:
            fallos.append((modo, sorted(capas), malas, sin_datos, internas, resultado and resultado['problemas']))
    return not fallos, fallos


@caso('F11', 'Textos con tildes, eñes y «€» se conservan en todos los formatos y modos (también desde latin-1)')
def _():
    origen = comun.carpeta('tildes')
    _escribir(os.path.join(origen, 'utf8.shp'), 'ESRI Shapefile')
    # Shapefile «antiguo» en latin-1 con su .cpg, y otro igual pero sin .cpg (lo más habitual en datos de hace años)
    _escribir(os.path.join(origen, 'latin1.shp'), 'ESRI Shapefile', codificacion='ISO-8859-15')
    _escribir(os.path.join(origen, 'cp1252.shp'), 'ESRI Shapefile', codificacion='windows-1252')
    with open(os.path.join(origen, 'cp1252.cpg'), 'w') as f:  #Lo que ArcGIS escribe en España
        f.write('1252')
    _escribir(os.path.join(origen, 'texto.geojson'), 'GeoJSON')
    _escribir(os.path.join(origen, 'tabla.gpkg'), 'GPKG', capa='tabla')
    fallos = []
    for modo in MODOS:
        resultado, _dw = _crear(origen, 'tildes', modo)
        capas = _capas(resultado)
        for nombre, (valida, _, textos) in capas.items():
            # «€» no existe en latin-1 puro (ISO-8859-15 y 1252 sí): se comprueba el resto del texto
            if not valida or not textos or not all(t and t.startswith(TEXTO[:-2]) for t in textos):
                fallos.append((modo, nombre, textos[:2]))
        if len(capas) != 5:
            fallos.append((modo, 'capas', sorted(capas)))
    return not fallos, fallos


@caso('F12', 'Geometrías 3D (Z y M), multiparte y curvas, con zona de trabajo: se recortan sin errores')
def _():
    origen = comun.carpeta('geometrias')
    gpkg = os.path.join(origen, 'geometrias.gpkg')
    _escribir(gpkg, 'GPKG', 'PolygonZM', ('POLYGON ZM((-3.875 36.745 10 1,-3.865 36.745 10 1,-3.865 36.755 12 1,'
                                          '-3.875 36.745 10 1))',), capa='poligonos_zm')
    _escribir(gpkg, 'GPKG', 'MultiPolygon', ('MULTIPOLYGON(((-3.875 36.745,-3.87 36.745,-3.87 36.75,-3.875 36.745)),'
                                             '((-3.80 36.70,-3.79 36.70,-3.79 36.71,-3.80 36.70)))',),
              capa='multiparte', anadir=True)
    _escribir(gpkg, 'GPKG', 'CurvePolygon', ('CURVEPOLYGON(CIRCULARSTRING(-3.875 36.75,-3.87 36.755,-3.865 36.75,'
                                             '-3.87 36.745,-3.875 36.75))',), capa='curvas', anadir=True)
    _escribir(gpkg, 'GPKG', 'LineStringZ', ('LINESTRING Z(-3.88 36.74 5,-3.80 36.70 9)',), capa='lineas_z', anadir=True)
    _escribir(os.path.join(origen, 'puntos_z.shp'), 'ESRI Shapefile', 'PointZ', ('POINT Z(-3.87 36.75 100)',))
    fallos = []
    for modo in MODOS:
        resultado, _dw = _crear(origen, 'geometrias', modo, zona=True)
        capas = _capas(resultado)
        malas = {n: v for n, v in capas.items() if not v[0] or not v[1]}
        if not resultado or len(capas) != 5 or malas:
            fallos.append((modo, sorted(capas), malas, resultado and resultado['problemas']))
    return not fallos, fallos


@caso('F13', 'GeoPackage con una tabla sin geometría (y con zona de trabajo): se copia y no da error')
def _():
    origen = comun.carpeta('sin_geometria')
    gpkg = os.path.join(origen, 'mixto.gpkg')
    _escribir(gpkg, 'GPKG', capa='parcelas')
    _escribir(gpkg, 'GPKG', 'NoGeometry', (None, None), capa='propietarios', anadir=True)
    fallos = []
    for modo in MODOS:
        for zona in (False, True):
            resultado, _dw = _crear(origen, 'sin_geometria', modo, zona=zona)
            capas = _capas(resultado)
            tabla = capas.get('propietarios')
            if not resultado or tabla is None or not tabla[0] or tabla[1] != 2:
                fallos.append((modo, zona, capas, resultado and resultado['problemas']))
    return not fallos, fallos


@caso('F14', 'Ráster VRT (apunta a otro fichero), multibanda con «sin datos» y JPG con world file, en los tres modos')
def _():
    origen = comun.carpeta('raster_raros')
    base = os.path.join(origen, 'base')
    os.makedirs(base)
    tif = os.path.join(base, 'mdt.tif')
    gdal.Translate(tif, os.path.join(comun.DATA, 'raster', 'mdt_4326.tif'))
    gdal.BuildVRT(os.path.join(origen, 'mosaico.vrt'), [tif]).FlushCache()
    driver = gdal.GetDriverByName('GTiff')
    ds = driver.Create(os.path.join(origen, 'ortofoto_rgb.tif'), 20, 20, 3, gdal.GDT_Byte)
    ds.SetGeoTransform((-3.88, 0.001, 0, 36.76, 0, -0.001))
    ds.SetProjection('EPSG:4326')
    for banda in range(1, 4):
        ds.GetRasterBand(banda).Fill(banda * 60)
        ds.GetRasterBand(banda).SetNoDataValue(0)
    ds.FlushCache()
    ds = None
    gdal.Translate(os.path.join(origen, 'foto.jpg'), os.path.join(origen, 'ortofoto_rgb.tif'), format='JPEG',
                   creationOptions=['WORLDFILE=YES'])
    fallos = []
    for modo in MODOS:
        resultado, _dw = _crear(origen, 'raster_raros', modo, marcadas=['mosaico.vrt', 'ortofoto_rgb.tif', 'foto.jpg'])
        capas = _capas(resultado)
        malas = [n for n, v in capas.items() if not v[0]]
        if not resultado or len(capas) != 3 or malas:
            fallos.append((modo, sorted(capas), malas, resultado and resultado['problemas']))
            continue
        p = QgsProject()
        p.read(resultado['proyecto'])
        bandas = {c.name(): c.bandCount() for c in p.mapLayers().values() if isinstance(c, QgsRasterLayer)}
        rutas = [c.source() for c in p.mapLayers().values()]
        p.clear()
        if bandas.get('ortofoto_rgb') != 3:
            fallos.append((modo, 'bandas', bandas))
        if any(r.lower().endswith('.vrt') for r in rutas):  #El VRT apunta a ficheros de fuera: siempre se convierte
            fallos.append((modo, 'VRT sin convertir', rutas))
    return not fallos, fallos


@caso('F15', 'Capa grande (50.000 polígonos) con zona de trabajo en segundo plano: termina en un tiempo razonable')
def _():
    origen = comun.carpeta('grande')
    memoria = QgsVectorLayer('Polygon?crs=EPSG:4326&field=nombre:string&field=n:integer', 'grande', 'memory')
    elementos = []
    for i in range(50000):
        x, y = -3.95 + (i % 250) * 0.0006, 36.70 + (i // 250) * 0.0005
        f = QgsFeature(memoria.fields())
        f.setGeometry(QgsGeometry.fromWkt(f'POLYGON(({x} {y},{x + 0.0005} {y},{x + 0.0005} {y + 0.0004},{x} {y})))'))
        f.setAttributes([f'{TEXTO} {i}', i])
        elementos.append(f)
    memoria.dataProvider().addFeatures(elementos)
    o = QgsVectorFileWriter.SaveVectorOptions()
    o.driverName = 'ESRI Shapefile'
    o.fileEncoding = 'UTF-8'
    QgsVectorFileWriter.writeAsVectorFormatV3(memoria, os.path.join(origen, 'parcelas.shp'),
                                              QgsProject.instance().transformContext(), o)
    inicio = time.time()
    resultado, _dw = _crear(origen, 'grande', 'single', zona=True, background=True)
    segundos = time.time() - inicio
    capas = _capas(resultado)
    parcelas = capas.get('parcelas')
    ok = resultado is not None and parcelas is not None and parcelas[0] and 0 < parcelas[1] < 50000 and segundos < 180
    return ok, (round(segundos, 1), parcelas and parcelas[1], resultado and resultado['problemas'])


@caso('F16', 'Capas internas de un GeoPackage con nombres raros (espacios, tildes, guiones, mayúsculas)')
def _():
    origen = comun.carpeta('nombres_internos')
    gpkg = os.path.join(origen, 'catastro.gpkg')
    nombres = ['Parcelas urbanas', 'Edificación-2024', 'CONSTRUCCIÓN', 'número 1']
    for i, nombre in enumerate(nombres):
        _escribir(gpkg, 'GPKG', capa=nombre, anadir=i > 0)
    fallos = []
    for modo in MODOS:
        resultado, _dw = _crear(origen, 'nombres_internos', modo)
        capas = _capas(resultado)
        if not resultado or len(capas) != len(nombres) or any(not v[0] or v[1] != 2 for v in capas.values()):
            fallos.append((modo, capas, resultado and resultado['problemas']))
    return not fallos, fallos


comun.terminar('H14 Formatos y datos de entrada')
