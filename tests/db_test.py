"""
Prueba de las bases de datos como origen (mejora 4.7): SpatiaLite y GeoPackage siempre, y PostGIS si está en marcha la base de
datos de prueba (localhost:5433, ver docs/DESARROLLO.md). No necesita internet.

Uso: tools\\probar.bat db_test.py   (o en la consola de Python de QGIS:)
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\db_test.py", encoding="utf-8").read())
"""
import os
import socket
import tempfile

import qgis.utils
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsLayerTreeGroup,
    QgsProject,
    QgsProviderRegistry,
    QgsRectangle,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt

qgis.utils.reloadPlugin('project_builder')
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data').replace('\\', '/')
TMP = tempfile.mkdtemp(prefix="pb_bd_").replace('\\', '/')
Clase = dock_module.ProjectBuilderDockWidget
avisos = []
_originales = {n: getattr(Clase, n) for n in ('warn', 'start_health_check', 'show_success', 'load_project_layers')}
Clase.warn = lambda self, msg: avisos.append(msg)
Clase.start_health_check = lambda self, force=False: None
Clase.show_success = lambda self, ruta, empty=(), *a, **k: None
Clase.load_project_layers = lambda self, *a: None
WGS84 = QgsCoordinateReferenceSystem('EPSG:4326')
ZONA = QgsRectangle(-3.91, 36.72, -3.876, 36.79)
POSTGIS = "pb_postgis_prueba"


def _hay_postgis():
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect(("localhost", 5433))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _items(item):
    for i in range(item.childCount()):
        yield item.child(i)
        yield from _items(item.child(i))


def _grupos(nodo, ruta=()):
    out = []
    for c in nodo.children():
        if isinstance(c, QgsLayerTreeGroup):
            out.append('/'.join((*ruta, c.name())))
            out += _grupos(c, (*ruta, c.name()))
    return out


def _panel(nombre, modo='single'):
    dw = Clase(qgis.utils.iface)
    dw.nameProject.setText(nombre)
    dw.pathFolderProject.setText(f"{TMP}/{nombre}")
    dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
    dw.outputFormat.setCurrentIndex(dw.outputFormat.findData(modo))
    dw.groupZone.setChecked(True)
    dw.zoneByExtent.setChecked(True)
    dw.zoneExtent.setOutputExtentFromUser(ZONA, WGS84)
    paneles.append(dw)
    return dw


def _xmax_ok(capa):
    """Todos los elementos dentro de la zona (longitud máxima <= la de la zona, en grados)."""
    from qgis.core import QgsCoordinateTransform, QgsGeometry
    t = QgsCoordinateTransform(capa.crs(), WGS84, QgsProject.instance())
    for f in capa.getFeatures():
        g = QgsGeometry(f.geometry())
        g.transform(t)
        if g.boundingBox().xMaximum() > ZONA.xMaximum() + 1e-6:
            return False
    return True


paneles = []

# 1. SpatiaLite: base de datos con dos tablas, creada para la prueba
sqlite = f"{TMP}/prueba.sqlite"
for fichero, tabla in ((DATA + "/vectorial/zonas_4326.shp", "zonas"), (DATA + "/vectorial/subcarpeta/puntos_23030.shp", "puntos")):
    opciones = QgsVectorFileWriter.SaveVectorOptions()
    opciones.driverName = 'SQLite'
    opciones.layerName = tabla
    opciones.datasourceOptions = ['SPATIALITE=YES']
    opciones.actionOnExistingFile = (QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer if os.path.exists(sqlite)
                                     else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile)
    QgsVectorFileWriter.writeAsVectorFormatV3(QgsVectorLayer(fichero, tabla, 'ogr'), sqlite, QgsProject.instance().transformContext(), opciones)
md_sqlite = QgsProviderRegistry.instance().providerMetadata('spatialite')
md_sqlite.saveConnection(md_sqlite.createConnection(f"dbname='{sqlite}'", {}), "pb_sqlite_prueba")

dw = _panel("spatialite")
raiz = dw.add_database('spatialite', "pb_sqlite_prueba")
tablas_sqlite = sorted(it.text(0) for it in _items(raiz) if it.data(0, dock_module.KIND_ROLE) == dock_module.DB_TABLE) if raiz else []
if raiz:
    raiz.setCheckState(0, Qt.CheckState.Checked)
filas_informe = {f['nombre']: f for f in dw.preview_rows()}
config = dw.config_to_dict()['bases_datos']
dw.create_project(background=False)
p1 = QgsProject()
p1.read(f"{TMP}/spatialite/spatialite.qgz")
c1 = {lyr.name(): lyr for lyr in p1.mapLayers().values() if lyr.name() != 'zona_trabajo'}

# 1b. GeoPackage conectado en QGIS (como los del Explorador)
import shutil  # noqa: E402
gpkg = f"{TMP}/conectado.gpkg"
shutil.copy2(DATA + "/vectorial/multicapa.gpkg", gpkg)
md_ogr = QgsProviderRegistry.instance().providerMetadata('ogr')
md_ogr.saveConnection(md_ogr.createConnection(gpkg, {}), "pb_gpkg_prueba")
gp = _panel("geopackage")
raiz_gp = gp.add_database('ogr', "pb_gpkg_prueba")
tablas_gp = sorted(it.text(0) for it in _items(raiz_gp) if it.data(0, dock_module.KIND_ROLE) == dock_module.DB_TABLE) if raiz_gp else []
en_menu = any(p == 'ogr' and n == "pb_gpkg_prueba" for p, n in dock_module.database.connections())
if raiz_gp:
    raiz_gp.setCheckState(0, Qt.CheckState.Checked)
gp.create_project(background=False)
p3 = QgsProject()
p3.read(f"{TMP}/geopackage/geopackage.qgz")
c3 = {lyr.name(): lyr for lyr in p3.mapLayers().values() if lyr.name() != 'zona_trabajo'}

# 2. La configuración vuelve a añadir la conexión y a marcar sus tablas
otro = Clase(qgis.utils.iface)
paneles.append(otro)
avisos.clear()
config_datos = {**otro.config_to_dict(), 'bases_datos': config + [{'proveedor': 'spatialite', 'conexion': 'no_existe', 'tablas': []}]}
avisos_config = otro.apply_config(config_datos)
recuperadas = sorted(t['tabla'] for t in otro.selected_db_tables())

# 3. Conexión que no responde: avisa y no se cuelga ni cierra QGIS
md_pg = QgsProviderRegistry.instance().providerMetadata('postgres')
md_pg.saveConnection(md_pg.createConnection("host=localhost port=5999 dbname=nada user=x password=x connect_timeout=3", {}), "pb_caida")
avisos.clear()
caida = otro.add_database('postgres', "pb_caida")
aviso_caida = list(avisos)
avisos.clear()  # ese aviso es el esperado

# 4. PostGIS (si la base de datos de prueba está en marcha)
postgis = _hay_postgis()
if postgis:
    md_pg.saveConnection(md_pg.createConnection(
        "host=localhost port=5433 dbname=ayuntamiento_prueba user=postgres password=projectbuilder sslmode=disable",
        {"saveUsername": True, "savePassword": True}), POSTGIS)
    pg = _panel("postgis", 'convert')
    raiz_pg = pg.add_database('postgres', POSTGIS)
    arbol_pg = {it.text(0): it for it in _items(raiz_pg)} if raiz_pg else {}
    esquemas_pg = sorted(n for n, it in arbol_pg.items() if it.data(0, dock_module.KIND_ROLE) == dock_module.DB_SCHEMA)
    for nombre in ('parcelas', 'viales', 'parcelas_grandes'):
        if nombre in arbol_pg:
            arbol_pg[nombre].setCheckState(0, Qt.CheckState.Checked)
    pg.create_project(background=False)
    p2 = QgsProject()
    p2.read(f"{TMP}/postgis/postgis.qgz")
    c2 = {lyr.name(): lyr for lyr in p2.mapLayers().values() if lyr.name() != 'zona_trabajo'}

for panel in paneles:
    panel.zoneLayer.setLayer(None)
    panel.deleteLater()
for nombre, funcion in _originales.items():
    setattr(Clase, nombre, funcion)


def _color(lyr):
    return lyr.renderer().symbol().color().name() if lyr is not None and hasattr(lyr.renderer(), 'symbol') else None


checks = {
    "[SpatiaLite] conexión añadida con sus tablas": tablas_sqlite == ['puntos', 'zonas'],
    "[SpatiaLite] informe de capas con las tablas": 'zonas' in filas_informe and filas_informe['zonas']['elementos'] > 0,
    "[SpatiaLite] tablas copiadas al GeoPackage del proyecto": sorted(c1) == ['puntos', 'zonas']
        and all(lyr.isValid() and "spatialite.gpkg" in lyr.source() for lyr in c1.values()),
    "[SpatiaLite] grupo = nombre de la conexión": "pb_sqlite_prueba" in _grupos(p1.layerTreeRoot()),
    "[SpatiaLite] recortadas a la zona": all(_xmax_ok(lyr) for lyr in c1.values()),
    "[GeoPackage] aparece en el menú de conexiones": en_menu,
    "[GeoPackage] conexión añadida con sus capas": tablas_gp == ['lineas_25830', 'zonas_4326'],
    "[GeoPackage] capas copiadas y recortadas": sorted(c3) == ['lineas_25830', 'zonas_4326']
        and all(lyr.isValid() and _xmax_ok(lyr) for lyr in c3.values()),
    "[configuración] recupera conexión y tablas": recuperadas == ['puntos', 'zonas'],
    "[configuración] avisa de la conexión que no existe": any('no_existe' in a for a in avisos_config),
    "conexión caída: avisa sin colgarse": caida is None and len(aviso_caida) == 1 and 'pb_caida' in aviso_caida[0],
}
if postgis:
    checks.update({
        "[PostGIS] esquemas catastro y urbanismo": {'catastro', 'urbanismo'} <= set(esquemas_pg),
        "[PostGIS] 3 tablas copiadas (incluida una vista)": sorted(c2) == ['parcelas', 'parcelas_grandes', 'viales']
            and all(lyr.isValid() for lyr in c2.values()),
        "[PostGIS] ficheros en conexión/esquema": os.path.isfile(f"{TMP}/postgis/{POSTGIS}/catastro/parcelas.gpkg")
            and os.path.isfile(f"{TMP}/postgis/{POSTGIS}/urbanismo/viales.gpkg"),
        "[PostGIS] estilo guardado en la base de datos": _color(c2.get('parcelas')) == '#2b8cbe',
        "[PostGIS] recortadas a la zona": all(_xmax_ok(lyr) for lyr in c2.values()),
    })
checks["sin avisos inesperados"] = not avisos

print("=" * 60)
print("QGIS", Qgis.version(), "· bases de datos", "(SpatiaLite y PostGIS)" if postgis else "(solo SpatiaLite: PostGIS de prueba apagada)")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if avisos:
    print("Avisos:", avisos)
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
