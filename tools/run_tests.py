r"""
Lanza las pruebas de tests/ cada una en un QGIS propio, SIN VENTANA: no toca el QGIS que tengas abierto,
las pruebas no se contaminan entre sí y, si una falla o se cierra, las demás siguen.

Uso (CMD, desde la carpeta del proyecto):
    "C:\Program Files\QGIS 3.40.13\bin\python-qgis-ltr.bat" tools\run_tests.py          (todas, QGIS 3.40)
    "C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat" tools\run_tests.py                (todas, QGIS 4)
    ... tools\run_tests.py zone_test.py stats_test.py                                    (solo esas)

El resumen sale en pantalla y en tests/resultados_qgis<versión>.txt (p. ej. resultados_qgis3.40.txt). Usa la configuración de pruebas de QGIS, no la tuya
(favoritos, plantillas y configuraciones guardadas no se tocan).
"""
import datetime
import importlib.util
import os
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRUEBAS = ['smoke_test.py', 'zone_test.py', 'config_test.py', 'layout_test.py', 'open_project_test.py', 'stats_test.py',
           'db_test.py', 'icons_test.py']
ESPERA = 600  #Segundos máximos por prueba


def ejecutar_una(prueba):
    """Se ejecuta en el proceso hijo: arranca QGIS sin ventana, carga el plugin desde esta carpeta y lanza la prueba."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from qgis.testing import start_app
    start_app()
    from qgis.analysis import QgsNativeAlgorithms
    from qgis.core import QgsApplication
    sys.path.append(os.path.join(QgsApplication.prefixPath(), 'python', 'plugins'))  #Ahí está Processing
    from processing.core.Processing import Processing
    Processing.initialize()  #Algoritmos de Processing (native:*, gdal:*)
    QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
    import qgis.utils
    from qgis.testing.mocked import get_iface
    qgis.utils.iface = get_iface()  #Interfaz simulada con un lienzo de mapa real
    from qgis.core import QgsCoordinateReferenceSystem, QgsRectangle
    lienzo = qgis.utils.iface.mapCanvas()  #Como un QGIS recién abierto: mapa en EPSG:4326
    lienzo.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
    lienzo.setExtent(QgsRectangle(-3.95, 36.70, -3.80, 36.80))
    qgis.utils.reloadPlugin = lambda nombre: None  #Cada prueba ya parte de un QGIS recién abierto
    # El plugin se importa como «project_builder» directamente desde la carpeta del proyecto
    spec = importlib.util.spec_from_file_location('project_builder', os.path.join(RAIZ, '__init__.py'),
                                                  submodule_search_locations=[RAIZ])
    modulo = importlib.util.module_from_spec(spec)
    sys.modules['project_builder'] = modulo
    spec.loader.exec_module(modulo)
    ruta = os.path.join(RAIZ, 'tests', prueba)
    with open(ruta, encoding='utf-8') as f:
        codigo = compile(f.read(), ruta, 'exec')
    exec(codigo, {'__name__': '__main__', '__file__': ruta})
    sys.stdout.flush()
    os._exit(0)  #Salida inmediata: evita mensajes de cierre de QGIS que no aportan nada


def main(pruebas):
    from qgis.core import Qgis
    version = '.'.join(Qgis.version().split('.')[:2])
    resultados = os.path.join(RAIZ, 'tests', f'resultados_qgis{version}.txt')
    lineas = [f"Pruebas ProjectBuilder · QGIS {Qgis.version()} · {datetime.datetime.now():%d/%m/%Y %H:%M}", ""]
    todo_bien = True
    for prueba in pruebas:
        desde = len(lineas)
        inicio = time.time()
        try:
            hijo = subprocess.run([sys.executable, os.path.abspath(__file__), '--una', prueba], capture_output=True,
                                  text=True, encoding='utf-8', errors='replace', timeout=ESPERA)
            salida, codigo = hijo.stdout + hijo.stderr, hijo.returncode
        except subprocess.TimeoutExpired:
            salida, codigo = '', 'tiempo agotado'
        segundos = round(time.time() - inicio)
        resultado = [linea for linea in salida.splitlines() if 'RESULTADO:' in linea]
        fallos = [linea.strip() for linea in salida.splitlines() if 'FALLO' in linea and 'RESULTADO' not in linea]
        if resultado and 'TODO CORRECTO' in resultado[-1]:
            lineas.append(f"  OK      {prueba} ({segundos} s)")
        else:
            todo_bien = False
            motivo = 'con fallos' if resultado else f'se cerró sin terminar (código {codigo})'
            lineas.append(f"  FALLO   {prueba} ({segundos} s): {motivo}")
            lineas += [f"            {f}" for f in fallos]
            if not resultado:
                lineas += [f"            | {l}" for l in salida.splitlines()[-25:]]
        print("\n".join(lineas[desde:]), flush=True)
    lineas += ["", "RESULTADO GLOBAL: " + ("TODO CORRECTO" if todo_bien else "HAY FALLOS")]
    with open(resultados, 'w', encoding='utf-8') as f:
        f.write("\n".join(lineas) + "\n")
    print("\n".join(lineas[-1:]))
    return 0 if todo_bien else 1


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--una':
        ejecutar_una(sys.argv[2])
    else:
        sys.exit(main([os.path.basename(a) for a in sys.argv[1:]] or PRUEBAS))
