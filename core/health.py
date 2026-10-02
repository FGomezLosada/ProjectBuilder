"""
Comprobación automática de los servicios web (en segundo plano, como mucho una vez por semana).

- Pide GetCapabilities a cada servicio del catálogo y a cada favorito.
- Si un servicio no responde, prueba las direcciones alternativas habituales (https, sin /wms.aspx...).
- Descarga la versión más reciente del catálogo publicada en GitHub.
El panel usa el resultado para desactivar temporalmente los servicios caídos y avisar de los favoritos que fallan.
"""

import concurrent.futures
import datetime
import json

from qgis.core import QgsBlockingNetworkRequest, QgsTask
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from . import services as svc
from .capabilities import detect_type, parse_capabilities

TIMEOUT_MS = 45000  #Algunos servidores (IGME) tardan más de 20 s


def fetch(url, authcfg=''):
    """Descarga una URL con la red de QGIS (respeta proxy y autenticación). Devuelve bytes o lanza OSError."""
    peticion = QNetworkRequest(QUrl(url))
    peticion.setTransferTimeout(TIMEOUT_MS)
    descarga = QgsBlockingNetworkRequest()
    if authcfg:
        descarga.setAuthCfg(authcfg)
    error = descarga.get(peticion, True)
    if error != QgsBlockingNetworkRequest.ErrorCode.NoError:  #Comparación explícita (en PyQt6 los enum valen True en un if)
        raise OSError(descarga.errorMessage() or 'sin respuesta')
    return bytes(descarga.reply().content())


def check_service(servicio, descargar=fetch):
    """
    Comprueba un servicio probando su URL y las alternativas habituales.
    Devuelve {'ok': bool, 'url': url que funciona (o la original), 'detalle': texto}.
    """
    detalle = ''
    for url in svc.url_variants(servicio.url):
        try:
            datos = descargar(svc.capabilities_url(url, servicio.type), servicio.authcfg)
            capas = parse_capabilities(datos, detect_type(datos, servicio.type))
        except (OSError, ValueError) as e:
            detalle = str(e)[:150]
            continue
        if servicio.layer and servicio.layer not in {c['layer'] for c in capas}:
            detalle = f"ya no existe la capa {servicio.layer}"
            continue
        if capas:
            return {'ok': True, 'url': url, 'detalle': '' if url == servicio.url else 'dirección actualizada automáticamente'}
    return {'ok': False, 'url': servicio.url, 'detalle': detalle or 'no responde'}


def check_due(health, dias=svc.CHECK_EVERY_DAYS):
    """True si nunca se ha comprobado o la última comprobación tiene más de 'dias' días."""
    try:
        ultima = datetime.date.fromisoformat(health.get('fecha', ''))
    except ValueError:
        return True
    return (datetime.date.today() - ultima).days >= dias


class HealthTask(QgsTask):
    """Comprueba en segundo plano una lista de servicios y descarga el catálogo de GitHub."""

    def __init__(self, servicios):
        super().__init__("ProjectBuilder: comprobando servicios web", QgsTask.Flag.CanCancel)
        self.servicios = {s.key(): s for s in servicios}  #Sin repetir
        self.resultados = {}
        self.catalogo_remoto = None  #Contenido del services.json de GitHub (bytes), si se ha podido descargar y es válido

    def run(self):
        with concurrent.futures.ThreadPoolExecutor(12) as hilos:  #Varios servidores a la vez
            futuros = {hilos.submit(check_service, s): k for k, s in self.servicios.items()}
            for i, futuro in enumerate(concurrent.futures.as_completed(futuros), start=1):
                if self.isCanceled():
                    return False
                self.resultados[futuros[futuro]] = futuro.result()
                self.setProgress(i * 100 / (len(futuros) + 1))
        try:
            datos = fetch(svc.REMOTE_CATALOG_URL)
            if 'grupos' in json.loads(datos.decode('utf-8')):  #Solo se acepta si tiene la estructura esperada
                self.catalogo_remoto = datos
        except (OSError, ValueError):
            pass  #Sin conexión o sin catálogo publicado: se sigue usando el que hay
        self.setProgress(100)
        return True
