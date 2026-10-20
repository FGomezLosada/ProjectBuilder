"""
Plan de pruebas · H06 Zona de trabajo (recorte por capa, por elementos seleccionados o por rectángulo, con margen).
Ver docs/PLAN_PRUEBAS.md. Uso: tools\\probar.bat (o tools\\run_tests.py casos_zona_test.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import caso, panel  # noqa: E402

from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRectangle, QgsVectorLayer  # noqa: E402

VECTORIAL = os.path.join(comun.DATA, 'vectorial')
DENTRO = 'POLYGON((-3.88 36.74,-3.86 36.74,-3.86 36.76,-3.88 36.76,-3.88 36.74))'  #Dentro de los datos de prueba


def _capa(nombre, wkts, crs='EPSG:4326'):
    ruta = comun.poligonos(os.path.join(comun.carpeta(f'zona_{nombre}'), f'{nombre}.shp'), wkts, crs)
    capa = QgsVectorLayer(ruta, nombre, 'ogr')
    QgsProject.instance().addMapLayer(capa)
    return capa


def _panel_zona(capa=None, nombre='zona'):
    dw = panel()
    comun.preparar(dw, [VECTORIAL], ['zonas_4326.shp', 'lugares_4326.geojson'], comun.carpeta(f'dest_{nombre}'), nombre)
    dw.groupZone.setChecked(True)
    dw.zoneByLayer.setChecked(True)
    dw.zoneLayer.setLayer(capa)
    return dw


def _rechaza(dw, *fragmentos):
    dw.last_result = None
    dw.create_project(background=False)
    informe = dw.show_layers_report()  #El informe de capas también calcula la zona
    return dw.last_result is None and comun.avisado(*fragmentos) and informe is None


@caso('Z01', 'Zona activada sin elegir capa')
def _():
    dw = _panel_zona(None)
    return _rechaza(dw, 'capa'), comun.avisos()


@caso('Z02', 'Capa de zona sin elementos')
def _():
    dw = _panel_zona(_capa('vacia', []))
    return _rechaza(dw, 'no tiene elementos'), comun.avisos()


@caso('Z03', '«Solo los seleccionados» sin nada seleccionado')
def _():
    dw = _panel_zona(_capa('sin_seleccion', [DENTRO]))
    dw.zoneSelected.setChecked(True)
    return _rechaza(dw, 'seleccionad'), comun.avisos()


@caso('Z04', 'Capa de zona sin SRC')
def _():
    capa = _capa('sin_src', [DENTRO], crs=None)
    capa.setCrs(QgsCoordinateReferenceSystem())  #Sin .prj (QGIS podría haberle puesto uno por defecto al abrirla)
    dw = _panel_zona(capa)
    return _rechaza(dw, 'SRC'), comun.avisos()


@caso('Z05', 'La capa de la zona se quita de QGIS después de elegirla')
def _():
    capa = _capa('quitada', [DENTRO])
    dw = _panel_zona(capa)
    QgsProject.instance().removeMapLayer(capa.id())
    comun.procesar_eventos()
    vacio = dw.zoneLayer.currentLayer() is None  #No debe saltar sola a otra capa de polígonos (hay varias abiertas)
    return vacio and comun.avisado('Se ha quitado', 'quitada') and _rechaza(dw, 'capa'), comun.avisos()


@caso('Z06', 'Rectángulo sin indicar (vacío)')
def _():
    dw = _panel_zona(None)
    dw.zoneByExtent.setChecked(True)
    dw.zoneExtent.setOutputExtentFromUser(QgsRectangle(), QgsCoordinateReferenceSystem('EPSG:4326'))
    dw.zoneExtent.clear()
    return _rechaza(dw, 'rectángulo'), comun.avisos()


@caso('Z07', 'Margen máximo permitido por el panel')
def _():
    dw = _panel_zona(_capa('margen', [DENTRO]))
    dw.zoneMargin.setValue(dw.zoneMargin.maximum())
    resultado = comun.crear(dw)
    capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
    return capas >= 2 and not malas, (capas, malas, comun.avisos())


@caso('Z08', 'Zona que no toca ninguna capa: se crea el proyecto y se explica que no hay datos en la zona')
def _():
    dw = _panel_zona(_capa('lejos', ['POLYGON((10 50,10.1 50,10.1 50.1,10 50.1,10 50))']))
    resultado = comun.crear(dw)
    if resultado is None:
        return False, comun.avisos()
    texto = getattr(dw, 'last_message', '')
    return len(resultado['vacias']) == 2 and 'sin datos en la zona' in texto, (resultado, texto)


@caso('Z09', 'Zona en grados con margen y proyecto en grados (el margen se mide en metros)')
def _():
    dw = _panel_zona(_capa('grados', [DENTRO]), 'grados')
    dw.zoneMargin.setValue(500)
    dw.selectProjection.setCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
    resultado = comun.crear(dw)
    capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
    return capas >= 2 and not malas, (capas, malas, comun.avisos())


@caso('Z10', 'Zona imposible de pasar al SRC del proyecto (polo sur con proyecto UTM 30N): mensaje claro')
def _():
    dw = _panel_zona(_capa('polo', ['POLYGON((-180 -90,180 -90,180 -80,-180 -80,-180 -90))']), 'polo')
    dw.zoneMargin.setValue(1000)
    dw.last_result = None
    dw.create_project(background=False)
    dw.show_layers_report()
    return True, comun.avisos()


@caso('Z11', 'Zona por rectángulo en un SRC distinto al del mapa y al del proyecto')
def _():
    dw = _panel_zona(None, 'rectangulo')
    dw.zoneByExtent.setChecked(True)
    dw.zoneExtent.setOutputExtentFromUser(QgsRectangle(408000, 4065000, 412000, 4070000), QgsCoordinateReferenceSystem('EPSG:25830'))
    resultado = comun.crear(dw)
    capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
    return capas >= 1 and not malas, (capas, malas, comun.avisos())


@caso('Z12', 'Zona de una capa temporal (en memoria) y luego guardar la configuración')
def _():
    memoria = QgsVectorLayer('Polygon?crs=EPSG:4326', 'temporal', 'memory')
    from qgis.core import QgsFeature, QgsGeometry
    f = QgsFeature()
    f.setGeometry(QgsGeometry.fromWkt(DENTRO))
    memoria.dataProvider().addFeatures([f])
    QgsProject.instance().addMapLayer(memoria)
    dw = _panel_zona(memoria, 'temporal')
    resultado = comun.crear(dw)
    datos = dw.config_to_dict()
    QgsProject.instance().removeMapLayer(memoria.id())
    avisos = dw.apply_config(datos)
    return resultado is not None and any('temporal' in a for a in avisos), avisos


comun.terminar('H06 Zona de trabajo')
