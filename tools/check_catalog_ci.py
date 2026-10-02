"""
Comprobación del catálogo (services.json) SIN QGIS, para la tarea automática mensual de GitHub.

Usa las mismas piezas que el plugin (core/services.py y core/capabilities.py son Python puro).
Escribe un informe en Markdown (informe_catalogo.md) y termina con código 1 si algún servicio falla.
"""
import concurrent.futures
import os
import ssl
import sys
import time
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from core import services as svc  # noqa: E402
from core.capabilities import detect_type, parse_capabilities  # noqa: E402

ESPERA = 45

# Recordatorio que llega en el email: qué hacer, dónde y cómo.
RECORDATORIO = [
    "",
    "---",
    "## Recordatorio: cómo arreglarlo",
    "",
    "**Dónde:** archivo `services.json` en la raíz del repositorio",
    "(en tu PC: `C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\services.json`, ábrelo con VS Code).",
    "",
    "**Qué hacer según el resultado:**",
    "- **CAMBIAR URL a ...** → el servicio funciona con la dirección nueva: busca el servicio por su nombre (Ctrl+F)",
    "  y cambia su `\"url\"` por la indicada.",
    "- **ya no existe la capa ...** → abre el servicio en QGIS (Capa → Añadir capa WMS/WMTS o WFS), mira el nombre",
    "  actual de la capa y cámbialo en `\"layer\"`.",
    "- **FALLO** → puede ser una caída temporal. Ábrelo antes en QGIS desde tu PC: si funciona, no hagas nada.",
    "  Si tampoco funciona y ya falló el mes pasado (ver *Cómo ver los avisos anteriores*, abajo), busca la nueva",
    "  dirección en la web del organismo o en https://www.idee.es/ y cámbiala;",
    "  si el servicio ha desaparecido, borra su bloque `{ ... }` completo (cuidado con las comas).",
    "- **FALLO: HTTP Error 52x** (520-527) → el servidor está detrás de Cloudflare y no respondió a GitHub, que",
    "  revisa desde EE. UU. Ábrelo antes en QGIS desde tu PC: si funciona, no hagas nada (no es un fallo real).",
    "",
    "**Después, siempre:**",
    "1. Cambia `\"version\"` (arriba del todo) por la fecha de hoy, p. ej. `\"2026-11-01\"`. Sin este cambio el plugin",
    "   no descarga el catálogo nuevo.",
    "2. Prueba en la consola de Python de QGIS:",
    "   `exec(open(r\"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\check_catalog.py\", encoding=\"utf-8\").read())`",
    "3. En CMD, desde la carpeta del proyecto:",
    "   ```",
    "   git switch main",
    "   git add services.json",
    "   git commit -m \"fix: actualiza servicios del catálogo\"",
    "   git push",
    "   ```",
    "5. Vuelve a la rama de trabajo: `git switch fase4 && git merge main`",
    "",
    "## Recordatorio: qué hacer en GitHub",
    "",
    "**Cerrar este aviso** (siempre, tanto si has corregido algo como si era una falsa alarma):",
    "1. En este email, pulsa el enlace **view it on GitHub** (abajo del todo), o entra en",
    "   https://github.com/FGomezLosada/ProjectBuilder/issues",
    "2. Abre la incidencia *Catálogo: servicios que no responden*.",
    "3. Baja hasta el final de la página y pulsa el botón **Close issue**.",
    "",
    "**Cómo ver los avisos anteriores:** en https://github.com/FGomezLosada/ProjectBuilder/issues pulsa",
    "**Closed** (encima de la lista). Ahí están los avisos de meses pasados con sus tablas.",
    "",
    "**Repetir la revisión cuando quieras** (p. ej. tras corregir, para confirmar que ya está bien):",
    "1. Entra en https://github.com/FGomezLosada/ProjectBuilder/actions",
    "2. A la izquierda, pulsa **Revisar catálogo de servicios**.",
    "3. A la derecha, pulsa **Run workflow** ▾, deja la rama **main** y pulsa el botón verde **Run workflow**.",
    "4. Espera 1-2 minutos y recarga (F5). Para leer el resultado: pulsa la fila nueva → **revisar** →",
    "   despliega **Comprobar servicios**. Si todo está bien no se crea aviso ni llega email.",
]
_ctx = ssl.create_default_context()


def descargar(url, _authcfg=''):
    peticion = urllib.request.Request(url, headers={'User-Agent': 'ProjectBuilder catalog check'})
    with urllib.request.urlopen(peticion, timeout=ESPERA, context=_ctx) as respuesta:
        return respuesta.read(8_000_000)


def comprobar(servicio, intentos=3, pausa=20):
    """Repite la comprobación si falla: algunos servidores tienen caídas de segundos."""
    for intento in range(intentos):
        resultado = _comprobar(servicio)
        if not resultado.startswith('FALLO') or intento == intentos - 1:
            return resultado
        time.sleep(pausa)


def _comprobar(servicio):
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
        lineas += RECORDATORIO
    with open(os.path.join(RAIZ, 'informe_catalogo.md'), 'w', encoding='utf-8') as f:
        f.write("\n".join(lineas) + "\n")
    print("\n".join(lineas))
    return 1 if problemas else 0


if __name__ == '__main__':
    sys.exit(main())
