"""
Configuraciones guardadas (mejora 4.9): guardar cómo se ha rellenado el panel para repetirlo con un clic.

Cada configuración es un fichero .json en la carpeta "configuraciones" del perfil de QGIS
(se conserva al actualizar el plugin y se puede copiar a otro ordenador o compartir con un compañero).
Este módulo solo lee y escribe los ficheros; qué se guarda lo decide el panel (config_to_dict / apply_config).
"""

import json
import os
import re
import unicodedata

from qgis.core import QgsDataSourceUri

from . import services as svc
from .mensajes import explicar

CONFIG_VERSION = 1  #Si algún día cambia el formato, permite leer las configuraciones antiguas


class ConfigError(Exception):
    """Error al leer o guardar una configuración (el mensaje se muestra al usuario)."""


def configs_dir():
    """Carpeta de las configuraciones dentro del perfil de QGIS."""
    return os.path.join(svc.profile_dir(), 'configuraciones')


def _slug(name):
    """Nombre de fichero a partir del nombre: 'Proyecto Urbanismo (2026)' -> 'proyecto_urbanismo_2026'."""
    texto = ''.join(c for c in unicodedata.normalize('NFD', name.lower()) if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', '_', texto).strip('_') or 'configuracion'


def config_path(name):
    """
    Fichero de la configuración con ese nombre. Si es nueva y su nombre «se parece» al de otra (Málaga y Malaga, o nombres
    sin letras latinas), se le da un fichero propio (_2, _3...) para no sobrescribir la otra.
    """
    carpeta = configs_dir()
    base = _slug(name)
    n, fichero = 2, base
    while True:
        ruta = os.path.join(carpeta, fichero + '.json')
        if not os.path.isfile(ruta):
            return ruta
        try:
            guardado = load_config(ruta).get('nombre') or ''
            if guardado == name or (not guardado and fichero == _slug(name)):  #Copiada a mano, sin «nombre»: vale el del fichero
                return ruta
        except ConfigError:
            return ruta  #Fichero estropeado con ese nombre: se puede sustituir
        fichero, n = f"{base}_{n}", n + 1


def strip_credentials(source):
    """
    Fuente de una capa sin usuario ni contraseña (p. ej. de una capa PostGIS guardada con contraseña): así una configuración
    se puede compartir sin revelarlas. Las fuentes que no son de base de datos se devuelven igual.
    """
    if not source or not re.search(r'(^|[\s&])(password|user|username)=', source):  #Sin credenciales (p. ej. un fichero)
        return source
    if '&' in source and '=' in source.split('&', 1)[0]:  #Servicios web (WMS, WMTS...): parámetros separados por &
        partes = [p for p in source.split('&') if p.split('=', 1)[0].lower() not in ('password', 'username', 'user')]
        return '&'.join(partes)
    uri = QgsDataSourceUri(source)
    uri.setPassword('')
    uri.setUsername('')
    return uri.uri(False)


def list_configs():
    """Nombres de las configuraciones guardadas, por orden alfabético: [(nombre, ruta)]."""
    carpeta = configs_dir()
    if not os.path.isdir(carpeta):
        return []
    lista = []
    for fichero in os.listdir(carpeta):
        if fichero.lower().endswith('.json'):
            ruta = os.path.join(carpeta, fichero)
            try:
                lista.append((load_config(ruta).get('nombre') or os.path.splitext(fichero)[0], ruta))
            except ConfigError:
                continue  #Un fichero estropeado no impide ver los demás
    return sorted(lista, key=lambda x: x[0].lower())


def load_config(path):
    try:
        with open(path, encoding='utf-8') as f:
            datos = json.load(f)
    except (OSError, ValueError) as e:
        if isinstance(e, FileNotFoundError):
            raise ConfigError(f"No se encuentra la configuración {path}: comprueba que sigue en su sitio") from e
        raise ConfigError(f"No se pudo leer la configuración {os.path.basename(path)}: está dañada o no es una "
                          f"configuración. Si te la pasó un compañero, pídele que la exporte de nuevo («Compartir → Exportar la configuración elegida»)") from e
    if not isinstance(datos, dict):
        raise ConfigError(f"La configuración {os.path.basename(path)} está dañada (no tiene el formato esperado). "
                          f"Si te la pasó un compañero, pídele que la exporte de nuevo («Compartir → Exportar la configuración elegida»)")
    return datos


def save_config(name, data):
    """Guarda la configuración con ese nombre (si ya existe, se sustituye). Devuelve la ruta del fichero."""
    os.makedirs(configs_dir(), exist_ok=True)
    ruta = config_path(name)
    datos = {'nombre': name, 'version': CONFIG_VERSION, **data}
    try:
        with open(ruta, 'w', encoding='utf-8') as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except OSError as e:
        raise ConfigError(f"No se pudo guardar la configuración: {explicar(e, 'Comprueba que se puede escribir en el perfil de QGIS')}") from e
    return ruta


def is_config(path):
    """True si el fichero .json es una configuración de ProjectBuilder (y no, por ejemplo, un GeoJSON)."""
    try:
        datos = load_config(path)
    except ConfigError:
        return False
    return 'capas' in datos and 'version' in datos and datos.get('type') != 'FeatureCollection'


def export_config(name, destination):
    """Copia la configuración guardada con ese nombre a otro fichero (para compartirla). Devuelve la ruta."""
    datos = load_config(config_path(name))
    try:
        with open(destination, 'w', encoding='utf-8') as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except OSError as e:
        raise ConfigError(f"No se pudo exportar la configuración a {destination}: {explicar(e, 'Elige otra carpeta')}") from e
    return destination


def import_config(path):
    """
    Añade a mis configuraciones la de un fichero .json (por ejemplo, de un compañero). Si ya hay una con ese nombre,
    se guarda como «nombre (2)», «nombre (3)»... para no perder ninguna. Devuelve el nombre con el que queda.
    """
    if not os.path.isfile(path):
        raise ConfigError(f"No se encuentra el fichero {path}: comprueba que sigue en su sitio")
    if not is_config(path):
        raise ConfigError(f"{os.path.basename(path)} no es una configuración de ProjectBuilder: elige un fichero .json "
                          "exportado desde ProjectBuilder («Compartir → Exportar la configuración elegida»)")
    datos = load_config(path)
    base = (datos.get('nombre') or os.path.splitext(os.path.basename(path))[0]).strip() or 'Configuración'
    nombre, n = base, 2
    while os.path.isfile(config_path(nombre)):
        nombre, n = f"{base} ({n})", n + 1
    datos.pop('nombre', None)
    datos.pop('version', None)
    save_config(nombre, datos)
    return nombre


def delete_config(name):
    ruta = config_path(name)
    try:
        if os.path.isfile(ruta):
            os.remove(ruta)
    except OSError as e:
        raise ConfigError(f"No se pudo borrar la configuración «{name}»: {explicar(e, 'Bórrala a mano desde la carpeta de configuraciones')}") from e


def normalize(datos):
    """
    Configuración con los tipos de datos esperados. Las configuraciones editadas a mano, dañadas o de una versión más
    nueva del plugin pueden traer valores raros: se ignoran (sin errores) y se avisa. Devuelve (datos limpios, avisos).
    """
    raros = []

    def de_tipo(clave, valor, tipos, defecto):
        if valor is None:
            return defecto
        if isinstance(valor, tipos) and not (isinstance(valor, bool) and bool not in (tipos if isinstance(tipos, tuple) else (tipos,))):
            return valor
        raros.append(clave)
        return defecto

    def lista_de(clave, valor, valido):
        elementos = de_tipo(clave, valor, list, [])
        buenos = [e for e in elementos if valido(e)]
        if len(buenos) != len(elementos):
            raros.append(clave)
        return buenos

    def texto(v):
        return isinstance(v, str) and v.strip() != ''

    numero = (int, float)
    capas = de_tipo('capas', datos.get('capas'), dict, {})
    servicios = de_tipo('servicios', datos.get('servicios'), dict, {})
    zona = de_tipo('zona', datos.get('zona'), dict, {})
    capa_zona = de_tipo('zona.capa', zona.get('capa'), dict, None)
    rectangulo = de_tipo('zona.rectangulo', zona.get('rectangulo'), list, None)
    if rectangulo is not None and (len(rectangulo) != 4 or not all(isinstance(v, numero) and not isinstance(v, bool)
                                                                   for v in rectangulo)):
        raros.append('zona.rectangulo')
        rectangulo = None
    margen = de_tipo('zona.margen', zona.get('margen'), numero, 0)
    limpio = {
        'capas': {
            'carpetas': lista_de('capas.carpetas', capas.get('carpetas'), texto),
            'sueltos': lista_de('capas.sueltos', capas.get('sueltos'), texto),
            'marcadas': lista_de('capas.marcadas', capas.get('marcadas'), lambda m: isinstance(m, dict) and texto(m.get('ruta'))
                                 and (m.get('capas') is None or isinstance(m.get('capas'), list))),
        },
        'formato': de_tipo('formato', datos.get('formato'), str, None),
        'reproyectar': de_tipo('reproyectar', datos.get('reproyectar'), bool, True),
        'src': de_tipo('src', datos.get('src'), str, ''),
        'servicios': {'activo': de_tipo('servicios.activo', servicios.get('activo'), bool, False),
                      'lista': lista_de('servicios.lista', servicios.get('lista'), lambda s: isinstance(s, dict))},
        'zona': {
            'activa': de_tipo('zona.activa', zona.get('activa'), bool, False),
            'tipo': zona.get('tipo') if zona.get('tipo') in ('capa', 'rectangulo') else 'capa',
            'capa': capa_zona if capa_zona is None or isinstance(capa_zona.get('fuente'), str) else None,
            'seleccion': lista_de('zona.seleccion', zona.get('seleccion'), lambda i: isinstance(i, int) and not isinstance(i, bool)),
            'solo_seleccion': de_tipo('zona.solo_seleccion', zona.get('solo_seleccion'), bool, False),
            'rectangulo': rectangulo,
            'src_rectangulo': de_tipo('zona.src_rectangulo', zona.get('src_rectangulo'), str, ''),
            'margen': max(0, margen),
            'anadir_capa': de_tipo('zona.anadir_capa', zona.get('anadir_capa'), bool, True),
        },
        'composiciones': lista_de('composiciones', datos.get('composiciones'),
                                  lambda c: isinstance(c, list) and len(c) == 2 and c[0] in ('proyecto', 'fichero') and texto(c[1])),
        'bases_datos': lista_de('bases_datos', datos.get('bases_datos'),
                                lambda b: isinstance(b, dict) and texto(b.get('proveedor')) and texto(b.get('conexion'))),
        'proyecto_abierto': lista_de('proyecto_abierto', datos.get('proyecto_abierto'), lambda c: isinstance(c, dict)),
    }
    if zona.get('tipo') not in (None, 'capa', 'rectangulo'):
        raros.append('zona.tipo')
    for bd in limpio['bases_datos']:
        bd['tablas'] = [t for t in (bd.get('tablas') if isinstance(bd.get('tablas'), list) else [])
                        if isinstance(t, list) and len(t) == 2 and all(isinstance(p, str) for p in t)]
    avisos = []
    version = datos.get('version')
    if isinstance(version, int) and version > CONFIG_VERSION:
        avisos.append("Esta configuración es de una versión más nueva de ProjectBuilder: actualiza el plugin "
                      "(Complementos → Administrar e instalar complementos) para cargarla entera")
    if raros:
        avisos.append(f"La configuración tenía datos que no se entienden ({', '.join(sorted(set(raros)))}): se han ignorado. "
                      "Revisa el panel y vuelve a guardarla con 💾 para corregirla")
    return limpio, avisos
