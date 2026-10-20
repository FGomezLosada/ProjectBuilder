"""
Plan de pruebas · H09 Crear el proyecto EN SEGUNDO PLANO (como al pulsar el botón): doble clic y cancelar.
Va en un QGIS propio (las tareas en segundo plano, mejor aisladas). Ver docs/PLAN_PRUEBAS.md.
Uso: tools\\probar.bat (o tools\\run_tests.py casos_fondo_test.py)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import caso, panel  # noqa: E402

VECTORIAL = os.path.join(comun.DATA, 'vectorial')
RASTER = os.path.join(comun.DATA, 'raster')


def _esperar(dw, segundos=90):
    limite = time.time() + segundos
    while dw.task is not None and time.time() < limite:
        comun.procesar_eventos(0.05)
    return dw.task is None


@caso('C05', 'Doble clic en «Crear proyecto»: se crea uno solo y se avisa de que ya se está creando')
def _():
    dw = panel()
    comun.preparar(dw, [VECTORIAL], ['zonas_4326.shp'], comun.carpeta('doble_clic'), 'doble')
    dw.create_project()
    dw.create_project()
    terminado = _esperar(dw)
    resultado = getattr(dw, 'last_result', None)
    return (terminado and resultado is not None and comun.avisado('ya se está creando')
            and dw.createProject.isEnabled()), comun.avisos()


@caso('C06', 'Cancelar la creación: se avisa de qué ha pasado y el panel vuelve a estar disponible')
def _():
    dw = panel()
    comun.preparar(dw, [VECTORIAL, RASTER], ['vectorial', 'raster'], comun.carpeta('cancelar'), 'cancelado')
    dw.create_project()
    dw.task.cancel()
    terminado = _esperar(dw)
    return terminado and comun.avisado('cancelad') and dw.createProject.isEnabled(), comun.avisos()


comun.terminar('H09 Crear en segundo plano')
