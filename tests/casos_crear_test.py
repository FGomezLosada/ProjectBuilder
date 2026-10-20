"""
Plan de pruebas · H09 Crear el proyecto · H10 Informe final, informe de capas y sus botones.
Ver docs/PLAN_PRUEBAS.md. Uso: tools\\probar.bat (o tools\\run_tests.py casos_crear_test.py)
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import caso, panel  # noqa: E402

from qgis.core import QgsProject, QgsVectorLayer  # noqa: E402
from qgis.PyQt.QtWidgets import QApplication  # noqa: E402

VECTORIAL = os.path.join(comun.DATA, 'vectorial')


def _creado(nombre, marcadas=('zonas_4326.shp', 'lugares_4326.geojson')):
    dw = panel()
    comun.preparar(dw, [VECTORIAL], list(marcadas), comun.carpeta(f'crear_{nombre}'), nombre)
    return dw, comun.crear(dw)


@caso('C01', 'El fichero .qgz no se puede escribir (hay una carpeta con ese nombre): se avisa con qué hacer')
def _():
    dw = panel()
    destino = comun.carpeta('qgz_carpeta')
    os.makedirs(os.path.join(destino, 'qgz.qgz'))
    comun.preparar(dw, [VECTORIAL], ['zonas_4326.shp'], destino, 'qgz')
    resultado = comun.crear(dw)
    return resultado is None and comun.avisado('qgz'), comun.avisos()


@caso('C02', 'Un ráster dañado (texto con extensión .tif) entre las capas: el resto se crea y se explica')
def _():
    datos = comun.copia_datos('raster_roto')
    with open(os.path.join(datos, 'raster', 'roto.tif'), 'w') as f:
        f.write('no soy un tif')
    dw = panel()
    comun.preparar(dw, [os.path.join(datos, 'raster')], ['raster'], comun.carpeta('crear_raster_roto'), 'raster_roto')
    resultado = comun.crear(dw)
    if resultado is None:
        return False, comun.avisos()
    capas, malas = comun.proyecto_valido(resultado['proyecto'])
    return capas == 3 and not malas and any('roto' in p for p in resultado['problemas']), resultado['problemas']


@caso('C03', 'Crear dos proyectos seguidos desde el mismo panel (cambiando solo el nombre)')
def _():
    dw = panel()
    comun.preparar(dw, [VECTORIAL], ['zonas_4326.shp'], comun.carpeta('seguidos'), 'primero')
    uno = comun.crear(dw)
    dw.nameProject.setText('segundo')
    dos = comun.crear(dw)
    return uno is not None and dos is not None and comun.proyecto_valido(dos['proyecto']) == (1, []), (uno, dos)


@caso('C04', 'Crear solo con capas del proyecto abierto en QGIS (sin carpetas)')
def _():
    capa = QgsVectorLayer(os.path.join(VECTORIAL, 'lugares_4326.geojson'), 'lugares abiertos', 'ogr')
    QgsProject.instance().addMapLayer(capa)
    try:
        dw = panel()
        comun.dock.ProjectBuilderDockWidget.load_project_layers(dw)
        comun.marcar(dw, 'lugares abiertos')
        dw.pathFolderProject.setText(comun.carpeta('solo_abierto'))
        dw.nameProject.setText('solo_abierto')
        resultado = comun.crear(dw)
    finally:
        QgsProject.instance().removeMapLayer(capa.id())
    return resultado is not None and comun.proyecto_valido(resultado['proyecto']) == (1, []), comun.avisos()


@caso('I01', '«Abrir proyecto», «Abrir carpeta» e «Informe…» cuando el proyecto ya se ha borrado')
def _():
    dw, resultado = _creado('borrado_luego')
    shutil.rmtree(os.path.dirname(resultado['proyecto']))
    comun.MENSAJES.clear()
    abiertos = []
    dw.iface.addProject = lambda ruta: abiertos.append(ruta)
    dw.open_created_project()
    dw.open_created_folder()
    dw.show_final_report()
    return not abiertos and len(comun.avisos()) == 3, (abiertos, comun.avisos())


@caso('I02', 'Informe final con capas de nombres raros (<, >, &, comillas): se ve bien, sin romper el HTML')
def _():
    capa = QgsVectorLayer(os.path.join(VECTORIAL, 'lugares_4326.geojson'), 'a<b>&c"d', 'ogr')
    QgsProject.instance().addMapLayer(capa)
    try:
        dw = panel()
        comun.dock.ProjectBuilderDockWidget.load_project_layers(dw)
        comun.marcar(dw, 'a<b>&c"d')
        dw.pathFolderProject.setText(comun.carpeta('dest_html_raro'))
        dw.nameProject.setText('html')
        comun.crear(dw)
        contenido, filas = dw.final_report()
    finally:
        QgsProject.instance().removeMapLayer(capa.id())
    return contenido is not None and '&lt;b&gt;' in contenido and '<b>&c' not in contenido, len(filas)


@caso('I03', 'Guardar el informe: carpeta que no existe, carpeta sin permiso, extensión desconocida y cancelar')
def _():
    dw, _resultado = _creado('guardar_informe')
    contenido, filas = dw.final_report()
    rutas = {'cancelar': '', 'no existe': os.path.join(comun.TMP, 'no', 'existe', 'informe.pdf'),
             'extensión rara': os.path.join(comun.carpeta('informes'), 'informe.txt'),
             'csv': os.path.join(comun.carpeta('informes_csv'), 'informe.csv')}
    bloqueada = comun.carpeta('informe_sin_permiso')
    if os.name == 'nt':
        rutas['sin permiso'] = os.path.join(bloqueada, 'informe.html')
        subprocess.run(['icacls', bloqueada, '/deny', '*S-1-1-0:(OI)(CI)(W,AD,WD)'], capture_output=True)
    resultados = {}
    try:
        for nombre, ruta in rutas.items():
            comun.MENSAJES.clear()
            dw.ask_save_path = lambda propuesta, ruta=ruta: ruta
            resultados[nombre] = (dw.save_layers_report(contenido, filas), list(comun.avisos()))
    finally:
        if os.name == 'nt':
            subprocess.run(['icacls', bloqueada, '/remove:d', '*S-1-1-0'], capture_output=True)
    ok = (resultados['cancelar'][0] is None and not resultados['cancelar'][1]
          and resultados['no existe'][0] is None and resultados['no existe'][1]
          and os.path.isfile(rutas['extensión rara']) and os.path.isfile(rutas['csv']))
    if 'sin permiso' in resultados:
        ok = ok and resultados['sin permiso'][0] is None and resultados['sin permiso'][1]
    return ok, resultados


@caso('I04', '«Copiar» el informe deja la tabla en el portapapeles (texto para Excel y HTML para Word)')
def _():
    dw, _resultado = _creado('copiar')
    _contenido, filas = dw.final_report()
    dw.copy_layers_report(filas)
    datos = QApplication.clipboard().mimeData()
    return 'zonas_4326' in datos.text() and '\t' in datos.text() and '<table' in datos.html(), datos.text()[:200]


@caso('I05', 'Informe de capas (antes de crear): sin nada marcado y con una capa que ya no existe')
def _():
    datos = comun.copia_datos('informe_previo')
    dw = panel()
    dw.show_layers_report()
    sin_nada = comun.avisado('marca')
    dw.add_source_folder(os.path.join(datos, 'vectorial'))
    comun.marcar(dw, 'zonas_4326.shp', 'lugares_4326.geojson')
    os.remove(os.path.join(datos, 'vectorial', 'lugares_4326.geojson'))
    filas = dw.preview_rows()
    dw.show_layers_report()
    return (sin_nada and len(filas) == 2 and any('No se encuentra' in f['detalle'] for f in filas)
            and any(v[0] == 'dialogo' for v in comun.VENTANAS)), (filas, comun.avisos())


@caso('I06', 'Informe final: los problemas y las capas sin datos aparecen en el informe')
def _():
    dw, resultado = _creado('con_problemas')
    dw.last_result['problemas'] = ['La capa x no se ha podido cargar: comprueba que el fichero se abre en QGIS']
    dw.last_result['vacias'] = ['capa_vacia']
    contenido, _filas = dw.final_report()
    return 'Problemas' in contenido and 'capa_vacia' in contenido, resultado


@caso('C07', 'Copiar la carpeta del proyecto creado a otro sitio (pendrive, otro ordenador): todo se ve, iconos y logos incluidos')
def _():
    from qgis.core import (QgsLayoutItemPicture, QgsMarkerSymbol, QgsPrintLayout, QgsReadWriteContext, QgsRenderContext,
                           QgsSingleSymbolRenderer, QgsSvgMarkerSymbolLayer)
    from qgis.PyQt.QtGui import QColor, QImage
    datos = comun.copia_datos('portable_datos')
    # Un estilo con un icono SVG de otra carpeta, y una plantilla con un logo de otra carpeta
    recursos = comun.carpeta('portable_recursos')
    svg = os.path.join(recursos, 'icono_propio.svg')
    with open(svg, 'w') as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle cx="5" cy="5" r="4"/></svg>')
    puntos = QgsVectorLayer(os.path.join(datos, 'vectorial', 'lugares_4326.geojson'), 'lugares', 'ogr')
    simbolo = QgsMarkerSymbol()
    simbolo.changeSymbolLayer(0, QgsSvgMarkerSymbolLayer(svg))
    puntos.setRenderer(QgsSingleSymbolRenderer(simbolo))
    puntos.saveNamedStyle(os.path.join(datos, 'vectorial', 'lugares_4326.qml'))
    del puntos
    logo = os.path.join(recursos, 'logo.png')
    imagen = QImage(20, 20, QImage.Format.Format_RGB32)
    imagen.fill(QColor('blue'))
    imagen.save(logo)
    composicion = QgsPrintLayout(QgsProject.instance())
    composicion.initializeDefaults()
    foto = QgsLayoutItemPicture(composicion)
    foto.setPicturePath(logo)
    composicion.addLayoutItem(foto)
    plantilla = os.path.join(recursos, 'plano_con_logo.qpt')
    composicion.saveAsTemplate(plantilla, QgsReadWriteContext())
    fallos = []
    for modo in ('single', 'convert', 'keep'):
        dw = panel()
        dw.add_layout_file(plantilla)
        comun.preparar(dw, [datos], ['vectorial', 'raster'], comun.carpeta(f'portable_{modo}'), 'portable')
        dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
        resultado = comun.crear(dw)
        dw._set_layout_files([])
        if not resultado:
            fallos.append((modo, 'no se creó', comun.avisos()))
            continue
        # Se copia la carpeta a otro sitio y se quita la original (como en otro ordenador)
        destino = os.path.join(comun.carpeta(f'pendrive_{modo}'), 'Copia del proyecto ñ')
        shutil.copytree(os.path.dirname(resultado['proyecto']), destino)
        shutil.rmtree(os.path.dirname(resultado['proyecto']), ignore_errors=True)
        p = QgsProject()
        p.read(os.path.join(destino, 'portable.qgz'))
        malas = [c.name() for c in p.mapLayers().values() if not c.isValid()]
        fuera = [c.source() for c in p.mapLayers().values() if c.isValid() and not os.path.normcase(
            os.path.abspath(c.source().split('|')[0])).startswith(os.path.normcase(os.path.abspath(destino)))]
        iconos = []
        for c in p.mapLayers().values():
            if isinstance(c, QgsVectorLayer) and c.renderer() is not None:
                for simb in c.renderer().symbols(QgsRenderContext()):
                    iconos += [capa.path() for capa in simb.symbolLayers() if isinstance(capa, QgsSvgMarkerSymbolLayer)]
        logos = [i.picturePath() for lay in p.layoutManager().printLayouts() for i in lay.items()
                 if isinstance(i, QgsLayoutItemPicture)]
        p.clear()
        sin_icono = [i for i in iconos if not os.path.isfile(i)]
        sin_logo = [i for i in logos if not os.path.isfile(i)]
        if malas or fuera or sin_icono or sin_logo or not iconos or not logos:
            fallos.append((modo, malas, fuera, iconos, logos))
    return not fallos, fallos


@caso('C08', 'Nombre y carpeta del proyecto con tildes, eñes, espacios, apóstrofo y paréntesis (válidos): se crea y se abre')
def _():
    fallos = []
    nombre = "Proyecto Málaga ñ O'Donnell (v2) 2026"
    for modo in ('single', 'convert', 'keep'):
        destino = os.path.join(comun.carpeta(f'Carpeta con espacios y tildes ñ {modo}'), "Sub carpeta d'ejemplo")
        dw = panel()
        comun.preparar(dw, [VECTORIAL], ['zonas_4326.shp', 'lugares_4326.geojson', 'multicapa.gpkg'], destino, nombre)
        dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
        resultado = comun.crear(dw)
        capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
        if not resultado or malas or capas < 3 or not resultado['proyecto'].endswith(nombre + '.qgz'):
            fallos.append((modo, capas, malas, resultado and resultado['problemas'], comun.avisos()))
    return not fallos, fallos


comun.terminar('H09-H10 Crear el proyecto e informes')
