"""
Plan de pruebas · H03 Capas del proyecto abierto en QGIS · H04 Bases de datos (GeoPackage, SpatiaLite y PostGIS caído)
· H13 Estilos e iconos. Sin servidor de bases de datos: se usan conexiones a ficheros y un PostGIS que no existe.
Ver docs/PLAN_PRUEBAS.md. Uso: tools\\probar.bat (o tools\\run_tests.py casos_origenes_test.py)
"""
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import caso, panel  # noqa: E402

from qgis.core import QgsProject, QgsProviderRegistry, QgsRasterLayer, QgsVectorLayer  # noqa: E402

VECTORIAL = os.path.join(comun.DATA, 'vectorial')
Clase = comun.Clase


def _con_capas(*capas):
    for c in capas:
        QgsProject.instance().addMapLayer(c)
    dw = panel()
    Clase.load_project_layers(dw)
    return dw


def _quitar(*capas):
    for c in capas:
        try:
            QgsProject.instance().removeMapLayer(c.id())
        except RuntimeError:
            pass


def _crear(dw, nombre):
    dw.pathFolderProject.setText(comun.carpeta(f'origen_{nombre}'))
    dw.nameProject.setText(nombre)
    return comun.crear(dw)


def _conexion(proveedor, nombre, uri):
    metadatos = QgsProviderRegistry.instance().providerMetadata(proveedor)
    metadatos.saveConnection(metadatos.createConnection(uri, {}), nombre)


def _borrar_conexion(proveedor, nombre):
    metadatos = QgsProviderRegistry.instance().providerMetadata(proveedor)
    if nombre in metadatos.connections():
        metadatos.deleteConnection(nombre)


@caso('O01', 'Capa del proyecto abierto cuyo fichero ya no existe (capa rota en QGIS): se avisa antes de empezar')
def _():
    rota = QgsVectorLayer(os.path.join(VECTORIAL, 'zonas_4326.shp'), 'zonas rotas', 'ogr')
    buena = QgsVectorLayer(os.path.join(VECTORIAL, 'lugares_4326.geojson'), 'lugares buenos', 'ogr')
    try:
        dw = _con_capas(rota, buena)
        comun.marcar(dw, 'zonas rotas', 'lugares buenos')
        rota.setDataSource(os.path.join(comun.TMP, 'se_ha_movido.shp'), 'zonas rotas', 'ogr')  #Como al abrir un proyecto con capas rotas
        resultado = _crear(dw, 'abierto_roto')
    finally:
        _quitar(rota, buena)
    return resultado is None and comun.avisado('zonas rotas'), comun.avisos()


@caso('O02', 'Capas temporales (en memoria): vacía, con elementos y sin geometría')
def _():
    from qgis.core import QgsFeature, QgsGeometry
    vacia = QgsVectorLayer('Point?crs=EPSG:4326', 'temporal vacía', 'memory')
    llena = QgsVectorLayer('Point?crs=EPSG:4326&field=nombre:string', 'temporal llena', 'memory')
    f = QgsFeature(llena.fields())
    f.setGeometry(QgsGeometry.fromWkt('POINT(-3.87 36.75)'))
    f.setAttribute('nombre', 'ñandú')
    llena.dataProvider().addFeatures([f])
    tabla = QgsVectorLayer('None?field=x:integer', 'tabla sin geometría', 'memory')
    try:
        dw = _con_capas(vacia, llena, tabla)
        comun.marcar(dw, 'temporal vacía', 'temporal llena', 'tabla sin geometría')
        resultado = _crear(dw, 'temporales')
    finally:
        _quitar(vacia, llena, tabla)
    capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
    return capas >= 2 and not malas, (capas, malas, resultado and resultado['problemas'], comun.avisos())


@caso('O03', 'Capas del proyecto con nombres raros, reservados o repetidos en grupos distintos')
def _():
    capas = [QgsVectorLayer(os.path.join(VECTORIAL, 'lugares_4326.geojson'), n, 'ogr')
             for n in ('CON', 'a/b:c*?', 'repetida', 'repetida', '   ', 'ñ' * 120)]
    for c in capas:
        QgsProject.instance().addMapLayer(c, False)
    raiz = QgsProject.instance().layerTreeRoot()
    for i, c in enumerate(capas):
        raiz.addGroup(f'grupo {i}/raro:').addLayer(c)
    dw = panel()
    Clase.load_project_layers(dw)
    for it in comun.todo(dw.treeWidget.invisibleRootItem()):
        if it.data(0, comun.dock.KIND_ROLE) == comun.dock.PROJECT_LAYER:
            it.setCheckState(0, comun.Qt.CheckState.Checked)
    fallos = []
    try:
        for modo in ('single', 'convert'):
            dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
            resultado = _crear(dw, f'nombres_{modo}')
            capas_ok, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
            if capas_ok != 6 or malas:
                fallos.append((modo, capas_ok, malas, resultado and resultado['problemas'], comun.avisos()))
    finally:
        _quitar(*capas)
        for i in range(len(capas)):
            grupo = raiz.findGroup(f'grupo {i}/raro:')
            if grupo is not None:
                raiz.removeChildNode(grupo)
    return not fallos, fallos


@caso('O04', 'Capa marcada que se quita del proyecto de QGIS antes de crear: se crea sin ella, sin errores')
def _():
    capa = QgsVectorLayer(os.path.join(VECTORIAL, 'lugares_4326.geojson'), 'se va', 'ogr')
    otra = QgsVectorLayer(os.path.join(VECTORIAL, 'zonas_4326.shp'), 'se queda', 'ogr')
    try:
        dw = _con_capas(capa, otra)
        comun.marcar(dw, 'se va', 'se queda')
        _quitar(capa)
        resultado = _crear(dw, 'quitada')
    finally:
        _quitar(otra)
    return resultado is not None and comun.proyecto_valido(resultado['proyecto']) == (1, []), comun.avisos()


@caso('O05', 'Capa de teselas XYZ (servicio web sin internet) y capa con filtro del proyecto abierto')
def _():
    xyz = QgsRasterLayer('type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0', 'OSM', 'wms')
    filtrada = QgsVectorLayer(os.path.join(VECTORIAL, 'zonas_4326.shp'), 'zonas filtradas', 'ogr')
    filtrada.setSubsetString('1 = 0')  #Filtro que no deja ningún elemento
    try:
        dw = _con_capas(xyz, filtrada)
        comun.marcar(dw, 'OSM', 'zonas filtradas')
        resultado = _crear(dw, 'xyz')
    finally:
        _quitar(xyz, filtrada)
    capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
    return capas >= 1 and not malas, (capas, malas, resultado and resultado['problemas'])


@caso('O06', 'Capa en edición con cambios sin guardar (del proyecto abierto o de una carpeta): se avisa antes de empezar')
def _():
    from qgis.core import QgsFeature, QgsGeometry
    datos = comun.copia_datos('edicion')
    ruta = os.path.join(datos, 'vectorial', 'zonas_4326.shp')
    capa = QgsVectorLayer(ruta, 'zonas en edición', 'ogr')
    antes = capa.featureCount()
    try:
        dw = _con_capas(capa)
        capa.startEditing()
        nuevo = QgsFeature(capa.fields())
        nuevo.setGeometry(QgsGeometry.fromWkt('POLYGON((-3.88 36.74,-3.87 36.74,-3.87 36.75,-3.88 36.74))'))
        capa.addFeature(nuevo)
        # 1. Marcada como capa del proyecto abierto
        comun.marcar(dw, 'zonas en edición')
        rechazo1 = _crear(dw, 'edicion1') is None and comun.avisado('zonas en edición', 'sin guardar')
        # 2. El mismo fichero marcado desde su carpeta (sin marcar la del proyecto abierto)
        otro = panel()
        comun.preparar(otro, [os.path.join(datos, 'vectorial')], ['zonas_4326.shp'], comun.carpeta('edicion2'), 'edicion2')
        rechazo2 = comun.crear(otro) is None and comun.avisado('zonas en edición', 'sin guardar')
        # 3. Guardados los cambios: se crea y el elemento nuevo está en el proyecto
        capa.commitChanges()
        resultado = comun.crear(otro)
        p = QgsProject()
        p.read(resultado['proyecto']) if resultado else None
        cuentas = [c.featureCount() for c in p.mapLayers().values() if c.name() == 'zonas_4326']
        p.clear()
    finally:
        if capa.isEditable():
            capa.rollBack()
        _quitar(capa)
    return rechazo1 and rechazo2 and cuentas == [antes + 1], (rechazo1, rechazo2, antes, cuentas, comun.avisos())


@caso('O07', 'Capas del proyecto abierto de texto delimitado (CSV con coordenadas) y virtuales: se copian con sus datos')
def _():
    carpeta = comun.carpeta('csv_virtual')
    csv = os.path.join(carpeta, 'pozos Málaga.csv')
    with open(csv, 'w', encoding='utf-8') as f:
        f.write('id;nombre;x;y\n1;Pozo «Ñ» 1;-3,87;36,75\n2;Pozo 2;-3,86;36,76\n')
    uri = f"file:///{csv.replace(os.sep, '/')}?type=csv&delimiter=;&decimalPoint=,&xField=x&yField=y&crs=EPSG:4326"
    texto = QgsVectorLayer(uri, 'pozos', 'delimitedtext')
    lugares = QgsVectorLayer(os.path.join(VECTORIAL, 'lugares_4326.geojson'), 'lugares_base', 'ogr')
    QgsProject.instance().addMapLayer(lugares)
    virtual = QgsVectorLayer(f"?query=SELECT * FROM \"{lugares.id()}\"", 'lugares virtual', 'virtual')
    validas = (texto.isValid(), virtual.isValid())  #Antes de añadirlas: después QGIS las borra al quitarlas
    try:
        dw = _con_capas(texto, virtual)
        comun.marcar(dw, 'pozos', 'lugares virtual')
        fallos = []
        for modo in ('single', 'convert'):
            dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
            resultado = _crear(dw, f'csv_{modo}')
            p = QgsProject()
            p.read(resultado['proyecto']) if resultado else None
            cuentas = {c.name(): c.featureCount() for c in p.mapLayers().values() if c.isValid()}
            textos = [f['nombre'] for c in p.mapLayers().values() if c.name() == 'pozos' for f in c.getFeatures()]
            p.clear()
            if cuentas.get('pozos') != 2 or not cuentas.get('lugares virtual') or 'Pozo «Ñ» 1' not in textos:
                fallos.append((modo, cuentas, textos, resultado and resultado['problemas']))
    finally:
        _quitar(texto, virtual, lugares)
    return all(validas) and not fallos, (validas, fallos)


@caso('B01', 'Configuración con una conexión de base de datos que ya no existe en QGIS')
def _():
    dw = panel()
    avisos = dw.apply_config({'bases_datos': [{'proveedor': 'ogr', 'conexion': 'No existe', 'tablas': [['', 'x']]},
                                              {'proveedor': 'proveedor_raro', 'conexion': 'x', 'tablas': []}]})
    problemas = [comun.revisar_mensaje(a) for a in avisos]
    return len(avisos) == 2 and not any(problemas), (avisos, problemas)


@caso('B02', 'Añadir la misma conexión dos veces, y una base de datos sin tablas con geometría')
def _():
    gpkg = os.path.join(comun.carpeta('bd_vacia'), 'sin_geometria.gpkg')
    tabla = QgsVectorLayer('None?field=x:integer', 'tabla', 'memory')
    from qgis.core import QgsVectorFileWriter
    opciones = QgsVectorFileWriter.SaveVectorOptions()
    opciones.driverName = 'GPKG'
    QgsVectorFileWriter.writeAsVectorFormatV3(tabla, gpkg, QgsProject.instance().transformContext(), opciones)
    _conexion('ogr', 'BD sin geometría', gpkg)
    try:
        dw = panel()
        raiz = dw.add_database('ogr', 'BD sin geometría')
        dw.add_database('ogr', 'BD sin geometría')
        textos = [raiz.child(i).text(0) for i in range(raiz.childCount())] if raiz else []
    finally:
        _borrar_conexion('ogr', 'BD sin geometría')
    return textos == ['No hay tablas con geometría'] and comun.avisado('ya está'), (textos, comun.avisos())


@caso('B03', 'Conexión a un GeoPackage que se ha borrado o movido')
def _():
    gpkg = os.path.join(comun.carpeta('bd_borrada'), 'borrada.gpkg')
    shutil.copy2(os.path.join(VECTORIAL, 'multicapa.gpkg'), gpkg)
    _conexion('ogr', 'BD borrada', gpkg)
    os.remove(gpkg)
    try:
        dw = panel()
        dw.add_database('ogr', 'BD borrada')
    finally:
        _borrar_conexion('ogr', 'BD borrada')
    return comun.avisado('BD borrada'), comun.avisos()


@caso('B04', 'Tabla de base de datos marcada que se borra antes de crear: el resto se crea y se explica')
def _():
    gpkg = os.path.join(comun.carpeta('bd_tabla'), 'tablas.gpkg')
    shutil.copy2(os.path.join(VECTORIAL, 'multicapa.gpkg'), gpkg)
    _conexion('ogr', 'BD tablas', gpkg)
    try:
        dw = panel()
        raiz = dw.add_database('ogr', 'BD tablas')
        tablas = [raiz.child(i) for i in range(raiz.childCount())]
        for t in tablas:
            t.setCheckState(0, comun.Qt.CheckState.Checked)
        conexion = QgsProviderRegistry.instance().providerMetadata('ogr').connections()['BD tablas']
        conexion.dropVectorTable('', tablas[0].text(0))  #Alguien borra una tabla mientras tanto
        resultado = _crear(dw, 'bd_borrada')
    finally:
        _borrar_conexion('ogr', 'BD tablas')
    return (resultado is None and comun.avisos()) or (resultado is not None and resultado['problemas']), (
        resultado and resultado['problemas'], comun.avisos())


@caso('B05', 'PostGIS con el servidor apagado: aviso claro y rápido, sin bloquear QGIS')
def _():
    _conexion('postgres', 'Servidor apagado', "host=127.0.0.1 port=1 dbname=nada user=nadie password=secreta connect_timeout=5")
    try:
        dw = panel()
        inicio = time.time()
        dw.add_database('postgres', 'Servidor apagado')
        segundos = time.time() - inicio
    finally:
        _borrar_conexion('postgres', 'Servidor apagado')
    texto = ' '.join(comun.avisos())
    return segundos < 20 and comun.avisado('Servidor apagado') and 'secreta' not in texto, (f"{segundos:.1f} s", comun.avisos())


@caso('E01', 'Estilo .qml dañado, vacío o de otra geometría junto a la capa: la capa se copia igual')
def _():
    datos = comun.copia_datos('estilos_rotos')
    vect = os.path.join(datos, 'vectorial')
    with open(os.path.join(vect, 'lugares_4326.qml'), 'w') as f:
        f.write('<qgis><esto no se cierra')
    shutil.copy2(os.path.join(vect, 'zonas_4326.qml'), os.path.join(vect, 'subcarpeta', 'puntos_23030.qml'))  #Polígonos en puntos
    with open(os.path.join(vect, 'limites_4326.qml'), 'w') as f:
        f.write('')
    dw = panel()
    comun.preparar(dw, [vect], ['lugares_4326.geojson', 'puntos_23030.shp', 'limites_4326.kml'],
                   comun.carpeta('dest_estilos'), 'estilos')
    resultado = comun.crear(dw)
    capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
    return capas == 3 and not malas, (capas, malas, resultado and resultado['problemas'])


@caso('E02', 'Estilo con un icono SVG que no existe: el proyecto se crea y se explica qué hacer')
def _():
    datos = comun.copia_datos('icono_falta')
    vect = os.path.join(datos, 'vectorial')
    capa = QgsVectorLayer(os.path.join(vect, 'lugares_4326.geojson'), 'l', 'ogr')
    from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer, QgsSvgMarkerSymbolLayer
    simbolo = QgsMarkerSymbol()
    simbolo.changeSymbolLayer(0, QgsSvgMarkerSymbolLayer('D:/cliente/iconos/no_existe_en_ningun_sitio.svg'))
    capa.setRenderer(QgsSingleSymbolRenderer(simbolo))
    capa.saveNamedStyle(os.path.join(vect, 'lugares_4326.qml'))
    del capa
    dw = panel()
    comun.preparar(dw, [vect], ['lugares_4326.geojson'], comun.carpeta('dest_icono_falta'), 'icono')
    resultado = comun.crear(dw)
    return resultado is not None and any('no_existe_en_ningun_sitio' in p for p in resultado['problemas']), (
        resultado and resultado['problemas'])


comun.terminar('H03-H04-H13 Proyecto abierto, bases de datos y estilos')
