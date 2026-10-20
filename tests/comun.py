"""
Utilidades comunes de las baterías de casos del plan de pruebas (docs/PLAN_PRUEBAS.md).

Cada caso se ejecuta con @caso('ID', 'descripción') y, además de lo que compruebe el propio caso, se vigilan siempre
las reglas del plan para TODOS los casos:
  3. Ningún caso, por absurdo que sea, puede dar un error de Python ni abrir una ventana de error: tiene que dar un
     mensaje claro en el panel.
  4. Los mensajes también se prueban: deben decir qué pasa y qué hacer (ver revisar_mensaje).

Uso dentro de una batería (tests/casos_*_test.py):
    import comun
    from comun import caso, panel
    @caso('A01', 'Añadir una carpeta que no existe')
    def _():
        dw = panel()
        dw.add_source_folder('C:/no/existe')
        return comun.avisado('no existe'), comun.ultimo_aviso()
    comun.terminar()
"""
import faulthandler
import os
import re
import shutil
import sys
import tempfile
import time
import traceback

import qgis.utils
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QCoreApplication, QSettings, Qt
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

qgis.utils.reloadPlugin('project_builder')
import project_builder.core.services as svc  # noqa: E402
import project_builder.project_builder_dockwidget as dock  # noqa: E402

faulthandler.enable(file=sys.stdout, all_threads=True)  #Si QGIS se cerrara, se ve dónde
# Si una batería se queda parada (p. ej. esperando una ventana que nadie ve), a los 5 minutos se muestra dónde y se sale
faulthandler.dump_traceback_later(300, exit=True, file=sys.stdout)
os.environ['PB_PRUEBAS'] = '1'

# ---------------------------------------------------------------- Entorno aislado (no toca el perfil real de QGIS)
PERFIL = tempfile.mkdtemp(prefix="pb_perfil_")
svc.profile_dir = lambda: PERFIL
svc.favorites_path = lambda: os.path.join(PERFIL, 'favoritos.json')
svc.health_path = lambda: os.path.join(PERFIL, 'estado_servicios.json')
QSettings().remove('project_builder')  #Opciones recordadas de otras pruebas (último SRC, plantillas...)
PLUGIN = os.path.dirname(dock.__file__)
DATA = os.path.join(PLUGIN, 'tests', 'data')
TMP = tempfile.mkdtemp(prefix="pb_casos_")
Clase = dock.ProjectBuilderDockWidget
START_HEALTH_CHECK = Clase.start_health_check  #Original, para los casos que prueban la revisión de servicios
Clase.start_health_check = lambda self, force=False: None  #Sin revisión de servicios por internet (salvo los casos que la prueban)

# ---------------------------------------------------------------- Vigilancia: mensajes, ventanas y errores de Python
MENSAJES = []  #(texto, nivel) de cada aviso del panel durante el caso
VENTANAS = []  #(tipo, título/texto) de cada ventana que se ha intentado abrir
EXCEPCIONES = []  #Errores de Python que han llegado a Qt (los que en QGIS abren la ventana de error)
RESPUESTAS = {}  #Respuestas a las ventanas «normales» (pedir un fichero, confirmar...): las fija cada caso
ABIERTOS = []  #Direcciones que se han intentado abrir con el navegador o el Explorador

_notify = Clase.notify


def _notify_vigilado(self, message, level=Qgis.MessageLevel.Info, duration=8):
    MENSAJES.append((str(message), level))
    return _notify(self, message, level, duration)


Clase.notify = _notify_vigilado
_show_success = Clase.show_success


def _show_success_vigilado(self, path_file, empty=(), errors=(), summary=None):
    for e in errors:  #Cada problema del informe final también debe decir qué pasa y qué hacer
        MENSAJES.append((str(e), Qgis.MessageLevel.Warning))
    return _show_success(self, path_file, empty, errors, summary)


Clase.show_success = _show_success_vigilado


def _ventana(tipo, valor=None):
    def abrir(*args, **kwargs):
        texto = ' | '.join(str(a) for a in args[1:3] if isinstance(a, str))
        VENTANAS.append((tipo, texto))
        return RESPUESTAS.get(tipo, valor)
    return abrir


QMessageBox.warning = staticmethod(_ventana('warning', QMessageBox.StandardButton.Ok))
QMessageBox.critical = staticmethod(_ventana('critical', QMessageBox.StandardButton.Ok))
QMessageBox.information = staticmethod(_ventana('information', QMessageBox.StandardButton.Ok))
QMessageBox.about = staticmethod(_ventana('about'))
QMessageBox.question = staticmethod(_ventana('question', QMessageBox.StandardButton.No))
QFileDialog.getOpenFileName = staticmethod(_ventana('abrir_fichero', ('', '')))
QFileDialog.getSaveFileName = staticmethod(_ventana('guardar_fichero', ('', '')))
QFileDialog.getExistingDirectory = staticmethod(_ventana('carpeta', ''))
QInputDialog.getText = staticmethod(_ventana('texto', ('', False)))
QDialog.exec = lambda self: VENTANAS.append(('dialogo', self.windowTitle())) or 0
QDesktopServices.openUrl = staticmethod(lambda url: ABIERTOS.append(url.toString()) or True)
VENTANAS_DE_ERROR = ('warning', 'critical', 'information', 'about')


def _excepthook(tipo, valor, tb):
    EXCEPCIONES.append(''.join(traceback.format_exception(tipo, valor, tb)))
    print("ERROR DE PYTHON QUE VERÍA EL USUARIO:\n" + EXCEPCIONES[-1], flush=True)


sys.excepthook = _excepthook
qgis.utils.showException = lambda tipo, valor, tb, *a, **k: _excepthook(tipo, valor, tb)

# ---------------------------------------------------------------- Regla 4: qué pasa y qué hacer
TECNICO = re.compile(
    r"Traceback|NoneType|object has no attribute|has no attribute|is not defined|unexpected keyword|\bErrno\b|"
    r"WinError|<qgis\.|<PyQt|QgsProcessingException|Permission denied|No such file|Could not|Unable to|"
    r"[Ff]ailed to|Access is denied|is not a valid|KeyError|TypeError|ValueError|AttributeError|RuntimeError|"
    r"\bNone\b|\bnan\b|\bTrue\b|\bFalse\b|\{…\}\{…\}", re.UNICODE)
# Verbos e indicaciones que dicen al usuario qué hacer (en imperativo o como sugerencia)
ACCION = re.compile(
    r"\b(elige|elígela|elígelo|escribe|indica|marca|márcala|desmarca|haz clic|pulsa|usa|utiliza|comprueba|revisa|"
    r"cierra|ciérralo|ciérrala|abre|ábrelo|ábrela|vuelve|asigna|asígnale|asígnaselo|añade|añádela|añádelo|quita|"
    r"quítala|quítalo|cambia|espera|guarda|guárdala|copia|selecciona|prueba|libera|conecta|crea|recupera|corrige|"
    r"renombra|mueve|instala|actualiza|reinicia|activa|actívala|desactiva|dibuja|repite|consulta|edita|envía|"
    r"envíaselo|arrastra|cancélalo|repara|reemplaza|sustituye|bórralo|bórrala|borra|sigue|puedes|hay que|debes|"
    r"tienes que|conviene|no hace falta hacer nada|no es un error|se volverá a comprobar|ver informe|ve a|"
    r"pídele|pide|descarga|instálalo|desmárcala|desmárcalo|desmárcalas|desmárcalos|escríbelo|escríbela|revísalo|revísala|"
    r"revísalos|revísalas|selecciónalo|selecciónala|selecciónalos|selecciónalas|conéctala|conéctalo|cópialo|cópiala|"
    r"cópialos|cópialas|muévelo|muévela|renómbralo|renómbrala|márcalo|márcalas|márcalos|ábrelos|ciérralos|quítalas|"
    r"quítalos|bórralos|actualízalo|elígelos|elígelas|añádelas|añádelos|reinstala|vuelve a|búscalo|búscala|"
    r"compruébalo|compruébala|repáralas|repáralo|asígnaselo|cámbialo|cámbiala|guárdalo)\b", re.IGNORECASE | re.UNICODE)


def revisar_mensaje(texto, nivel=Qgis.MessageLevel.Warning):
    """
    Problema del mensaje según la regla 4, o None si está bien. Todos: sin restos técnicos (errores de Python en inglés,
    «None»...). Los avisos (Warning/Critical): además deben decir qué hacer (o que no hace falta hacer nada).
    """
    texto = (texto or '').strip()
    if not texto:
        return "mensaje vacío"
    tecnico = TECNICO.search(texto)
    if tecnico:
        return f"texto técnico «{tecnico.group(0)}»"
    if nivel in (Qgis.MessageLevel.Warning, Qgis.MessageLevel.Critical) and not ACCION.search(texto):
        return "no dice qué hacer"
    return None


# ---------------------------------------------------------------- Casos
RESULTADOS = {}  #ID -> (descripción, ok, detalle)
PANELES = []


def procesar_eventos(segundos=0.15):
    """Deja correr los temporizadores del panel (resumen, árbol del proyecto...) como en QGIS."""
    limite = time.time() + segundos
    while time.time() < limite:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def caso(ident, descripcion):
    """Decorador: ejecuta el caso al definirlo y vigila las reglas 3 y 4 durante todo el caso."""
    def envolver(funcion):
        MENSAJES.clear()
        VENTANAS.clear()
        EXCEPCIONES.clear()
        ABIERTOS.clear()
        RESPUESTAS.clear()
        errores_previos = len(getattr(dock, 'ERRORES_INESPERADOS', []))
        print(f"[inicio] {ident} {descripcion}", flush=True)
        inicio = time.time()
        try:
            resultado = funcion()
            ok, detalle = resultado if isinstance(resultado, tuple) else (bool(resultado), '')
        except Exception:  # noqa: BLE001
            ok, detalle = False, "Error de Python (el usuario vería la ventana de error):\n" + traceback.format_exc(limit=8)
        procesar_eventos()
        problemas = []
        if EXCEPCIONES:
            problemas.append("errores de Python durante el caso:\n" + "\n".join(EXCEPCIONES))
        inesperados = getattr(dock, 'ERRORES_INESPERADOS', [])[errores_previos:]
        if inesperados:
            problemas.append("errores imprevistos capturados por el panel:\n" + "\n".join(inesperados))
        de_error = [v for v in VENTANAS if v[0] in VENTANAS_DE_ERROR]
        if de_error:
            problemas.append(f"se ha abierto una ventana de aviso: {de_error}")
        for texto, nivel in MENSAJES:
            problema = revisar_mensaje(texto, nivel)
            if problema:
                problemas.append(f"mensaje poco claro ({problema}): «{texto}»")
        if problemas:
            ok = False
            detalle = f"{detalle}\n" + "\n".join(problemas)
        RESULTADOS[ident] = (descripcion, bool(ok), str(detalle or ''))
        print(f"[fin] {ident} {'OK' if ok else 'FALLO'} ({time.time() - inicio:.1f} s)", flush=True)
        return funcion
    return envolver


def panel():
    dw = Clase(qgis.utils.iface)
    PANELES.append(dw)
    procesar_eventos(0.05)
    MENSAJES.clear()  #Lo que diga el panel al abrirse no es parte del caso (salvo en los casos que lo prueban)
    return dw


def avisos(nivel=None):
    return [t for t, n in MENSAJES if nivel is None or n == nivel]


def avisado(*fragmentos):
    """True si algún aviso del caso contiene todos los fragmentos (sin distinguir mayúsculas)."""
    return any(all(f.lower() in t.lower() for f in fragmentos) for t in avisos())


def ultimo_aviso():
    return MENSAJES[-1][0] if MENSAJES else '(ningún aviso)'


def todo(item):
    for i in range(item.childCount()):
        yield item.child(i)
        yield from todo(item.child(i))


def item(dw, texto, arbol=None):
    arbol = arbol or dw.treeWidget
    return next((it for it in todo(arbol.invisibleRootItem()) if it.text(0) == texto), None)


def marcar(dw, *textos, arbol=None):
    for texto in textos:
        encontrado = item(dw, texto, arbol)
        assert encontrado is not None, f"no está en el árbol: {texto}"
        encontrado.setCheckState(0, Qt.CheckState.Checked)


def carpeta(nombre):
    """Carpeta nueva y vacía dentro de la carpeta temporal de las pruebas."""
    ruta = os.path.join(TMP, nombre)
    shutil.rmtree(ruta, ignore_errors=True)
    os.makedirs(ruta)
    return ruta


def copia_datos(nombre='datos'):
    """Copia de tests/data/vectorial y raster en una carpeta temporal (para poder estropearla sin miedo)."""
    destino = os.path.join(TMP, nombre)
    shutil.rmtree(destino, ignore_errors=True)
    shutil.copytree(DATA, destino)
    return destino


def poligonos(ruta, wkts, crs='EPSG:4326', driver='ESRI Shapefile', capa=None):
    memoria = QgsVectorLayer(f"Polygon?crs={crs}" if crs else "Polygon", 'tmp', 'memory')
    elementos = []
    for wkt in wkts:
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        elementos.append(f)
    memoria.dataProvider().addFeatures(elementos)
    opciones = QgsVectorFileWriter.SaveVectorOptions()
    opciones.driverName = driver
    if capa:
        opciones.layerName = capa
    error = QgsVectorFileWriter.writeAsVectorFormatV3(memoria, ruta, QgsProject.instance().transformContext(), opciones)[0]
    assert error == QgsVectorFileWriter.WriterError.NoError, error
    return ruta


def preparar(dw, carpetas_origen, marcadas, destino, nombre='proyecto', crs='EPSG:25830'):
    """Rellena el panel: carpetas de capas, capas marcadas, destino, nombre y SRC."""
    for c in carpetas_origen:
        dw.add_source_folder(c)
    marcar(dw, *marcadas)
    dw.pathFolderProject.setText(destino)
    dw.nameProject.setText(nombre)
    dw.selectProjection.setCrs(QgsCoordinateReferenceSystem(crs))


def crear(dw):
    """Crea el proyecto en primer plano (como el botón, pero esperando a que termine). Devuelve el resultado o None."""
    dw.last_result = None
    dw.create_project(background=False)
    procesar_eventos()
    return getattr(dw, 'last_result', None)


def proyecto_valido(ruta):
    """(número de capas, capas no válidas) del proyecto guardado."""
    p = QgsProject()
    p.read(ruta)
    capas = list(p.mapLayers().values())
    malas = [c.name() for c in capas if not c.isValid()]
    p.clear()
    return len(capas), malas


def terminar(nombre_bateria):
    """Resumen de la batería (lo lee tools/run_tests.py: RESULTADO y FALLO)."""
    for p in PANELES:
        try:
            p.deleteLater()
        except RuntimeError:
            pass
    procesar_eventos(0.2)
    fallos = {k: v for k, v in RESULTADOS.items() if not v[1]}
    print("=" * 70)
    print(f"QGIS {Qgis.version()} · {nombre_bateria}: {len(RESULTADOS) - len(fallos)}/{len(RESULTADOS)} casos correctos")
    for ident, (descripcion, ok, detalle) in RESULTADOS.items():
        print(f"  {'OK   ' if ok else 'FALLO'} {ident} {descripcion}")
        if not ok:
            for linea in detalle.strip().splitlines()[-30:]:
                print(f"          {linea}")
    print("RESULTADO:", "TODO CORRECTO" if RESULTADOS and not fallos else "HAY FALLOS")
    print("=" * 70, flush=True)
