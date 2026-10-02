"""
Comprobación del catálogo (services.json) SIN QGIS, para la tarea automática mensual de GitHub.

Usa las mismas piezas que el plugin (core/services.py y core/capabilities.py son Python puro).
Escribe un informe en Markdown (informe_catalogo.md) y termina con código 1 si algún servicio falla.
"""
import concurrent.futures
import os
import ssl
import sys
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from core import services as svc  # noqa: E402
from core.capabilities import detect_type, parse_capabilities  # noqa: E402

ESPERA = 45
_ctx = ssl.create_default_context()


def descargar(url, _authcfg=''):
    peticion = urllib.request.Request(url, headers={'User-Agent': 'ProjectBuilder catalog check'})
    with urllib.request.urlopen(peticion, timeout=ESPERA, context=_ctx) as respuesta:
        return respuesta.read(8_000_000)


def comprobar(servicio):
    detalle = ''
    for url in svc.url_variants(servicio.url):
        try:
            datos = descargar(svc.capabilities_url(url, servicio.type))
            capas = parse_capabilities(datos, detect_type(datos, servicio.type))
        except Exception as e:  # noqa: BLE001 (cualquier fallo cuenta)
            detalle = f"{type(e).__name__}: {str(e)[:120]}"
            continue
        if servicio.layer and servicio.layer not in {c['layer'] for c in capas}:
            detalle = f"ya no existe la capa `{servicio.layer}`"
            continue
        if capas:
            return 'OK' if url == servicio.url else f"CAMBIAR URL a `{url}`"
    return f"FALLO: {detalle or 'no responde'}"


def main():
    catalogo = [(g, s) for g, lista in svc.load_catalog(os.path.join(RAIZ, 'services.json')) for s in lista]
    with concurrent.futures.ThreadPoolExecutor(16) as hilos:
        resultados = list(hilos.map(lambda gs: (gs[0], gs[1], comprobar(gs[1])), catalogo))
    problemas = [(g, s, r) for g, s, r in resultados if r != 'OK']
    lineas = [f"Comprobados **{len(resultados)}** servicios del catálogo: **{len(problemas)}** con problemas.", ""]
    if problemas:
        lineas += ["| Grupo | Servicio | Resultado | URL |", "|---|---|---|---|"]
        lineas += [f"| {g} | {s.name} | {r} | {s.url} |" for g, s, r in problemas]
        lineas += ["", "Los servicios con **CAMBIAR URL** funcionan con la dirección indicada: basta con actualizarla en `services.json`."]
    with open(os.path.join(RAIZ, 'informe_catalogo.md'), 'w', encoding='utf-8') as f:
        f.write("\n".join(lineas) + "\n")
    print("\n".join(lineas))
    return 1 if problemas else 0


if __name__ == '__main__':
    sys.exit(main())
