"""
Iconos de los estilos (mejora 4.8): SVG e imágenes que usan las capas, copiados a la carpeta del proyecto.

Un estilo (.qml, el del proyecto abierto o el guardado en una base de datos) solo guarda la RUTA de cada icono: si el
proyecto se lleva a otro ordenador, los iconos desaparecen. Aquí se buscan los iconos que usan los símbolos de cada capa
(marcadores y rellenos SVG, marcadores y rellenos de imagen), se copian a <proyecto>/iconos/ y el símbolo pasa a apuntar
a la copia. Como el proyecto guarda rutas relativas, la carpeta del proyecto queda autónoma.
Los iconos que trae QGIS de serie no se copian (están en cualquier instalación).
"""

import filecmp
import os
import shutil

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsRasterFillSymbolLayer,
    QgsRasterMarkerSymbolLayer,
    QgsRenderContext,
    QgsSvgMarkerSymbolLayer,
    QgsSVGFillSymbolLayer,
    QgsSymbolLayerUtils,
    QgsVectorLayer,
)

ICONS_FOLDER = 'iconos'


def _accessors(symbol_layer):
    """(leer, escribir, es_svg) de la ruta de imagen de un nivel de símbolo, o None si no usa imagen."""
    if isinstance(symbol_layer, (QgsSvgMarkerSymbolLayer, QgsRasterMarkerSymbolLayer)):
        return symbol_layer.path, symbol_layer.setPath, isinstance(symbol_layer, QgsSvgMarkerSymbolLayer)
    if isinstance(symbol_layer, QgsSVGFillSymbolLayer):
        return symbol_layer.svgFilePath, symbol_layer.setSvgFilePath, True
    if isinstance(symbol_layer, QgsRasterFillSymbolLayer):
        return symbol_layer.imageFilePath, symbol_layer.setImageFilePath, False
    return None


def _symbol_layers(symbol):
    """Todos los niveles de un símbolo, incluidos los de sus subsímbolos (p. ej. el marcador de una línea de marcadores)."""
    for nivel in symbol.symbolLayers():
        yield nivel
        sub = nivel.subSymbol()
        if sub is not None:
            yield from _symbol_layers(sub)


def _builtin_dirs():
    """Carpetas de SVG de la propia instalación de QGIS (lo que hay ahí no se copia)."""
    raices = [QgsApplication.pkgDataPath(), QgsApplication.prefixPath()]
    return [os.path.normcase(os.path.abspath(r)) for r in raices if r]


def _resolve(ruta, es_svg, resolver):
    """Ruta absoluta del icono (None si no existe). Un SVG puede venir solo por su nombre (carpetas de SVG de QGIS)."""
    if not ruta or ruta.startswith(('base64:', 'http://', 'https://')):
        return None
    candidatos = [ruta]
    if es_svg:
        candidatos.append(QgsSymbolLayerUtils.svgSymbolNameToPath(ruta, resolver))
    for candidato in candidatos:
        if candidato and os.path.isfile(candidato):
            return os.path.abspath(candidato)
    return None


def _unique_target(carpeta, origen, copiados):
    """Destino del icono en iconos/: mismo nombre; si ya hay otro distinto con ese nombre, nombre_2, nombre_3..."""
    base, ext = os.path.splitext(os.path.basename(origen))
    n, nombre = 2, os.path.basename(origen)
    while True:
        destino = os.path.join(carpeta, nombre)
        if not os.path.exists(destino) or filecmp.cmp(origen, destino, shallow=False):
            return destino
        nombre = f"{base}_{n}{ext}"
        n += 1


def localize(project, project_folder, layers=None):
    """
    Copia a <project_folder>/iconos/ los iconos que usan las capas (todas las del proyecto si layers es None)
    y hace que los símbolos apunten a la copia. Devuelve (capas cambiadas, [(capa, icono que no se encuentra)]).
    """
    carpeta = os.path.join(project_folder, ICONS_FOLDER)
    internas = _builtin_dirs()
    resolver = QgsProject.instance().pathResolver()
    copiados, cambiadas, faltan = {}, [], []
    for capa in (layers if layers is not None else project.mapLayers().values()):
        if not isinstance(capa, QgsVectorLayer) or capa.renderer() is None:
            continue
        cambiada = False
        for simbolo in capa.renderer().symbols(QgsRenderContext()):
            for nivel in _symbol_layers(simbolo):
                acceso = _accessors(nivel)
                if acceso is None:
                    continue
                leer, escribir, es_svg = acceso
                ruta = leer()
                origen = _resolve(ruta, es_svg, resolver)
                if origen is None:
                    if ruta and not ruta.startswith(('base64:', 'http://', 'https://')):
                        faltan.append((capa.name(), os.path.basename(ruta)))
                    continue
                if any(os.path.normcase(origen).startswith(d + os.sep) for d in internas):
                    continue  #Icono de serie de QGIS
                clave = os.path.normcase(origen)
                if clave not in copiados:
                    os.makedirs(carpeta, exist_ok=True)
                    destino = _unique_target(carpeta, origen, copiados)
                    if not os.path.exists(destino):
                        shutil.copy2(origen, destino)
                    copiados[clave] = destino
                if os.path.normcase(os.path.abspath(ruta)) != os.path.normcase(copiados[clave]):
                    escribir(copiados[clave].replace('\\', '/'))
                    cambiada = True
        if cambiada:
            capa.triggerRepaint()
            cambiadas.append(capa)
    return cambiadas, sorted(set(faltan))
