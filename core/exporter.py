"""Exportación (copia + reproyección) de capas a la carpeta del proyecto."""

import os
import shutil

import processing

from .formats import extension, style_path, vector_sublayers


class ExportError(Exception):
    """Error al exportar una capa (el mensaje se muestra al usuario)."""


def export_layer(path_source, path_target, crs, feedback=None, layers=None):
    """
    Copia la capa path_source en path_target reproyectada al SRC crs (QgsCoordinateReferenceSystem).
    En un GeoPackage, layers es la lista de nombres de capas a exportar (None = todas).
    Si existe un .qml junto a la capa de origen, se copia junto a la capa exportada.
    Lanza ExportError si algo falla.
    """
    os.makedirs(os.path.dirname(path_target), exist_ok=True)  #Crea las carpetas y subcarpetas donde irá el archivo
    ext = extension(path_source)
    try:
        if ext == '.gpkg':
            # GeoPackage: se reproyecta cada capa interna por separado y luego se empaquetan todas en el GeoPackage de destino
            capas = []
            for sublayer in vector_sublayers(path_source):
                if layers is not None and sublayer.name() not in layers:  #Solo las capas marcadas en el árbol
                    continue
                capa = processing.run("native:reprojectlayer", {'INPUT': sublayer.uri(),
                                                                 'TARGET_CRS': crs,
                                                                 'OUTPUT': 'TEMPORARY_OUTPUT'}, feedback=feedback)['OUTPUT']
                capa.setName(sublayer.name())  #El nombre de la capa será el nombre de la tabla dentro del GeoPackage
                capas.append(capa)
            processing.run("native:package", {'LAYERS': capas, 'OUTPUT': path_target,
                                              'OVERWRITE': True, 'SAVE_STYLES': False}, feedback=feedback)
        elif ext == '.shp':
            processing.run("native:reprojectlayer", {'INPUT': path_source,
                                                     'TARGET_CRS': crs,
                                                     'OUTPUT': path_target}, feedback=feedback)
        elif ext == '.tif':
            processing.run("gdal:warpreproject", {'INPUT': path_source,
                                                  'TARGET_CRS': crs,
                                                  'RESAMPLING': 0,
                                                  'OUTPUT': path_target}, feedback=feedback)
        else:
            raise ExportError(f"El formato {ext} no está disponible en la exportación")
    except ExportError:
        raise
    except Exception as e:
        raise ExportError(f"No se pudo exportar {os.path.basename(path_source)}: {e}") from e

    # Copia el estilo junto a la capa en la carpeta del proyecto (solo si existe un .qml en origen)
    qml = style_path(path_source)
    if os.path.isfile(qml):
        shutil.copy2(qml, style_path(path_target))
