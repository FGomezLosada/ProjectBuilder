"""Lectura de los servicios web (WMS) definidos en services.json."""

import json
import os
from dataclasses import dataclass

# services.json está en la carpeta principal del plugin (junto a metadata.txt)
SERVICES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'services.json')


class ServicesError(Exception):
    """Error al leer services.json (el mensaje indica dónde está el problema)."""


@dataclass
class Service:
    name: str  #Nombre que se ve en el desplegable del plugin
    url: str  #Dirección del servicio (sin ?SERVICE=WMS...)
    layer: str  #Nombre técnico de la capa dentro del servicio
    crs: str = 'EPSG:25830'  #SRC en el que se pide la imagen
    format: str = 'image/png'

    def uri(self):
        """Cadena de conexión que QGIS necesita para cargar la capa WMS."""
        return f"crs={self.crs}&dpiMode=7&format={self.format}&layers={self.layer}&styles&url={self.url}"


def load_services(path=SERVICES_FILE):
    """
    Lee los WMS de services.json y los devuelve en un diccionario {nombre: Service},
    en el mismo orden que en el fichero. Lanza ServicesError si el fichero tiene errores.
    """
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise ServicesError(f"No se encuentra el fichero de servicios: {path}") from e
    except json.JSONDecodeError as e:
        raise ServicesError(f"Error en services.json, línea {e.lineno}, columna {e.colno}: {e.msg}") from e

    services = {}
    for i, item in enumerate(data.get('wms', []), start=1):
        try:
            service = Service(**item)
        except TypeError as e:
            raise ServicesError(f"Error en services.json, servicio WMS n.º {i}: faltan datos o hay campos desconocidos "
                                f"(se necesitan name, url, layer y opcionalmente crs y format)") from e
        services[service.name] = service
    return services
