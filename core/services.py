"""
Servicios web (WMS, WMTS, WFS): catálogo del plugin (services.json), favoritos del usuario y conexiones de QGIS.

- Catálogo: services.json en la carpeta del plugin, organizado en grupos (Estatal, comunidades...).
- Favoritos: capas que el usuario marca con la estrella; se guardan en su perfil de QGIS (favoritos.json).
- Conexiones de QGIS: las que el usuario tiene en el Administrador de fuentes de datos (se leen, no se modifican).
"""

import json
import os
from dataclasses import asdict, dataclass, field

# services.json está en la carpeta principal del plugin (junto a metadata.txt)
SERVICES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'services.json')
WMS, WMTS, WFS = 'wms', 'wmts', 'wfs'
PREFERRED_CRS = ('EPSG:25830', 'EPSG:3857', 'EPSG:4326', 'EPSG:4258')  #SRC preferidos para pedir imágenes WMS


class ServicesError(Exception):
    """Error al leer services.json o favoritos.json (el mensaje indica dónde está el problema)."""


@dataclass
class Service:
    """Una capa de un servicio web (o un servicio entero si layer está vacío: sus capas se consultan al desplegarlo)."""

    name: str  #Nombre que se ve en el árbol y en el proyecto
    url: str  #Dirección del servicio (sin ?SERVICE=...)
    layer: str = ''  #Nombre técnico de la capa dentro del servicio ('' = servicio completo, se despliega)
    type: str = WMS  #wms, wmts o wfs
    crs: str = ''  #SRC en el que se pide (vacío = se elige según el proyecto y lo que admita el servidor)
    format: str = 'image/png'
    style: str = ''
    tilematrixset: str = ''  #Solo WMTS
    authcfg: str = ''  #Autenticación guardada en QGIS (solo conexiones del usuario)
    crs_list: list = field(default_factory=list)  #SRC que admite la capa (de GetCapabilities)

    def key(self):
        """Identificador único de la capa (para favoritos y para no añadirla dos veces)."""
        return f"{self.type}|{self.url.rstrip('/?')}|{self.layer}".lower()

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v not in ('', [], None)}

    @classmethod
    def from_dict(cls, data):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def choose_crs(self, project_crs=''):
        """SRC con el que pedir la capa: el fijado, el del proyecto si el servidor lo admite, o uno habitual."""
        if self.crs:
            return self.crs
        if project_crs and (not self.crs_list or project_crs in self.crs_list):
            return project_crs
        return next((c for c in PREFERRED_CRS if c in self.crs_list), self.crs_list[0] if self.crs_list else 'EPSG:3857')

    def uri(self, project_crs=''):
        """Cadena de conexión que QGIS necesita para cargar la capa."""
        auth = f"&authcfg={self.authcfg}" if self.authcfg else ''
        if self.type == WFS:
            auth_wfs = f" authcfg='{self.authcfg}'" if self.authcfg else ''
            return (f"pagingEnabled='true' restrictToRequestBBOX='1' srsname='{self.choose_crs(project_crs)}' "
                    f"typename='{self.layer}' url='{self.url}' version='auto'{auth_wfs}")  #restrictToRequestBBOX: pide solo lo visible
        if self.type == WMTS:
            crs = self.crs or ('EPSG:3857' if 'google' in self.tilematrixset.lower() or '3857' in self.tilematrixset else self.tilematrixset)
            return (f"contextualWMSLegend=0&crs={crs}&dpiMode=7&format={self.format}&layers={self.layer}"
                    f"&styles={self.style or 'default'}&tileMatrixSet={self.tilematrixset}&url={self.url}{auth}")  #QGIS añade él la petición GetCapabilities
        return f"crs={self.choose_crs(project_crs)}&dpiMode=7&format={self.format}&layers={self.layer}&styles={self.style}&url={self.url}{auth}"

    def provider(self):
        return 'WFS' if self.type == WFS else 'wms'  #WMTS también se carga con el proveedor "wms" de QGIS


def capabilities_url(url, service_type):
    """URL de la petición GetCapabilities del servicio."""
    if 'request=getcapabilities' in url.lower():
        return url
    sep = '&' if '?' in url else '?'
    return f"{url}{sep}SERVICE={service_type.upper()}&REQUEST=GetCapabilities"


def guess_type(url, default=WMS):
    """Tipo de servicio a partir de la URL (las conexiones WMS de QGIS también incluyen WMTS)."""
    return WMTS if 'wmts' in url.lower() else default


# ---------------------------------------------------------------- Catálogo (services.json)

def load_catalog(path=SERVICES_FILE):
    """
    Lee services.json y devuelve una lista de (nombre de grupo, [Service]) en el orden del fichero.
    Admite el formato con grupos {"grupos": [{"nombre": ..., "servicios": [...]}]}
    y el formato antiguo {"wms": [...]} (todo en un grupo "Servicios").
    """
    data = _read_json(path, "services.json")
    grupos = data.get('grupos')
    if grupos is None:
        grupos = [{'nombre': 'Servicios', 'servicios': data.get('wms', [])}]
    resultado = []
    for g, grupo in enumerate(grupos, start=1):
        servicios = []
        for i, item in enumerate(grupo.get('servicios', []), start=1):
            try:
                servicios.append(Service.from_dict(item))
            except TypeError as e:
                raise ServicesError(f"Error en services.json, grupo {g}, servicio {i}: faltan datos "
                                    f"(se necesitan al menos name y url)") from e
        resultado.append((grupo.get('nombre', f'Grupo {g}'), servicios))
    return resultado


def load_services(path=SERVICES_FILE):
    """Todas las capas del catálogo en un diccionario {nombre: Service} (compatibilidad con versiones anteriores)."""
    return {s.name: s for _, servicios in load_catalog(path) for s in servicios}


# ---------------------------------------------------------------- Favoritos (perfil del usuario)

def favorites_path():
    """favoritos.json en la carpeta del perfil de QGIS (se conserva al actualizar el plugin)."""
    from qgis.core import QgsApplication
    return os.path.join(QgsApplication.qgisSettingsDirPath(), 'project_builder', 'favoritos.json')


def load_favorites(path=None):
    path = path or favorites_path()
    if not os.path.isfile(path):
        return []
    return [Service.from_dict(d) for d in _read_json(path, "favoritos.json").get('favoritos', [])]


def save_favorites(favorites, path=None):
    path = path or favorites_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'favoritos': [s.to_dict() for s in favorites]}, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- Conexiones guardadas en QGIS

def qgis_connections():
    """
    Conexiones WMS/WMTS y WFS guardadas en QGIS, como Service sin capa (se despliegan para ver sus capas).
    Solo se leen; el plugin nunca las modifica.
    """
    from qgis.core import QgsOwsConnection
    conexiones = []
    for tipo in ('WMS', 'WFS'):
        try:
            nombres = QgsOwsConnection.connectionList(tipo)
        except Exception:  #Si una versión de QGIS cambia esta API, simplemente no se listan
            continue
        for nombre in nombres:
            uri = QgsOwsConnection(tipo, nombre).uri()
            url = uri.param('url')
            if url:
                servicio_tipo = WFS if tipo == 'WFS' else guess_type(url)
                conexiones.append(Service(nombre, url, type=servicio_tipo, authcfg=uri.authConfigId()))
    return conexiones


def _read_json(path, nombre):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise ServicesError(f"No se encuentra el fichero {nombre}: {path}") from e
    except json.JSONDecodeError as e:
        raise ServicesError(f"Error en {nombre}, línea {e.lineno}, columna {e.colno}: {e.msg}") from e
