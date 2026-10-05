"""Recorrido de las carpetas de capas para saber qué se puede añadir al proyecto."""

import os
from dataclasses import dataclass, field

from qgis.core import Qgis, QgsWkbTypes

from .formats import (
    CONTAINER_EXTENSIONS,
    FOLDER,
    MULTILAYER,
    RASTER,
    RASTER_EXTENSIONS,
    VECTOR,
    VECTOR_EXTENSIONS,
    extension,
    vector_sublayers,
)

# Tipo de geometría (para elegir el icono del árbol)
POINT, LINE, POLYGON, TABLE = 'point', 'line', 'polygon', 'table'


@dataclass
class Entry:
    """Un elemento de la carpeta de capas: una subcarpeta o una capa admitida."""

    name: str  #Nombre que se ve en el árbol
    path: str  #Ruta completa (no se ve en el árbol, se guarda internamente)
    kind: str  #FOLDER, VECTOR, MULTILAYER o RASTER
    children: list = field(default_factory=list)  #Solo las carpetas (y los ficheros con varias capas) tienen hijos
    layer: str = None  #Solo en las capas internas de un fichero multicapa: nombre de la capa
    geometry: str = None  #POINT, LINE, POLYGON o TABLE (solo capas vectoriales)


def _geometry(sublayer):
    """Tipo de geometría de una capa interna (QgsProviderSublayerDetails)."""
    tipo = QgsWkbTypes.geometryType(sublayer.wkbType())
    return {Qgis.GeometryType.Point: POINT, Qgis.GeometryType.Line: LINE,
            Qgis.GeometryType.Polygon: POLYGON}.get(tipo, TABLE)


def scan_entry(path):
    """
    Entry de una sola ruta: una carpeta (con todo su contenido) o un fichero con un formato admitido.
    Devuelve None si el fichero no es una capa admitida (p. ej. un .dbf suelto o un .json que no es GeoJSON).
    """
    name = os.path.basename(os.path.normpath(path)) or path
    ext = extension(path)
    if os.path.isdir(path):  #Se recorre también su contenido (recursivo)
        return Entry(name, path, FOLDER, scan_folder(path))
    if ext in RASTER_EXTENSIONS:
        return Entry(name, path, RASTER)
    if ext in VECTOR_EXTENSIONS:
        sublayers = vector_sublayers(path)  #Se consulta una sola vez qué capas tiene el fichero
        if not sublayers:
            return None
        if ext in CONTAINER_EXTENSIONS or len(sublayers) > 1:  #Sus capas internas se muestran como hijos (GeoPackage, KML con carpetas...)
            capas = [Entry(s.name(), path, VECTOR, layer=s.name(), geometry=_geometry(s)) for s in sublayers]
            return Entry(name, path, MULTILAYER, capas)
        return Entry(name, path, VECTOR, geometry=_geometry(sublayers[0]))
    return None


def scan_folder(start_path):
    """
    Recorre start_path (y sus subcarpetas) y devuelve la lista de Entry.
    Solo se incluyen carpetas y ficheros con un formato admitido. Orden alfabético.
    """
    entries = []
    for name in sorted(os.listdir(start_path), key=str.lower):
        entry = scan_entry(os.path.join(start_path, name))
        if entry is not None:
            entries.append(entry)
    return entries
