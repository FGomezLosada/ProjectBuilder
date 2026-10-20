"""
Plan de pruebas · H11 Composiciones de impresión: plantillas .qpt que no existen, dañadas o borradas, composiciones
del proyecto abierto que desaparecen y logos (imágenes) de las plantillas.
Ver docs/PLAN_PRUEBAS.md. Uso: tools\\probar.bat (o tools\\run_tests.py casos_composiciones_test.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import caso, panel  # noqa: E402

from qgis.core import (  # noqa: E402
    QgsLayoutItemMap,
    QgsLayoutItemPicture,
    QgsPrintLayout,
    QgsProject,
    QgsReadWriteContext,
)
from qgis.PyQt.QtGui import QColor, QImage  # noqa: E402

VECTORIAL = os.path.join(comun.DATA, 'vectorial')


def _plantilla(ruta, logo=None):
    """Plantilla .qpt con un mapa (y un logo, si se indica)."""
    layout = QgsPrintLayout(QgsProject.instance())
    layout.initializeDefaults()
    mapa = QgsLayoutItemMap(layout)
    layout.addLayoutItem(mapa)
    if logo:
        imagen = QgsLayoutItemPicture(layout)
        imagen.setPicturePath(logo)
        layout.addLayoutItem(imagen)
    assert layout.saveAsTemplate(ruta, QgsReadWriteContext())
    return ruta


def _crear_con(dw, nombre):
    comun.preparar(dw, [VECTORIAL], ['zonas_4326.shp'], comun.carpeta(f'comp_{nombre}'), nombre)
    return comun.crear(dw)


@caso('L01', 'Añadir una plantilla que no existe')
def _():
    dw = panel()
    dw.add_layout_file(os.path.join(comun.TMP, 'no_existe.qpt'))
    return comun.avisado('no_existe.qpt'), comun.avisos()


@caso('L02', 'Plantillas dañadas (texto, vacía, XML de otra cosa): se avisa al añadirlas y no entran en la lista')
def _():
    carpeta = comun.carpeta('qpt_rotas')
    contenidos = {'texto.qpt': 'no soy una plantilla', 'vacia.qpt': '', 'otra_cosa.qpt': '<qgis><nada/></qgis>'}
    dw = panel()
    for nombre, contenido in contenidos.items():
        ruta = os.path.join(carpeta, nombre)
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write(contenido)
        dw.add_layout_file(ruta)
    en_lista = [n for n in contenidos if comun.item(dw, n[:-4], dw.layoutsTree) is not None]
    resultado = _crear_con(dw, 'rotas')
    dw._set_layout_files([])
    return (len(comun.avisos()) == 3 and not en_lista and resultado is not None and not resultado['problemas']), (
        en_lista, comun.avisos())


@caso('L03', 'Plantilla añadida, marcada y borrada del disco antes de crear')
def _():
    ruta = _plantilla(os.path.join(comun.carpeta('qpt_borrada'), 'borrada.qpt'))
    dw = panel()
    dw.add_layout_file(ruta)
    os.remove(ruta)
    resultado = _crear_con(dw, 'qpt_borrada')
    dw._set_layout_files([])
    return resultado is not None and resultado['composiciones'] in (0, 1), (resultado and resultado['problemas'])


@caso('L04', 'Composición del proyecto abierto que se borra después de marcarla')
def _():
    layout = QgsPrintLayout(QgsProject.instance())
    layout.initializeDefaults()
    layout.setName('Plano que se borra')
    QgsProject.instance().layoutManager().addLayout(layout)
    dw = panel()
    comun.marcar(dw, 'Plano que se borra', arbol=dw.layoutsTree)
    QgsProject.instance().layoutManager().removeLayout(layout)
    comun.procesar_eventos()
    resultado = _crear_con(dw, 'comp_borrada')
    return resultado is not None, comun.avisos()


@caso('L05', 'Quitar plantilla: sin hacer clic antes, y sobre una composición del proyecto (no se puede)')
def _():
    layout = QgsPrintLayout(QgsProject.instance())
    layout.initializeDefaults()
    layout.setName('Del proyecto')
    QgsProject.instance().layoutManager().addLayout(layout)
    dw = panel()
    dw.remove_layout_file()
    dw.layoutsTree.setCurrentItem(comun.item(dw, 'Del proyecto', dw.layoutsTree))
    dw.remove_layout_file()
    QgsProject.instance().layoutManager().removeLayout(layout)
    return len(comun.avisos()) == 2, comun.avisos()


@caso('L06', 'Plantilla con un logo: el logo viaja con el proyecto (se copia a la carpeta del proyecto)')
def _():
    carpeta = comun.carpeta('qpt_logo')
    logo = os.path.join(carpeta, 'logo_empresa.png')
    imagen = QImage(20, 20, QImage.Format.Format_RGB32)
    imagen.fill(QColor('red'))
    imagen.save(logo)
    ruta = _plantilla(os.path.join(carpeta, 'con_logo.qpt'), logo)
    dw = panel()
    dw.add_layout_file(ruta)
    resultado = _crear_con(dw, 'logo')
    dw._set_layout_files([])
    if resultado is None:
        return False, comun.avisos()
    os.remove(logo)  #Como al llevar el proyecto a otro ordenador: el logo original ya no está
    p = QgsProject()
    p.read(resultado['proyecto'])
    rutas = [i.picturePath() for l in p.layoutManager().printLayouts() for i in l.items() if isinstance(i, QgsLayoutItemPicture)]
    p.clear()
    return rutas and all(os.path.isfile(r) for r in rutas), rutas


comun.terminar('H11 Composiciones')
