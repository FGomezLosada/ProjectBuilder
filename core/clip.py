"""
Zona de trabajo (mejora 4.4): la geometría con la que se recortan las capas del proyecto.

La zona puede salir de una capa de polígonos (entera o solo sus elementos seleccionados) o de un rectángulo,
con un margen opcional en metros. Se guarda en un GeoPackage temporal que usan los algoritmos de recorte
y que, si se pide, se copia al proyecto como capa "zona_trabajo".
"""

import os
import shutil

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsProcessingUtils,
    QgsProject,
    QgsReferencedRectangle,
    QgsVectorFileWriter,
    QgsVectorLayer,
)

from .formats import style_path

ZONE_TABLE = 'zona_trabajo'  #Nombre de la capa de la zona dentro del proyecto
ZONE_STYLE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'styles', 'zona_trabajo.qml')  #Contorno rojo sin relleno


class ZoneError(Exception):
    """La zona de trabajo no se puede calcular (el mensaje se muestra al usuario)."""


def _transform(geometry, source_crs, target_crs):
    """Copia de la geometría pasada de un SRC a otro."""
    geometry = QgsGeometry(geometry)
    if source_crs != target_crs:
        geometry.transform(QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance()))
    return geometry


def geometry_from_layer(layer, selected_only=False):
    """Une todos los polígonos de la capa (o solo los seleccionados) en una sola geometría. Devuelve (geometría, SRC)."""
    if layer is None or not layer.isValid():
        raise ZoneError("Elige la capa que marca la zona de trabajo")
    features = layer.selectedFeatures() if selected_only else layer.getFeatures()
    geometries = [f.geometry() for f in features if f.hasGeometry()]
    if not geometries:
        raise ZoneError("No hay elementos seleccionados en la capa de la zona" if selected_only
                        else f"La capa {layer.name()} no tiene elementos")
    geometry = QgsGeometry.unaryUnion(geometries)  #Un municipio con varias partes (islas...) queda como un solo multipolígono
    if geometry.isNull() or geometry.type() != Qgis.GeometryType.Polygon:
        raise ZoneError(f"La capa {layer.name()} no es de polígonos")
    return geometry.makeValid(), layer.crs()


def geometry_from_extent(rectangle, crs):
    """Rectángulo (p. ej. la extensión del mapa o uno dibujado) como geometría. Devuelve (geometría, SRC)."""
    if rectangle is None or rectangle.isNull() or rectangle.isEmpty():
        raise ZoneError("Indica el rectángulo de la zona de trabajo (p. ej. la extensión actual del mapa)")
    return QgsGeometry.fromRect(rectangle), crs


def utm_crs(geometry, crs):
    """SRC UTM (WGS 84) del huso donde cae el centro de la geometría: para medir en metros si los datos están en grados."""
    centro = _transform(geometry.centroid(), crs, QgsCoordinateReferenceSystem('EPSG:4326')).asPoint()
    huso = min(int((centro.x() + 180) / 6) + 1, 60)
    return QgsCoordinateReferenceSystem(f"EPSG:{(32600 if centro.y() >= 0 else 32700) + huso}")


def _in_metres(crs):
    return crs.isValid() and not crs.isGeographic() and crs.mapUnits() == Qgis.DistanceUnit.Meters


def apply_margin(geometry, crs, metres, preferred_crs=None):
    """
    Amplía la zona un margen en metros (buffer). Si el SRC de la zona no está en metros (p. ej. EPSG:4326, en grados)
    se usa el SRC del proyecto o, si tampoco, el UTM de la zona: así 500 m son siempre 500 m.
    Devuelve (geometría, SRC).
    """
    if not metres:
        return geometry, crs
    destino = crs if _in_metres(crs) else preferred_crs if preferred_crs is not None and _in_metres(preferred_crs) \
        else utm_crs(geometry, crs)
    return _transform(geometry, crs, destino).buffer(metres, 16), destino


def write_zone(geometry, crs, path=None):
    """
    Guarda la zona en un GeoPackage (por defecto, temporal) con su estilo .qml al lado.
    Devuelve la ruta del GeoPackage.
    """
    path = path or QgsProcessingUtils.generateTempFilename(ZONE_TABLE + '.gpkg')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    capa = QgsVectorLayer(f"MultiPolygon?crs={crs.authid() or 'wkt:' + crs.toWkt()}", ZONE_TABLE, 'memory')
    elemento = QgsFeature()
    geometry = QgsGeometry(geometry)
    geometry.convertToMultiType()
    elemento.setGeometry(geometry)
    capa.dataProvider().addFeatures([elemento])
    opciones = QgsVectorFileWriter.SaveVectorOptions()
    opciones.driverName = 'GPKG'
    opciones.layerName = ZONE_TABLE
    error, mensaje, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(capa, path, QgsProject.instance().transformContext(), opciones)
    if error != QgsVectorFileWriter.WriterError.NoError:  #Comparación explícita (en PyQt6 los enum siempre valen True)
        raise ZoneError(f"No se pudo guardar la zona de trabajo: {mensaje}")
    if os.path.isfile(ZONE_STYLE):
        shutil.copy2(ZONE_STYLE, style_path(path))  #El estilo viaja con la zona (lo usan las exportaciones)
    return path


def zone_uri(path):
    """Fuente de la zona para los algoritmos de Processing."""
    return f"{path}|layername={ZONE_TABLE}"


def view_extent(geometry, crs, target_crs, margin=0.05):
    """Extensión de la zona en el SRC del proyecto, con un pequeño margen: será la vista inicial al abrirlo."""
    rectangulo = _transform(geometry, crs, target_crs).boundingBox()
    rectangulo.grow(max(rectangulo.width(), rectangulo.height()) * margin)
    return QgsReferencedRectangle(rectangulo, target_crs)
