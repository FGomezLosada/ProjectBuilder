"""
Capas del proyecto abierto en QGIS como origen (mejora 4.10).

Cada capa se trata de una de estas dos formas:
- COPIAR: capas de fichero o de base de datos (Shapefile, GeoPackage, PostGIS, capas temporales...).
  Se copian al proyecto nuevo como las de las carpetas (formato de salida, reproyección, zona de trabajo).
- ENLAZAR: servicios web (WMS/WMTS/XYZ, WFS, ArcGIS...) y otros tipos (malla, nube de puntos, teselas vectoriales).
  No hay datos que copiar: se añade al proyecto nuevo una copia de la capa que apunta a la misma fuente.
En los dos casos se conserva el estilo que la capa tiene en el proyecto abierto.
"""

import os
import re

from qgis.core import (
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsProcessingUtils,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsVectorFileWriter,
    QgsVectorLayer,
)

from .formats import vector_sublayers

COPY, LINK = 'copiar', 'enlazar'
WEB_VECTOR = {'WFS', 'OAPIF', 'arcgisfeatureserver'}  #Proveedores vectoriales de servicios web


def safe_name(text):
    """Nombre válido para un fichero, una carpeta o una tabla: quita los caracteres que Windows no admite."""
    return re.sub(r'[\\/:*?"<>|]+', '_', text).strip(' .') or 'capa'


def tree(project=None):
    """
    Árbol de capas del proyecto como lista anidada:
    [('grupo', nombre, expandido, [hijos...]), ('capa', capa), ...] (mismo orden que el panel de capas de QGIS).
    """
    project = project or QgsProject.instance()

    def recorrer(nodo):
        hijos = []
        for hijo in nodo.children():
            if isinstance(hijo, QgsLayerTreeGroup):
                hijos.append(('grupo', hijo.name(), hijo.isExpanded(), recorrer(hijo)))
            elif isinstance(hijo, QgsLayerTreeLayer) and hijo.layer() is not None:
                hijos.append(('capa', hijo.layer()))
        return hijos

    return recorrer(project.layerTreeRoot())


def _decoded(layer):
    return QgsProviderRegistry.instance().decodeUri(layer.providerType(), layer.source())


def file_path(layer):
    """Fichero de la capa (o '' si no es una capa de fichero)."""
    ruta = _decoded(layer).get('path') or ''
    return ruta if os.path.isfile(ruta) else ''


def how(layer):
    """COPY o LINK según el tipo de capa (ver arriba)."""
    if isinstance(layer, QgsVectorLayer):
        return LINK if layer.providerType() in WEB_VECTOR else COPY
    if isinstance(layer, QgsRasterLayer):
        return COPY if layer.providerType() == 'gdal' and file_path(layer) else LINK
    return LINK


def save_style(layer):
    """Guarda el estilo actual de la capa en un .qml temporal y devuelve su ruta (o None si no se puede)."""
    ruta = QgsProcessingUtils.generateTempFilename(safe_name(layer.name()) + '.qml')
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    _, ok = layer.saveNamedStyle(ruta)
    return ruta if ok and os.path.isfile(ruta) else None


def prepare_copy(layer):
    """
    Fuente desde la que exportar una capa a COPIAR: (fichero, nombre de la capa dentro del fichero o None).
    - Capa de fichero sin filtro: se exporta directamente desde su fichero (rápido, sirve para capas grandes).
    - Capa temporal, de base de datos, con filtro, etc.: se guarda antes en un GeoPackage temporal
      (así se respeta el filtro y se puede exportar en segundo plano).
    """
    ruta = file_path(layer)
    if isinstance(layer, QgsRasterLayer):
        return ruta, None
    if layer.providerType() == 'ogr' and ruta and not layer.subsetString():
        nombre = _decoded(layer).get('layerName')
        if not nombre:
            subcapas = vector_sublayers(ruta)
            nombre = subcapas[0].name() if subcapas else None
        return ruta, nombre
    nombre = safe_name(layer.name())
    temporal = QgsProcessingUtils.generateTempFilename(nombre + '.gpkg')
    os.makedirs(os.path.dirname(temporal), exist_ok=True)
    opciones = QgsVectorFileWriter.SaveVectorOptions()
    opciones.driverName = 'GPKG'
    opciones.layerName = nombre
    error, mensaje, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(layer, temporal, QgsProject.instance().transformContext(),
                                                                     opciones)
    if error != QgsVectorFileWriter.WriterError.NoError:  #Comparación explícita (en PyQt6 los enum siempre valen True)
        raise OSError(f"No se pudo leer la capa {layer.name()}: {mensaje}")
    return temporal, nombre
