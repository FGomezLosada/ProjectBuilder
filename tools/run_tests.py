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
           'db_test.py', 'icons_test.py', 'tree_test.py', 'messages_test.py', 'robustez_test.py', 'robustez_fondo_test.py',
           # Plan de pruebas (docs/PLAN_PRUEBAS.md): una batería de casos por herramienta
           'casos_panel_test.py', 'casos_arbol_test.py', 'casos_origenes_test.py', 'casos_servicios_test.py',
           'casos_zona_test.py', 'casos_destino_test.py', 'casos_crear_test.py', 'casos_fondo_test.py',
           'casos_composiciones_test.py', 'casos_configuraciones_test.py', 'casos_formatos_test.py',
           'auditoria_mensajes_test.py']
# Si aparece cualquiera de estos textos, la prueba falla aunque sus casos digan que todo va bien: el usuario habría visto
# la ventana de error de Python (regla 3 del plan de pruebas)
ERRORES_DE_PYTHON = ('ERROR DE PYTHON QUE VERÍA EL USUARIO', 'ERROR INESPERADO', 'Traceback (most recent call last)')
ESPERA = 420  #Segundos máximos por prueba (si se pasa, algo se ha quedado esperando: p. ej. una ventana)


def _arrancar_qgis():
    """
    Arranca QGIS sin ventana, como qgis.testing.start_app, pero con una organización propia en las opciones.
    start_app usa «QGIS / QGIS-TEST»: si el registro de Windows tiene muchas claves bajo HKCU\\Software\\QGIS (otras
    baterías de pruebas dejan una por proceso), QGIS 4 se queda parado al arrancar leyéndolas todas.
    """
    import tempfile
    import qgis.testing
    from qgis.core import QgsApplication
    from qgis.PyQt.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    QCoreApplication.setOrganizationName('ProjectBuilder-Pruebas')
    QCoreApplication.setOrganizationDomain('projectbuilder.invalid')
    QCoreApplication.setApplicationName('QGIS-TEST')
    os.environ['QGIS_CUSTOM_CONFIG_PATH'] = tempfile.mkdtemp('', 'QGIS-PythonTestConfigPath-')
    aplicacion = QgsApplication(list(map(os.fsencode, sys.argv)), True)
    aplicacion.initQgis()
    aplicacion.messageLog().messageReceived.connect(lambda mensaje, etiqueta, nivel: print(f"{etiqueta}({nivel}): {mensaje}"))
    qgis.testing.QGISAPP = aplicacion  #Así start_app (al que llama get_iface) reutiliza esta aplicación
    return aplicacion


def ejecutar_una(prueba):
    """Se ejecuta en el proceso hijo: arranca QGIS sin ventana, carga el plugin desde esta carpeta y lanza la prueba."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    _arrancar_qgis()
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


def _foto_datos():
    """Copia de tests/data antes de las pruebas (QGIS abre los GeoPackage en modo escritura y les cambia metadatos)."""
    import shutil
    import tempfile
    copia = os.path.join(tempfile.mkdtemp(prefix='pb_datos_'), 'data')
    shutil.copytree(os.path.join(RAIZ, 'tests', 'data'), copia)
    return copia


def _restaurar_datos(copia):
    """Deja tests/data como estaba antes de las pruebas: así el repositorio no aparece modificado."""
    import filecmp
    import shutil
    datos = os.path.join(RAIZ, 'tests', 'data')
    for carpeta, _, ficheros in os.walk(datos):
        for nombre in ficheros:  #Ficheros nuevos (p. ej. .aux.xml que crea GDAL al calcular estadísticas)
            ruta = os.path.join(carpeta, nombre)
            if not os.path.exists(os.path.join(copia, os.path.relpath(ruta, datos))):
                try:
                    os.remove(ruta)
                except OSError:
                    pass
    for carpeta, _, ficheros in os.walk(copia):
        for nombre in ficheros:
            original = os.path.join(carpeta, nombre)
            ruta = os.path.join(datos, os.path.relpath(original, copia))
            if not os.path.exists(ruta) or not filecmp.cmp(original, ruta, shallow=False):
                try:
                    os.makedirs(os.path.dirname(ruta), exist_ok=True)
                    shutil.copy2(original, ruta)
                except OSError:
                    pass


def main(pruebas):
    from qgis.core import Qgis
    version = '.'.join(Qgis.version().split('.')[:2])
    foto = _foto_datos()
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
        except subprocess.TimeoutExpired as e:  #Lo que llegó a escribir, para saber en qué caso se quedó parada
            parcial = [x.decode('utf-8', 'replace') if isinstance(x, bytes) else (x or '') for x in (e.stdout, e.stderr)]
            salida, codigo = ''.join(parcial), 'tiempo agotado'
        segundos = round(time.time() - inicio)
        _restaurar_datos(foto)
        resultado = [linea for linea in salida.splitlines() if 'RESULTADO:' in linea]
        fallos = [linea.strip() for linea in salida.splitlines() if 'FALLO' in linea and 'RESULTADO' not in linea]
        python = [t for t in ERRORES_DE_PYTHON if t in salida]
        if python:
            fallos.append(f"error de Python durante la prueba ({python[0]}): ver el detalle")
        if resultado and 'TODO CORRECTO' in resultado[-1] and not python:
            lineas.append(f"  OK      {prueba} ({segundos} s)")
        else:
            todo_bien = False
            motivo = 'con fallos' if resultado and not python else 'error de Python' if resultado else \
                f'se cerró sin terminar (código {codigo})'
            lineas.append(f"  FALLO   {prueba} ({segundos} s): {motivo}")
            lineas += [f"            {f}" for f in fallos]
            if not resultado:
                lineas += [f"            | {l}" for l in salida.splitlines()[-25:]]
            detalle = os.path.join(RAIZ, 'tests', f"detalle_{os.path.splitext(prueba)[0]}_qgis{version}.txt")
            with open(detalle, 'w', encoding='utf-8') as f:  #Salida completa, para ver el motivo de cada fallo
                f.write(salida)
            lineas.append(f"            (detalle completo en tests\\{os.path.basename(detalle)})")
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
