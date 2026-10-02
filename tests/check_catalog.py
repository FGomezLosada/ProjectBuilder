"""
Comprueba los servicios del catálogo (services.json): que el servidor responde y que la capa indicada existe.
Úsalo de vez en cuando: los servicios oficiales cambian de dirección con los años.

Uso (consola de Python de QGIS 3 o QGIS 4; necesita internet, tarda unos segundos):
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\check_catalog.py", encoding="utf-8").read())
"""
import concurrent.futures
import ssl
import urllib.request

import qgis.utils

qgis.utils.reloadPlugin('project_builder')
from project_builder.core import services as svc  # noqa: E402
from project_builder.core.capabilities import detect_type, parse_capabilities  # noqa: E402

ESPERA = 45  # segundos máximos por servidor (algunos, como el IGME, tardan más de 20 s)
_ctx = ssl.create_default_context()


def _comprobar(servicio):
    """Devuelve (servicio, 'OK'|'FALLO', detalle)."""
    url = svc.capabilities_url(servicio.url, servicio.type)
    try:
        peticion = urllib.request.Request(url, headers={'User-Agent': 'QGIS ProjectBuilder'})
        with urllib.request.urlopen(peticion, timeout=ESPERA, context=_ctx) as respuesta:
            datos = respuesta.read(8_000_000)
        capas = parse_capabilities(datos, detect_type(datos, servicio.type))
    except Exception as e:  # noqa: BLE001 (cualquier fallo de red o de formato cuenta como fallo)
        return servicio, 'FALLO', f"{type(e).__name__}: {str(e)[:90]}"
    if not capas:
        return servicio, 'FALLO', "el servicio no ofrece capas"
    if servicio.layer and servicio.layer not in {c['layer'] for c in capas}:
        return servicio, 'FALLO', f"no existe la capa '{servicio.layer}'"
    return servicio, 'OK', f"{len(capas)} capas"


catalogo = [(grupo, s) for grupo, servicios in svc.load_catalog() for s in servicios]
with concurrent.futures.ThreadPoolExecutor(24) as hilos:  # en paralelo y fuera de la interfaz: QGIS no se bloquea
    resultados = list(hilos.map(lambda gs: (gs[0], *_comprobar(gs[1])), catalogo))

print("=" * 70)
fallos = [r for r in resultados if r[2] != 'OK']
for grupo, servicio, estado, detalle in resultados:
    if estado != 'OK':
        print(f"  FALLO  [{grupo}] {servicio.name}: {detalle}\n         {servicio.url}")
print(f"{len(resultados) - len(fallos)} de {len(resultados)} servicios responden correctamente")
print("RESULTADO:", "TODO CORRECTO" if not fallos else f"{len(fallos)} SERVICIOS CON PROBLEMAS")
print("=" * 70)
