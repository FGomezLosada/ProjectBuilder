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

from . import services as svc

CONFIG_VERSION = 1  #Si algún día cambia el formato, permite leer las configuraciones antiguas


class ConfigError(Exception):
    """Error al leer o guardar una configuración (el mensaje se muestra al usuario)."""


def configs_dir():
    """Carpeta de las configuraciones dentro del perfil de QGIS."""
    return os.path.join(svc.profile_dir(), 'configuraciones')


def _slug(name):
    """Nombre de fichero a partir del nombre: 'Proyecto Nerja (2026)' -> 'proyecto_nerja_2026'."""
    texto = ''.join(c for c in unicodedata.normalize('NFD', name.lower()) if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', '_', texto).strip('_') or 'configuracion'


def config_path(name):
    return os.path.join(configs_dir(), _slug(name) + '.json')


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
        raise ConfigError(f"No se pudo leer la configuración {os.path.basename(path)}: {e}") from e
    if not isinstance(datos, dict):
        raise ConfigError(f"La configuración {os.path.basename(path)} no tiene el formato esperado")
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
        raise ConfigError(f"No se pudo guardar la configuración: {e}") from e
    return ruta


def delete_config(name):
    ruta = config_path(name)
    if os.path.isfile(ruta):
        os.remove(ruta)
