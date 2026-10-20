"""
Plan de pruebas · H07 Formato de salida, SRC y reproyección · H08 Nombre y carpeta del proyecto (validación).
Ver docs/PLAN_PRUEBAS.md. Uso: tools\\probar.bat (o tools\\run_tests.py casos_destino_test.py)
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import caso, panel  # noqa: E402

from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsVectorLayer  # noqa: E402

VECTORIAL = os.path.join(comun.DATA, 'vectorial')
RASTER = os.path.join(comun.DATA, 'raster')


def _panel_listo(nombre='destino', destino=None):
    dw = panel()
    comun.preparar(dw, [VECTORIAL], ['zonas_4326.shp'], destino or comun.carpeta(f'dest_{nombre}'), nombre)
    return dw


def _rechaza(dw, *fragmentos):
    """Crear no debe hacer nada salvo avisar (con los fragmentos indicados)."""
    dw.last_result = None
    dw.create_project(background=False)
    return dw.last_result is None and comun.avisado(*fragmentos)


@caso('D01', 'Nombre vacío o solo con espacios')
def _():
    dw = _panel_listo()
    resultados = []
    for nombre in ('', '    '):
        dw.nameProject.setText(nombre)
        resultados.append(_rechaza(dw, 'nombre'))
    return all(resultados), comun.avisos()


@caso('D02', 'Nombres no válidos: caracteres prohibidos, extensión .qgz, nombre reservado y acabado en punto')
def _():
    dw = _panel_listo()
    rechazados = {}
    for nombre in ('a/b', 'a\\b', 'plano: 1', 'qué?', '"x"', '<x>', 'a|b', 'a*b', 'proyecto.qgz', 'CON', 'nul', 'proyecto.',
                   'proyecto ', ' .'):
        dw.nameProject.setText(nombre)
        rechazados[nombre] = _rechaza(dw, 'nombre')
    # «proyecto » (con espacio al final) es válido: se quita el espacio
    rechazados.pop('proyecto ')
    return all(rechazados.values()), rechazados


@caso('D03', 'Nombre o carpeta tan largos que la ruta no cabe en Windows: se avisa antes de empezar')
def _():
    dw = _panel_listo()
    dw.nameProject.setText('n' * 240)
    return _rechaza(dw, 'larga'), comun.avisos()


@caso('D04', 'Carpeta del proyecto: vacía, relativa, que es un fichero, unidad que no existe')
def _():
    dw = _panel_listo()
    fichero = os.path.join(comun.carpeta('es_fichero'), 'proyecto.txt')
    with open(fichero, 'w') as f:
        f.write('x')
    casos = {'': 'carpeta', 'relativa\\sub': 'completa', fichero: 'fichero', 'Q:\\no_existe\\proyecto': 'unidad'}
    letras = [l for l in 'QWYXJ' if not os.path.exists(f'{l}:\\')]
    if letras:
        casos = {k.replace('Q:', f'{letras[0]}:'): v for k, v in casos.items()}
    resultados = {}
    for ruta, fragmento in casos.items():
        dw.pathFolderProject.setText(ruta)
        resultados[ruta] = _rechaza(dw, fragmento)
    return all(resultados.values()), (resultados, comun.avisos())


@caso('D05', 'Carpeta del proyecto sin permiso de escritura: se avisa antes de empezar, con qué hacer')
def _():
    if os.name != 'nt':
        return True, 'solo en Windows'
    bloqueada = comun.carpeta('sin_permiso')
    todos = '*S-1-1-0'
    subprocess.run(['icacls', bloqueada, '/deny', f'{todos}:(OI)(CI)(W,AD,WD)'], capture_output=True)
    try:
        dw = _panel_listo(destino=os.path.join(bloqueada, 'proyecto'))
        rechazado = _rechaza(dw, 'permiso')
        dw.pathFolderProject.setText(bloqueada)
        rechazado2 = _rechaza(dw, 'permiso')
    finally:
        subprocess.run(['icacls', bloqueada, '/remove:d', todos], capture_output=True)
    return rechazado and rechazado2, comun.avisos()


@caso('D06', 'Volver a crear un proyecto con el mismo nombre en la misma carpeta (sobrescribir)')
def _():
    destino = comun.carpeta('repetido')
    fallos = []
    for vez, marcadas in enumerate((['zonas_4326.shp', 'lugares_4326.geojson'], ['zonas_4326.shp'])):
        dw = panel()
        comun.preparar(dw, [VECTORIAL], marcadas, destino, 'repetido')
        resultado = comun.crear(dw)
        capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
        if capas != len(marcadas) or malas:
            fallos.append((vez, capas, malas))
    tablas = [s.name() for s in __import__('qgis.core', fromlist=['QgsProviderRegistry']).QgsProviderRegistry.instance()
              .querySublayers(os.path.join(destino, 'repetido.gpkg'))]
    return not fallos and 'lugares_4326' not in tablas, (fallos, tablas)


@caso('D07', 'El GeoPackage del proyecto anterior está abierto en QGIS: se avisa de que hay que cerrarlo')
def _():
    destino = comun.carpeta('bloqueado')
    dw = _panel_listo('bloqueado', destino)
    primero = comun.crear(dw)
    capa = QgsVectorLayer(os.path.join(destino, 'bloqueado.gpkg') + '|layername=zonas_4326', 'abierta', 'ogr')
    QgsProject.instance().addMapLayer(capa)
    _ = capa.getFeatures().__next__()  #La capa se lee: el fichero queda abierto
    try:
        rechazado = os.name != 'nt' or _rechaza(dw, 'bloqueado.gpkg', 'ciérr')
    finally:
        QgsProject.instance().removeMapLayer(capa.id())
    return primero is not None and rechazado, comun.avisos()


@caso('D08', 'Carpeta de red que no existe (\\\\servidor\\...)')
def _():
    dw = _panel_listo()
    dw.pathFolderProject.setText('\\\\127.0.0.1\\recurso_que_no_existe$\\proyecto')
    return _rechaza(dw, 'proyecto'), comun.avisos()


@caso('F01', 'Los tres formatos de salida, con y sin reproyección, con capas de todos los tipos de prueba')
def _():
    fallos = []
    for modo in ('single', 'convert', 'keep'):
        for reproyectar in (True, False):
            dw = panel()
            comun.preparar(dw, [VECTORIAL, RASTER], ['vectorial', 'raster'],
                           comun.carpeta(f'formato_{modo}_{reproyectar}'), f'formato_{modo}')
            dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
            dw.reprojectCheck.setChecked(reproyectar)
            resultado = comun.crear(dw)
            if resultado is None:
                fallos.append((modo, reproyectar, comun.avisos()))
                continue
            capas, malas = comun.proyecto_valido(resultado['proyecto'])
            if capas < 8 or malas or resultado['problemas']:
                fallos.append((modo, reproyectar, capas, malas, resultado['problemas']))
    return not fallos, fallos


@caso('F02', 'SRC del proyecto sin elegir o no válido: se avisa')
def _():
    dw = _panel_listo()
    dw.selectProjection.setCrs(QgsCoordinateReferenceSystem())
    return _rechaza(dw, 'src'), comun.avisos()


@caso('F03', 'SRC del proyecto geográfico (EPSG:4326) y SRC personalizado sin código EPSG')
def _():
    fallos = []
    for crs in (QgsCoordinateReferenceSystem('EPSG:4326'),
                QgsCoordinateReferenceSystem.fromProj('+proj=tmerc +lat_0=0 +lon_0=-4 +k=0.9996 +x_0=500000 +y_0=0 '
                                                      '+ellps=GRS80 +units=m +no_defs')):
        dw = _panel_listo('src_raro')
        comun.marcar(dw, 'lugares_4326.geojson')
        dw.selectProjection.setCrs(crs)
        resultado = comun.crear(dw)
        capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
        if capas != 2 or malas:
            fallos.append((crs.description(), capas, malas, comun.avisos()))
    return not fallos, fallos


@caso('F04', 'Capas con el mismo nombre en carpetas distintas y mismo nombre con distinta extensión')
def _():
    origen = comun.carpeta('iguales')
    for sub in ('a', 'b'):
        os.makedirs(os.path.join(origen, sub))
        comun.poligonos(os.path.join(origen, sub, 'rios.shp'), ['POLYGON((-3.9 36.7,-3.8 36.7,-3.8 36.8,-3.9 36.7))'])
    shutil.copy2(os.path.join(VECTORIAL, 'lugares_4326.geojson'), os.path.join(origen, 'a', 'rios.geojson'))
    fallos = []
    for modo in ('single', 'convert', 'keep'):
        dw = panel()
        comun.preparar(dw, [origen], ['iguales'], comun.carpeta(f'iguales_{modo}'), 'iguales')
        dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
        resultado = comun.crear(dw)
        capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
        if capas != 3 or malas:
            fallos.append((modo, capas, malas))
    return not fallos, fallos


@caso('F05', 'Dos carpetas de origen con el mismo nombre (p. ej. dos «Cartografía»)')
def _():
    origen1 = os.path.join(comun.carpeta('cliente1'), 'Cartografia')
    origen2 = os.path.join(comun.carpeta('cliente2'), 'Cartografia')
    for o in (origen1, origen2):
        os.makedirs(o)
        comun.poligonos(os.path.join(o, 'parcelas.shp'), ['POLYGON((-3.9 36.7,-3.8 36.7,-3.8 36.8,-3.9 36.7))'])
    dw = panel()
    dw.add_source_folder(origen1)
    dw.add_source_folder(origen2)
    for it in comun.todo(dw.treeWidget.invisibleRootItem()):
        if it.text(0) == 'parcelas.shp':
            it.setCheckState(0, comun.Qt.CheckState.Checked)
    dw.pathFolderProject.setText(comun.carpeta('dos_cartografias'))
    dw.nameProject.setText('dos')
    resultado = comun.crear(dw)
    capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
    return capas == 2 and not malas, (capas, malas)


@caso('D10', 'Carpeta pegada con comillas («Copiar como ruta de acceso»), con espacios alrededor o con barras «/»')
def _():
    fallos = []
    base = comun.carpeta('pegada')
    for i, texto in enumerate(['"{}"', '  {}  ', "'{}'", '"{}', '{}']):  #El último, con barras «/» en vez de «\\»
        destino = os.path.join(base, f'proyecto {i}')
        escrito = texto.format(destino if i != 4 else destino.replace(os.sep, '/'))
        dw = _panel_listo(f'pegada{i}', destino=escrito)
        resultado = comun.crear(dw)
        esperado = os.path.normcase(os.path.normpath(os.path.join(destino, f'pegada{i}.qgz')))
        if not resultado or os.path.normcase(os.path.normpath(resultado['proyecto'])) != esperado:
            fallos.append((escrito, resultado and resultado['proyecto'], comun.avisos()))
    return not fallos, fallos


comun.terminar('H07-H08 Formato, SRC, nombre y carpeta')
