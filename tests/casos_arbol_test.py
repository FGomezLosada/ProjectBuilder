"""
Plan de pruebas · H02 Árbol de capas: añadir y quitar carpetas, buscar, arrastrar, información, «Ver en el mapa»,
menú del clic derecho y ficheros que cambian en el disco después de añadirlos.
Ver docs/PLAN_PRUEBAS.md. Uso: tools\\probar.bat (o tools\\run_tests.py casos_arbol_test.py)
"""
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import caso, panel  # noqa: E402

from qgis.core import QgsCoordinateReferenceSystem  # noqa: E402
from qgis.PyQt.QtCore import QMimeData, Qt, QUrl  # noqa: E402

VECTORIAL = os.path.join(comun.DATA, 'vectorial')
RASTER = os.path.join(comun.DATA, 'raster')


@caso('A01', 'Añadir una carpeta que no existe')
def _():
    dw = panel()
    dw.add_source_folder(os.path.join(comun.TMP, 'no_existe'))
    return comun.avisado('no existe') and dw.treeWidget.topLevelItemCount() == 0, comun.avisos()


@caso('A02', 'Carpeta vacía: aparece, no cuenta capas y al crear se pide marcar alguna')
def _():
    dw = panel()
    vacia = comun.carpeta('vacia')
    dw.add_source_folder(vacia)
    comun.marcar(dw, 'vacia')
    dw.nameProject.setText('vacio')
    dw.pathFolderProject.setText(comun.carpeta('destino_vacio'))
    dw.create_project(background=False)
    return dw.count_layers() == 0 and comun.avisado('ninguna capa'), comun.avisos()


@caso('A03', 'Añadir la misma carpeta dos veces, o una subcarpeta de una ya añadida')
def _():
    dw = panel()
    dw.add_source_folder(VECTORIAL)
    dw.add_source_folder(VECTORIAL)
    dw.add_source_folder(os.path.join(VECTORIAL, 'subcarpeta'))
    raices = dw.treeWidget.topLevelItemCount()
    return raices == 1 and comun.avisado('ya está'), (raices, comun.avisos())


@caso('A04', 'Añadir primero una subcarpeta (con capas marcadas) y luego la carpeta madre: se integran sin perder lo marcado')
def _():
    dw = panel()
    dw.add_source_folder(os.path.join(VECTORIAL, 'subcarpeta'))
    comun.marcar(dw, 'puntos_23030.shp')
    dw.add_source_folder(VECTORIAL)
    puntos = comun.item(dw, 'puntos_23030.shp')
    return (dw.treeWidget.topLevelItemCount() == 1 and puntos is not None
            and puntos.checkState(0) == Qt.CheckState.Checked), dw.source_folders()


@caso('A05', 'Nombres raros: mayúsculas, tildes, espacios, apóstrofo, emoji, «#» y «%»')
def _():
    raros = comun.carpeta("Cartografía d'Alacant #1 50% 🗺")
    nombres = ["Río Vélez.SHP", "l'Horta nord.shp", "capa 🌍.shp", "100% suelo#2.shp"]
    for n in nombres:
        comun.poligonos(os.path.join(raros, n), ['POLYGON((-3.9 36.7,-3.8 36.7,-3.8 36.8,-3.9 36.7))'])
    nombres = sorted(f for f in os.listdir(raros) if f.lower().endswith('.shp'))  #Como hayan quedado en el disco
    dw = panel()
    dw.add_source_folder(raros)
    vistos = {it.text(0) for it in comun.todo(dw.treeWidget.invisibleRootItem())}
    faltan = [n for n in nombres if n not in vistos]
    comun.marcar(dw, *nombres)
    destino = comun.carpeta("Destino d'Alacant 🗺")
    dw.pathFolderProject.setText(destino)
    dw.nameProject.setText("proyecto d'Alacant")
    resultado = comun.crear(dw)
    capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
    return not faltan and capas == 4 and not malas and not resultado['problemas'], (faltan, capas, malas, comun.avisos())


@caso('A06', 'Ficheros dañados o que no son capas: no rompen el árbol ni la creación del proyecto')
def _():
    rota = comun.carpeta('ficheros_rotos')
    with open(os.path.join(rota, 'vacio.gpkg'), 'wb'):
        pass
    with open(os.path.join(rota, 'texto.tif'), 'w') as f:
        f.write('esto no es un ráster')
    with open(os.path.join(rota, 'datos.json'), 'w') as f:
        f.write('{"no": "es geojson"}')
    with open(os.path.join(rota, 'vacio.kml'), 'w') as f:
        f.write('')
    with open(os.path.join(rota, 'basura.geojson'), 'wb') as f:
        f.write(os.urandom(2000))
    shp = comun.poligonos(os.path.join(rota, 'sin_dbf.shp'), ['POLYGON((0 0,1 0,1 1,0 0))'])
    os.remove(shp[:-4] + '.dbf')
    comun.poligonos(os.path.join(rota, 'buena.shp'), ['POLYGON((-3.9 36.7,-3.8 36.7,-3.8 36.8,-3.9 36.7))'])
    dw = panel()
    dw.add_source_folder(rota)
    comun.marcar(dw, 'ficheros_rotos')
    dw.pathFolderProject.setText(comun.carpeta('destino_rotos'))
    dw.nameProject.setText('rotos')
    for it in comun.todo(dw.treeWidget.invisibleRootItem()):
        dw.item_info(it)  #Pasar el ratón por cada elemento
    resultado = comun.crear(dw)
    if resultado is None:
        return False, comun.avisos()
    capas, malas = comun.proyecto_valido(resultado['proyecto'])
    return capas >= 1 and not malas, (capas, malas, resultado['problemas'])


@caso('A07', 'Carpeta con miles de ficheros que no son capas: se añade en poco tiempo')
def _():
    grande = comun.carpeta('muchos_ficheros')
    for i in range(3000):
        with open(os.path.join(grande, f'documento_{i}.txt'), 'w') as f:
            f.write('x')
    for i in range(20):
        os.makedirs(os.path.join(grande, f'sub_{i}', 'mas'))
    shutil.copy2(os.path.join(VECTORIAL, 'lugares_4326.geojson'), os.path.join(grande, 'sub_3', 'mas', 'lugares.geojson'))
    dw = panel()
    inicio = time.time()
    dw.add_source_folder(grande)
    segundos = time.time() - inicio
    return segundos < 15 and comun.item(dw, 'lugares.geojson') is not None, f"{segundos:.1f} s"


@caso('A08', 'Carpeta enorme (como añadir C:\\ o Documentos): se corta a tiempo y se explica qué hacer')
def _():
    enorme = comun.carpeta('enorme')
    for i in range(60):
        sub = os.path.join(enorme, f'carpeta_{i:02d}')
        os.makedirs(sub)
        for j in range(200):
            with open(os.path.join(sub, f'f_{j}.tif'), 'w') as f:  #Aparentan ráster: hay que mirarlos todos
                f.write('')
    dw = panel()
    tope = comun.dock.scanner_module.MAX_ENTRIES
    comun.dock.scanner_module.MAX_ENTRIES = 3000  #El tope real (20.000) se prueba igual con menos ficheros
    try:
        inicio = time.time()
        dw.add_source_folder(enorme)
        segundos = time.time() - inicio
        dw.add_source_folder(VECTORIAL)  #Una carpeta normal después: sin aviso de carpeta grande
    finally:
        comun.dock.scanner_module.MAX_ENTRIES = tope
    avisos_grande = [a for a in comun.avisos() if 'muy grande' in a]
    return segundos < 20 and len(avisos_grande) == 1, (f"{segundos:.1f} s", comun.avisos())


@caso('A09', 'Buscar en el árbol: tildes, mayúsculas, sin resultados y caracteres especiales')
def _():
    dw = panel()
    dw.add_source_folder(VECTORIAL)
    resultados = {}
    for texto in ('ZONAS', 'lugáres', 'no existe nada', '(', '[*', '\\', '%', '   '):
        dw.filterBox.setText(texto)
        comun.procesar_eventos(0.02)
        resultados[texto] = sum(1 for it in comun.todo(dw.treeWidget.invisibleRootItem())
                                if not it.isHidden() and it.parent() is not None)  #Las carpetas añadidas siempre se ven
    dw.filterBox.clear()
    return resultados['ZONAS'] >= 1 and resultados['lugáres'] >= 1 and resultados['no existe nada'] == 0, resultados


@caso('A10', 'Quitar carpeta: sin hacer clic antes, y sobre el bloque del proyecto abierto')
def _():
    dw = panel()
    dw.remove_current_folder()
    primero = comun.avisado('haz clic')
    dw.add_source_folder(VECTORIAL)
    dw.treeWidget.setCurrentItem(comun.item(dw, 'zonas_4326.shp'))
    dw.remove_current_folder()
    return primero and dw.treeWidget.topLevelItemCount() == 0, comun.avisos()


@caso('A11', 'Arrastrar al panel cosas raras: rutas que no existen, .dbf suelto, proyecto .qgz, GeoJSON, carpeta')
def _():
    rara = comun.carpeta('arrastrar')
    shutil.copy2(os.path.join(VECTORIAL, 'zonas_4326.dbf'), os.path.join(rara, 'suelto.dbf'))
    with open(os.path.join(rara, 'proyecto.qgz'), 'wb') as f:
        f.write(b'PK')
    with open(os.path.join(rara, 'nota.txt'), 'w') as f:
        f.write('hola')
    dw = panel()
    avisos = dw.add_dropped([os.path.join(rara, 'no_existe.shp'), os.path.join(rara, 'suelto.dbf'),
                             os.path.join(rara, 'proyecto.qgz'), os.path.join(rara, 'nota.txt'),
                             os.path.join(VECTORIAL, 'lugares_4326.geojson'), RASTER,
                             os.path.join(VECTORIAL, 'zonas_4326.shp'), os.path.join(VECTORIAL, 'zonas_4326.dbf'),
                             (os.path.join(VECTORIAL, 'multicapa.gpkg'), 'no_existe_esta_capa')])
    dw.warn("No se ha podido añadir todo:\n\n- " + "\n- ".join(avisos)) if avisos else None
    marcadas = [it.text(0) for it in comun.todo(dw.treeWidget.invisibleRootItem()) if it.checkState(0) == Qt.CheckState.Checked]
    ok = ('lugares_4326.geojson' in marcadas and 'zonas_4326.shp' in marcadas
          and any('no_existe.shp' in a for a in avisos) and any('proyecto.qgz' in a for a in avisos)
          and any('nota.txt' in a for a in avisos))
    for a in avisos:
        problema = comun.revisar_mensaje(a)
        if problema:
            return False, f"aviso al arrastrar poco claro ({problema}): {a}"
    return ok, (marcadas, avisos)


@caso('A12', 'Arrastrar desde el Explorador: datos sin rutas, URL web, capas del panel Capas de QGIS')
def _():
    dw = panel()
    vacio = QMimeData()
    web = QMimeData()
    web.setUrls([QUrl('https://www.ign.es/capa.shp')])
    capas = QMimeData()
    capas.setData('application/qgis.layertreemodeldata', b'<x/>')
    return all(dw.drop_paths(m) is None for m in (vacio, web, capas, None)), 'se aceptaría algo que no se puede añadir'


@caso('A13', 'Información al pasar el ratón: cada tipo de elemento y una capa borrada del disco después de añadirla')
def _():
    datos = comun.copia_datos('info')
    dw = panel()
    dw.add_source_folder(datos)
    os.remove(os.path.join(datos, 'vectorial', 'lugares_4326.geojson'))
    textos = {it.text(0): dw.item_info(it) for it in comun.todo(dw.treeWidget.invisibleRootItem())}
    return all(t is None or 'None' not in t for t in textos.values()), textos


@caso('A14', '«Ver en el mapa»: capa borrada, ráster sin SRC, capa vacía y un solo punto')
def _():
    datos = comun.copia_datos('ver_mapa')
    vacia = comun.poligonos(os.path.join(datos, 'vacia.shp'), [])
    with open(os.path.join(datos, 'raster', 'sin_src.asc'), 'w') as f:
        f.write("ncols 2\nnrows 2\nxllcorner 0\nyllcorner 0\ncellsize 1\n1 2\n3 4\n")
    dw = panel()
    dw.add_source_folder(datos)
    os.remove(os.path.join(datos, 'vectorial', 'zonas_4326.shp'))
    for nombre in ('zonas_4326.shp', 'vacia.shp', 'sin_src.asc', 'lugares_4326.geojson', 'mdt_4326.tif'):
        elemento = comun.item(dw, nombre)
        dw.show_on_map(elemento)
        dw.tree_double_clicked(elemento)
    del vacia
    return comun.avisado('zonas_4326.shp') and comun.avisado('vacia.shp'), comun.avisos()


@caso('A15', 'Menú del clic derecho en cada tipo de elemento; «Quitar» y «Abrir la carpeta» funcionan')
def _():
    dw = panel()
    dw.add_source_folder(VECTORIAL)
    menus = {}
    for it in list(comun.todo(dw.treeWidget.invisibleRootItem())):
        menu = dw.tree_menu(it)
        menus[it.text(0)] = [a.text() for a in menu.actions() if a.text()]
        menu.deleteLater()
    abrir = next(a for a in dw.tree_menu(comun.item(dw, 'zonas_4326.shp')).actions() if a.text() == 'Abrir la carpeta')
    abrir.trigger()
    quitar = next(a for a in dw.tree_menu(comun.item(dw, 'zonas_4326.shp')).actions() if a.text().startswith('Quitar'))
    quitar.trigger()
    return (dw.treeWidget.topLevelItemCount() == 0 and comun.ABIERTOS
            and all('Ver en el mapa' in v for k, v in menus.items() if k.endswith(('.shp', '.geojson')))), menus


@caso('A16', 'Capa marcada que se borra del disco antes de crear: se avisa antes de empezar, diciendo cuál y qué hacer')
def _():
    datos = comun.copia_datos('borrada')
    dw = panel()
    comun.preparar(dw, [os.path.join(datos, 'vectorial')], ['zonas_4326.shp', 'lugares_4326.geojson'],
                   comun.carpeta('destino_borrada'), 'borrada')
    os.remove(os.path.join(datos, 'vectorial', 'zonas_4326.shp'))
    resultado = comun.crear(dw)
    return resultado is None and comun.avisado('zonas_4326.shp', 'desmárcalas'), comun.avisos()


@caso('A17', 'Carpeta de capas borrada o renombrada después de añadirla: crear avisa claramente')
def _():
    datos = comun.copia_datos('renombrada')
    dw = panel()
    comun.preparar(dw, [os.path.join(datos, 'vectorial')], ['vectorial'], comun.carpeta('destino_renombrada'), 'renombrada')
    os.rename(os.path.join(datos, 'vectorial'), os.path.join(datos, 'vectorial_nueva'))
    resultado = comun.crear(dw)
    return resultado is None and comun.avisado('ya no están', 'vuelve a añadir'), comun.avisos()


@caso('A18', 'Multicapa: marcar solo algunas capas internas y crear en los tres formatos')
def _():
    fallos = []
    for modo in ('single', 'convert', 'keep'):
        dw = panel()
        dw.add_source_folder(VECTORIAL)
        multicapa = comun.item(dw, 'multicapa.gpkg')
        multicapa.child(0).setCheckState(0, Qt.CheckState.Checked)
        dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
        dw.pathFolderProject.setText(comun.carpeta(f'destino_multi_{modo}'))
        dw.nameProject.setText('multi')
        dw.selectProjection.setCrs(QgsCoordinateReferenceSystem('EPSG:25830'))
        resultado = comun.crear(dw)
        capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
        if capas != 1 or malas:
            fallos.append((modo, capas, malas))
    return not fallos, fallos


comun.terminar('H02 Árbol de capas')
