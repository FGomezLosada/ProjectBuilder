"""
ProjectBuilder - Panel (dock) con la interfaz del plugin.

Aquí solo está la parte visual (botones, árbol, mensajes). La lógica de exportar capas
y construir el proyecto está en la carpeta core/.

copyright : (C) 2023 by Francisco Gómez Losada
email     : pgomezlosada@gmail.com
license   : GNU GPL v2 or later
"""

import os
import unicodedata

from qgis.core import Qgis, QgsApplication
from qgis.gui import QgsFilterLineEdit
from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QMessageBox,
    QPushButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .core import project as qgis_project
from .core.task import ExportTask
from .core.formats import FOLDER, GEOPACKAGE, VECTOR
from .core.scanner import scan_folder
from .core.services import ServicesError, load_services

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'project_builder_dockwidget_base.ui'))
PLUGIN_DIR = os.path.dirname(__file__)

# Iconos del árbol según el tipo de elemento
ICONS = {
    FOLDER: os.path.join(PLUGIN_DIR, 'icon', 'folder.png'),
    VECTOR: os.path.join(PLUGIN_DIR, 'icon', 'file_vectorial.png'),
    GEOPACKAGE: os.path.join(PLUGIN_DIR, 'icon', 'file_vectorial.png'),
}
RASTER_ICON = os.path.join(PLUGIN_DIR, 'icon', 'file_raster.png')
PATH_ROLE = Qt.ItemDataRole.UserRole  #Donde se guarda la ruta en cada elemento del árbol
KIND_ROLE = Qt.ItemDataRole.UserRole + 1  #Tipo de elemento (carpeta, vectorial, GeoPackage, ráster)
LAYER_ROLE = Qt.ItemDataRole.UserRole + 2  #Nombre de la capa interna (solo en las capas de un GeoPackage)


def normalizar(texto):
    """Texto en minúsculas y sin tildes, para que la búsqueda encuentre 'Nerja' al escribir 'nerja' y 'via' en 'vía'."""
    return ''.join(c for c in unicodedata.normalize('NFD', texto.lower()) if unicodedata.category(c) != 'Mn')


class ProjectBuilderDockWidget(QtWidgets.QDockWidget, FORM_CLASS):



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
        self.treeWidget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)  #Las capas se eligen con las casillas, no seleccionando filas
        self.add_filter_box()
        self.treeWidget.clear()
        self.load_wms_combo()  #Llamar a funcion añade wms a combo al inicio


    def warn(self, message):
        """Muestra un aviso al usuario."""
        QMessageBox.warning(self, "Error", message)

    def add_filter_box(self):
        """
        Coloca una caja de búsqueda justo encima del árbol de capas.
        Se crea por código para no tener que editar el .ui: se sustituye el árbol por un bloque (búsqueda + árbol).
        """
        layout = self.treeWidget.parentWidget().layout()
        row, column, row_span, column_span = layout.getItemPosition(layout.indexOf(self.treeWidget))
        layout.removeWidget(self.treeWidget)
        bloque = QWidget()
        vbox = QVBoxLayout(bloque)
        vbox.setContentsMargins(0, 0, 0, 0)
        self.filterBox = QgsFilterLineEdit()
        self.filterBox.setShowSearchIcon(True)
        self.filterBox.setPlaceholderText("Buscar capas o carpetas…")
        self.filterBox.textChanged.connect(self.apply_filter)  #Se filtra mientras se escribe
        vbox.addWidget(self.filterBox)
        vbox.addWidget(self.treeWidget)
        layout.addWidget(bloque, row, column, row_span, column_span)

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
        self.filterBox.clear()
        if os.path.isdir(folder):
            self._add_tree_items(self.treeWidget, scan_folder(folder))

    def _add_tree_items(self, parent, entries):
        for entry in entries:
            item = QTreeWidgetItem(parent, [entry.name])
            item.setData(0, PATH_ROLE, entry.path)  #Se le guarda la ruta al objeto internamente (se ve en el panel el nombre, pero no la ruta)
            item.setData(0, KIND_ROLE, entry.kind)
            item.setData(0, LAYER_ROLE, entry.layer)
            item.setIcon(0, QIcon(ICONS.get(entry.kind, RASTER_ICON)))
            # Casilla de verificación. En las carpetas, AutoTristate hace que marcar la carpeta marque todo su contenido
            # (y si solo hay algunos elementos marcados, la casilla de la carpeta aparece a medias)
            flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if entry.kind in (FOLDER, GEOPACKAGE):  #El GeoPackage también: marcarlo marca todas sus capas internas
                flags |= Qt.ItemFlag.ItemIsAutoTristate
            item.setFlags(flags)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            self._add_tree_items(item, entry.children)  #Recursivo: añade el contenido de las subcarpetas

    def selected_sources(self):
        """
        Lo que hay que copiar al proyecto, como lista de (ruta, capas):
        - carpetas y ficheros marcados: (ruta, None)
        - GeoPackage marcado entero: (ruta, None) -> se exportan todas sus capas
        - GeoPackage marcado a medias: (ruta, [nombres de las capas marcadas])
        """
        sources = []

        def recorrer(item):
            estado = item.checkState(0)
            if item.data(0, KIND_ROLE) == GEOPACKAGE:
                if estado == Qt.CheckState.Checked:
                    sources.append((item.data(0, PATH_ROLE), None))
                elif estado == Qt.CheckState.PartiallyChecked:
                    capas = [item.child(i).data(0, LAYER_ROLE) for i in range(item.childCount())
                             if item.child(i).checkState(0) == Qt.CheckState.Checked]
                    sources.append((item.data(0, PATH_ROLE), capas))
                return  #Sus capas internas ya están incluidas: no se recorren como elementos sueltos
            if estado == Qt.CheckState.Checked:
                sources.append((item.data(0, PATH_ROLE), None))
            for i in range(item.childCount()):
                recorrer(item.child(i))  #Llamada recursiva: repite lo mismo dentro de cada subcarpeta

        for i in range(self.treeWidget.topLevelItemCount()):
            recorrer(self.treeWidget.topLevelItem(i))
        return sources

    def apply_filter(self, texto):
        """Muestra solo los elementos cuyo nombre contiene el texto (y las carpetas que los contienen)."""
        texto = normalizar(texto.strip())

        def filtrar(item, padre_coincide):
            coincide = padre_coincide or texto in normalizar(item.text(0))  #Si una carpeta coincide, se ve todo su contenido
            hijos_visibles = [filtrar(item.child(i), coincide) for i in range(item.childCount())]  #Lista (no any) para recorrer todos
            visible = coincide or any(hijos_visibles)
            item.setHidden(not visible)
            if texto and any(hijos_visibles):
                item.setExpanded(True)  #Se despliegan las carpetas para ver lo encontrado
            return visible

        for i in range(self.treeWidget.topLevelItemCount()):
            filtrar(self.treeWidget.topLevelItem(i), not texto)

    # ------------------------------------------------------------------ Servicios WMS

    def load_wms_combo(self):
        """Añadir nombres wms a combo (se leen de services.json)"""
        self.wmsComboBox.clear()
        try:
            self.services = load_services()
        except ServicesError as e:  #Si services.json tiene un error, se avisa y el plugin sigue funcionando sin WMS
            self.services = {}
            self.iface.messageBar().pushMessage("ProjectBuilder", str(e), level=Qgis.MessageLevel.Critical, duration=0)
        self.wmsComboBox.addItems(list(self.services.keys()))

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
        if self.addWMS.isChecked() and not self.wmsComboBox.checkedItems():
            return "No ha seleccionado ningún WMS"
        hay_capas = bool(self.selected_sources())
        if not hay_capas and not self.addWMS.isChecked():  #Hace falta al menos una capa o un servicio WMS
            return "No se ha marcado ninguna capa ni ningún servicio WMS"
        if hay_capas:  #La carpeta de capas solo se comprueba si se van a copiar capas (un proyecto solo con WMS no la necesita)
            if not os.path.isdir(folder_layers):
                return "Acceso a capas no válido"
            # Evitar sobrescribir los datos de origen: el proyecto no puede estar en la carpeta de capas ni dentro de ella
            origen = os.path.normcase(os.path.abspath(folder_layers))
            destino = os.path.normcase(os.path.abspath(folder_project))
            if destino == origen or destino.startswith(origen + os.sep):
                return "La carpeta del proyecto no puede ser la carpeta de capas ni estar dentro de ella"
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
        jobs = []  #(origen, destino, capas) de las capas a exportar
        for path_source, layers in self.selected_sources():
            # Misma estructura de subcarpetas que el origen, dentro de la carpeta del proyecto
            path_target = os.path.join(folder_project, os.path.relpath(path_source, folder_layers))
            if os.path.isdir(path_source):  #Comprobar si es un directorio
                os.makedirs(path_target, exist_ok=True)  #Crear directorio de forma recursiva
            else:
                jobs.append((path_source, path_target, layers))

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
                    qgis_project.add_wms(project, group, wms, self.services[wms].uri())
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
