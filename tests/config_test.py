"""
Prueba de las configuraciones guardadas (mejora 4.9) con los datos de tests/data (no necesita internet).

Uso (consola de Python de QGIS 3 o QGIS 4):
    exec(open(r"C:\\Users\\Usuario\\Documents\\dev\\ProjectBuilder\\tests\\config_test.py", encoding="utf-8").read())

Rellena un panel, guarda la configuración, la carga en otro panel nuevo y comprueba que queda igual.
Usa un perfil temporal: no toca las configuraciones ni los favoritos del usuario.
"""
import json
import os
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsProject, QgsRectangle, QgsVectorLayer
from qgis.PyQt.QtCore import Qt

qgis.utils.reloadPlugin('project_builder')
import project_builder.core.configs as configs  # noqa: E402
import project_builder.core.services as svc_module  # noqa: E402
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

PERFIL = tempfile.mkdtemp(prefix="pb_perfil_")
svc_module.profile_dir = lambda: PERFIL
svc_module.favorites_path = lambda: PERFIL + "/favoritos.json"
svc_module.health_path = lambda: PERFIL + "/estado_servicios.json"
DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data').replace('\\', '/')
Clase = dock_module.ProjectBuilderDockWidget
avisos = []
_originales = {n: getattr(Clase, n) for n in ('warn', 'start_health_check', 'ask_name', 'confirm')}
Clase.warn = lambda self, msg: avisos.append(msg)
dock_module.ProjectBuilderDockWidget.load_project_layers = lambda self, *a: None  # sin el bloque del proyecto abierto: no depende de lo que tenga abierto el usuario
Clase.start_health_check = lambda self, force=False: None  # sin revisar servicios por internet
Clase.ask_name = lambda self, actual: "Prueba Nerja"
Clase.confirm = lambda self, pregunta: True
paneles = []


def _panel():
    dw = Clase(qgis.utils.iface)
    paneles.append(dw)
    return dw


def _items(item):
    for i in range(item.childCount()):
        yield item.child(i)
        yield from _items(item.child(i))


# Capa de la zona abierta en QGIS, con un elemento seleccionado
zona = QgsVectorLayer(DATA + "/vectorial/zonas_4326.shp", "zonas_4326", "ogr")
QgsProject.instance().addMapLayer(zona)
zona.selectByIds([0])

# 1. Panel rellenado a mano
a = _panel()
for carpeta in (DATA + '/vectorial', DATA + '/raster'):
    a.add_source_folder(carpeta)
for it in list(_items(a.treeWidget.invisibleRootItem())):
    if it.text(0) in ('zonas_4326.shp', 'lineas_25830', 'raster'):  # un fichero, una capa de un GeoPackage y una carpeta entera
        it.setCheckState(0, Qt.CheckState.Checked)
a.outputFormat.setCurrentIndex(a.outputFormat.findData('convert'))
a.reprojectCheck.setChecked(False)
a.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
a.addWMS.setChecked(True)
for it in a._service_leaves():
    if it.text(0) == 'Mapa base IGN':
        it.setCheckState(0, Qt.CheckState.Checked)
a.groupZone.setChecked(True)
a.zoneByLayer.setChecked(True)
a.zoneLayer.setLayer(zona)
a.zoneSelected.setChecked(True)
a.zoneMargin.setValue(250)
a.zoneAddLayer.setChecked(False)
a.zoneExtent.setOutputExtentFromUser(QgsRectangle(-3.9, 36.73, -3.86, 36.78), QgsCoordinateReferenceSystem("EPSG:4326"))
a.save_current_config()
ruta = configs.config_path("Prueba Nerja")
guardado = os.path.isfile(ruta) and ruta.endswith('prueba_nerja.json')
original = a.config_to_dict()
fuentes_a = a.selected_sources()
nombres = [n for n, _ in configs.list_configs()]
en_desplegable = [a.configCombo.itemText(i) for i in range(a.configCombo.count())]

# 2. Panel nuevo: se elige la configuración en el desplegable
zona.removeSelection()
b = _panel()
b.config_chosen(b.configCombo.findText("Prueba Nerja"))
cargada = b.config_to_dict()
fuentes_b = b.selected_sources()
seleccion_b = zona.selectedFeatureIds()
elegida = b.configCombo.currentText()

# 3. Capa de servicio que no está a la vista (venía de desplegar un servicio) y carpeta que ya no existe
datos = configs.load_config(ruta)
datos['servicios']['lista'].append({'name': 'Capa extra', 'url': 'https://ejemplo.org/wms', 'layer': 'extra', 'type': 'wms'})
datos['capas']['carpetas'].append(DATA + '/no_existe')
with open(ruta, 'w', encoding='utf-8') as f:
    json.dump(datos, f)
for dw in paneles:
    dw.zoneLayer.setLayer(None)  # los paneles dejan de usar la capa antes de quitarla del proyecto
QgsProject.instance().removeMapLayer(zona.id())  # la capa de la zona ya no está abierta: se debe abrir desde su fichero
c = _panel()
avisos.clear()
c.config_chosen(c.configCombo.findText("Prueba Nerja"))
avisos_c = list(avisos)
raices_c = [c.servicesTree.topLevelItem(i).text(0) for i in range(c.servicesTree.topLevelItemCount())]
servicios_c = sorted(s.name for s in c.selected_services())
capa_reabierta = c.zoneLayer.currentLayer()
reabierta = capa_reabierta is not None and capa_reabierta.source().replace('\\', '/').endswith('zonas_4326.shp')
c.reset_form()
limpio = not c.config_services and c.configCombo.currentIndex() == 0 and not c.groupZone.isChecked()

# 4. Borrar
c.config_chosen(c.configCombo.findText("Prueba Nerja"))
c.delete_current_config()
tras_borrar = configs.list_configs()

for dw in paneles:
    dw.zoneLayer.setLayer(None)
if capa_reabierta is not None:
    QgsProject.instance().removeMapLayer(capa_reabierta.id())
for nombre, funcion in _originales.items():
    setattr(Clase, nombre, funcion)
for dw in paneles:
    dw.deleteLater()

checks = {
    "se guarda un fichero .json en el perfil": guardado,
    "aparece en la lista y en el desplegable": nombres == ['Prueba Nerja'] and 'Prueba Nerja' in en_desplegable,
    "al cargarla el panel queda igual": cargada == original,
    "mismas capas marcadas": fuentes_b == fuentes_a and len(fuentes_a) >= 4,
    "carpeta entera guardada como carpeta": any(m['ruta'].replace('\\', '/').endswith('/raster') and m['capas'] is None
                                                for m in original['capas']['marcadas']),
    "recupera la selección de la zona": seleccion_b == [0],
    "el desplegable se queda en la configuración elegida": elegida == "Prueba Nerja",
    "servicio no visible se muestra aparte y marcado": "Servicios de la configuración" in raices_c
        and servicios_c == ['Capa extra', 'Mapa base IGN'],
    "abre la capa de la zona desde su fichero si no está abierta": reabierta,
    "avisa de la carpeta que ya no existe": len(avisos_c) == 1 and 'no_existe' in avisos_c[0],
    "Limpiar quita también la configuración": limpio,
    "borrar la configuración": tras_borrar == [],
}

print("=" * 60)
print("QGIS", Qgis.version(), "· configuraciones guardadas")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if avisos_c and not checks["avisa de la carpeta que ya no existe"]:
    print("Avisos:", avisos_c)
if not checks["al cargarla el panel queda igual"]:
    print("Diferencias:", {k: (original[k], cargada.get(k)) for k in original if original[k] != cargada.get(k)})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
