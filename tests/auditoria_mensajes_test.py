"""
Plan de pruebas · H15 Mensajes (regla 4: deben decir qué pasa y qué hacer).

M01 revisa TODOS los mensajes que el código puede mostrar al usuario, aunque ningún caso llegue a provocarlos: avisos del
panel, errores de las capas, de la zona, de las configuraciones... Se leen del propio código (sin ejecutarlo).
M02 comprueba que los errores del sistema y de QGIS (en inglés, con códigos) se traducen a palabras del usuario.
Ver docs/PLAN_PRUEBAS.md. Uso: tools\\probar.bat (o tools\\run_tests.py auditoria_mensajes_test.py)
"""
import ast
import errno
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import caso  # noqa: E402

from qgis.core import Qgis  # noqa: E402

FICHEROS = [os.path.join(comun.PLUGIN, 'project_builder_dockwidget.py'), os.path.join(comun.PLUGIN, 'project_builder.py'),
            *sorted(glob.glob(os.path.join(comun.PLUGIN, 'core', '*.py')))]
ERRORES_VISIBLES = {'ZoneError', 'ConfigError', 'DatabaseError', 'LayoutError', 'ExportError', 'ServicesError', 'OSError',
                    'ValueError'}  #Excepciones cuyo texto acaba en el panel o en el informe final
LISTAS_DE_AVISOS = {'avisos', 'errors', 'errores', 'prepare_errors', 'notes', 'problemas'}
# Huecos que ya dicen qué hacer: explicar(...) (M02) y las constantes con la indicación (M03 comprueba su texto)
ACCIONES_EN_CONSTANTES = ('explicar', 'REVISAR', '_REPARAR', 'ACCION_')
NO_ES_MENSAJE = ('<', 'Geometría:', 'Tamaño', 'SRC:', 'recortadas', 'Catálogo de servicios actualizado')


def _plantilla(nodo):
    """Texto fijo de un mensaje, con 'X' en lo que se calcula al momento. None si no hay texto fijo."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.JoinedStr):
        return ''.join(v.value if isinstance(v, ast.Constant) else _hueco(v) for v in nodo.values)
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
        a, b = _plantilla(nodo.left), _plantilla(nodo.right)
        return None if a is None and b is None else (a or 'X') + (b or 'X')
    if isinstance(nodo, ast.IfExp):
        return _plantilla(nodo.body) or _plantilla(nodo.orelse)
    return None


def _hueco(valor):
    """Lo que se calcula dentro de un f-string: 'X', salvo explicar(...), que ya dice qué hacer (ver M02)."""
    codigo = ast.unparse(getattr(valor, 'value', valor))
    if any(c in codigo for c in ACCIONES_EN_CONSTANTES):
        return 'X (comprueba)'
    return 'X'


def _nombre(func):
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')


def mensajes():
    """[(fichero:línea, plantilla, nivel)] de todo lo que el código puede mostrar al usuario."""
    lista = []
    for ruta in FICHEROS:
        arbol = ast.parse(open(ruta, encoding='utf-8').read())
        for nodo in ast.walk(arbol):
            plantilla, nivel = None, Qgis.MessageLevel.Warning
            if isinstance(nodo, ast.Call) and nodo.args:
                nombre = _nombre(nodo.func)
                if nombre in ('warn', 'avisar'):
                    plantilla = _plantilla(nodo.args[0])
                elif nombre == 'notify':
                    plantilla = _plantilla(nodo.args[0])
                    nivel_txt = ast.unparse(nodo.args[1]) if len(nodo.args) > 1 else 'Info'
                    nivel = Qgis.MessageLevel.Warning if ('Warning' in nivel_txt or 'Critical' in nivel_txt) \
                        else Qgis.MessageLevel.Info
                elif nombre in ERRORES_VISIBLES:
                    plantilla = _plantilla(nodo.args[0])
                elif nombre == '_note' and len(nodo.args) > 1:
                    plantilla = _plantilla(nodo.args[1])
                elif nombre == 'append' and isinstance(nodo.func, ast.Attribute):
                    lista_destino = nodo.func.value
                    destino = lista_destino.attr if isinstance(lista_destino, ast.Attribute) else getattr(lista_destino, 'id', '')
                    if destino in LISTAS_DE_AVISOS:
                        plantilla = _plantilla(nodo.args[0])
            if plantilla and plantilla.strip(' X\n:-') and not plantilla.startswith(NO_ES_MENSAJE):
                lista.append((f"{os.path.basename(ruta)}:{nodo.lineno}", plantilla, nivel))
    return lista


@caso('M01', 'Todos los mensajes del código dicen qué pasa y qué hacer, sin restos técnicos')
def _():
    malos = []
    todos = mensajes()
    for donde, plantilla, nivel in todos:
        problema = comun.revisar_mensaje(plantilla.replace('X', 'capa'), nivel)
        if problema:
            malos.append(f"{donde} ({problema}): {plantilla!r}")
    return len(todos) > 40 and not malos, f"{len(malos)} de {len(todos)} mensajes por mejorar:\n" + "\n".join(malos)


@caso('M02', 'Los errores del sistema y de QGIS se explican en palabras del usuario, con qué hacer')
def _():
    from project_builder.core import mensajes as m
    errores = [
        PermissionError(errno.EACCES, 'Permission denied', 'C:/x.gpkg'),
        FileNotFoundError(errno.ENOENT, 'No such file or directory', 'C:/x'),
        OSError(errno.ENOSPC, 'No space left on device'),
        OSError(errno.ENAMETOOLONG, 'File name too long'),
        Exception('Could not create destination layer for OUTPUT: invalid value'),
        Exception('could not connect to server: Connection refused\n\tIs the server running on host "127.0.0.1"'),
        Exception('FATAL:  password authentication failed for user "x"'),
        Exception('algo totalmente desconocido'),
    ]
    if os.name == 'nt':
        errores += [OSError(None, 'El proceso no tiene acceso al archivo porque está siendo utilizado por otro proceso', 'x', 32),
                    OSError(None, 'El nombre del archivo o la extensión es demasiado largo', 'x', 206)]
    malos = []
    for e in errores:
        texto = m.explicar(e)
        problema = comun.revisar_mensaje(f"No se pudo guardar: {texto}")
        if problema:
            malos.append(f"{e!r} -> «{texto}» ({problema})")
    return not malos, malos


@caso('M03', 'Las indicaciones guardadas en constantes (REVISAR..., _REPARAR) dicen qué hacer')
def _():
    malos, vistas = [], 0
    for ruta in FICHEROS:
        for nodo in ast.walk(ast.parse(open(ruta, encoding='utf-8').read())):
            if isinstance(nodo, ast.Assign) and any(isinstance(t, ast.Name) and t.id.startswith(('REVISAR', '_REPARAR', 'ACCION_'))
                                                    for t in nodo.targets):
                textos = [c.value for c in ast.walk(nodo.value) if isinstance(c, ast.Constant) and isinstance(c.value, str)
                          and ' ' in c.value]
                for texto in textos:
                    vistas += 1
                    problema = comun.revisar_mensaje(texto)
                    if problema:
                        malos.append(f"{os.path.basename(ruta)}:{nodo.lineno} ({problema}): {texto!r}")
    return vistas >= 4 and not malos, malos


comun.terminar('H15 Mensajes')
