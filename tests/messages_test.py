"""
Prueba de los avisos dentro del panel (V6) y del informe final al crear el proyecto (V7). Sin internet.

Uso: tools\\probar.bat (o tools\\run_tests.py messages_test.py)
"""
import os
import tempfile

import qgis.utils
from qgis.core import Qgis, QgsCoordinateReferenceSystem
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMessageBox, QPushButton

qgis.utils.reloadPlugin('project_builder')
import project_builder.core.services as svc_module  # noqa: E402
import project_builder.project_builder_dockwidget as dock_module  # noqa: E402

PERFIL = tempfile.mkdtemp(prefix="pb_perfil_")
svc_module.profile_dir = lambda: PERFIL
svc_module.favorites_path = lambda: PERFIL + "/favoritos.json"
svc_module.health_path = lambda: PERFIL + "/estado_servicios.json"
DATA = os.path.join(os.path.dirname(dock_module.__file__), 'tests', 'data')
Clase = dock_module.ProjectBuilderDockWidget
_originales = {n: getattr(Clase, n) for n in ('start_health_check', 'load_project_layers', 'show_report_dialog')}
Clase.start_health_check = lambda self, force=False: None
Clase.load_project_layers = lambda self, *a: None
dialogos = []
Clase.show_report_dialog = lambda self, contenido, filas=(), titulo='': dialogos.append((titulo, len(filas)))
ventanas = []  #Si algo abriera una ventana de aviso, la prueba lo detectaría
_warning = QMessageBox.warning
QMessageBox.warning = lambda *a, **k: ventanas.append(a)


def _items(item):
    for i in range(item.childCount()):
        yield item.child(i)
        yield from _items(item.child(i))


def _texto(barra):
    item = barra.currentItem()
    return item.text() if item is not None else None


dw = Clase(qgis.utils.iface)
barra = dw.messageBar

# 1. Un error de validación sale en la barra del panel, no en una ventana
dw.create_project(background=False)  #Sin nombre ni carpeta
paso1 = (_texto(barra) == "No se ha introducido un nombre para el proyecto" and not ventanas
         and barra.currentItem().level() == Qgis.MessageLevel.Warning)

# 2. Un aviso largo: se ve la primera línea y el resto con «Más»
dw.warn("Configuración cargada, pero con estos avisos:\n\n- Ya no existe la carpeta X\n- Ya no existe Y")
paso2 = _texto(barra) == "Configuración cargada, pero con estos avisos:" and barra.currentItem().duration() == 0

# 3. Crear un proyecto: informe final con botones
dw.add_source_folder(os.path.join(DATA, 'vectorial'))
for it in list(_items(dw.treeWidget.invisibleRootItem())):
    if it.text(0) in ('zonas_4326.shp', 'lugares_4326.geojson'):
        it.setCheckState(0, Qt.CheckState.Checked)
destino = os.path.join(tempfile.mkdtemp(prefix="pb_msg_"), "proyecto")
dw.pathFolderProject.setText(destino)
dw.nameProject.setText("avisos")
dw.selectProjection.setCrs(QgsCoordinateReferenceSystem("EPSG:25830"))
dw.create_project(background=False)
texto_final = _texto(barra) or ''
item_final = barra.currentItem()
botones = [b.text() for b in item_final.findChildren(QPushButton)] if item_final is not None else []
paso3 = (texto_final.startswith("Proyecto «avisos» creado") and "2 capas" in texto_final and " en " in texto_final
         and item_final.level() == Qgis.MessageLevel.Success and botones == ['Abrir proyecto', 'Abrir carpeta', 'Informe…']
         and item_final.duration() == 0)
# Al crear otro proyecto, los avisos anteriores desaparecen
avisos_antes = len(barra.items())

# 4. Informe completo
contenido, filas = dw.final_report()
paso4 = (contenido is not None and len(filas) == 2 and 'zonas_4326' in contenido and 'Tiempo' in contenido
         and 'Tamaño de la carpeta' in contenido and 'Problemas' in contenido)
item_final.findChildren(QPushButton)[2].click()  #«Informe…»
paso4b = dialogos == [("ProjectBuilder · Proyecto creado", 2)]

# 5. Con problemas: el informe final sale en naranja y los lista
dw.show_success(os.path.join(destino, "avisos.qgz"), empty=['vacia'], errors=['No se pudo copiar la capa X'],
                summary={'capas': 1, 'segundos': 75, 'tamano': 2048})
texto_problemas = _texto(barra) or ''
contenido_p, _ = dw.final_report()
paso5 = (barra.currentItem().level() == Qgis.MessageLevel.Warning and "1 problema" in texto_problemas
         and "1 min 15 s" in texto_problemas and "1 sin datos en la zona" in texto_problemas
         and 'No se pudo copiar la capa X' in contenido_p and 'vacia' in contenido_p)

# 6. Al volver a pulsar Crear se limpian los avisos anteriores
dw.nameProject.clear()
dw.create_project(background=False)
paso6 = avisos_antes >= 1 and len(barra.items()) == 1 and _texto(barra).startswith("No se ha introducido")

QMessageBox.warning = _warning
for nombre, funcion in _originales.items():
    setattr(Clase, nombre, funcion)
dw.deleteLater()

checks = {
    "los errores salen en la barra del panel, sin ventanas": paso1,
    "aviso largo: primera línea y el resto con «Más», hasta cerrarlo": paso2,
    "informe final con capas, tamaño, tiempo y botones": paso3,
    "informe completo de las capas creadas": paso4,
    "el botón «Informe…» abre el informe": paso4b,
    "con problemas: aviso naranja y problemas en el informe": paso5,
    "al volver a crear se limpian los avisos anteriores": paso6,
}

print("=" * 60)
print("QGIS", Qgis.version(), "· avisos en el panel e informe final")
for nombre, ok in checks.items():
    print(("  OK   " if ok else "  FALLO") + "  " + nombre)
if not all(checks.values()):
    print("Detalles:", {'texto_final': texto_final, 'botones': botones, 'ventanas': ventanas, 'filas': len(filas),
                        'problemas': texto_problemas, 'dialogos': dialogos, 'items': len(barra.items()), 'antes': avisos_antes})
print("RESULTADO:", "TODO CORRECTO" if all(checks.values()) else "HAY FALLOS")
print("=" * 60)
