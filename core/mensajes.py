"""
Errores del sistema y de QGIS explicados al usuario (regla 4 del plan de pruebas: qué pasa y qué hacer).

Los errores de Windows, de GDAL o de PostgreSQL llegan en inglés y con códigos («[WinError 32]», «Permission denied»,
«could not connect to server»...). Aquí se traducen a una frase que dice qué pasa y qué hacer. Lo que no se reconoce
se muestra tal cual (la primera línea), seguido de la indicación que se pase en que_hacer.
"""

import errno
import re

# (texto que aparece en el error, en minúsculas) -> explicación con qué hacer
_POR_TEXTO = [
    (('being used by another process', 'siendo utilizado por otro proceso', 'used by another process', 'locked',
      'database is locked', 'bloqueado'),
     "el fichero está abierto en otro programa (o en QGIS). Ciérralo y vuelve a intentarlo"),
    (('permission denied', 'access is denied', 'acceso denegado', 'read-only', 'solo lectura', 'not permitted'),
     "no tienes permiso para escribir ahí (o el fichero está abierto en otro programa). Elige otra carpeta o "
     "ciérralo y vuelve a intentarlo"),
    (('unable to perform zip', 'perform zip', 'unable to save to file', 'could not write', 'unable to open database file'),
     "no se pudo escribir el fichero (o no se encuentra). Comprueba que la carpeta existe, que se puede escribir en ella "
     "y que no hay otro programa usando ese fichero"),
    (('no space left', 'disk full', 'espacio suficiente en el disco', 'not enough space'),
     "el disco está lleno. Libera espacio o elige otra unidad"),
    (('file name too long', 'filename too long', 'path too long', 'demasiado largo', 'name too long'),
     "la ruta es demasiado larga para Windows. Usa una carpeta con una ruta más corta (p. ej. C:\\Proyectos)"),
    (('network path', 'network path was not found', 'no se encuentra la ruta de red', 'network name', 'nombre de red'),
     "no se llega a la carpeta de red. Comprueba que estás conectado a la red y que la ruta es correcta"),
    (('could not connect to server', 'connection refused', 'connection failed', 'host not found', 'unknown host', 'is the server running', 'no route to host',
      'could not translate host name', 'timeout expired', 'connection timed out'),
     "el servidor no responde. Comprueba que está encendido, la conexión a la red y los datos de la conexión en QGIS"),
    (('operation canceled', 'operation cancelled', 'timed out', 'timeout'),
     "el servidor tarda demasiado en responder. Prueba más tarde o revisa la dirección de la conexión"),
    (('password authentication failed', 'authentication failed', 'no password supplied', 'role "', 'autenticación'),
     "el usuario o la contraseña de la conexión no son correctos. Revísalos en el Administrador de fuentes de datos "
     "de QGIS"),
    (('no such file', 'cannot find the path', 'cannot find the file', 'no se encuentra', 'does not exist', 'not found'),
     "no se encuentra el fichero o la carpeta. Comprueba que existe y que la unidad está conectada"),
    (('could not create destination layer', 'unable to create', 'cannot create', 'no se pudo crear'),
     "no se pudo crear el fichero de destino. Comprueba que se puede escribir en la carpeta y que no hay otro "
     "fichero abierto con ese nombre"),
    (('invalid geometry', 'geometría no válida', 'geometry is invalid', 'self-intersection', 'ring self'),
     "la capa tiene geometrías no válidas. Repáralas en QGIS (Vectorial → Herramientas de geometría → Reparar "
     "geometrías) y vuelve a crear el proyecto"),
    (('not recognized as a supported file format', 'not recognised as a supported file format',
      'no se reconoce como un formato'),
     "el fichero está dañado o no es del formato que indica su extensión. Comprueba que se abre en QGIS"),
]
# Códigos de error de Windows (winerror) y del sistema (errno) -> un fragmento de la explicación que les corresponde
_POR_CODIGO = {
    32: 'being used', 33: 'being used',  #Fichero en uso
    5: 'permission denied', errno.EACCES: 'permission denied', errno.EPERM: 'permission denied',
    errno.EROFS: 'permission denied',  #Sin permiso
    112: 'no space left', errno.ENOSPC: 'no space left',  #Disco lleno
    206: 'file name too long', errno.ENAMETOOLONG: 'file name too long',  #Ruta demasiado larga
    53: 'network path', 67: 'network path', 1231: 'network path',  #Red
    2: 'no such file', 3: 'no such file', errno.ENOENT: 'no such file',  #No existe
}


def _por_fragmento(fragmento):
    return next(explicacion for fragmentos, explicacion in _POR_TEXTO if any(f.startswith(fragmento) for f in fragmentos))


def explicar(error, que_hacer="Vuelve a intentarlo y, si se repite, revisa la capa o el fichero en QGIS"):
    """
    Frase en palabras del usuario para un error (excepción o texto): qué pasa y qué hacer.
    que_hacer: indicación que se añade si el error no se reconoce.
    """
    codigo = getattr(error, 'winerror', None) or getattr(error, 'errno', None)
    if isinstance(codigo, int) and codigo in _POR_CODIGO:
        return _por_fragmento(_POR_CODIGO[codigo])
    texto = (getattr(error, 'strerror', None) or str(error) or '').strip()
    minusculas = texto.lower()
    for fragmentos, explicacion in _POR_TEXTO:
        if any(f in minusculas for f in fragmentos):
            return explicacion
    primera = re.sub(r'\s+', ' ', texto.splitlines()[0] if texto else '').strip(' .:') or 'error desconocido'
    if len(primera) > 160:
        primera = primera[:157] + '…'
    return f"{primera}. {que_hacer}"
