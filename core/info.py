"""
Información rápida de una capa para mostrarla al pasar el ratón por el árbol (V4) y su extensión para «Ver en el mapa» (V5).

Todo se lee de la cabecera de los ficheros, sin recorrer los datos, para que el panel no se quede parado.
Los formatos de texto muy grandes (GeoJSON, KML...) no se abren: habría que leerlos enteros.
"""

import os

from qgis.core import (
    QgsCoordinateTransform,
    QgsCsException,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .formats import RASTER_EXTENSIONS, extension

# Ficheros que acompañan a una capa y forman parte de ella (cuentan en su tamaño)
SIDECARS = {
    '.shp': ('.shx', '.dbf', '.prj', '.cpg', '.qix', '.sbn', '.sbx', '.shp.xml'),
    '.tab': ('.dat', '.id', '.map', '.ind'),
    '.mif': ('.mid',),
    '.asc': ('.prj',),
    '.tif': ('.tfw', '.tif.aux.xml'),
    '.tiff': ('.tfw', '.tiff.aux.xml'),
    '.jpg': ('.jgw', '.jpg.aux.xml'),
    '.png': ('.pgw', '.png.aux.xml'),
}
# Formatos que hay que leer enteros para abrirlos: por encima de este tamaño no se abren al pasar el ratón
SLOW_EXTENSIONS = ('.geojson', '.json', '.kml', '.gml', '.dxf', '.gpx', '.mif')
SLOW_LIMIT = 20 * 1024 * 1024


def human_size(nbytes):
    """Tamaño legible con coma decimal: 850 B, 12,4 KB, 3,1 MB, 1,2 GB."""
    if nbytes < 1024:
        return f"{nbytes} B"
    for unidad in ('KB', 'MB', 'GB', 'TB'):
        nbytes /= 1024
        if nbytes < 1024 or unidad == 'TB':
            return f"{nbytes:.1f} {unidad}".replace('.', ',')
    return ''


def companions(path):
    """El fichero y los que lo acompañan (.shx, .dbf, .prj... de un shapefile) que existen de verdad."""
    base, ext = os.path.splitext(path)
    ficheros = [path]
    for extra in SIDECARS.get(ext.lower(), ()):
        candidato = base + extra if not extra.startswith(ext.lower()) else path + extra[len(ext):]
        for variante in (candidato, base + extra.upper()):
            if os.path.isfile(variante) and variante not in ficheros:
                ficheros.append(variante)
                break
    return ficheros


def file_size(path):
    """Tamaño en bytes de una capa (con sus ficheros acompañantes) o de todo lo que hay en una carpeta."""
    if os.path.isdir(path):
        total = 0
        for carpeta, _subcarpetas, ficheros in os.walk(path):
            for f in ficheros:
                try:
                    total += os.path.getsize(os.path.join(carpeta, f))
                except OSError:
                    pass
        return total
    total = 0
    for f in companions(path):
        try:
            total += os.path.getsize(f)
        except OSError:
            pass
    return total


def new_files_size(folder, since):
    """
    Lo que ocupan los ficheros de la carpeta (y sus subcarpetas) escritos desde el instante since (time.time()).
    Así se mide solo el proyecto recién creado, aunque se haya creado en una carpeta con otras cosas (Documentos...).
    """
    total = 0
    for carpeta, _subcarpetas, ficheros in os.walk(folder):
        for f in ficheros:
            try:
                estado = os.stat(os.path.join(carpeta, f))
            except OSError:
                continue
            if estado.st_mtime >= since - 2:  #2 s de margen por la precisión de la hora de algunos discos
                total += estado.st_size
    return total


def _crs_text(crs):
    if not crs.isValid():
        return "sin SRC definido"
    return f"{crs.authid()} · {crs.description()}" if crs.authid() else crs.description()


def open_layer(path, layer=None):
    """Abre una capa de fichero (sin añadirla al proyecto). layer: capa interna de un GeoPackage o similar."""
    if extension(path) in RASTER_EXTENSIONS:
        return QgsRasterLayer(path, os.path.basename(path), 'gdal')
    uri = f"{path}|layername={layer}" if layer else path
    return QgsVectorLayer(uri, layer or os.path.basename(path), 'ogr')


def too_slow(path):
    """True si abrir el fichero obligaría a leerlo entero (texto muy grande)."""
    try:
        return extension(path) in SLOW_EXTENSIONS and os.path.getsize(path) > SLOW_LIMIT
    except OSError:
        return False


def layer_lines(capa):
    """Líneas de información de una capa ya abierta: SRC, geometría y elementos, o tamaño en píxeles."""
    if capa is None or not capa.isValid():
        return ["No se puede abrir la capa"]
    lineas = [f"SRC: {_crs_text(capa.crs())}"]
    if isinstance(capa, QgsVectorLayer):
        geometria = QgsWkbTypes.displayString(capa.wkbType()) or "sin geometría"
        n = capa.featureCount()
        elementos = f"{n:,}".replace(',', '.') if n >= 0 else "desconocido"
        lineas.append(f"Geometría: {geometria} · {elementos} elemento{'s' if n != 1 else ''}")
    elif isinstance(capa, QgsRasterLayer):
        bandas = capa.bandCount()
        lineas.append(f"{capa.width():,} × {capa.height():,} píxeles · {bandas} banda{'s' if bandas != 1 else ''}".replace(',', '.'))
        unidades = QgsUnitTypes.toAbbreviatedString(capa.crs().mapUnits()) if capa.crs().isValid() else ''
        lineas.append(f"Tamaño de píxel: {capa.rasterUnitsPerPixelX():.4g} {unidades}".rstrip().replace('.', ','))
    return lineas


def describe_file(path, layer=None, sublayers=None):
    """
    Texto del recuadro de información de un fichero de capas (o de una capa interna de un GeoPackage).
    sublayers: número de capas internas, si es un fichero con varias (no se abre cada una).
    """
    lineas = [path if not layer else f"{path}  ·  capa «{layer}»"]
    if sublayers is not None:
        lineas.append(f"{sublayers} capa{'s' if sublayers != 1 else ''} dentro")
    elif too_slow(path):
        lineas.append("Fichero grande: se ve su contenido al crear el proyecto")
    else:
        lineas += layer_lines(open_layer(path, layer))
    tamano = human_size(file_size(path))
    lineas.append(f"Tamaño del fichero: {tamano}" if layer or sublayers is not None else f"Tamaño: {tamano}")
    return "\n".join(lineas)


def describe_folder(path, layers, nbytes):
    """Texto del recuadro de información de una carpeta: ruta, número de capas que se ven de ella y lo que ocupan."""
    return "\n".join([path, f"{layers} capa{'s' if layers != 1 else ''} · {human_size(nbytes)}"])


def map_extent(capas, destino):
    """
    Rectángulo que ocupan las capas en el SRC destino (el del mapa). Las capas sin SRC se toman tal cual.
    Devuelve None si ninguna tiene extensión (capas vacías o sin geometría).
    """
    total = QgsRectangle()
    total.setNull()
    for capa in capas:
        if capa is None or not capa.isValid():
            continue
        extension_capa = capa.extent()
        if extension_capa.isNull():
            continue
        if capa.crs().isValid() and destino.isValid() and capa.crs() != destino:
            try:
                extension_capa = QgsCoordinateTransform(capa.crs(), destino, QgsProject.instance()).transformBoundingBox(extension_capa)
            except QgsCsException:
                continue
        total.combineExtentWith(extension_capa)
    return None if total.isNull() else total
