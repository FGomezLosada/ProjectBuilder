"""
ProjectBuilder - Panel (dock) con la interfaz del plugin.

Aquí solo está la parte visual (botones, árbol, mensajes). La lógica de exportar capas
y construir el proyecto está en la carpeta core/.

copyright : (C) 2023 by Francisco Gómez Losada
email     : pgomezlosada@gmail.com
license   : GNU GPL v2 or later
"""

import os

from qgis.core import Qgis, QgsApplication
from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QPushButton, QTreeWidgetItem

from .core import project as qgis_project
from .core.task import ExportTask
from .core.formats import FOLDER, VECTOR
from .core.scanner import scan_folder
from .wms.wms import dict_wms

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'project_builder_dockwidget_base.ui'))
PLUGIN_DIR = os.path.dirname(__file__)

# Iconos del árbol según el tipo de elemento
ICONS = {
    FOLDER: os.path.join(PLUGIN_DIR, 'icon', 'folder.png'),
    VECTOR: os.path.join(PLUGIN_DIR, 'icon', 'file_vectorial.png'),
}
RASTER_ICON = os.path.join(PLUGIN_DIR, 'icon', 'file_raster.png')
PATH_ROLE = Qt.ItemDataRole.UserRole  #Donde se guarda la ruta en cada elemento del árbol


class ProjectBuilderDockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    def __init__(self, iface, parent=None):
        """Constructor."""
        super().__init__(parent)
        self.setupUi(self)

        self.iface = iface
        self.task = None  #Tarea de exportación en curso (se guarda para que Python no la elimine antes de tiempo)

        # Disparadores
        self.selectFolder.clicked.connect(self.select_layers_folder)
        self.selectFolderProject.clicked.connect(self.select_project_folder)
        self.createProject.clicked.connect(lambda: self.create_project())  #lambda: la señal clicked envía un True/False que no queremos recibir
        self.treeWidget.itemActivated.connect(self.select_tree_children)  #Función selección hijos en el árbol (con el doble click)
        self.treeWidget.clear()
        self.load_wms_combo()  #Llamar a funcion añade wms a combo al inicio

    def closeEvent(self, event):  # noqa: N802 (nombre impuesto por Qt)
        self.closingPlugin.emit()
        event.accept()

    def warn(self, message):
        """Muestra un aviso al usuario."""
        QMessageBox.warning(self, "Error", message)

    # ------------------------------------------------------------------ Selección de carpetas

    def select_project_folder(self):
        folder = QFileDialog.getExistingDirectory(None, "Selecciona Carpeta", "", QFileDialog.Option.DontResolveSymlinks)
        self.pathFolderProject.setText(folder)

    def select_layers_folder(self):
        folder = QFileDialog.getExistingDirectory(None, "Selecciona Carpeta", "", QFileDialog.Option.DontResolveSymlinks)
        self.pathFolder.setText(folder)
        self.load_tree(folder)

    # ------------------------------------------------------------------ Árbol de capas

    def load_tree(self, folder):
        """Rellena el árbol con las carpetas y capas admitidas de folder."""
        self.treeWidget.clear()
        if os.path.isdir(folder):
            self._add_tree_items(self.treeWidget, scan_folder(folder))

    def _add_tree_items(self, parent, entries):
        for entry in entries:
            item = QTreeWidgetItem(parent, [entry.name])
            item.setData(0, PATH_ROLE, entry.path)  #Se le guarda la ruta al objeto internamente (se ve en el panel el nombre, pero no la ruta)
            item.setIcon(0, QIcon(ICONS.get(entry.kind, RASTER_ICON)))
            self._add_tree_items(item, entry.children)  #Recursivo: añade el contenido de las subcarpetas

    def select_tree_children(self, item, column):
        # Al hacer doble clic en una carpeta, todos sus elementos (y los de sus subcarpetas) toman su mismo estado: seleccionados o no
        seleccionar = item.isSelected()
        for i in range(item.childCount()):
            child_item = item.child(i)
            child_item.setSelected(seleccionar)
            self.select_tree_children(child_item, column)  #Llamada recursiva: repite lo mismo dentro de cada subcarpeta

    def selected_paths(self):
        """Rutas de los elementos seleccionados en el árbol (sin repetir)."""
        return list(dict.fromkeys(item.data(0, PATH_ROLE) for item in self.treeWidget.selectedItems()))

    # ------------------------------------------------------------------ Servicios WMS

    def load_wms_combo(self):
        """Añadir nombres wms a combo"""
        self.wmsComboBox.clear()
        self.wmsComboBox.addItems(list(dict_wms.keys()))

    # ------------------------------------------------------------------ Crear proyecto

    def validate(self):
        """Comprueba los datos del formulario. Devuelve un mensaje de error o None si todo está bien."""
        name = self.nameProject.text().strip()
        folder_project = self.pathFolderProject.text()
        folder_layers = self.pathFolder.text()
        if not name:
            return "No se ha introducido un nombre para el proyecto"
        if not os.path.isdir(folder_project):
            return "Carpeta de proyecto no válida"
        if not os.path.isdir(folder_layers):
            return "Acceso a capas no válido"
        # Evitar sobrescribir los datos de origen: el proyecto no puede estar en la carpeta de capas ni dentro de ella
        origen = os.path.normcase(os.path.abspath(folder_layers))
        destino = os.path.normcase(os.path.abspath(folder_project))
        if destino == origen or destino.startswith(origen + os.sep):
            return "La carpeta del proyecto no puede ser la carpeta de capas ni estar dentro de ella"
        if self.addWMS.isChecked() and not self.wmsComboBox.checkedItems():
            return "No ha seleccionado ningún WMS"
        return None

    def create_project(self, background=True):
        """
        Lanza la creación del proyecto. Las capas se exportan en segundo plano (QgsTask)
        y, al terminar, se construye y guarda el proyecto en finish_project().
        background=False ejecuta todo seguido (lo usa tests/smoke_test.py).
        """
        error = self.validate()
        if error:
            return self.warn(error)

        folder_project = self.pathFolderProject.text()
        folder_layers = self.pathFolder.text()
        jobs = []  #Pares (origen, destino) de las capas a exportar
        for path_source in self.selected_paths():
            # Misma estructura de subcarpetas que el origen, dentro de la carpeta del proyecto
            path_target = os.path.join(folder_project, os.path.relpath(path_source, folder_layers))
            if os.path.isdir(path_source):  #Comprobar si es un directorio
                os.makedirs(path_target, exist_ok=True)  #Crear directorio de forma recursiva
            else:
                jobs.append((path_source, path_target))

        self.task = ExportTask(jobs, self.selectProjection.crs())
        if background:
            self.createProject.setEnabled(False)  #Evita lanzar dos veces la creación mientras se exporta
            self.task.taskCompleted.connect(lambda: self.finish_project(True))
            self.task.taskTerminated.connect(lambda: self.finish_project(False))
            QgsApplication.taskManager().addTask(self.task)  #QGIS muestra el progreso abajo a la derecha
        else:
            self.finish_project(self.task.run())

    def finish_project(self, completed):
        """Se ejecuta al terminar la exportación: crea el proyecto con las capas exportadas, añade los WMS y lo guarda."""
        self.createProject.setEnabled(True)
        task, self.task = self.task, None
        if not completed:
            return self.iface.messageBar().pushMessage("ProjectBuilder", "Creación del proyecto cancelada",
                                                       level=Qgis.MessageLevel.Warning, duration=5)

        project = qgis_project.create_project(self.pathFolderProject.text(), self.nameProject.text().strip(),
                                              self.selectProjection.crs())
        errors = list(task.errors)  #Se acumulan los errores para mostrarlos todos juntos al final
        for path_target in task.exported:
            try:
                qgis_project.add_layer(project, path_target)
            except ValueError as e:
                errors.append(str(e))

        if self.addWMS.isChecked():  #Si el boton de wms esta activado, se crea el grupo y se añaden los seleccionados
            group = qgis_project.add_group(project, 'WMS')
            for wms in self.wmsComboBox.checkedItems():  #Recorrer wms seleccionados y obtener name y url del diccionario
                try:
                    qgis_project.add_wms(project, group, wms, dict_wms[wms]['url'])
                except ValueError as e:
                    errors.append(str(e))

        try:
            path_file = qgis_project.save_project(project)
        except OSError as e:
            return self.warn(str(e))

        if errors:
            self.warn("El proyecto se ha creado, pero con estos problemas:\n\n- " + "\n- ".join(errors))
        self.show_success(path_file)

    def show_success(self, path_file):
        """Mensaje de que se ha creado el proyecto, con un botón para abrirlo en QGIS."""
        bar = self.iface.messageBar()
        message = bar.createMessage("ProjectBuilder", f"Proyecto creado: {path_file}")
        button = QPushButton("Abrir proyecto")
        button.clicked.connect(lambda: self.iface.addProject(path_file))  #QGIS pregunta antes si hay que guardar el proyecto actual
        message.layout().addWidget(button)
        bar.pushWidget(message, Qgis.MessageLevel.Success, 15)
