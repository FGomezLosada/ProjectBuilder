"""Formatos de capa que admite el plugin, reglas del formato de salida y utilidades para reconocerlos."""

import os

from qgis.core import Qgis, QgsProviderRegistry

# ---------------------------------------------------------------- Formatos de entrada (siempre en minúsculas)
VECTOR_EXTENSIONS = ('.shp', '.gpkg', '.sqlite', '.geojson', '.json', '.kml', '.gml', '.fgb',
                     '.tab', '.mif', '.dxf', '.gpx')
RASTER_EXTENSIONS = ('.tif', '.tiff', '.ecw', '.jp2', '.asc', '.img', '.vrt', '.png', '.jpg', '.jpeg', '.sid')
SUPPORTED_EXTENSIONS = VECTOR_EXTENSIONS + RASTER_EXTENSIONS

# Ficheros que pueden contener varias capas: siempre se muestran con sus capas como hijos en el árbol
CONTAINER_EXTENSIONS = ('.gpkg', '.sqlite')

# ---------------------------------------------------------------- Formato de salida
SINGLE = 'single'  #Un solo GeoPackage con todas las capas vectoriales + ráster en GeoTIFF (recomendado)
CONVERT = 'convert'  #Un GeoPackage por capa (vectoriales) y GeoTIFF comprimido (ráster)
KEEP = 'keep'  #Conservar el formato original siempre que GDAL pueda escribirlo

# Vectoriales que se pueden conservar (GDAL los escribe sin problemas). DXF y GPX tienen esquemas muy
# rígidos (se pierden atributos), por eso se convierten a GeoPackage aunque se elija conservar.
KEEP_VECTOR = ('.shp', '.geojson', '.json', '.kml', '.gml', '.fgb', '.tab', '.mif')
# Ráster que se pueden conservar. ECW, MrSID y VRT no (formatos propietarios o ficheros que apuntan a otros).
KEEP_RASTER = ('.tif', '.tiff', '.img', '.asc', '.jp2', '.png', '.jpg', '.jpeg')

# Opciones del GeoTIFF de salida: compresión sin pérdida y teselado para que cargue rápido
GEOTIFF_OPTIONS = '-co COMPRESS=DEFLATE -co TILED=YES'

# ---------------------------------------------------------------- Tipos de elemento del árbol
FOLDER = 'folder'
VECTOR = 'vector'
MULTILAYER = 'multilayer'  #Vectorial con varias capas (GeoPackage, SpatiaLite, KML con carpetas...): se muestran como hijos
RASTER = 'raster'


def extension(path):
    """Extensión del fichero en minúsculas, para reconocer también .SHP, .TIF..."""
    return os.path.splitext(path)[1].lower()


def vector_sublayers(path):
    """Capas vectoriales que contiene un fichero (un GeoPackage puede tener varias)."""
    return [s for s in QgsProviderRegistry.instance().querySublayers(path)
            if s.type() == Qgis.LayerType.Vector]  #Solo capas vectoriales (se ignoran ráster o tablas internas)


def layer_kind(path):
    """Devuelve VECTOR, MULTILAYER, RASTER o None si el formato no está admitido."""
    ext = extension(path)
    if ext in CONTAINER_EXTENSIONS:
        return MULTILAYER
    if ext in VECTOR_EXTENSIONS:
        n = len(vector_sublayers(path))
        if n == 0:  #Por ejemplo un .json que no es GeoJSON: no se muestra
            return None
        return MULTILAYER if n > 1 else VECTOR
    if ext in RASTER_EXTENSIONS:
        return RASTER
    return None


def output_path(path_target, kind, mode):
    """
    Ruta final de una capa exportada a fichero propio según el formato de salida (CONVERT o KEEP;
    en SINGLE solo se usa para los ráster, que siempre salen en GeoTIFF).
    Las capas con varias capas internas siempre salen en GeoPackage (es el formato que las admite todas).
    """
    base, ext = os.path.splitext(path_target)
    ext = ext.lower()
    if kind == MULTILAYER:
        return base + '.gpkg'
    if kind == RASTER:
        return path_target if (mode == KEEP and ext in KEEP_RASTER) else base + '.tif'
    return path_target if (mode == KEEP and ext in KEEP_VECTOR) else base + '.gpkg'


def style_path(path):
    """Ruta del estilo .qml que acompaña a una capa (mismo nombre, extensión .qml)."""
    return os.path.splitext(path)[0] + '.qml'
