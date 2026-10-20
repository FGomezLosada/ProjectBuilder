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
# Versión más reciente del catálogo, publicada en GitHub: el plugin la descarga (como mucho una vez por semana)
REMOTE_CATALOG_URL = 'https://raw.githubusercontent.com/FGomezLosada/ProjectBuilder/main/services.json'
CHECK_EVERY_DAYS = 7  #Cada cuántos días se comprueban los servicios y se busca un catálogo nuevo
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
    heavy: bool = False  #Servicio pesado (p. ej. WFS de toda España): se avisa en el árbol

    def __post_init__(self):
        """
        Comprueba los datos (pueden venir de un favoritos.json o un services.json editado a mano). Lanza TypeError si falta
        el nombre o la dirección; el resto de valores raros se corrigen (números a texto, vacíos...).
        """
        if not isinstance(self.name, (str, int, float)) or not str(self.name).strip():
            raise TypeError("servicio sin nombre")
        if not isinstance(self.url, str) or not self.url.strip():
            raise TypeError("servicio sin dirección")
        self.name, self.url = str(self.name).strip(), self.url.strip()
        for campo in ('layer', 'type', 'crs', 'format', 'style', 'tilematrixset', 'authcfg'):
            valor = getattr(self, campo)
            setattr(self, campo, '' if valor is None or isinstance(valor, (list, dict, bool)) else str(valor))
        self.type = self.type.lower() if self.type.lower() in (WMS, WMTS, WFS) else WMS
        self.format = self.format or 'image/png'
        self.crs_list = [str(c) for c in self.crs_list] if isinstance(self.crs_list, list) else []
        self.heavy = self.heavy is True

    def key(self):
        """Identificador único de la capa (para favoritos y para no añadirla dos veces)."""
        return f"{self.type}|{self.url.rstrip('/?')}|{self.layer}".lower()

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v not in ('', [], None, False)}

    @classmethod
    def from_dict(cls, data):
        """Service a partir de un diccionario. Lanza TypeError si no es un diccionario o le falta el nombre o la dirección."""
        if not isinstance(data, dict):
            raise TypeError("el servicio no es un diccionario")
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
        if self.type == WFS:
            auth_wfs = f" authcfg='{self.authcfg}'" if self.authcfg else ''
            return (f"pagingEnabled='true' restrictToRequestBBOX='1' srsname='{self.choose_crs(project_crs)}' "
                    f"typename='{self.layer}' url='{self.url}' version='auto'{auth_wfs}")  #restrictToRequestBBOX: pide solo lo visible
        if self.type == WMTS:
            if self.crs:
                crs = self.crs
            elif 'google' in self.tilematrixset.lower() or '3857' in self.tilematrixset:
                crs = 'EPSG:3857'
            else:  #El SRC que declara el servicio para ese conjunto de teselas (su nombre puede no ser un SRC)
                crs = self.crs_list[0] if self.crs_list else self.tilematrixset
            params = [('contextualWMSLegend', '0'), ('crs', crs), ('dpiMode', '7'), ('format', self.format),
                      ('layers', self.layer), ('styles', self.style or 'default'), ('tileMatrixSet', self.tilematrixset),
                      ('url', capabilities_url(self.url, WMTS))]  #En WMTS, QGIS espera la URL completa de GetCapabilities
        else:
            params = [('crs', self.choose_crs(project_crs)), ('dpiMode', '7'), ('format', self.format),
                      ('layers', self.layer), ('styles', self.style), ('url', self.url)]
        if self.authcfg:
            params.append(('authcfg', self.authcfg))
        return _encode(params)

    def provider(self):
        return 'WFS' if self.type == WFS else 'wms'  #WMTS también se carga con el proveedor "wms" de QGIS


def _encode(params):
    """
    Une los parámetros con QgsDataSourceUri, que protege los caracteres especiales de cada valor
    (p. ej. una URL que ya lleva '?a=1&b=2'). Sin QGIS (pruebas fuera de QGIS) se unen tal cual.
    """
    try:
        from qgis.core import QgsDataSourceUri
    except ImportError:
        return '&'.join(f"{k}={v}" for k, v in params)
    uri = QgsDataSourceUri()
    for clave, valor in params:
        uri.setParam(clave, valor)
    return bytes(uri.encodedUri()).decode()


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
    if not isinstance(grupos, list):
        raise ServicesError("El catálogo de servicios (services.json) está dañado: «grupos» debe ser una lista. "
                            "Vuelve a instalar el plugin o espera a la próxima actualización del catálogo")
    resultado = []
    for g, grupo in enumerate(grupos, start=1):
        if not isinstance(grupo, dict):
            raise ServicesError(f"El catálogo de servicios (services.json) está dañado en el grupo {g}. "
                                "Vuelve a instalar el plugin o espera a la próxima actualización del catálogo")
        servicios = []
        for i, item in enumerate(grupo.get('servicios', []), start=1):
            try:
                servicios.append(Service.from_dict(item))
            except (TypeError, AttributeError) as e:
                raise ServicesError(f"El catálogo de servicios (services.json) está dañado: al servicio {i} del grupo {g} "
                                    "le falta el nombre o la dirección (name y url). Vuelve a instalar el plugin o espera "
                                    "a la próxima actualización del catálogo") from e
        resultado.append((grupo.get('nombre', f'Grupo {g}'), servicios))
    return resultado


def catalog_version(path):
    """Versión (fecha AAAA-MM-DD) de un services.json; '' si no tiene o no se puede leer."""
    try:
        return str(_read_json(path, "services.json").get('version', ''))
    except ServicesError:
        return ''


def best_catalog_path():
    """
    El catálogo más reciente: el que trae el plugin o el descargado de GitHub (en el perfil del usuario),
    según su campo "version". Si el descargado está dañado, se usa el del plugin.
    """
    descargado = os.path.join(profile_dir(), 'services_remoto.json')
    if os.path.isfile(descargado) and catalog_version(descargado) > catalog_version(SERVICES_FILE):
        try:
            load_catalog(descargado)  #Solo se usa si se puede leer entero
            return descargado
        except ServicesError:
            pass
    return SERVICES_FILE


def load_services(path=SERVICES_FILE):
    """Todas las capas del catálogo en un diccionario {nombre: Service} (compatibilidad con versiones anteriores)."""
    return {s.name: s for _, servicios in load_catalog(path) for s in servicios}


# ---------------------------------------------------------------- Favoritos (perfil del usuario)

def profile_dir():
    """Carpeta del plugin dentro del perfil de QGIS: lo que se guarda aquí se conserva al actualizar el plugin."""
    from qgis.core import QgsApplication
    return os.path.join(QgsApplication.qgisSettingsDirPath(), 'project_builder')


def favorites_path():
    """favoritos.json en la carpeta del perfil de QGIS."""
    return os.path.join(profile_dir(), 'favoritos.json')


# ---------------------------------------------------------------- Estado de los servicios (comprobación automática)

def health_path():
    """estado_servicios.json: resultado de la última comprobación automática de los servicios."""
    return os.path.join(profile_dir(), 'estado_servicios.json')


def load_health(path=None):
    """
    {'fecha': 'AAAA-MM-DD', 'servicios': {clave: {'ok': bool, 'url': url que funciona, 'detalle': texto}}}
    Si el fichero está dañado o tiene datos raros, se ignora lo que no sirve (se volverá a comprobar).
    """
    path = path or health_path()
    try:
        datos = _read_json(path, "estado_servicios.json") if os.path.isfile(path) else {}
    except ServicesError:
        return {}
    servicios = datos.get('servicios')
    limpio = {}
    for clave, estado in (servicios.items() if isinstance(servicios, dict) else ()):
        if isinstance(clave, str) and isinstance(estado, dict):
            limpio[clave] = {'ok': estado.get('ok') is not False,
                             'url': estado.get('url') if isinstance(estado.get('url'), str) else '',
                             'detalle': str(estado.get('detalle') or '')}
    fecha = datos.get('fecha')
    return {'fecha': fecha if isinstance(fecha, str) else '', 'servicios': limpio}


def save_health(health, path=None):
    path = path or health_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(health, f, ensure_ascii=False, indent=2)


def url_variants(url):
    """
    Direcciones alternativas que se prueban si un servicio no responde, con los cambios más habituales
    de los organismos: pasar a https, quitar la terminación antigua /wms.aspx y la barra final.
    """
    variantes = [url]
    def anadir(u):
        if u and u not in variantes:
            variantes.append(u)
    if url.startswith('http://'):
        anadir('https://' + url[len('http://'):])
    for v in list(variantes):
        base, _, consulta = v.partition('?')
        if base.lower().endswith('/wms.aspx'):
            anadir(base[:-len('/wms.aspx')] + (f'?{consulta}' if consulta else ''))
        if base.endswith('/'):
            anadir(base.rstrip('/') + (f'?{consulta}' if consulta else ''))
    return variantes


def load_favorites(path=None, descartados=None):
    """
    Favoritos guardados. Los que estén dañados (sin nombre o sin dirección...) se saltan y se anotan en descartados
    (si se pasa una lista), para no perder los buenos. Lanza ServicesError si el fichero entero no se puede leer.
    """
    path = path or favorites_path()
    if not os.path.isfile(path):
        return []
    lista = _read_json(path, "favoritos.json").get('favoritos', [])
    if not isinstance(lista, list):
        raise ServicesError("El fichero de favoritos está dañado (no tiene una lista de favoritos): vuelve a añadir tus "
                            "favoritos con ★")
    favoritos = []
    for d in lista:
        try:
            favoritos.append(Service.from_dict(d))
        except (TypeError, AttributeError):
            if descartados is not None:
                descartados.append(d)
    return favoritos


def save_favorites(favorites, path=None):
    """Guarda los favoritos. Lanza ServicesError (con el motivo explicado) si no se puede escribir el fichero."""
    path = path or favorites_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'favoritos': [s.to_dict() for s in favorites]}, f, ensure_ascii=False, indent=2)
    except OSError as e:
        from .mensajes import explicar
        raise ServicesError(f"No se pudieron guardar los favoritos en {path}: {explicar(e)}") from e


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


_REPARAR = {  #Qué hacer si cada fichero está dañado
    'services.json': "Vuelve a instalar el plugin o espera a la próxima actualización del catálogo",
    'favoritos.json': "Vuelve a añadir tus favoritos con ★",
    'estado_servicios.json': "No hace falta hacer nada: se volverá a comprobar",
}


def _read_json(path, nombre):
    try:
        with open(path, encoding='utf-8') as f:
            datos = json.load(f)
    except FileNotFoundError as e:
        raise ServicesError(f"No se encuentra el fichero {nombre} ({path}). Vuelve a instalar el plugin") from e
    except json.JSONDecodeError as e:
        raise ServicesError(f"El fichero {nombre} está dañado (línea {e.lineno}, columna {e.colno}). "
                            f"{_REPARAR.get(nombre, 'Vuelve a instalar el plugin')}") from e
    except (ValueError, OSError) as e:  #Codificación que no es UTF-8, fichero bloqueado...
        from .mensajes import explicar
        raise ServicesError(f"No se puede leer {nombre}: {explicar(e, _REPARAR.get(nombre, 'Vuelve a instalar el plugin'))}") from e
    if not isinstance(datos, dict):
        raise ServicesError(f"El fichero {nombre} está dañado (no tiene el formato esperado). "
                            f"{_REPARAR.get(nombre, 'Vuelve a instalar el plugin')}")
    return datos
