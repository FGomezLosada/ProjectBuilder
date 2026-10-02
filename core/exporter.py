"""Exportación (copia + reproyección + conversión de formato) de capas a la carpeta del proyecto."""

import os
import shutil

import processing
from qgis.core import QgsProcessingUtils, QgsVectorLayer

from .formats import GEOTIFF_OPTIONS, RASTER_EXTENSIONS, extension, style_path, vector_sublayers


class ExportError(Exception):
    """Error al exportar una capa (el mensaje se muestra al usuario)."""


def _crs_for(uri, crs):
    """
    SRC de salida de una capa vectorial: el indicado o, si crs es None (no reproyectar), el suyo propio.
    Reproyectar al mismo SRC que ya tiene la capa equivale a copiarla tal cual.
    """
    return crs if crs is not None else QgsVectorLayer(uri, 'origen', 'ogr').crs()


def export_layer(path_source, path_target, crs, feedback=None, layers=None):
    """
    Copia la capa path_source en su propio fichero path_target, reproyectada al SRC crs
    (crs=None: se copia en su SRC original, sin reproyectar).
    El formato de salida lo marca la extensión de path_target (ver formats.output_path).
    En ficheros con varias capas, layers es la lista de nombres a exportar (None = todas).
    Si existe un .qml junto a la capa de origen, se copia junto a la capa exportada.
    Devuelve la ruta final (puede cambiar si un formato no se puede escribir y se pasa a GeoTIFF).
    Lanza ExportError si algo falla.
    """
    os.makedirs(os.path.dirname(path_target), exist_ok=True)  #Crea las carpetas y subcarpetas donde irá el archivo
    try:
        if extension(path_source) in RASTER_EXTENSIONS:
            path_target = _export_raster(path_source, path_target, crs, feedback)
        elif extension(path_target) == '.gpkg':
            _export_to_geopackage(path_source, path_target, crs, feedback, layers)
        else:  #Se conserva el formato vectorial original: la extensión de salida indica el formato
            processing.run("native:reprojectlayer", {'INPUT': path_source, 'TARGET_CRS': _crs_for(path_source, crs),
                                                     'OUTPUT': path_target}, feedback=feedback)
    except Exception as e:
        raise ExportError(f"No se pudo exportar {os.path.basename(path_source)}: {e}") from e

    # Copia el estilo junto a la capa en la carpeta del proyecto (solo si existe un .qml en origen)
    qml = style_path(path_source)
    if os.path.isfile(qml):
        shutil.copy2(qml, style_path(path_target))
    return path_target


def export_to_shared_geopackage(path_source, gpkg, tables, crs, feedback=None):
    """
    Añade capas de path_source como tablas nuevas del GeoPackage común del proyecto (gpkg).
    tables: diccionario {nombre de la capa en origen: nombre de la tabla en el GeoPackage}.
    Cada capa se escribe directamente en el GeoPackage (sin pasar por memoria), así sirve también para capas grandes.
    """
    os.makedirs(os.path.dirname(gpkg), exist_ok=True)
    try:
        for sublayer in vector_sublayers(path_source):
            if sublayer.name() not in tables:  #Solo las capas marcadas en el árbol
                continue
            destino = f"ogr:dbname='{gpkg}' table=\"{tables[sublayer.name()]}\" (geom)"  #Tabla dentro del GeoPackage
            processing.run("native:reprojectlayer", {'INPUT': sublayer.uri(), 'TARGET_CRS': _crs_for(sublayer.uri(), crs),
                                                     'OUTPUT': destino}, feedback=feedback)
    except Exception as e:
        raise ExportError(f"No se pudo exportar {os.path.basename(path_source)}: {e}") from e


def _export_to_geopackage(path_source, path_target, crs, feedback, layers):
    """
    Un vectorial a su propio GeoPackage: se reproyecta cada capa interna por separado y luego se empaquetan
    todas en el GeoPackage de destino (sirve igual para un Shapefile que para un GeoPackage con varias capas).
    """
    capas = []
    for sublayer in vector_sublayers(path_source):
        if layers is not None and sublayer.name() not in layers:  #Solo las capas marcadas en el árbol
            continue
        capa = processing.run("native:reprojectlayer", {'INPUT': sublayer.uri(), 'TARGET_CRS': _crs_for(sublayer.uri(), crs),
                                                         'OUTPUT': 'TEMPORARY_OUTPUT'}, feedback=feedback)['OUTPUT']
        capa.setName(sublayer.name())  #El nombre de la capa será el nombre de la tabla dentro del GeoPackage
        capas.append(capa)
    processing.run("native:package", {'LAYERS': capas, 'OUTPUT': path_target,
                                      'OVERWRITE': True, 'SAVE_STYLES': False}, feedback=feedback)


def _export_raster(path_source, path_target, crs, feedback):
    """
    Reproyecta un ráster. GeoTIFF e IMG se escriben directamente; ASC, JPEG2000, PNG y JPG solo se pueden
    crear "copiando" otro ráster, así que primero se reproyecta a un GeoTIFF temporal y luego se convierte.
    Si esa conversión falla (p. ej. falta el controlador JPEG2000), la capa se queda en GeoTIFF.
    """
    ext = extension(path_target)
    if ext in ('.tif', '.tiff', '.img'):
        _warp(path_source, path_target, crs, feedback)
        return path_target
    temporal = QgsProcessingUtils.generateTempFilename('reproyectado.tif')
    _warp(path_source, temporal, crs, feedback)
    try:
        processing.run("gdal:translate", {'INPUT': temporal, 'OUTPUT': path_target}, feedback=feedback)
        return path_target
    except Exception:
        geotiff = os.path.splitext(path_target)[0] + '.tif'
        shutil.copy2(temporal, geotiff)
        return geotiff


def _warp(path_source, path_target, crs, feedback):
    """Reproyecta un ráster con gdalwarp; si crs es None (no reproyectar) lo copia con gdal_translate."""
    extra = GEOTIFF_OPTIONS if extension(path_target) in ('.tif', '.tiff') else ''
    if crs is None:
        processing.run("gdal:translate", {'INPUT': path_source, 'EXTRA': extra, 'OUTPUT': path_target}, feedback=feedback)
        return
    processing.run("gdal:warpreproject", {'INPUT': path_source, 'TARGET_CRS': crs, 'RESAMPLING': 0,
                                          'EXTRA': extra, 'OUTPUT': path_target}, feedback=feedback)
