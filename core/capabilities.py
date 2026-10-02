"""
Lectura de la respuesta GetCapabilities de un servicio WMS, WMTS o WFS (sin interfaz ni red).

Recibe el XML que devuelve el servidor y devuelve la lista de capas que ofrece, con lo necesario
para cargarlas en QGIS. Al ser Python puro se puede probar sin QGIS.
"""

from xml.etree import ElementTree as ET


def _tag(el):
    return el.tag.split('}')[-1]  #Nombre de la etiqueta sin el espacio de nombres (wms:Layer -> Layer)


def _child_text(el, *names):
    for c in el:
        if _tag(c) in names and (c.text or '').strip():
            return c.text.strip()
    return ''


def _children(el, name):
    return [c for c in el if _tag(c) == name]


def detect_type(data, default='wms'):
    """Tipo de servicio según la respuesta (una conexión "WMS" de QGIS puede ser en realidad WMTS)."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return default
    tag = _tag(root)
    if tag == 'WFS_Capabilities':
        return 'wfs'
    if tag == 'Capabilities' and any(_tag(c) == 'Contents' for c in root):
        return 'wmts'
    if tag in ('WMS_Capabilities', 'WMT_MS_Capabilities'):
        return 'wms'
    return default


def parse_capabilities(data, service_type):
    """
    Devuelve una lista de diccionarios {'layer', 'title', 'crs', 'format', 'style', 'tilematrixset'}.
    service_type: 'wms', 'wmts' o 'wfs'. Lanza ValueError si el XML no es válido o es un error del servidor.
    """
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError(f"La respuesta del servidor no es XML válido: {e}") from e
    if _tag(root) in ('ServiceExceptionReport', 'ExceptionReport'):
        raise ValueError("El servidor ha devuelto un error: " + ' '.join(t.strip() for t in root.itertext() if t.strip())[:200])
    if service_type == 'wfs':
        return _parse_wfs(root)
    if service_type == 'wmts':
        return _parse_wmts(root)
    return _parse_wms(root)


def _parse_wms(root):
    capas = []

    def recorrer(layer, crs_heredados, formato):
        crs = crs_heredados + [c.text.strip() for c in layer if _tag(c) in ('CRS', 'SRS') and c.text]
        nombre = _child_text(layer, 'Name')
        if nombre:  #Las capas sin nombre son solo "carpetas" del servicio: no se pueden pedir
            capas.append({'layer': nombre, 'title': _child_text(layer, 'Title') or nombre,
                          'crs': crs, 'format': formato, 'style': '', 'tilematrixset': ''})
        for hija in _children(layer, 'Layer'):
            recorrer(hija, crs, formato)

    formatos = [f.text for f in root.iter() if _tag(f) == 'Format' and f.text and f.text.startswith('image/')]
    formato = 'image/png' if 'image/png' in formatos else (formatos[0] if formatos else 'image/png')
    for capability in root.iter():
        if _tag(capability) == 'Capability':
            for layer in _children(capability, 'Layer'):
                recorrer(layer, [], formato)
            break
    return capas


def _parse_wmts(root):
    capas = []
    for contents in root.iter():
        if _tag(contents) != 'Contents':
            continue
        for layer in _children(contents, 'Layer'):
            formatos = [c.text for c in layer if _tag(c) == 'Format' and c.text]
            estilos = [_child_text(s, 'Identifier') for s in _children(layer, 'Style')]
            matrices = [_child_text(link, 'TileMatrixSet') for link in _children(layer, 'TileMatrixSetLink')]
            capas.append({'layer': _child_text(layer, 'Identifier'), 'title': _child_text(layer, 'Title') or _child_text(layer, 'Identifier'),
                          'crs': [], 'format': 'image/png' if 'image/png' in formatos else (formatos[0] if formatos else 'image/png'),
                          'style': estilos[0] if estilos else 'default',
                          'tilematrixset': next((m for m in matrices if 'Google' in m or '3857' in m), matrices[0] if matrices else '')})
        break
    return capas


def _parse_wfs(root):
    capas = []
    for ft in root.iter():
        if _tag(ft) == 'FeatureType':
            nombre = _child_text(ft, 'Name')
            if nombre:
                crs = _child_text(ft, 'DefaultCRS', 'DefaultSRS', 'SRS')
                capas.append({'layer': nombre, 'title': _child_text(ft, 'Title') or nombre,
                              'crs': [crs] if crs else [], 'format': '', 'style': '', 'tilematrixset': ''})
    return capas
