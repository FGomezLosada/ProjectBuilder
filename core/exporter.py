"""Exportación (recorte + copia + reproyección + conversión de formato) de capas a la carpeta del proyecto."""

import os
import shutil

import processing
from qgis.core import Qgis, QgsCoordinateTransform, QgsProcessingUtils, QgsProject, QgsRasterLayer, QgsVectorLayer

from .clip import zone_uri
from .formats import GEOTIFF_OPTIONS, RASTER_EXTENSIONS, extension, style_path, vector_sublayers


class ExportError(Exception):
    """Error al exportar una capa (el mensaje se muestra al usuario)."""


class EmptyLayer(Exception):
    """La capa no tiene nada dentro de la zona de trabajo: no se exporta (no es un error)."""


def _crs_for(uri, crs):
    """
    SRC de salida de una capa vectorial: el indicado o, si crs es None (no reproyectar), el suyo propio.
    Reproyectar al mismo SRC que ya tiene la capa equivale a copiarla tal cual.
    """
    return crs if crs is not None else QgsVectorLayer(uri, 'origen', 'ogr').crs()


def _vector(uri, crs, zone, output, feedback):
    """
    Recorta (si hay zona) y reproyecta una capa vectorial, escribiendo el resultado en output.
    Se recorta primero y se reproyecta después: así solo se reproyecta lo que queda dentro (más rápido).
    native:clip corta los elementos por el borde de la zona (un polígono que sobresale se queda solo con su parte de dentro)
    y adapta la zona al SRC de la capa automáticamente.
    Devuelve False si no queda ningún elemento dentro de la zona.
    """
    entrada = uri
    if zone and QgsVectorLayer(uri, 'origen', 'ogr').isSpatial():  #Las tablas sin geometría se copian enteras
        entrada = processing.run("native:clip", {'INPUT': uri, 'OVERLAY': zone_uri(zone), 'OUTPUT': 'TEMPORARY_OUTPUT'},
                                 feedback=feedback)['OUTPUT']
        if entrada.featureCount() == 0:
            return False
    processing.run("native:reprojectlayer", {'INPUT': entrada, 'TARGET_CRS': _crs_for(uri, crs), 'OUTPUT': output},
                   feedback=feedback)
    return True


def export_layer(path_source, path_target, crs, feedback=None, layers=None, zone=None, empty=None):
    """
    Copia la capa path_source en su propio fichero path_target, reproyectada al SRC crs
    (crs=None: se copia en su SRC original, sin reproyectar).
    El formato de salida lo marca la extensión de path_target (ver formats.output_path).
    En ficheros con varias capas, layers es la lista de nombres a exportar (None = todas).
    zone: GeoPackage de la zona de trabajo (None = sin recorte). En empty se anotan las capas internas que quedan vacías.
    Si existe un .qml junto a la capa de origen, se copia junto a la capa exportada.
    Devuelve la ruta final (puede cambiar si un formato no se puede escribir y se pasa a GeoTIFF).
    Lanza EmptyLayer si no queda nada dentro de la zona y ExportError si algo falla.
    """
    os.makedirs(os.path.dirname(path_target), exist_ok=True)  #Crea las carpetas y subcarpetas donde irá el archivo
    try:
        if extension(path_source) in RASTER_EXTENSIONS:
            path_target = _export_raster(path_source, path_target, crs, feedback, zone)
        elif extension(path_target) == '.gpkg':
            _export_to_geopackage(path_source, path_target, crs, feedback, layers, zone, empty)
        elif not _vector(path_source, crs, zone, path_target, feedback):  #Se conserva el formato vectorial original
            raise EmptyLayer(os.path.basename(path_source))
    except EmptyLayer:
        raise
    except Exception as e:
        raise ExportError(f"No se pudo exportar {os.path.basename(path_source)}: {e}") from e

    # Copia el estilo junto a la capa en la carpeta del proyecto (solo si existe un .qml en origen)
    qml = style_path(path_source)
    if os.path.isfile(qml):
        shutil.copy2(qml, style_path(path_target))
    return path_target


def export_to_shared_geopackage(path_source, gpkg, tables, crs, feedback=None, zone=None):
    """
    Añade capas de path_source como tablas nuevas del GeoPackage común del proyecto (gpkg).
    tables: diccionario {nombre de la capa en origen: nombre de la tabla en el GeoPackage}.
    Cada capa se escribe directamente en el GeoPackage (sin pasar por memoria), así sirve también para capas grandes.
    Devuelve la lista de capas de origen que han quedado vacías al recortarlas por la zona (no se escriben).
    """
    os.makedirs(os.path.dirname(gpkg), exist_ok=True)
    vacias = []
    try:
        for sublayer in vector_sublayers(path_source):
            if sublayer.name() not in tables:  #Solo las capas marcadas en el árbol
                continue
            destino = f"ogr:dbname='{gpkg}' table=\"{tables[sublayer.name()]}\" (geom)"  #Tabla dentro del GeoPackage
            if not _vector(sublayer.uri(), crs, zone, destino, feedback):
                vacias.append(sublayer.name())
    except Exception as e:
        raise ExportError(f"No se pudo exportar {os.path.basename(path_source)}: {e}") from e
    return vacias


def _export_to_geopackage(path_source, path_target, crs, feedback, layers, zone=None, empty=None):
    """
    Un vectorial a su propio GeoPackage: se recorta y reproyecta cada capa interna por separado y luego se empaquetan
    todas en el GeoPackage de destino (sirve igual para un Shapefile que para un GeoPackage con varias capas).
    """
    capas = []
    for sublayer in vector_sublayers(path_source):
        if layers is not None and sublayer.name() not in layers:  #Solo las capas marcadas en el árbol
            continue
        temporal = QgsProcessingUtils.generateTempFilename(f"{sublayer.name()}.gpkg")
        if not _vector(sublayer.uri(), crs, zone, temporal, feedback):
            if empty is not None:
                empty.append(sublayer.name())
            continue
        capa = QgsVectorLayer(temporal, sublayer.name(), 'ogr')
        capa.setName(sublayer.name())  #El nombre de la capa será el nombre de la tabla dentro del GeoPackage
        capas.append(capa)
    if not capas:
        raise EmptyLayer(os.path.basename(path_source))
    processing.run("native:package", {'LAYERS': capas, 'OUTPUT': path_target,
                                      'OVERWRITE': True, 'SAVE_STYLES': False}, feedback=feedback)


def _raster_outside(path_source, zone):
    """True si el ráster no toca la zona de trabajo (se comparan sus extensiones en el SRC del ráster)."""
    raster, zona = QgsRasterLayer(path_source, 'origen'), QgsVectorLayer(zone_uri(zone), 'zona', 'ogr')
    if not (raster.isValid() and zona.isValid() and raster.crs().isValid()):
        return False  #Sin datos suficientes para saberlo: se intenta recortar igualmente
    extension_zona = QgsCoordinateTransform(zona.crs(), raster.crs(), QgsProject.instance()).transformBoundingBox(zona.extent())
    return not extension_zona.intersects(raster.extent())


def _nodata(path_source):
    """
    Valor "sin datos" para lo que queda fuera de la zona. Si el ráster ya tiene uno se respeta;
    si no, 0 en imágenes (Byte, p. ej. ortofotos) y -9999 en el resto (p. ej. un MDT, donde 0 es una altura válida).
    """
    capa = QgsRasterLayer(path_source, 'origen')  #Se guarda en una variable: si no, Python la borra y su proveedor con ella
    proveedor = capa.dataProvider()
    if proveedor is None or proveedor.sourceHasNoDataValue(1):
        return None
    return 0 if proveedor.dataType(1) == Qgis.DataType.Byte else -9999


def _export_raster(path_source, path_target, crs, feedback, zone=None):
    """
    Recorta (si hay zona) y reproyecta un ráster. GeoTIFF e IMG se escriben directamente; ASC, JPEG2000, PNG y JPG
    solo se pueden crear "copiando" otro ráster, así que primero se procesa a un GeoTIFF temporal y luego se convierte.
    Si esa conversión falla (p. ej. falta el controlador JPEG2000), la capa se queda en GeoTIFF.
    """
    if zone and _raster_outside(path_source, zone):
        raise EmptyLayer(os.path.basename(path_source))
    ext = extension(path_target)
    if ext in ('.tif', '.tiff', '.img'):
        _warp(path_source, path_target, crs, feedback, zone)
        return path_target
    temporal = QgsProcessingUtils.generateTempFilename('reproyectado.tif')
    _warp(path_source, temporal, crs, feedback, zone)
    try:
        processing.run("gdal:translate", {'INPUT': temporal, 'OUTPUT': path_target}, feedback=feedback)
        return path_target
    except Exception:
        geotiff = os.path.splitext(path_target)[0] + '.tif'
        shutil.copy2(temporal, geotiff)
        return geotiff


def _warp(path_source, path_target, crs, feedback, zone=None):
    """
    Reproyecta un ráster con gdalwarp; si crs es None (no reproyectar) lo copia con gdal_translate.
    Con zona de trabajo, antes se recorta por su forma en el SRC original del ráster: lo de fuera queda "sin datos"
    y el fichero se reduce a la extensión de la zona. Se hace en dos pasos porque si se recorta y reproyecta a la vez,
    GDAL aplica la resolución original (p. ej. 0,001 grados) como si fueran metros y crea un ráster gigantesco.
    """
    extra = GEOTIFF_OPTIONS if extension(path_target) in ('.tif', '.tiff') else ''
    if zone:
        recorte = QgsProcessingUtils.generateTempFilename('recorte.tif')
        processing.run("gdal:cliprasterbymasklayer", {'INPUT': path_source, 'MASK': zone_uri(zone),
                                                      'NODATA': _nodata(path_source), 'CROP_TO_CUTLINE': True,
                                                      'KEEP_RESOLUTION': True, 'OUTPUT': recorte}, feedback=feedback)
        if not os.path.isfile(recorte):
            raise ExportError(f"No se pudo recortar {os.path.basename(path_source)} por la zona de trabajo")
        path_source = recorte
    if crs is None:
        processing.run("gdal:translate", {'INPUT': path_source, 'EXTRA': extra, 'OUTPUT': path_target}, feedback=feedback)
        return
    processing.run("gdal:warpreproject", {'INPUT': path_source, 'TARGET_CRS': crs, 'RESAMPLING': 0,
                                          'EXTRA': extra, 'OUTPUT': path_target}, feedback=feedback)
