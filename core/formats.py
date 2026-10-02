"""Formatos de capa que admite el plugin y utilidades para reconocerlos."""

import os

from qgis.core import Qgis, QgsProviderRegistry

# Extensiones admitidas (siempre en minúsculas)
VECTOR_EXTENSIONS = ('.shp', '.gpkg')
RASTER_EXTENSIONS = ('.tif',)  #.ecw se añadirá cuando se implemente su exportación
SUPPORTED_EXTENSIONS = VECTOR_EXTENSIONS + RASTER_EXTENSIONS

# Tipos de elemento que se muestran en el árbol
FOLDER = 'folder'
VECTOR = 'vector'
GEOPACKAGE = 'geopackage'  #Vectorial que puede contener varias capas (se muestran como hijos en el árbol)
RASTER = 'raster'


def extension(path):
    """Extensión del fichero en minúsculas, para reconocer también .SHP, .TIF..."""
    return os.path.splitext(path)[1].lower()


def layer_kind(path):
    """Devuelve VECTOR, GEOPACKAGE, RASTER o None si el formato no está admitido."""
    ext = extension(path)
    if ext == '.gpkg':
        return GEOPACKAGE
    if ext in VECTOR_EXTENSIONS:
        return VECTOR
    if ext in RASTER_EXTENSIONS:
        return RASTER
    return None


def style_path(path):
    """Ruta del estilo .qml que acompaña a una capa (mismo nombre, extensión .qml)."""
    return os.path.splitext(path)[0] + '.qml'


def vector_sublayers(path):
    """Capas vectoriales que contiene un fichero (un GeoPackage puede tener varias)."""
    return [s for s in QgsProviderRegistry.instance().querySublayers(path)
            if s.type() == Qgis.LayerType.Vector]  #Solo capas vectoriales (se ignoran ráster o tablas internas)
