"""Construcción del proyecto de QGIS (.qgz): capas, grupos y servicios."""

import os

from qgis.core import (
    Qgis,
    QgsLayerTreeLayer,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)

from .exporter import vector_sublayers
from .formats import extension, style_path


def create_project(folder, name, crs):
    """
    Crea un proyecto nuevo (en memoria) que se guardará en folder/name.qgz.
    Se fija la ruta desde el principio para que las capas se guarden con rutas relativas.
    """
    project = QgsProject()
    project.setFileName(os.path.join(folder, name + '.qgz'))  #.qgz: formato recomendado (zip con el .qgs y sus datos auxiliares)
    project.setFilePathStorage(Qgis.FilePathType.Relative)  #Rutas relativas: el proyecto funciona aunque se mueva la carpeta completa
    project.setCrs(crs)
    return project


def save_project(project):
    """Guarda el proyecto en su ruta (una sola vez, al final). Devuelve la ruta del fichero."""
    if not project.write():
        raise OSError(f"No se pudo guardar el proyecto: {project.error()}")
    return project.fileName()


def _add_to_tree(parent, layer, position=0):
    """Añade una capa al árbol de capas: sin expandir y no visible."""
    node = QgsLayerTreeLayer(layer)
    parent.insertChildNode(position, node)  #El índice indica la posición en el árbol (0 = arriba, -1 = abajo)
    node.setExpanded(False)  #La capa aparece sin expandir
    node.setItemVisibilityChecked(False)  #La capa aparece no visible


def add_layer(project, path):
    """
    Añade al proyecto la capa (o capas, si es un GeoPackage) del fichero path.
    Si hay un .qml con el mismo nombre se aplica su estilo. Devuelve la lista de capas añadidas.
    """
    ext = extension(path)
    name = os.path.splitext(os.path.basename(path))[0]
    if ext == '.shp':
        layers = [QgsVectorLayer(path, name, 'ogr')]
        layers[0].setProviderEncoding('UTF-8')
    elif ext == '.gpkg':
        layers = [QgsVectorLayer(s.uri(), s.name(), 'ogr') for s in vector_sublayers(path)]
    elif ext == '.tif':
        layers = [QgsRasterLayer(path, name)]
    else:
        raise ValueError(f"Error en la capa {name}: no se reconoce el tipo")

    qml = style_path(path)
    for layer in layers:
        if not layer.isValid():
            raise ValueError(f"La capa {layer.name()} no es válida")
        if ext != '.gpkg' and os.path.isfile(qml):  #Los GeoPackage no usan .qml (pueden guardar el estilo dentro)
            layer.loadNamedStyle(qml)
        project.addMapLayer(layer, False)  #Se añade al proyecto pero no aparece en el árbol (lo colocamos nosotros)
        _add_to_tree(project.layerTreeRoot(), layer)
    return layers


def add_group(project, group_name):
    """Crea un grupo en el árbol de capas (sin expandir y no visible)."""
    group = project.layerTreeRoot().addGroup(group_name)
    group.setIsMutuallyExclusive(False)  #True (permite activar una sola capa), False (permite activar varias capas a la vez)
    group.setExpanded(False)
    group.setItemVisibilityChecked(False)
    return group


def add_wms(project, group, name, uri):
    """
    Añade un servicio WMS al grupo indicado.
    Se añade al final (-1) para que el orden sea el mismo que en la lista de servicios.
    """
    layer = QgsRasterLayer(uri, name, 'wms')
    if not layer.isValid():
        raise ValueError(f"El servicio {name} no se ha podido cargar")
    project.addMapLayer(layer, False)
    _add_to_tree(group, layer, position=-1)
    return layer
