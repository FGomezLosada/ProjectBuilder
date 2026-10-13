"""Exportación (recorte + copia + reproyección + conversión de formato) de capas a la carpeta del proyecto."""

import os
import shutil

import processing
from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsCsException,
    QgsDataSourceUri,
    QgsProcessingUtils,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)

from .clip import zone_uri
from .formats import GEOTIFF_OPTIONS, RASTER_EXTENSIONS, extension, style_path, vector_sublayers


class ExportError(Exception):
    """Error al exportar una capa (el mensaje se muestra al usuario)."""


class EmptyLayer(Exception):
    """La capa no tiene nada dentro de la zona de trabajo: no se exporta (no es un error)."""


# Extensiones de salida que solo puede tener un ráster (ver formats.output_path)
RASTER_OUTPUTS = ('.tif', '.tiff', '.img', '.asc', '.jp2', '.png', '.jpg', '.jpeg')


def _same_file(a, b):
    """True si las dos rutas son el mismo fichero (sin distinguir mayúsculas en Windows)."""
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _check_not_source(path_source, path_target):
    """Nunca se escribe encima de los datos de origen (protección final, además de la del panel)."""
    if _same_file(path_source.split('|')[0], path_target):
        raise ExportError(f"No se exporta {os.path.basename(path_target)}: el destino es el propio fichero de origen")


def _note(notes, mensaje):
    if notes is not None and mensaje not in notes:
        notes.append(mensaje)


def geopackage_table(gpkg, table):
    """Destino de Processing para una tabla de un GeoPackage, con la ruta bien escapada (apóstrofos, rutas de red...)."""
    uri = QgsDataSourceUri()
    uri.setDatabase(gpkg)
    uri.setDataSource('', table, 'geom')
    return 'ogr:' + uri.uri(False)




def _crs_for(uri, crs):
    """
    SRC de salida de una capa vectorial: el indicado o, si crs es None (no reproyectar), el suyo propio.
    Reproyectar al mismo SRC que ya tiene la capa equivale a copiarla tal cual.
    """
    return crs if crs is not None else QgsVectorLayer(uri, 'origen', 'ogr').crs()


def _clip_to(entrada, zone, feedback):
    """
    native:clip a un GeoPackage temporal (no en memoria: sirve para capas grandes). Si GeoPackage no admite los campos
    de la capa (p. ej. un shapefile con un campo «fid» repetido), se recorta en memoria como alternativa.
    """
    try:
        salida = QgsProcessingUtils.generateTempFilename('recorte.gpkg')
        processing.run("native:clip", {'INPUT': entrada, 'OVERLAY': zone_uri(zone), 'OUTPUT': salida}, feedback=feedback)
        return salida
    except Exception:  # noqa: BLE001
        return processing.run("native:clip", {'INPUT': entrada, 'OVERLAY': zone_uri(zone), 'OUTPUT': 'TEMPORARY_OUTPUT'},
                              feedback=feedback)['OUTPUT']


def _clip(uri, zone, feedback):
    """
    Recorta la capa por la zona. Si falla (casi siempre por geometrías no válidas, frecuentes en cartografía antigua,
    sea cual sea el idioma del mensaje de QGIS), se reparan las geometrías y se intenta una vez más; si vuelve a fallar,
    se informa del error original. Devuelve (recorte: ruta o capa, True si hubo que reparar geometrías).
    """
    try:
        return _clip_to(uri, zone, feedback), False
    except Exception as error:  # noqa: BLE001
        if feedback is not None and feedback.isCanceled():
            raise
        try:
            reparada = QgsProcessingUtils.generateTempFilename('reparada.gpkg')
            processing.run("native:fixgeometries", {'INPUT': uri, 'OUTPUT': reparada}, feedback=feedback)
            return _clip_to(reparada, zone, feedback), True
        except Exception:  # noqa: BLE001
            raise error from None


def _count(capa_o_ruta):
    capa = capa_o_ruta if isinstance(capa_o_ruta, QgsVectorLayer) else QgsVectorLayer(capa_o_ruta, 'recorte', 'ogr')
    return capa.featureCount()


def _vector(uri, crs, zone, output, feedback, notes=None):
    """
    Recorta (si hay zona) y reproyecta una capa vectorial, escribiendo el resultado en output.
    Se recorta primero y se reproyecta después: así solo se reproyecta lo que queda dentro (más rápido).
    native:clip corta los elementos por el borde de la zona (un polígono que sobresale se queda solo con su parte de dentro)
    y adapta la zona al SRC de la capa automáticamente.
    Una capa sin SRC (p. ej. un shapefile sin .prj) no se puede recortar ni reproyectar con seguridad: se copia tal cual
    y se avisa en notes. Devuelve False si no queda ningún elemento dentro de la zona.
    """
    origen = QgsVectorLayer(uri, 'origen', 'ogr')
    nombre = origen.name() if origen.isValid() else os.path.basename(uri.split('|')[0])
    if origen.isValid() and origen.isSpatial() and not origen.crs().isValid():
        _note(notes, f"La capa {os.path.basename(uri.split('|')[0])} no tiene SRC (¿falta el .prj?): "
                     "se ha copiado sin reproyectar ni recortar")
        #Copia tal cual (este algoritmo, a diferencia de savefeatures, también escribe en una tabla del GeoPackage común)
        processing.run("native:extractbyexpression", {'INPUT': uri, 'EXPRESSION': 'TRUE', 'OUTPUT': output}, feedback=feedback)
        return True
    entrada = uri
    if zone and origen.isSpatial():  #Las tablas sin geometría se copian enteras
        entrada, reparada = _clip(uri, zone, feedback)
        if reparada:
            _note(notes, f"La capa {nombre} tenía geometrías no válidas: se han reparado al recortarla")
        if _count(entrada) == 0:
            return False
    processing.run("native:reprojectlayer", {'INPUT': entrada, 'TARGET_CRS': _crs_for(uri, crs), 'OUTPUT': output},
                   feedback=feedback)
    return True


def export_layer(path_source, path_target, crs, feedback=None, layers=None, zone=None, empty=None, notes=None):
    """
    Copia la capa path_source en su propio fichero path_target, reproyectada al SRC crs
    (crs=None: se copia en su SRC original, sin reproyectar).
    El formato de salida lo marca la extensión de path_target (ver formats.output_path).
    En ficheros con varias capas, layers es la lista de nombres a exportar (None = todas).
    zone: GeoPackage de la zona de trabajo (None = sin recorte). En empty se anotan las capas internas que quedan vacías.
    Si existe un .qml junto a la capa de origen, se copia junto a la capa exportada.
    Devuelve la ruta final (puede cambiar si un formato no se puede escribir y se pasa a GeoTIFF).
    En notes se anotan avisos que no impiden exportar (capa sin SRC, geometrías reparadas...).
    Lanza EmptyLayer si no queda nada dentro de la zona y ExportError si algo falla.
    """
    _check_not_source(path_source, path_target)
    try:
        os.makedirs(os.path.dirname(path_target), exist_ok=True)  #Crea las carpetas y subcarpetas donde irá el archivo
        # Ráster: por la extensión de origen o, si es poco común (.gtiff, .sdat...), porque su destino solo puede ser ráster
        if extension(path_source) in RASTER_EXTENSIONS or extension(path_target) in RASTER_OUTPUTS:
            path_target = _export_raster(path_source, path_target, crs, feedback, zone, notes)
        elif extension(path_target) == '.gpkg':
            _export_to_geopackage(path_source, path_target, crs, feedback, layers, zone, empty, notes)
        else:  #Se conserva el formato vectorial original
            _remove_previous(path_target)
            if not _vector(path_source, crs, zone, path_target, feedback, notes):
                raise EmptyLayer(os.path.basename(path_source))
        # Copia el estilo junto a la capa en la carpeta del proyecto (solo si existe un .qml en origen)
        qml = style_path(path_source)
        if os.path.isfile(qml) and not _same_file(qml, style_path(path_target)):
            shutil.copy2(qml, style_path(path_target))
    except (EmptyLayer, ExportError):
        raise
    except Exception as e:
        raise ExportError(f"No se pudo exportar {os.path.basename(path_source)}: {e}") from e
    return path_target


def _remove_previous(path_target):
    """Borra el resultado de una exportación anterior; si está en uso (abierto en QGIS), se avisa claramente."""
    if os.path.exists(path_target):
        try:
            os.remove(path_target)
        except OSError as e:
            raise ExportError(f"No se puede sobrescribir {path_target}: ¿está abierto en QGIS? ({e.strerror})") from e


def export_to_shared_geopackage(path_source, gpkg, tables, crs, feedback=None, zone=None, notes=None):
    """
    Añade capas de path_source como tablas nuevas del GeoPackage común del proyecto (gpkg).
    tables: diccionario {nombre de la capa en origen: nombre de la tabla en el GeoPackage}.
    Cada capa se escribe directamente en el GeoPackage (sin pasar por memoria), así sirve también para capas grandes.
    Devuelve la lista de capas de origen que han quedado vacías al recortarlas por la zona (no se escriben).
    """
    _check_not_source(path_source, gpkg)
    vacias = []
    try:
        os.makedirs(os.path.dirname(gpkg), exist_ok=True)
        for sublayer in vector_sublayers(path_source):
            if sublayer.name() not in tables:  #Solo las capas marcadas en el árbol
                continue
            destino = geopackage_table(gpkg, tables[sublayer.name()])  #Tabla dentro del GeoPackage
            if not _vector(sublayer.uri(), crs, zone, destino, feedback, notes):
                vacias.append(sublayer.name())
    except ExportError:
        raise
    except Exception as e:
        raise ExportError(f"No se pudo exportar {os.path.basename(path_source)}: {e}") from e
    return vacias


def _export_to_geopackage(path_source, path_target, crs, feedback, layers, zone=None, empty=None, notes=None):
    """
    Un vectorial a su propio GeoPackage: se recorta y reproyecta cada capa interna por separado y luego se empaquetan
    todas en el GeoPackage de destino (sirve igual para un Shapefile que para un GeoPackage con varias capas).
    """
    capas = []
    for sublayer in vector_sublayers(path_source):
        if layers is not None and sublayer.name() not in layers:  #Solo las capas marcadas en el árbol
            continue
        temporal = QgsProcessingUtils.generateTempFilename(f"{sublayer.name()}.gpkg")
        if not _vector(sublayer.uri(), crs, zone, temporal, feedback, notes):
            if empty is not None:
                empty.append(sublayer.name())
            continue
        capa = QgsVectorLayer(temporal, sublayer.name(), 'ogr')
        capa.setName(sublayer.name())  #El nombre de la capa será el nombre de la tabla dentro del GeoPackage
        capas.append(capa)
    if not capas:
        raise EmptyLayer(os.path.basename(path_source))
    _remove_previous(path_target)
    processing.run("native:package", {'LAYERS': capas, 'OUTPUT': path_target,
                                      'OVERWRITE': True, 'SAVE_STYLES': False}, feedback=feedback)


def _raster_outside(path_source, zone):
    """True si el ráster no toca la zona de trabajo (se comparan sus extensiones en el SRC del ráster)."""
    raster, zona = QgsRasterLayer(path_source, 'origen'), QgsVectorLayer(zone_uri(zone), 'zona', 'ogr')
    if not (raster.isValid() and zona.isValid() and raster.crs().isValid()):
        return False  #Sin datos suficientes para saberlo: se intenta recortar igualmente
    try:
        extension_zona = QgsCoordinateTransform(zona.crs(), raster.crs(), QgsProject.instance()).transformBoundingBox(zona.extent())
    except QgsCsException:
        return False
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


def _export_raster(path_source, path_target, crs, feedback, zone=None, notes=None):
    """
    Recorta (si hay zona) y reproyecta un ráster. GeoTIFF e IMG se escriben directamente; ASC, JPEG2000, PNG y JPG
    solo se pueden crear "copiando" otro ráster, así que primero se procesa a un GeoTIFF temporal y luego se convierte.
    Si esa conversión falla (p. ej. falta el controlador JPEG2000), la capa se queda en GeoTIFF.
    """
    raster = QgsRasterLayer(path_source, 'origen')
    if raster.isValid() and not raster.crs().isValid():  #Sin SRC no se puede recortar ni reproyectar con seguridad
        _note(notes, f"La capa {os.path.basename(path_source)} no tiene SRC: se ha copiado sin reproyectar ni recortar")
        crs, zone = None, None
    del raster  #Se suelta el fichero antes de procesarlo
    if zone and _raster_outside(path_source, zone):
        raise EmptyLayer(os.path.basename(path_source))
    _remove_previous(path_target)
    ext = extension(path_target)
    if ext in ('.tif', '.tiff', '.img'):
        _warp(path_source, path_target, crs, feedback, zone)
        _check_written(path_target, path_source)
        return path_target
    temporal = QgsProcessingUtils.generateTempFilename('reproyectado.tif')
    _warp(path_source, temporal, crs, feedback, zone)
    _check_written(temporal, path_source)
    try:
        processing.run("gdal:translate", {'INPUT': temporal, 'OUTPUT': path_target}, feedback=feedback)
    except Exception:  # noqa: BLE001 (se comprueba abajo si se ha escrito)
        pass
    if os.path.isfile(path_target):
        return path_target
    geotiff = os.path.splitext(path_target)[0] + '.tif'  #Formato que GDAL no puede escribir aquí: se queda en GeoTIFF
    _remove_previous(geotiff)
    shutil.copy2(temporal, geotiff)
    return geotiff


def _check_written(path, path_source):
    """Los algoritmos de GDAL no siempre avisan si fallan: se comprueba que el fichero existe de verdad."""
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise ExportError(f"GDAL no pudo escribir {os.path.basename(path_source)} (¿falta espacio, permisos o el fichero está en uso?)")


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
