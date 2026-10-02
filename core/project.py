"""Construcción del proyecto de QGIS (.qgz): capas, grupos y servicios."""

import os

from qgis.core import (
    Qgis,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)

from .formats import MULTILAYER, RASTER, VECTOR, extension, layer_kind, style_path, vector_sublayers


def create_project(folder, name, crs):
    """
    Crea un proyecto nuevo (en memoria) que se guardará en folder/name.qgz.
    Se fija la ruta desde el principio para que las capas se guarden con rutas relativas.
    """
    project = QgsProject()
    project.setFileName(os.path.join(folder, name + '.qgz'))  #.qgz: formato recomendado (zip con el .qgs y sus datos auxiliares)
    project.setFilePathStorage(Qgis.FilePathType.Relative)  #Rutas relativas: el proyecto funciona aunque se mueva la carpeta completa
    project.setCrs(crs)
    project.setTitle(name)  #Título = nombre: los textos con [% @project_title %] de las composiciones se rellenan solos
    return project


def save_project(project):
    """Guarda el proyecto en su ruta (una sola vez, al final). Devuelve la ruta del fichero."""
    if not project.write():
        raise OSError(f"No se pudo guardar el proyecto: {project.error()}")
    return project.fileName()


def _add_to_tree(parent, layer, position=-1):
    """Añade una capa al árbol de capas: sin expandir y no visible."""
    node = QgsLayerTreeLayer(layer)
    parent.insertChildNode(position, node)  #El índice indica la posición en el árbol (0 = arriba, -1 = abajo)
    node.setExpanded(False)  #La capa aparece sin expandir
    node.setItemVisibilityChecked(False)  #La capa aparece no visible


def group_for(project, path):
    """
    Devuelve el grupo del árbol de capas indicado por path (p. ej. ('vectorial', 'subcarpeta')),
    creando los que falten. Así el proyecto refleja la organización de las carpetas de origen.
    """
    group = project.layerTreeRoot()
    for name in path:
        child = next((c for c in group.children() if isinstance(c, QgsLayerTreeGroup) and c.name() == name), None)
        if child is None:
            child = group.addGroup(name)
            child.setExpanded(True)
        group = child
    return group


def _apply_style(layer, qml, save_in_geopackage=False):
    """Aplica un .qml; si la capa está en un GeoPackage, guarda además el estilo dentro como estilo por defecto."""
    if not qml or not os.path.isfile(qml):
        return
    layer.loadNamedStyle(qml)
    if save_in_geopackage:
        try:  # noqa: SIM105 (más legible así)
            layer.saveStyleToDatabase("default", "ProjectBuilder", True, "")  #Al abrir el GeoPackage en otro proyecto, sale con su estilo
        except Exception:
            pass  #Si no se puede guardar dentro, el estilo sigue guardado en el proyecto


def add_layer(project, path, group_path=(), qml=None, name=None):
    """
    Añade al proyecto la capa (o capas, si el fichero tiene varias) del fichero path, dentro del grupo group_path.
    Si el fichero tiene una sola capa y hay un .qml con el mismo nombre, se aplica su estilo
    (o el estilo qml indicado: el que tenía la capa en el proyecto abierto en QGIS). name: nombre de la capa (si tiene una).
    Devuelve la lista de capas añadidas.
    """
    name = os.path.splitext(os.path.basename(path))[0]
    kind = layer_kind(path)
    if kind == RASTER:
        layers = [QgsRasterLayer(path, name)]
    elif kind in (VECTOR, MULTILAYER):
        sublayers = vector_sublayers(path)
        if len(sublayers) == 1 and extension(path) != '.gpkg':  #Una sola capa: se usa el nombre del fichero (en GeoPackage, el de la tabla)
            layers = [QgsVectorLayer(sublayers[0].uri(), name, 'ogr')]
        else:
            layers = [QgsVectorLayer(s.uri(), s.name(), 'ogr') for s in sublayers]
        if extension(path) == '.shp':
            layers[0].setProviderEncoding('UTF-8')
    else:
        raise ValueError(f"Error en la capa {name}: no se reconoce el tipo")

    group = group_for(project, group_path)
    for layer in layers:
        if not layer.isValid():
            raise ValueError(f"La capa {layer.name()} no es válida")
        if len(layers) == 1:  #El .qml es de una capa: solo se aplica si el fichero tiene una
            _apply_style(layer, qml or style_path(path))
            if name:
                layer.setName(name)
        project.addMapLayer(layer, False)  #Se añade al proyecto pero no aparece en el árbol (lo colocamos nosotros)
        _add_to_tree(group, layer)
    return layers


def add_geopackage_tables(project, gpkg, tables, group_path=(), qml=None):
    """Añade tablas del GeoPackage común del proyecto. qml: estilo de origen (si la capa venía de un fichero de una sola capa)."""
    group = group_for(project, group_path)
    added = []
    for table in tables:
        layer = QgsVectorLayer(f"{gpkg}|layername={table}", table, 'ogr')
        if not layer.isValid():
            raise ValueError(f"La capa {table} no es válida")
        _apply_style(layer, qml, save_in_geopackage=True)
        project.addMapLayer(layer, False)
        _add_to_tree(group, layer)
        added.append(layer)
    return added


def add_group(project, group_name):
    """Crea un grupo en el árbol de capas (sin expandir y no visible)."""
    group = project.layerTreeRoot().addGroup(group_name)
    group.setIsMutuallyExclusive(False)  #True (permite activar una sola capa), False (permite activar varias capas a la vez)
    group.setExpanded(False)
    group.setItemVisibilityChecked(False)
    return group


def add_service(project, group, service):
    """
    Añade una capa de un servicio web (WMS, WMTS o WFS) al grupo indicado.
    Se añade al final (-1) para que el orden sea el mismo que en la lista de servicios.
    """
    uri = service.uri(project.crs().authid())
    if service.provider() == 'WFS':
        layer = QgsVectorLayer(uri, service.name, 'WFS')
    else:
        layer = QgsRasterLayer(uri, service.name, 'wms')
    if not layer.isValid():
        raise ValueError(f"El servicio {service.name} no se ha podido cargar")
    project.addMapLayer(layer, False)
    _add_to_tree(group, layer, position=-1)
    return layer


def set_view_extent(project, extent):
    """Vista inicial del proyecto (QgsReferencedRectangle): al abrirlo, el mapa aparece centrado en la zona de trabajo."""
    project.viewSettings().setDefaultViewExtent(extent)


def put_on_top(project, layers):
    """
    Lleva las capas a lo alto del árbol de capas y las deja visibles (se usa con la zona de trabajo,
    para que al abrir el proyecto se vea el contorno de la zona por encima de todo).
    """
    root = project.layerTreeRoot()
    for layer in reversed(layers):
        node = root.findLayer(layer.id())
        if node is None:
            continue
        copia = node.clone()
        copia.setItemVisibilityChecked(True)
        root.insertChildNode(0, copia)
        node.parent().removeChildNode(node)


def add_linked_layer(project, layer, group_path=()):
    """
    Añade una capa que no se copia (servicio web, malla, nube de puntos...): una copia de la capa del proyecto abierto,
    con su misma fuente y su estilo. layer debe ser ya una copia (layer.clone()) que no pertenezca a ningún proyecto.
    """
    if not layer.isValid():
        raise ValueError(f"La capa {layer.name()} no se ha podido cargar")
    project.addMapLayer(layer, False)
    _add_to_tree(group_for(project, group_path), layer)
    return layer

