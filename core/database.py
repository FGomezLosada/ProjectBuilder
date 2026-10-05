"""
Bases de datos como origen de capas (mejora 4.7): PostGIS, SpatiaLite y GeoPackage conectados en QGIS.

Se usan las conexiones que el usuario ya tiene guardadas en QGIS (Administrador de fuentes de datos), con su usuario
y contraseña. Las tablas marcadas se copian al proyecto como el resto de capas: primero se descargan a un GeoPackage
temporal (en segundo plano y, si hay zona de trabajo, solo lo que cae en su rectángulo) y después siguen el camino
normal (formato de salida, reproyección y recorte).
"""

from qgis.core import (
    Qgis,
    QgsAbstractDatabaseProviderConnection,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsDataSourceUri,
    QgsProviderRegistry,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)

PROVIDERS = {  #Proveedor de QGIS -> (nombre que se muestra, icono)
    'postgres': ('PostGIS', '/mIconPostgis.svg'),
    'spatialite': ('SpatiaLite', '/mIconSpatialite.svg'),
    'ogr': ('GeoPackage', '/mGeoPackage.svg'),  #Conexiones GeoPackage del Explorador de QGIS
}
SYSTEM_TABLES = {'layer_styles', 'spatial_ref_sys', 'geometry_columns', 'geography_columns', 'raster_columns',
                 'raster_overviews', 'topology', 'layer'}  #Tablas internas que no se muestran


class DatabaseError(Exception):
    """No se puede conectar o leer la base de datos (el mensaje se muestra al usuario)."""


def _metadata(provider):
    return QgsProviderRegistry.instance().providerMetadata(provider)


def connections():
    """Conexiones guardadas en QGIS: lista de (proveedor, nombre), por proveedor y orden alfabético."""
    lista = []
    for provider in PROVIDERS:
        metadatos = _metadata(provider)
        if metadatos is None:
            continue
        lista += [(provider, nombre) for nombre in sorted(metadatos.connections(), key=str.lower)]
    return lista


def connection(provider, name):
    metadatos = _metadata(provider)
    conexiones = metadatos.connections() if metadatos else {}
    if name not in conexiones:
        raise DatabaseError(f"No existe la conexión {PROVIDERS.get(provider, (provider,))[0]} «{name}» en QGIS")
    return conexiones[name]


def tables(provider, name):
    """
    Tablas y vistas con geometría de una conexión: lista de diccionarios con esquema, tabla, geometría (tipo de QGIS),
    vista (True/False) y uri (la fuente para abrirla como capa). Lanza DatabaseError si no se puede conectar.
    """
    conexion = connection(provider, name)
    filtro = QgsAbstractDatabaseProviderConnection.TableFlag.Vector | QgsAbstractDatabaseProviderConnection.TableFlag.View
    try:
        propiedades = conexion.tables('', filtro)
    except Exception as e:  #QgsProviderConnectionException: servidor caído, contraseña incorrecta...
        raise DatabaseError(f"No se pudo conectar a «{name}»: {e}") from e
    lista = []
    for tabla in propiedades:
        if not tabla.geometryColumn() or tabla.tableName().lower() in SYSTEM_TABLES:
            continue
        tipos = tabla.geometryColumnTypes()
        wkb = tipos[0].wkbType if tipos else Qgis.WkbType.Unknown
        if provider == 'ogr':  #GeoPackage: la dirección es el fichero y el nombre de la capa (fichero.gpkg|layername=capa)
            lista.append({'esquema': '', 'tabla': tabla.tableName(), 'geometria': QgsWkbTypes.geometryType(wkb), 'vista': False,
                          'uri': conexion.tableUri(tabla.schema(), tabla.tableName())})
            continue
        uri = QgsDataSourceUri(conexion.uri())
        claves = tabla.primaryKeyColumns()
        if not claves:  #Vistas: no tienen clave primaria; se usa una columna identificadora si la hay
            try:
                nombres = [c.name() for c in conexion.fields(tabla.schema(), tabla.tableName())]
            except Exception:  # noqa: BLE001
                nombres = []
            claves = [c for c in ('gid', 'id', 'fid', 'ogc_fid', 'objectid') if c in nombres][:1]
        uri.setDataSource(tabla.schema(), tabla.tableName(), tabla.geometryColumn(), '', claves[0] if claves else '')
        # No se fijan el tipo de geometría ni el SRID en la dirección: QGIS los detecta solo y, si se fijan,
        # no encuentra el estilo de la capa guardado en la base de datos (tabla layer_styles)
        lista.append({'esquema': tabla.schema(), 'tabla': tabla.tableName(), 'geometria': QgsWkbTypes.geometryType(wkb),
                      'vista': bool(tabla.flags() & QgsAbstractDatabaseProviderConnection.TableFlag.View),
                      'uri': uri.uri(False)})
    return sorted(lista, key=lambda t: (t['esquema'].lower(), t['tabla'].lower()))


def download(uri, provider, destination, layer_name, zone_extent=None):
    """
    Descarga una tabla a un GeoPackage (se puede llamar en segundo plano). zone_extent: (rectángulo, SRC) de la zona
    de trabajo; si se indica, solo se descargan los elementos que caen en ese rectángulo (el recorte exacto viene después).
    Devuelve el número de elementos descargados. Lanza DatabaseError si algo falla.
    """
    capa = QgsVectorLayer(uri, layer_name, provider)
    if not capa.isValid():
        raise DatabaseError(f"No se pudo abrir la tabla {layer_name} de la base de datos")
    opciones = QgsVectorFileWriter.SaveVectorOptions()
    opciones.driverName = 'GPKG'
    opciones.layerName = layer_name
    contexto = QgsCoordinateTransformContext()
    if zone_extent is not None:
        rectangulo, crs = zone_extent
        if crs != capa.crs():
            rectangulo = QgsCoordinateTransform(crs, capa.crs(), contexto).transformBoundingBox(rectangulo)
        opciones.filterExtent = rectangulo  #El servidor solo envía lo que cae en el rectángulo de la zona
    error, mensaje, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(capa, destination, contexto, opciones)
    if error != QgsVectorFileWriter.WriterError.NoError:  #Comparación explícita (en PyQt6 los enum siempre valen True)
        raise DatabaseError(f"No se pudo descargar la tabla {layer_name}: {mensaje}")
    return QgsVectorLayer(destination, layer_name, 'ogr').featureCount()
