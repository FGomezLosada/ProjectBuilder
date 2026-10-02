"""
Composiciones de impresión (mejora 4.5): copiar al proyecto nuevo composiciones del proyecto abierto en QGIS
o de plantillas .qpt (de cualquier carpeta o de la carpeta de plantillas del perfil de QGIS).

Los mapas de cada composición pasan a mostrar las capas del proyecto nuevo, en su SRC, centrados en la zona
de trabajo (o en todas las capas). Los textos del cajetín pueden usar expresiones de QGIS como
[% @project_title %], que se rellenan solas porque el título del proyecto es su nombre.
"""

import os

from qgis.core import (
    QgsApplication,
    QgsCoordinateTransform,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsPrintLayout,
    QgsProcessingUtils,
    QgsReadWriteContext,
    QgsRectangle,
)
from qgis.PyQt.QtXml import QDomDocument


class LayoutError(Exception):
    """Error al leer o añadir una composición (el mensaje se muestra al usuario)."""


def qgis_templates_dir():
    """Carpeta de plantillas de composición del perfil de QGIS (Diseñador → Guardar como plantilla)."""
    return os.path.join(QgsApplication.qgisSettingsDirPath(), 'composer_templates')


def qgis_templates():
    """Plantillas .qpt de la carpeta del perfil de QGIS, por orden alfabético."""
    carpeta = qgis_templates_dir()
    if not os.path.isdir(carpeta):
        return []
    return sorted((os.path.join(carpeta, f) for f in os.listdir(carpeta) if f.lower().endswith('.qpt')),
                  key=lambda r: os.path.basename(r).lower())


def project_layouts(project):
    """Nombres de las composiciones de impresión de un proyecto (p. ej. el que está abierto en QGIS)."""
    return sorted((l.name() for l in project.layoutManager().printLayouts()), key=str.lower)


def snapshot_layout(project, name):
    """
    Guarda una composición del proyecto abierto como plantilla .qpt temporal y devuelve su ruta.
    Se hace al pulsar Crear: así se copia tal como está en ese momento, aunque luego se cambie de proyecto.
    """
    layout = project.layoutManager().layoutByName(name)
    if layout is None:
        raise LayoutError(f"La composición «{name}» ya no está en el proyecto abierto")
    ruta = QgsProcessingUtils.generateTempFilename(f"{name}.qpt")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    if not layout.saveAsTemplate(ruta, QgsReadWriteContext()):
        raise LayoutError(f"No se pudo copiar la composición «{name}»")
    return ruta


def _read_template(path):
    try:
        with open(path, 'rb') as f:
            contenido = f.read()
    except OSError as e:
        raise LayoutError(f"No se puede leer la plantilla {path}: {e}") from e
    documento = QDomDocument()
    documento.setContent(contenido)  #En Qt6 devuelve un objeto y en Qt5 una tupla: se comprueba el resultado abajo
    if documento.documentElement().isNull() or documento.documentElement().tagName() != 'Layout':
        raise LayoutError(f"{os.path.basename(path)} no es una plantilla de composición de QGIS (.qpt)")
    return documento


def _unique_name(project, name):
    usados = {l.name().lower() for l in project.layoutManager().layouts()}
    candidato, n = name, 2
    while candidato.lower() in usados:
        candidato = f"{name} ({n})"
        n += 1
    return candidato


def layers_extent(project, layers):
    """Extensión conjunta de las capas, en el SRC del proyecto (para centrar los mapas si no hay zona de trabajo)."""
    total = QgsRectangle()
    for capa in layers:
        if not capa.isValid() or capa.extent().isEmpty():
            continue
        extension = QgsCoordinateTransform(capa.crs(), project.crs(), project).transformBoundingBox(capa.extent())
        if total.isNull():
            total = QgsRectangle(extension)
        else:
            total.combineExtentWith(extension)
    return total


def add_layout(project, path, name=None, extent=None):
    """
    Añade al proyecto la composición de la plantilla path. extent: rectángulo (en el SRC del proyecto) en el que
    se centran los mapas; None = se deja el de la plantilla. Devuelve la composición añadida.
    """
    documento = _read_template(path)
    layout = QgsPrintLayout(project)
    _, ok = layout.loadFromTemplate(documento, QgsReadWriteContext(), True)
    if not ok:
        raise LayoutError(f"No se pudo cargar la plantilla {os.path.basename(path)}")
    layout.setName(_unique_name(project, name or os.path.splitext(os.path.basename(path))[0]))
    for item in layout.items():
        if isinstance(item, QgsLayoutItemMap):
            item.setFollowVisibilityPreset(False)
            item.setKeepLayerSet(False)  #El mapa muestra las capas del proyecto nuevo (no las de la plantilla)
            item.setLayers([])
            item.setCrs(project.crs())
            if extent is not None and not extent.isEmpty():
                item.zoomToExtent(extent)  #Ajusta la escala para que quepa la zona, sin deformar el mapa
        elif isinstance(item, QgsLayoutItemLegend):
            item.setAutoUpdateModel(True)  #La leyenda se rellena con las capas del proyecto nuevo
    if not project.layoutManager().addLayout(layout):
        raise LayoutError(f"No se pudo añadir la composición «{layout.name()}»")
    return layout
