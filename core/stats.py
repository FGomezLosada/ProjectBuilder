"""
Estadísticas de las capas (mejora 4.6): elementos, superficie, longitud, tamaño... e informe HTML.

Las superficies y longitudes se miden sobre el elipsoide (en metros reales), aunque la capa esté en grados.
Se usan en dos momentos:
- Antes de crear el proyecto (botón «Estadísticas…»): sobre las capas de origen, recortadas «al vuelo» por la zona.
- Al terminar: sobre las capas ya copiadas al proyecto nuevo, para el informe informe_<proyecto>.html.
"""

import datetime
import html
import os

from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsFeatureRequest,
    QgsGeometry,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsVectorLayer,
)

GEOMETRY_NAMES = {Qgis.GeometryType.Point: 'Puntos', Qgis.GeometryType.Line: 'Líneas', Qgis.GeometryType.Polygon: 'Polígonos'}
DEFAULT_ELLIPSOID = 'EPSG:7030'  #WGS 84 (si el proyecto no tiene elipsoide)


def number(valor, decimales=2):
    """Número en formato español: 1.234,56."""
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(',', '#').replace('.', ',').replace('#', '.')


def human_size(octetos):
    if octetos is None:
        return '—'
    for unidad in ('B', 'KB', 'MB', 'GB'):
        if octetos < 1024 or unidad == 'GB':
            return f"{number(octetos, 0 if unidad == 'B' else 1)} {unidad}"
        octetos /= 1024


def file_size(layer):
    """Tamaño del fichero de la capa (None si no es de fichero)."""
    ruta = QgsProviderRegistry.instance().decodeUri(layer.providerType(), layer.source()).get('path') or ''
    return os.path.getsize(ruta) if os.path.isfile(ruta) else None


def _measurer(crs, ellipsoid):
    medidor = QgsDistanceArea()
    medidor.setSourceCrs(crs, QgsProject.instance().transformContext())
    medidor.setEllipsoid(ellipsoid if ellipsoid and ellipsoid != 'NONE' else DEFAULT_ELLIPSOID)
    return medidor


def layer_stats(layer, group=(), zone=None, ellipsoid=None, with_size=True):
    """
    Estadísticas de una capa, como diccionario (una fila del informe).
    zone: (geometría, SRC) para calcularlas como si la capa estuviera ya recortada por la zona de trabajo.
    """
    fila = {'nombre': layer.name(), 'grupo': ' / '.join(group), 'tipo': 'Servicio web', 'elementos': None,
            'superficie_ha': None, 'longitud_km': None, 'src': layer.crs().authid() or '—',
            'tamano': file_size(layer) if with_size else None, 'detalle': ''}
    if isinstance(layer, QgsRasterLayer) and layer.providerType() == 'gdal':
        fila['tipo'] = 'Ráster'
        fila['detalle'] = (f"{layer.width()} × {layer.height()} px · píxel {number(layer.rasterUnitsPerPixelX(), 2)} × "
                           f"{number(layer.rasterUnitsPerPixelY(), 2)} · {layer.bandCount()} banda{'s' if layer.bandCount() != 1 else ''}")
        return fila
    if not isinstance(layer, QgsVectorLayer) or layer.providerType() in ('WFS', 'OAPIF', 'arcgisfeatureserver'):
        fila['tamano'] = None
        return fila
    if not layer.isSpatial():
        fila.update(tipo='Tabla', elementos=layer.featureCount())
        return fila
    tipo = layer.geometryType()
    fila['tipo'] = GEOMETRY_NAMES.get(tipo, 'Vectorial')
    medidor = _measurer(layer.crs(), ellipsoid)
    peticion = QgsFeatureRequest().setNoAttributes()
    recorte = None
    if zone is not None:
        recorte = QgsGeometry(zone[0])
        if zone[1] != layer.crs():
            recorte.transform(QgsCoordinateTransform(zone[1], layer.crs(), QgsProject.instance()))
        peticion.setFilterRect(recorte.boundingBox())  #Solo se leen los elementos cercanos a la zona
    elementos, superficie, longitud = 0, 0.0, 0.0
    for elemento in layer.getFeatures(peticion):
        geometria = elemento.geometry()
        if geometria.isNull():
            continue
        if recorte is not None:
            # Comprobación normal de QGIS (sin «motor de geometría» aparte: depende de otra geometría
            # y, si Python las libera en mal orden, puede dañar la memoria de QGIS)
            if not recorte.intersects(geometria):
                continue
            if tipo != Qgis.GeometryType.Point:
                geometria = geometria.intersection(recorte)  #Igual que al recortar: solo cuenta la parte de dentro
        elementos += 1
        if tipo == Qgis.GeometryType.Polygon:
            superficie += medidor.measureArea(geometria)
        elif tipo == Qgis.GeometryType.Line:
            longitud += medidor.measureLength(geometria)
    fila['elementos'] = elementos
    if tipo == Qgis.GeometryType.Polygon:
        fila['superficie_ha'] = superficie / 10000
    elif tipo == Qgis.GeometryType.Line:
        fila['longitud_km'] = longitud / 1000
    return fila


def totals(filas):
    """Totales: capas, servicios, elementos, hectáreas de polígonos y kilómetros de líneas."""
    capas = [f for f in filas if f['tipo'] != 'Servicio web']
    return {
        'capas': len(capas),
        'servicios': len(filas) - len(capas),
        'elementos': sum(f['elementos'] or 0 for f in capas),
        'superficie_ha': sum(f['superficie_ha'] or 0 for f in capas),
        'longitud_km': sum(f['longitud_km'] or 0 for f in capas),
    }


def report_html(titulo, datos, filas, vacias=()):
    """
    Informe completo en HTML (sencillo: se ve igual en el navegador y en la ventana de QGIS).
    datos: lista de (etiqueta, valor) para la cabecera. filas: resultado de layer_stats.
    """
    e = html.escape
    t = totals(filas)
    celdas = []
    for f in filas:
        medida = (f"{number(f['superficie_ha'])} ha" if f['superficie_ha'] is not None
                  else f"{number(f['longitud_km'], 3)} km" if f['longitud_km'] is not None else '')
        elementos = number(f['elementos'], 0) if f['elementos'] is not None else ''
        celdas.append(f"<tr><td>{e(f['nombre'])}</td><td>{e(f['grupo'])}</td><td>{e(f['tipo'])}</td>"
                      f"<td class='n'>{elementos}</td><td class='n'>{medida}</td><td>{e(f['src'])}</td>"
                      f"<td class='n'>{human_size(f['tamano']) if f['tamano'] is not None else ''}</td><td>{e(f['detalle'])}</td></tr>")
    cabecera = ''.join(f"<tr><th>{e(k)}</th><td>{e(str(v))}</td></tr>" for k, v in datos)
    resumen = (f"<b>{t['capas']}</b> capa{'s' if t['capas'] != 1 else ''} · <b>{t['servicios']}</b> servicio"
               f"{'s' if t['servicios'] != 1 else ''} web · <b>{number(t['elementos'], 0)}</b> elementos · "
               f"<b>{number(t['superficie_ha'])}</b> ha de polígonos · <b>{number(t['longitud_km'], 3)}</b> km de líneas")
    sin_datos = (f"<h2>Capas sin datos en la zona de trabajo</h2><p>{e(', '.join(vacias))}</p>" if vacias else '')
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>{e(titulo)}</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; font-size: 10pt; margin: 16px; color: #222; }}
h1 {{ font-size: 15pt; margin-bottom: 4px; }} h2 {{ font-size: 11pt; margin-top: 18px; }}
table {{ border-collapse: collapse; margin-top: 6px; }}
th, td {{ border: 1px solid #ccc; padding: 3px 6px; text-align: left; vertical-align: top; }}
th {{ background: #eef3e8; }} td.n {{ text-align: right; white-space: nowrap; }}
.resumen {{ background: #f6f8f4; border: 1px solid #d5e0c8; padding: 6px 8px; margin-top: 8px; }}
.pie {{ color: #777; font-size: 8pt; margin-top: 18px; }}
</style></head><body>
<h1>{e(titulo)}</h1>
<table>{cabecera}</table>
<p class="resumen">{resumen}</p>
<h2>Capas</h2>
<table><tr><th>Capa</th><th>Grupo</th><th>Tipo</th><th>Elementos</th><th>Superficie / longitud</th><th>SRC</th><th>Tamaño</th><th>Detalle</th></tr>
{''.join(celdas)}</table>
{sin_datos}
<p class="pie">Generado por ProjectBuilder el {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}.
Superficies y longitudes medidas sobre el elipsoide (metros reales).</p>
</body></html>
"""


def write_report(path, titulo, datos, filas, vacias=()):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(report_html(titulo, datos, filas, vacias))
    return path


def service_row(name, group='Servicios web'):
    """Fila del informe para un servicio web (no tiene elementos ni tamaño)."""
    return {'nombre': name, 'grupo': group, 'tipo': 'Servicio web', 'elementos': None, 'superficie_ha': None,
            'longitud_km': None, 'src': '', 'tamano': None, 'detalle': ''}
