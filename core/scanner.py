"""Recorrido de la carpeta de capas para saber qué se puede añadir al proyecto."""

import os
from dataclasses import dataclass, field

from .formats import FOLDER, GEOPACKAGE, VECTOR, layer_kind, vector_sublayers


@dataclass
class Entry:
    """Un elemento de la carpeta de capas: una subcarpeta o una capa admitida."""

    name: str  #Nombre que se ve en el árbol
    path: str  #Ruta completa (no se ve en el árbol, se guarda internamente)
    kind: str  #FOLDER, VECTOR, GEOPACKAGE o RASTER
    children: list = field(default_factory=list)  #Solo las carpetas (y los GeoPackage) tienen hijos
    layer: str = None  #Solo en las capas internas de un GeoPackage: nombre de la capa


def scan_folder(start_path):
    """
    Recorre start_path (y sus subcarpetas) y devuelve la lista de Entry.
    Solo se incluyen carpetas y ficheros con un formato admitido. Orden alfabético.
    """
    entries = []
    for name in sorted(os.listdir(start_path), key=str.lower):
        path = os.path.join(start_path, name)
        if os.path.isdir(path):  #Se comprueba si es un directorio y se recorre también (recursivo)
            entries.append(Entry(name, path, FOLDER, scan_folder(path)))
        else:
            kind = layer_kind(path)
            if kind == GEOPACKAGE:  #Sus capas internas se muestran como hijos para poder elegirlas una a una
                capas = [Entry(s.name(), path, VECTOR, layer=s.name()) for s in vector_sublayers(path)]
                entries.append(Entry(name, path, kind, capas))
            elif kind is not None:  #Si no es un formato admitido no se añade
                entries.append(Entry(name, path, kind))
    return entries
