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

from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsProject
from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtCore import QSettings, Qt, QTimer
from qgis.PyQt.QtWidgets import QAbstractItemView, QFileDialog, QMessageBox, QPushButton, QTreeWidgetItem

from .core import project as qgis_project
from .core.formats import (
    CONVERT,
    FOLDER,
    KEEP,
    MULTILAYER,
    RASTER,
    SINGLE,
    VECTOR,
    layer_kind,
    output_path,
    style_path,
    vector_sublayers,
)
from .core.scanner import LINE, POINT, POLYGON, TABLE, scan_folder
from .core.services import ServicesError, load_services
from .core.task import ExportTask, Job

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'project_builder_dockwidget_base.ui'))
PLUGIN_DIR = os.path.dirname(__file__)

# Iconos nativos de QGIS (se adaptan al tema claro/oscuro): según el tipo de elemento y, en vectoriales, la geometría
ICONS = {
    FOLDER: '/mIconFolder.svg',
    MULTILAYER: '/mGeoPackage.svg',
    RASTER: '/mIconRasterLayer.svg',
    POINT: '/mIconPointLayer.svg',
    LINE: '/mIconLineLayer.svg',
    POLYGON: '/mIconPolygonLayer.svg',
    TABLE: '/mIconVector.svg',  #Geometría desconocida o sin geometría: icono genérico de capa vectorial
}
MODE_NAMES = {SINGLE: "un solo GeoPackage", CONVERT: "un GeoPackage por capa", KEEP: "formato original"}
PATH_ROLE = Qt.ItemDataRole.UserRole  #Donde se guarda la ruta en cada elemento del árbol
KIND_ROLE = Qt.ItemDataRole.UserRole + 1  #Tipo de elemento (carpeta, vectorial, multicapa, ráster)
LAYER_ROLE = Qt.ItemDataRole.UserRole + 2  #Nombre de la capa interna (solo en las capas de un fichero multicapa)
SETTINGS = 'project_builder/'  #Prefijo de las opciones que el plugin guarda en la configuración de QGIS


def normalizar(texto):
    """Texto en minúsculas y sin tildes, para que la búsqueda encuentre 'Nerja' al escribir 'nerja' y 'via' en 'vía'."""
    return ''.join(c for c in unicodedata.normalize('NFD', texto.lower()) if unicodedata.category(c) != 'Mn')


def nombre_unico(nombre, usados):
    """Devuelve nombre, o nombre_2, nombre_3... si ya está en usados (sin distinguir mayúsculas). Lo añade a usados."""
    candidato, n = nombre, 2
    while candidato.lower() in usados:
        candidato = f"{nombre}_{n}"
        n += 1
    usados.add(candidato.lower())
    return candidato


def dentro_de(ruta, carpeta):
    """True si ruta es carpeta o está dentro de ella."""
    ruta, carpeta = os.path.normcase(os.path.abspath(ruta)), os.path.normcase(os.path.abspath(carpeta))
    return ruta == carpeta or ruta.startswith(carpeta.rstrip(os.sep) + os.sep)


class ProjectBuilderDockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    def __init__(self, iface, parent=None):
        """Constructor."""
        super().__init__(parent)
        self.setupUi(self)

        self.iface = iface
        self.task = None  #Tarea de exportación en curso (se guarda para que Python no la elimine antes de tiempo)

        # Iconos de los botones (nativos de QGIS)
        self.addFolderButton.setIcon(QgsApplication.getThemeIcon('/symbologyAdd.svg'))
        self.removeFolderButton.setIcon(QgsApplication.getThemeIcon('/symbologyRemove.svg'))
        self.resetButton.setIcon(QgsApplication.getThemeIcon('/mActionFileNew.svg'))
        self.filterBox.setShowSearchIcon(True)

        # Formatos de salida
        self.outputFormat.addItem("Un solo GeoPackage + GeoTIFF (recomendado)", SINGLE)
        self.outputFormat.addItem("Un GeoPackage por capa + GeoTIFF", CONVERT)
        self.outputFormat.addItem("Conservar el formato original", KEEP)
        self.outputFormat.setToolTip(
            "Un solo GeoPackage: todas las capas vectoriales en <proyecto>.gpkg (con sus estilos dentro);\n"
            "  los ráster en GeoTIFF comprimido, en carpetas como las de origen. Las carpetas de origen pasan a ser grupos.\n"
            "Un GeoPackage por capa: cada vectorial en su .gpkg, conservando la estructura de carpetas.\n"
            "Conservar: cada capa mantiene su formato; si GDAL no puede escribirlo (ECW, MrSID, DXF, GPX...)\n"
            "  se convierte igualmente. Los ficheros con varias capas siempre salen en GeoPackage.")

        # Disparadores
        self.addFolderButton.clicked.connect(self.select_layers_folder)
        self.removeFolderButton.clicked.connect(self.remove_current_folder)
        self.filterBox.textChanged.connect(self.apply_filter)  #Se filtra mientras se escribe
        self.selectFolderProject.clicked.connect(self.select_project_folder)
        self.resetButton.clicked.connect(self.reset_form)
        self.createProject.clicked.connect(lambda: self.create_project())  #lambda: la señal clicked envía un True/False que no queremos recibir
        self.treeWidget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)  #Las capas se eligen con las casillas, no seleccionando filas
        self.treeWidget.clear()
        self.load_wms_combo()  #Llamar a funcion añade wms a combo al inicio
        self.load_last_crs()
        self.selectProjection.crsChanged.connect(self.remember_crs)

        # Resumen en vivo de lo que se va a generar. Se recalcula con un pequeño retardo: al marcar una carpeta
        # Qt avisa una vez por cada elemento que cambia, y así se calcula una sola vez al final.
        self.summaryTimer = QTimer(self)
        self.summaryTimer.setSingleShot(True)
        self.summaryTimer.setInterval(50)
        self.summaryTimer.timeout.connect(self.update_summary)
        for senal in (self.treeWidget.itemChanged, self.wmsComboBox.checkedItemsChanged, self.addWMS.toggled,
                      self.outputFormat.currentIndexChanged, self.nameProject.textChanged, self.pathFolderProject.textChanged,
                      self.reprojectCheck.toggled, self.selectProjection.crsChanged):
            senal.connect(lambda *args: self.summaryTimer.start())
        self.update_summary()

    def load_last_crs(self):
        """SRC inicial: el último usado (se recuerda entre sesiones) o, la primera vez, el del proyecto abierto en QGIS."""
        crs = QgsCoordinateReferenceSystem(QSettings().value(SETTINGS + 'last_crs', ''))
        if not crs.isValid():
            crs = QgsProject.instance().crs()
        if not crs.isValid():
            crs = QgsCoordinateReferenceSystem('EPSG:25830')  #ETRS89 / UTM 30N (España peninsular)
        self.selectProjection.setCrs(crs)

    def remember_crs(self, crs):
        if crs.isValid():
            QSettings().setValue(SETTINGS + 'last_crs', crs.authid() or crs.toWkt())

    def warn(self, message):
        """Muestra un aviso al usuario."""
        QMessageBox.warning(self, "Error", message)

    def reset_form(self):
        """Vacía el formulario: carpetas, capas marcadas, nombre, destino, WMS y formato. Se mantiene el SRC."""
        self.treeWidget.clear()
        self.filterBox.clear()
        self.nameProject.clear()
        self.pathFolderProject.clear()
        self.outputFormat.setCurrentIndex(0)  #Modo recomendado
        self.reprojectCheck.setChecked(True)
        self.addWMS.setChecked(False)
        self.wmsComboBox.deselectAllOptions()
        self.update_summary()

    # ------------------------------------------------------------------ Selección de carpetas

    @staticmethod
    def _last_dir(key):
        """Última carpeta usada en un diálogo (se recuerda entre sesiones de QGIS)."""
        return QSettings().value(SETTINGS + key, '')

    @staticmethod
    def _remember_dir(key, folder):
        QSettings().setValue(SETTINGS + key, folder)

    def select_project_folder(self):
        folder = QFileDialog.getExistingDirectory(None, "Selecciona Carpeta", self._last_dir('last_project_dir'),
                                                  QFileDialog.Option.DontResolveSymlinks)
        if folder:
            self._remember_dir('last_project_dir', folder)
            self.pathFolderProject.setText(folder)

    def select_layers_folder(self):
        folder = QFileDialog.getExistingDirectory(None, "Añadir carpeta de capas", self._last_dir('last_layers_dir'),
                                                  QFileDialog.Option.DontResolveSymlinks)
        if folder:
            self._remember_dir('last_layers_dir', os.path.dirname(folder))  #Se abre en la carpeta "madre", para elegir otra hermana fácilmente
            self.add_source_folder(folder)

    def source_folders(self):
        """Rutas de las carpetas de capas añadidas (las raíces del árbol)."""
        return [self.treeWidget.topLevelItem(i).data(0, PATH_ROLE) for i in range(self.treeWidget.topLevelItemCount())]

    def add_source_folder(self, folder):
        """Añade una carpeta de capas como nueva raíz del árbol (sin perder lo ya marcado en las demás)."""
        if not os.path.isdir(folder):
            return self.warn(f"La carpeta no existe: {folder}")
        for existente in self.source_folders():  #No se permite repetir una carpeta ni añadir una que ya esté dentro de otra
            if dentro_de(folder, existente) or dentro_de(existente, folder):
                return self.warn(f"Esa carpeta ya está incluida (o incluye a otra) del árbol:\n{existente}")
        raiz = QTreeWidgetItem(self.treeWidget, [os.path.basename(os.path.normpath(folder)) or folder])
        raiz.setToolTip(0, folder)  #Al pasar el ratón se ve la ruta completa
        self._setup_item(raiz, folder, FOLDER, None)
        self._add_tree_items(raiz, scan_folder(folder))
        raiz.setExpanded(True)
        self.apply_filter(self.filterBox.text())  #Si hay una búsqueda escrita, se aplica también a la carpeta nueva
        self.update_summary()

    def remove_current_folder(self):
        """Quita del árbol la carpeta de capas a la que pertenece el elemento en el que se ha hecho clic."""
        item = self.treeWidget.currentItem()
        if item is None:
            return self.warn("Haz clic en la carpeta que quieres quitar (o en cualquier capa suya)")
        while item.parent() is not None:  #Se sube hasta la raíz (la carpeta añadida)
            item = item.parent()
        self.treeWidget.takeTopLevelItem(self.treeWidget.indexOfTopLevelItem(item))
        self.update_summary()

    def load_tree(self, folder):
        """Deja el árbol solo con la carpeta indicada (se mantiene por compatibilidad con las pruebas)."""
        self.treeWidget.clear()
        self.filterBox.clear()
        self.add_source_folder(folder)

    # ------------------------------------------------------------------ Árbol de capas

    def _setup_item(self, item, path, kind, layer, geometry=None):
        item.setData(0, PATH_ROLE, path)  #Se le guarda la ruta al objeto internamente (se ve en el panel el nombre, pero no la ruta)
        item.setData(0, KIND_ROLE, kind)
        item.setData(0, LAYER_ROLE, layer)
        item.setIcon(0, QgsApplication.getThemeIcon(ICONS.get(geometry or kind, ICONS[TABLE])))
        # Casilla de verificación. En las carpetas, AutoTristate hace que marcar la carpeta marque todo su contenido
        # (y si solo hay algunos elementos marcados, la casilla de la carpeta aparece a medias)
        flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
        if kind in (FOLDER, MULTILAYER):  #Los ficheros multicapa también: marcarlos marca todas sus capas internas
            flags |= Qt.ItemFlag.ItemIsAutoTristate
        item.setFlags(flags)
        item.setCheckState(0, Qt.CheckState.Unchecked)

    def _add_tree_items(self, parent, entries):
        for entry in entries:
            item = QTreeWidgetItem(parent, [entry.name])
            self._setup_item(item, entry.path, entry.kind, entry.layer, entry.geometry)
            self._add_tree_items(item, entry.children)  #Recursivo: añade el contenido de las subcarpetas

    def selected_sources(self):
        """
        Lo que hay que copiar al proyecto, como lista de (carpeta raíz, ruta, capas):
        - carpetas y ficheros marcados: capas = None
        - fichero multicapa (GeoPackage...) marcado entero: capas = None -> se exportan todas sus capas
        - fichero multicapa marcado a medias: capas = [nombres de las capas marcadas]
        """
        sources = []

        def recorrer(item, raiz):
            estado = item.checkState(0)
            if item.data(0, KIND_ROLE) == MULTILAYER:
                if estado == Qt.CheckState.Checked:
                    sources.append((raiz, item.data(0, PATH_ROLE), None))
                elif estado == Qt.CheckState.PartiallyChecked:
                    capas = [item.child(i).data(0, LAYER_ROLE) for i in range(item.childCount())
                             if item.child(i).checkState(0) == Qt.CheckState.Checked]
                    sources.append((raiz, item.data(0, PATH_ROLE), capas))
                return  #Sus capas internas ya están incluidas: no se recorren como elementos sueltos
            if estado == Qt.CheckState.Checked and item.parent() is not None:  #La raíz en sí no se copia, solo su contenido
                sources.append((raiz, item.data(0, PATH_ROLE), None))
            for i in range(item.childCount()):
                recorrer(item.child(i), raiz)  #Llamada recursiva: repite lo mismo dentro de cada subcarpeta

        for i in range(self.treeWidget.topLevelItemCount()):
            raiz = self.treeWidget.topLevelItem(i)
            recorrer(raiz, raiz.data(0, PATH_ROLE))
        return sources

    def count_layers(self):
        """Número de capas que se van a exportar (las de los ficheros multicapa cuentan una a una)."""
        total = 0
        for _raiz, path, layers in self.selected_sources():
            if os.path.isdir(path):
                continue
            total += len(layers) if layers is not None else len(self._item_layers(path)) or 1
        return total

    def _item_layers(self, path):
        """Capas internas de un fichero multicapa según el árbol (sin volver a leer el disco)."""
        def buscar(item):
            if item.data(0, KIND_ROLE) == MULTILAYER and item.data(0, PATH_ROLE) == path:
                return [item.child(i).data(0, LAYER_ROLE) for i in range(item.childCount())]
            for i in range(item.childCount()):
                encontrado = buscar(item.child(i))
                if encontrado is not None:
                    return encontrado
            return None
        return buscar(self.treeWidget.invisibleRootItem()) or []

    def update_summary(self):
        """Texto bajo el formulario con lo que se va a generar, p. ej. '7 capas · 2 WMS · un solo GeoPackage → ...qgz'."""
        capas = self.count_layers()
        wms = len(self.wmsComboBox.checkedItems()) if self.addWMS.isChecked() else 0
        partes = [f"{capas} capa{'s' if capas != 1 else ''}"]
        if wms:
            partes.append(f"{wms} WMS")
        if capas:
            partes.append(MODE_NAMES.get(self.outputFormat.currentData(), ''))
            if self.reprojectCheck.isChecked():  #Deja claro qué se hace con el SRC de las capas
                partes.append(f"reproyectadas a {self.selectProjection.crs().authid() or 'SRC del proyecto'}")
            else:
                partes.append("en su SRC original")
        texto = " · ".join(partes)
        nombre, carpeta = self.nameProject.text().strip(), self.pathFolderProject.text().strip()
        if nombre and carpeta:
            texto += f"  →  {os.path.join(carpeta, nombre + '.qgz')}"
        self.summaryLabel.setText(texto)

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
            raiz = self.treeWidget.topLevelItem(i)
            for j in range(raiz.childCount()):  #Las carpetas añadidas (raíces) siempre se ven
                filtrar(raiz.child(j), not texto)

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
        if not name:
            return "No se ha introducido un nombre para el proyecto"
        if not folder_project.strip():
            return "No se ha indicado la carpeta del proyecto"
        if os.path.exists(folder_project) and not os.path.isdir(folder_project):
            return "La ruta del proyecto es un fichero, no una carpeta"
        if self.addWMS.isChecked() and not self.wmsComboBox.checkedItems():
            return "No ha seleccionado ningún WMS"
        if not self.selected_sources() and not self.addWMS.isChecked():  #Hace falta al menos una capa o un servicio WMS
            return "No se ha marcado ninguna capa ni ningún servicio WMS"
        # Evitar sobrescribir los datos de origen: el proyecto no puede estar en ninguna carpeta de capas ni dentro de ella
        for carpeta in self.source_folders():
            if dentro_de(folder_project, carpeta):
                return f"La carpeta del proyecto no puede ser una carpeta de capas ni estar dentro de ella:\n{carpeta}"
        return None

    def build_jobs(self, folder_project, name, mode):
        """
        Prepara la lista de trabajos (Job) a partir de lo marcado en el árbol.
        - Cada carpeta añadida es un grupo del proyecto (y, en los modos de ficheros sueltos, una subcarpeta).
        - En el modo "un solo GeoPackage", todos los vectoriales van como tablas de <nombre>.gpkg.
        """
        gpkg = os.path.join(folder_project, name + '.gpkg')
        nombres_raiz = {}  #Carpeta raíz -> nombre de grupo/subcarpeta (único, por si dos carpetas se llaman igual)
        raices_usadas, tablas_usadas, rutas_usadas = set(), set(), set()
        jobs = []
        for raiz, path_source, layers in self.selected_sources():
            if raiz not in nombres_raiz:
                nombres_raiz[raiz] = nombre_unico(os.path.basename(os.path.normpath(raiz)) or 'capas', raices_usadas)
            rel = os.path.relpath(path_source, raiz)
            if os.path.isdir(path_source):  #Comprobar si es un directorio
                if mode != SINGLE:
                    os.makedirs(os.path.join(folder_project, nombres_raiz[raiz], rel), exist_ok=True)  #Crear directorio de forma recursiva
                continue
            kind = layer_kind(path_source)
            carpetas = [p for p in os.path.dirname(rel).split(os.sep) if p]
            group = (nombres_raiz[raiz], *carpetas)
            if kind == MULTILAYER:  #Las capas de un fichero multicapa van en un grupo con el nombre del fichero
                group = (*group, os.path.splitext(os.path.basename(path_source))[0])

            if mode == SINGLE and kind != RASTER:
                capas = layers if layers is not None else [s.name() for s in vector_sublayers(path_source)]
                una_capa = len(capas) == 1 and kind == VECTOR
                tablas = {capa: nombre_unico(os.path.splitext(os.path.basename(path_source))[0] if una_capa else capa, tablas_usadas)
                          for capa in capas}
                jobs.append(Job(path_source, gpkg, group, tables=tablas, qml=style_path(path_source) if una_capa else None))
                continue

            # Misma estructura de subcarpetas que el origen, dentro de la carpeta del proyecto
            # (en el modo "un solo GeoPackage" solo llegan aquí los ráster, que salen en GeoTIFF)
            path_target = output_path(os.path.join(folder_project, nombres_raiz[raiz], rel), kind, CONVERT if mode == SINGLE else mode)
            base, ext = os.path.splitext(path_target)
            path_target = nombre_unico(base, rutas_usadas) + ext  #p. ej. rios.shp y rios.geojson convertidos ambos a rios.gpkg
            jobs.append(Job(path_source, path_target, group, layers=layers))
        return jobs

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
        name = self.nameProject.text().strip()
        try:
            os.makedirs(folder_project, exist_ok=True)  #Si la carpeta del proyecto no existe, se crea (con las intermedias que falten)
        except OSError as e:
            return self.warn(f"No se pudo crear la carpeta del proyecto:\n{folder_project}\n\n{e}")
        gpkg = os.path.join(folder_project, name + '.gpkg')
        if self.outputFormat.currentData() == SINGLE and os.path.exists(gpkg):
            try:
                os.remove(gpkg)  #Se empieza con un GeoPackage limpio (si no, se mezclarían tablas de un proyecto anterior)
            except OSError:
                return self.warn(f"No se puede sobrescribir {gpkg}.\n¿Está abierto en QGIS? Ciérralo o elige otro nombre.")
        jobs = self.build_jobs(folder_project, name, self.outputFormat.currentData())

        crs = self.selectProjection.crs() if self.reprojectCheck.isChecked() else None  #None: se copian en su SRC original
        self.task = ExportTask(jobs, crs)
        if background:
            self.createProject.setEnabled(False)  #Evita lanzar dos veces la creación mientras se exporta
            self.resetButton.setEnabled(False)
            self.task.taskCompleted.connect(lambda: self.finish_project(True))
            self.task.taskTerminated.connect(lambda: self.finish_project(False))
            QgsApplication.taskManager().addTask(self.task)  #QGIS muestra el progreso abajo a la derecha
        else:
            self.finish_project(self.task.run())

    def finish_project(self, completed):
        """Se ejecuta al terminar la exportación: crea el proyecto con las capas exportadas, añade los WMS y lo guarda."""
        self.createProject.setEnabled(True)
        self.resetButton.setEnabled(True)
        task, self.task = self.task, None
        if not completed:
            return self.iface.messageBar().pushMessage("ProjectBuilder", "Creación del proyecto cancelada",
                                                       level=Qgis.MessageLevel.Warning, duration=5)

        project = qgis_project.create_project(self.pathFolderProject.text(), self.nameProject.text().strip(),
                                              self.selectProjection.crs())
        errors = list(task.errors)  #Se acumulan los errores para mostrarlos todos juntos al final
        for output in task.outputs:
            try:
                if output.tables:  #Tablas del GeoPackage común
                    qgis_project.add_geopackage_tables(project, output.path, output.tables, output.group, output.qml)
                else:
                    qgis_project.add_layer(project, output.path, output.group)
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
