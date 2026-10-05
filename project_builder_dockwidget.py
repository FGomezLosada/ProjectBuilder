"""
ProjectBuilder - Panel (dock) con la interfaz del plugin.

Aquí solo está la parte visual (botones, árbol, mensajes). La lógica de exportar capas
y construir el proyecto está en la carpeta core/.

copyright : (C) 2023 by Francisco Gómez Losada
email     : pgomezlosada@gmail.com
license   : GNU GPL v2 or later
"""

import datetime
from functools import partial
import os
import unicodedata

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsNetworkAccessManager,
    QgsProject,
    QgsGeometry,
    QgsIconUtils,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.gui import QgsExtentWidget
from qgis.PyQt import QtWidgets, sip, uic
from qgis.PyQt.QtCore import QMimeData, QSettings, Qt, QTimer, QUrl
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QToolButton,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .core import configs
from .core import database
from .core import icons
from .core import layouts
from .core import open_project
from .core import stats
from .core import project as qgis_project
from .core import services as svc
from .core.clip import (
    ZONE_TABLE,
    ZoneError,
    apply_margin,
    geometry_from_extent,
    geometry_from_layer,
    view_extent,
    write_zone,
    zone_uri,
)
from .core.capabilities import detect_type, parse_capabilities
from .core.health import HealthTask, check_due
from .core.formats import (
    CONTAINER_EXTENSIONS,
    CONVERT,
    FOLDER,
    KEEP,
    MULTILAYER,
    RASTER,
    SINGLE,
    VECTOR,
    extension,
    layer_kind,
    output_path,
    style_path,
    vector_sublayers,
)
from .core.scanner import LINE, POINT, POLYGON, TABLE, scan_folder
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
SERVICE_ICONS = {svc.WMS: '/mIconWms.svg', svc.WMTS: '/mIconWms.svg', svc.WFS: '/mIconVector.svg'}
MODE_NAMES = {SINGLE: "un solo GeoPackage", CONVERT: "un GeoPackage por capa", KEEP: "formato original"}
PATH_ROLE = Qt.ItemDataRole.UserRole  #Donde se guarda la ruta en cada elemento del árbol
KIND_ROLE = Qt.ItemDataRole.UserRole + 1  #Tipo de elemento (carpeta, vectorial, multicapa, ráster)
LAYER_ROLE = Qt.ItemDataRole.UserRole + 2  #Nombre de la capa interna (solo en las capas de un fichero multicapa)
SERVICE_ROLE = Qt.ItemDataRole.UserRole + 3  #Servicio web (diccionario) de cada elemento del árbol de servicios
LAYOUT_ROLE = Qt.ItemDataRole.UserRole + 5  #Composición de cada elemento de la lista: ['proyecto', nombre] o ['fichero', ruta]
NODE_ROLE = Qt.ItemDataRole.UserRole + 4  #Tipo de nodo del árbol de servicios: raíz, grupo, servicio (desplegable) o capa
PROJECT_ROOT, PROJECT_GROUP, PROJECT_LAYER = 'proyecto', 'grupo_proyecto', 'capa_proyecto'  #Bloque del proyecto abierto
DB_ROOT, DB_SCHEMA, DB_TABLE = 'basedatos', 'esquema', 'tabla_bd'  #Bloques de bases de datos (PostGIS, SpatiaLite)
DB_ROLE = Qt.ItemDataRole.UserRole + 6  #Datos de una tabla de base de datos (proveedor, conexión, esquema, tabla, uri)
DB_GEOMETRY = {Qgis.GeometryType.Point: POINT, Qgis.GeometryType.Line: LINE, Qgis.GeometryType.Polygon: POLYGON}
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


def _items_de(item):
    """Todos los elementos que cuelgan de item (recorrido recursivo, sin QTreeWidgetItemIterator)."""
    for i in range(item.childCount()):
        yield item.child(i)
        yield from _items_de(item.child(i))


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
        self.statsButton.clicked.connect(self.show_layers_report)
        self.statsButton.setIcon(QgsApplication.getThemeIcon('/mAlgorithmBasicStatistics.svg'))
        self.createProject.clicked.connect(lambda: self.create_project())  #lambda: la señal clicked envía un True/False que no queremos recibir
        self.treeWidget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)  #Las capas se eligen con las casillas, no seleccionando filas
        self.treeWidget.clear()
        self.newConnectionButton.setIcon(QgsApplication.getThemeIcon('/symbologyAdd.svg'))
        self.refreshServicesButton.setText("⟳")
        menu = QMenu(self.newConnectionButton)  #Abre el diálogo de QGIS para crear una conexión nueva
        menu.addAction("Nueva conexión WMS / WMTS…", lambda: self.iface.openDataSourceManagerPage('wms'))
        menu.addAction("Nueva conexión WFS…", lambda: self.iface.openDataSourceManagerPage('wfs'))
        self.newConnectionButton.setMenu(menu)
        self.newConnectionButton.setPopupMode(self.newConnectionButton.ToolButtonPopupMode.InstantPopup)
        self.refreshServicesButton.setToolTip("Volver a leer las conexiones y comprobar ahora todos los servicios")
        self.refreshServicesButton.clicked.connect(lambda: (self.load_services_tree(), self.start_health_check(force=True)))
        self.favoriteButton.clicked.connect(self.toggle_favorite)
        self.servicesFilter.textChanged.connect(self.apply_services_filter)
        self.servicesTree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.servicesTree.itemExpanded.connect(self.load_service_layers)  #Las capas de un servicio se piden al desplegarlo
        self.favoritesDefault.setChecked(QSettings().value(SETTINGS + 'favorites_default', False, type=bool))
        self.favoritesDefault.toggled.connect(lambda v: QSettings().setValue(SETTINGS + 'favorites_default', v))
        self.config_services = []  #Capas de servicios de una configuración que no están a la vista en el árbol
        self.pending = {}  #Peticiones GetCapabilities en curso (se guardan para que no se eliminen antes de tiempo)
        self.health_task = None  #Comprobación automática de servicios en curso
        self.load_services_tree()
        # Unos segundos después de abrir el panel (si toca: una vez por semana). El temporizador es «hijo» del panel:
        # si el panel se cierra antes, el temporizador desaparece con él y la revisión no llega a lanzarse.
        self.healthTimer = QTimer(self)
        self.healthTimer.setSingleShot(True)
        self.healthTimer.timeout.connect(self.start_health_check)
        self.healthTimer.start(3000)
        self.apply_favorites_default()
        self.load_last_crs()
        self.selectProjection.crsChanged.connect(self.remember_crs)
        self.setup_zone()
        self.setup_open_project()
        self.setup_databases()
        self.setup_layouts()
        self.setup_configs()

        # Resumen en vivo de lo que se va a generar. Se recalcula con un pequeño retardo: al marcar una carpeta
        # Qt avisa una vez por cada elemento que cambia, y así se calcula una sola vez al final.
        self.summaryTimer = QTimer(self)
        self.summaryTimer.setSingleShot(True)
        self.summaryTimer.setInterval(50)
        self.summaryTimer.timeout.connect(self.update_summary)
        for senal in (self.treeWidget.itemChanged, self.servicesTree.itemChanged, self.addWMS.toggled,
                      self.outputFormat.currentIndexChanged, self.nameProject.textChanged, self.pathFolderProject.textChanged,
                      self.reprojectCheck.toggled, self.selectProjection.crsChanged, self.groupZone.toggled,
                      self.zoneByLayer.toggled, self.zoneLayer.layerChanged, self.zoneSelected.toggled,
                      self.zoneMargin.valueChanged):
            senal.connect(self.schedule_summary)
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

    # ------------------------------------------------------------------ Informe de capas (4.6)

    def _zone_description(self):
        if not self.groupZone.isChecked():
            return "No"
        if self.zoneByLayer.isChecked():
            capa = self.zoneLayer.currentLayer()
            texto = f"Capa «{capa.name() if capa else '—'}»" + (" (elementos seleccionados)" if self.zoneSelected.isChecked() else "")
        else:
            texto = "Rectángulo"
        margen = int(self.zoneMargin.value())
        return texto + (f" + {margen} m de margen" if margen else "")

    def _report_header(self):
        """Datos generales del informe de capas."""
        crs = self.selectProjection.crs()
        return [
            ("Proyecto", self.nameProject.text().strip() or "—"),
            ("Carpeta", self.pathFolderProject.text().strip() or "—"),
            ("Fecha", datetime.datetime.now().strftime('%d/%m/%Y %H:%M')),
            ("SRC del proyecto", f"{crs.authid()} · {crs.description()}"),
            ("Formato de salida", MODE_NAMES.get(self.outputFormat.currentData(), '')),
            ("Reproyección", "Sí, todas las capas al SRC del proyecto" if self.reprojectCheck.isChecked()
             else "No, cada capa en su SRC original"),
            ("Zona de trabajo", self._zone_description()),
        ]

    def preview_rows(self):
        """
        Estadísticas de lo marcado, antes de crear el proyecto: las capas de origen recortadas «al vuelo» por la zona
        (sin escribir nada salvo la zona temporal). Lanza ZoneError si la zona no se puede calcular.
        """
        zona = None
        ruta_zona, _ = self.build_zone()
        if ruta_zona:
            capa_zona = QgsVectorLayer(zone_uri(ruta_zona), 'zona', 'ogr')
            elemento = next(capa_zona.getFeatures(), None)
            if elemento is not None:
                zona = (QgsGeometry(elemento.geometry()), capa_zona.crs())
        self.zone_area_ha = stats.layer_stats(capa_zona, ellipsoid=QgsProject.instance().ellipsoid())['superficie_ha'] \
            if zona is not None else None
        elipsoide = QgsProject.instance().ellipsoid()
        filas = []
        for raiz, path, layers in self.selected_sources():
            if os.path.isdir(path):
                continue
            carpetas = [p for p in os.path.dirname(os.path.relpath(path, raiz)).split(os.sep) if p]
            grupo = (os.path.basename(os.path.normpath(raiz)), *carpetas)
            kind = layer_kind(path)
            if kind == RASTER:
                filas.append(stats.layer_stats(QgsRasterLayer(path, os.path.splitext(os.path.basename(path))[0]), grupo))
                continue
            subcapas = vector_sublayers(path)
            for subcapa in subcapas:
                if layers is not None and subcapa.name() not in layers:
                    continue
                nombre = os.path.splitext(os.path.basename(path))[0] if len(subcapas) == 1 and kind == VECTOR else subcapa.name()
                filas.append(stats.layer_stats(QgsVectorLayer(subcapa.uri(), nombre, 'ogr'), grupo, zona, elipsoide))
        for grupos, capa in self.selected_project_layers():
            filas.append(stats.layer_stats(capa, grupos, zona if open_project.how(capa) == open_project.COPY else None, elipsoide))
        for t in self.selected_db_tables():
            filas.append(stats.layer_stats(QgsVectorLayer(t['uri'], t['tabla'], t['proveedor']), self._db_groups(t), zona, elipsoide,
                                           with_size=False))
        if self.addWMS.isChecked():
            filas += [stats.service_row(s.name) for s in self.selected_services()]
        return filas

    def show_layers_report(self):
        """Botón «Informe de capas…»: calcula al instante lo que llevará el proyecto y lo muestra en una ventana."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)  #Con capas grandes puede tardar unos segundos
        try:
            filas = self.preview_rows()
        except ZoneError as e:
            return self.warn(str(e))
        finally:
            QApplication.restoreOverrideCursor()
        if not filas:
            return self.warn("No hay capas ni servicios marcados")
        datos = self._report_header()
        if getattr(self, 'zone_area_ha', None) is not None:
            datos.append(("Superficie de la zona", f"{stats.number(self.zone_area_ha)} ha"))
        nombre = self.nameProject.text().strip() or "proyecto"
        self.show_report_dialog(stats.report_html(f"Informe de capas · {nombre}", datos, filas), filas)

    def show_report_dialog(self, contenido, filas=()):
        """Ventana con el informe de capas, con «Guardar…» (PDF, HTML o CSV) y «Copiar» (método aparte para las pruebas)."""
        dialogo = QDialog(self)
        dialogo.setWindowTitle("ProjectBuilder · Informe de capas")
        dialogo.resize(980, 600)
        disposicion = QVBoxLayout(dialogo)
        visor = QTextBrowser(dialogo)
        visor.setHtml(contenido)
        disposicion.addWidget(visor)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialogo)
        guardar = botones.addButton("Guardar…", QDialogButtonBox.ButtonRole.ActionRole)
        guardar.setToolTip("Guardar el informe como PDF (para imprimir), HTML (navegador) o CSV (tabla para Excel)")
        guardar.clicked.connect(lambda: self.save_layers_report(contenido, filas))
        copiar = botones.addButton("Copiar", QDialogButtonBox.ButtonRole.ActionRole)
        copiar.setToolTip("Copiar la tabla de capas para pegarla en Excel o Word")
        copiar.clicked.connect(lambda: self.copy_layers_report(filas))
        botones.rejected.connect(dialogo.reject)
        disposicion.addWidget(botones)
        dialogo.exec()

    def ask_save_path(self, propuesta):
        """Pide dónde y en qué formato guardar el informe (método aparte para poder probarlo sin ventanas)."""
        ruta, filtro = QFileDialog.getSaveFileName(self, "Guardar informe de capas", propuesta,
                                                   "PDF (*.pdf);;Página web (*.html);;Tabla para Excel (*.csv)")
        if ruta and not os.path.splitext(ruta)[1]:  #Si no se escribe la extensión, se toma la del formato elegido
            ruta += {'PDF': '.pdf', 'Pág': '.html', 'Tab': '.csv'}.get(filtro[:3], '.pdf')
        return ruta

    def save_layers_report(self, contenido, filas):
        """Guarda el informe en el formato que indique la extensión elegida (.pdf, .html o .csv)."""
        carpeta = self.pathFolderProject.text().strip() or self._last_dir('last_project_dir')
        nombre = self.nameProject.text().strip() or 'proyecto'
        ruta = self.ask_save_path(os.path.join(carpeta, f"informe_capas_{nombre}.pdf"))
        if not ruta:
            return None
        try:
            stats.save_report(ruta, contenido, filas)
        except OSError as e:
            return self.warn(f"No se pudo guardar el informe:\n{e}")
        self.iface.messageBar().pushMessage("ProjectBuilder", f"Informe guardado: {ruta}", level=Qgis.MessageLevel.Success, duration=8)
        return ruta

    def copy_layers_report(self, filas):
        """Copia la tabla de capas al portapapeles: como tabla en Word y como celdas en Excel."""
        datos = QMimeData()
        datos.setText(stats.rows_text(filas, '\t'))  #Excel: una celda por columna
        datos.setHtml(stats.rows_html(filas))  #Word: tabla con formato
        QApplication.clipboard().setMimeData(datos)
        self.iface.messageBar().pushMessage("ProjectBuilder", "Tabla de capas copiada al portapapeles",
                                            level=Qgis.MessageLevel.Info, duration=4)

    # ------------------------------------------------------------------ Bases de datos: PostGIS y SpatiaLite (4.7)

    def setup_databases(self):
        """Botón «Añadir base de datos» con un menú de las conexiones guardadas en QGIS (se rellena al abrirlo)."""
        self.addDatabaseButton.setIcon(QgsApplication.getThemeIcon('/mIconPostgis.svg'))
        self.addDatabaseButton.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addDatabaseButton.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.addDatabaseButton)
        menu.aboutToShow.connect(self.fill_database_menu)  #Así salen también las conexiones creadas después
        self.addDatabaseButton.setMenu(menu)

    def fill_database_menu(self):
        menu = self.addDatabaseButton.menu()
        menu.clear()
        conexiones = database.connections()
        for provider, (titulo, icono) in database.PROVIDERS.items():
            cabecera = menu.addAction(titulo)
            cabecera.setEnabled(False)
            propias = [nombre for p, nombre in conexiones if p == provider]
            for nombre in propias:
                accion = menu.addAction(QgsApplication.getThemeIcon(icono), nombre)
                accion.triggered.connect(partial(self.add_database, provider, nombre))
            if not propias:
                menu.addAction("    (no hay conexiones)").setEnabled(False)
        menu.addSeparator()
        menu.addAction("Nueva conexión PostGIS…", partial(self.iface.openDataSourceManagerPage, 'postgres'))
        menu.addAction("Nueva conexión SpatiaLite…", partial(self.iface.openDataSourceManagerPage, 'spatialite'))

    def _roots(self, kind):
        raices = (self.treeWidget.topLevelItem(i) for i in range(self.treeWidget.topLevelItemCount()))
        return [r for r in raices if r.data(0, KIND_ROLE) == kind]

    def _setup_db_item(self, item, kind, path, icon):
        item.setData(0, PATH_ROLE, path)
        item.setData(0, KIND_ROLE, kind)
        item.setData(0, LAYER_ROLE, None)
        item.setIcon(0, QgsApplication.getThemeIcon(icon))
        flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
        if kind != DB_TABLE:
            flags |= Qt.ItemFlag.ItemIsAutoTristate  #Marcar la conexión o un esquema marca todas sus tablas
        item.setFlags(flags)
        item.setCheckState(0, Qt.CheckState.Unchecked)

    def add_database(self, provider, name, *args, avisos=None):
        """
        Añade al árbol una conexión de QGIS con sus esquemas y tablas con geometría. Si avisos es una lista,
        los problemas se anotan ahí (al cargar una configuración) en lugar de mostrarse en una ventana.
        """
        avisar = avisos.append if avisos is not None else self.warn
        clave = f"{provider}:{name}"
        if any(r.data(0, PATH_ROLE) == clave for r in self._roots(DB_ROOT)):
            return avisar(f"La conexión «{name}» ya está en el árbol")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)  #Conectar a un servidor puede tardar unos segundos
        try:
            tablas = database.tables(provider, name)
        except database.DatabaseError as e:
            return avisar(str(e))
        finally:
            QApplication.restoreOverrideCursor()
        titulo, icono = database.PROVIDERS.get(provider, (provider, '/mIconDbSchema.svg'))
        raiz = QTreeWidgetItem(self.treeWidget, [name])
        raiz.setToolTip(0, f"Base de datos {titulo} · conexión «{name}» de QGIS")
        self._setup_db_item(raiz, DB_ROOT, clave, icono)
        esquemas = {}
        for t in tablas:
            padre = raiz
            if t['esquema']:  #SpatiaLite no tiene esquemas: las tablas van directamente bajo la conexión
                if t['esquema'] not in esquemas:
                    esquemas[t['esquema']] = QTreeWidgetItem(raiz, [t['esquema']])
                    self._setup_db_item(esquemas[t['esquema']], DB_SCHEMA, f"{clave}/{t['esquema']}", '/mIconDbSchema.svg')
                padre = esquemas[t['esquema']]
            item = QTreeWidgetItem(padre, [t['tabla']])
            self._setup_db_item(item, DB_TABLE, t['uri'], ICONS.get(DB_GEOMETRY.get(t['geometria']), ICONS[TABLE]))
            item.setData(0, DB_ROLE, {'proveedor': provider, 'conexion': name, 'esquema': t['esquema'], 'tabla': t['tabla'],
                                      'uri': t['uri']})
            item.setToolTip(0, (f"{t['esquema']}." if t['esquema'] else '') + t['tabla'] + (" (vista)" if t['vista'] else ""))
        if not tablas:
            aviso = QTreeWidgetItem(raiz, ["No hay tablas con geometría"])
            aviso.setDisabled(True)
        raiz.setExpanded(True)
        self.apply_filter(self.filterBox.text())
        self.update_summary()
        return raiz

    def selected_db_tables(self):
        """Tablas marcadas de las bases de datos, como diccionarios (proveedor, conexión, esquema, tabla, uri)."""
        seleccion = []

        def recorrer(item):
            for i in range(item.childCount()):
                hijo = item.child(i)
                if hijo.data(0, KIND_ROLE) == DB_TABLE and hijo.checkState(0) == Qt.CheckState.Checked:
                    seleccion.append(dict(hijo.data(0, DB_ROLE)))
                recorrer(hijo)

        for raiz in self._roots(DB_ROOT):
            recorrer(raiz)
        return seleccion

    @staticmethod
    def _db_groups(tabla):
        """Grupos del proyecto (y subcarpetas) de una tabla: conexión / esquema."""
        return (tabla['conexion'],) + ((tabla['esquema'],) if tabla['esquema'] else ())

    def build_db_jobs(self, folder_project, gpkg, mode, tablas_usadas, rutas_usadas):
        """Trabajos (Job) de las tablas marcadas. La descarga se hace luego en segundo plano (ExportTask)."""
        jobs = []
        for t in self.selected_db_tables():
            grupos = self._db_groups(t)
            nombre = open_project.safe_name(t['tabla'])
            capa = QgsVectorLayer(t['uri'], t['tabla'], t['proveedor'])  #Al abrirla se carga su estilo guardado en la BD
            estilo = open_project.save_style(capa) if capa.isValid() else None
            if mode == SINGLE:
                jobs.append(Job(t['uri'], gpkg, grupos, tables={nombre: nombre_unico(nombre, tablas_usadas)}, qml=estilo,
                                provider=t['proveedor'], db_layer=nombre))
                continue
            ruta = os.path.join(folder_project, *[open_project.safe_name(g) for g in grupos], nombre + '.gpkg')
            base, ext = os.path.splitext(output_path(ruta, VECTOR, mode))
            jobs.append(Job(t['uri'], nombre_unico(base, rutas_usadas) + ext, grupos, qml=estilo, name=t['tabla'],
                            provider=t['proveedor'], db_layer=nombre))
        return jobs

    # ------------------------------------------------------------------ Capas del proyecto abierto (4.10)

    def setup_open_project(self):
        """Bloque «Proyecto abierto en QGIS» del árbol de capas, que se actualiza solo si cambia el proyecto abierto."""
        self.projectTimer = QTimer(self)  #Al abrir un proyecto QGIS avisa muchas veces seguidas: se recalcula una sola vez
        self.projectTimer.setSingleShot(True)
        self.projectTimer.setInterval(300)
        self.projectTimer.timeout.connect(self.load_project_layers)
        proyecto = QgsProject.instance()
        raiz = proyecto.layerTreeRoot()
        for senal in (proyecto.layersAdded, proyecto.layersRemoved, proyecto.readProject, proyecto.cleared,
                      raiz.addedChildren, raiz.removedChildren, raiz.nameChanged):
            senal.connect(self.schedule_project_layers)
        self.load_project_layers()

    def schedule_project_layers(self, *args):
        """Pide actualizar el bloque del proyecto abierto (método y no lambda: ver schedule_summary)."""
        if hasattr(self, 'projectTimer'):
            self.projectTimer.start()

    def _project_root(self):
        for i in range(self.treeWidget.topLevelItemCount()):
            if self.treeWidget.topLevelItem(i).data(0, KIND_ROLE) == PROJECT_ROOT:
                return self.treeWidget.topLevelItem(i)
        return None

    def _project_leaves(self, item=None):
        """Elementos-capa del bloque del proyecto abierto."""
        item = item or self._project_root()
        if item is None:
            return []
        hojas = []
        for i in range(item.childCount()):
            hijo = item.child(i)
            if hijo.data(0, KIND_ROLE) == PROJECT_LAYER:
                hojas.append(hijo)
            hojas += self._project_leaves(hijo)
        return hojas

    def _setup_project_item(self, item, kind, icon, layer_id=None):
        item.setData(0, KIND_ROLE, kind)
        item.setData(0, PATH_ROLE, '')
        item.setData(0, LAYER_ROLE, layer_id)
        item.setIcon(0, icon)
        flags = item.flags() | Qt.ItemFlag.ItemIsUserCheckable
        if kind != PROJECT_LAYER:
            flags |= Qt.ItemFlag.ItemIsAutoTristate  #Marcar el proyecto o un grupo marca todas sus capas
        item.setFlags(flags)
        item.setCheckState(0, Qt.CheckState.Unchecked)

    def load_project_layers(self, *args):
        """
        (Re)crea el bloque «Proyecto abierto en QGIS» con el mismo árbol de grupos y capas que el panel de capas de QGIS,
        conservando lo que ya estuviera marcado. Si el proyecto abierto no tiene capas, el bloque no aparece.
        """
        marcadas = {item.data(0, LAYER_ROLE) for item in self._project_leaves() if item.checkState(0) == Qt.CheckState.Checked}
        raiz = self._project_root()
        expandida = raiz.isExpanded() if raiz is not None else True
        if raiz is not None:
            self.treeWidget.takeTopLevelItem(self.treeWidget.indexOfTopLevelItem(raiz))
        arbol = open_project.tree()
        if arbol:
            self.treeWidget.blockSignals(True)
            raiz = QTreeWidgetItem(["Proyecto abierto en QGIS"])
            self.treeWidget.insertTopLevelItem(0, raiz)  #Siempre arriba del todo
            raiz.setToolTip(0, "Capas del proyecto abierto ahora mismo en QGIS. Se copian con su estilo actual;\n"
                               "los servicios web se añaden tal cual (sin copiar datos).")
            self._setup_project_item(raiz, PROJECT_ROOT, QgsApplication.getThemeIcon('/mIconQgsProjectFile.svg'))

            def anadir(padre, hijos):
                for hijo in hijos:
                    if hijo[0] == 'grupo':
                        grupo = QTreeWidgetItem(padre, [hijo[1]])
                        self._setup_project_item(grupo, PROJECT_GROUP, QgsApplication.getThemeIcon('/mActionFolder.svg'))
                        anadir(grupo, hijo[3])
                        grupo.setExpanded(hijo[2])
                    else:
                        capa = hijo[1]
                        item = QTreeWidgetItem(padre, [capa.name()])
                        self._setup_project_item(item, PROJECT_LAYER, QgsIconUtils.iconForLayer(capa), capa.id())
                        enlazada = open_project.how(capa) == open_project.LINK
                        item.setToolTip(0, capa.publicSource() + ("\nSe añade tal cual (servicio web u otro tipo de capa): no se copian datos"
                                                                  if enlazada else "\nSe copia con su estilo actual"))
                        if capa.id() in marcadas:
                            item.setCheckState(0, Qt.CheckState.Checked)

            anadir(raiz, arbol)
            raiz.setExpanded(expandida)
            self.treeWidget.blockSignals(False)
            self.apply_filter(self.filterBox.text())
        self.schedule_summary()

    def selected_project_layers(self):
        """Capas marcadas del proyecto abierto, como lista de (grupos, capa); p. ej. (('Catastro',), <capa parcelas>)."""
        seleccion = []
        for item in self._project_leaves():
            capa = QgsProject.instance().mapLayer(item.data(0, LAYER_ROLE))
            if item.checkState(0) != Qt.CheckState.Checked or capa is None:
                continue
            grupos, padre = [], item.parent()
            while padre is not None and padre.data(0, KIND_ROLE) == PROJECT_GROUP:
                grupos.insert(0, padre.text(0))
                padre = padre.parent()
            seleccion.append((tuple(grupos), capa))
        return seleccion

    def build_project_jobs(self, folder_project, gpkg, mode, tablas_usadas, rutas_usadas):
        """
        Trabajos (Job) de las capas marcadas del proyecto abierto. Se preparan aquí, en primer plano, porque hay que leer
        las capas del proyecto: su estilo actual (.qml temporal) y, si no son de fichero, una copia en un GeoPackage temporal.
        Las capas que no se copian (servicios web...) se guardan en self.project_links para añadirlas al terminar.
        """
        jobs, self.project_links, self.prepare_errors = [], [], []
        for grupos, capa in self.selected_project_layers():
            estilo = open_project.save_style(capa)
            if open_project.how(capa) == open_project.LINK:
                copia = capa.clone()  #Misma fuente y mismo estilo, pero independiente del proyecto abierto
                if copia is None:
                    self.prepare_errors.append(f"No se pudo copiar la capa {capa.name()}")
                else:
                    copia.setName(capa.name())
                    self.project_links.append((grupos, copia))
                continue
            try:
                fuente, subcapa = open_project.prepare_copy(capa)
            except OSError as e:
                self.prepare_errors.append(str(e))
                continue
            nombre = open_project.safe_name(capa.name())
            es_vectorial = isinstance(capa, QgsVectorLayer)
            if es_vectorial and mode == SINGLE:  #Como tabla del GeoPackage común
                jobs.append(Job(fuente, gpkg, grupos, tables={subcapa: nombre_unico(nombre, tablas_usadas)}, qml=estilo))
                continue
            carpetas = [open_project.safe_name(g) for g in grupos]  #Subcarpetas = grupos del proyecto abierto
            ruta = os.path.join(folder_project, *carpetas, nombre + os.path.splitext(fuente)[1])
            path_target = output_path(ruta, VECTOR if es_vectorial else RASTER, CONVERT if mode == SINGLE else mode)
            base, ext = os.path.splitext(path_target)
            path_target = nombre_unico(base, rutas_usadas) + ext
            multicapa = es_vectorial and len(vector_sublayers(fuente)) > 1
            jobs.append(Job(fuente, path_target, grupos, layers=[subcapa] if multicapa else None, qml=estilo, name=capa.name()))
        return jobs

    # ------------------------------------------------------------------ Composiciones de impresión (4.5)

    def setup_layouts(self):
        """Lista de composiciones: las del proyecto abierto, mis plantillas .qpt y las plantillas del perfil de QGIS."""
        self.addLayoutButton.setIcon(QgsApplication.getThemeIcon('/mActionFileOpen.svg'))
        self.addLayoutButton.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.removeLayoutButton.setIcon(QgsApplication.getThemeIcon('/symbologyRemove.svg'))
        self.addLayoutButton.clicked.connect(self.add_layout_file)
        self.removeLayoutButton.clicked.connect(self.remove_layout_file)
        self.layoutsTree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.layoutsTree.itemChanged.connect(self.schedule_summary)
        # Si en QGIS se abre otro proyecto o se crea/borra una composición, la lista se actualiza sola
        proyecto = QgsProject.instance()
        proyecto.readProject.connect(self.load_layouts_tree)
        proyecto.cleared.connect(self.load_layouts_tree)
        proyecto.layoutManager().layoutAdded.connect(self.load_layouts_tree)
        proyecto.layoutManager().layoutRemoved.connect(self.load_layouts_tree)
        self.load_layouts_tree()

    @staticmethod
    def _layout_files():
        """Plantillas .qpt añadidas con el botón (se recuerdan entre sesiones de QGIS)."""
        valor = QSettings().value(SETTINGS + 'layout_files', [])
        return [valor] if isinstance(valor, str) else list(valor or [])

    @staticmethod
    def _set_layout_files(rutas):
        QSettings().setValue(SETTINGS + 'layout_files', rutas)

    def load_layouts_tree(self, *args):
        """Rellena la lista de composiciones conservando lo que ya estuviera marcado."""
        marcadas = set(self.selected_layouts())
        self.layoutsTree.blockSignals(True)
        self.layoutsTree.clear()
        bloques = [
            ("Del proyecto abierto", [('proyecto', n, n) for n in layouts.project_layouts(QgsProject.instance())]),
            ("Mis plantillas .qpt", [('fichero', r, os.path.splitext(os.path.basename(r))[0])
                                     for r in self._layout_files() if os.path.isfile(r)]),
            ("Plantillas de QGIS", [('fichero', r, os.path.splitext(os.path.basename(r))[0])
                                    for r in layouts.qgis_templates()]),
        ]
        for titulo, elementos in bloques:
            if not elementos:
                continue
            raiz = QTreeWidgetItem(self.layoutsTree, [titulo])
            raiz.setFlags(raiz.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            for tipo, valor, texto in elementos:
                item = QTreeWidgetItem(raiz, [texto])
                item.setData(0, LAYOUT_ROLE, [tipo, valor])
                item.setToolTip(0, valor if tipo == 'fichero' else f"Composición «{valor}» del proyecto abierto en QGIS")
                item.setIcon(0, QgsApplication.getThemeIcon('/mIconLayout.svg'))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Checked if (tipo, valor) in marcadas else Qt.CheckState.Unchecked)
            raiz.setExpanded(True)
        if not self.layoutsTree.topLevelItemCount():
            aviso = QTreeWidgetItem(self.layoutsTree, ["Sin composiciones: usa «Añadir plantilla .qpt…»"])
            aviso.setDisabled(True)
        self.layoutsTree.blockSignals(False)
        self.schedule_summary()

    def _layout_items(self):
        return [raiz.child(i) for raiz in (self.layoutsTree.topLevelItem(j) for j in range(self.layoutsTree.topLevelItemCount()))
                for i in range(raiz.childCount())]

    def selected_layouts(self):
        """Composiciones marcadas, como (tipo, valor): ('proyecto', nombre) o ('fichero', ruta). Sin repetir."""
        vistas = []
        for item in self._layout_items():
            clave = tuple(item.data(0, LAYOUT_ROLE))
            if item.checkState(0) == Qt.CheckState.Checked and clave not in vistas:
                vistas.append(clave)
        return vistas

    def check_layouts(self, claves):
        """Marca las composiciones indicadas [(tipo, valor)] y desmarca el resto."""
        claves = {tuple(c) for c in claves}
        for item in self._layout_items():
            marcar = tuple(item.data(0, LAYOUT_ROLE)) in claves
            item.setCheckState(0, Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked)

    def add_layout_file(self, ruta=None):
        """Añade una plantilla .qpt de cualquier carpeta a «Mis plantillas .qpt» (y la deja marcada)."""
        if not ruta:
            ruta, _ = QFileDialog.getOpenFileName(self, "Añadir plantilla de composición", self._last_dir('last_layout_dir'),
                                                  "Plantillas de composición (*.qpt)")
        if not ruta:
            return
        self._remember_dir('last_layout_dir', os.path.dirname(ruta))
        rutas = [r for r in self._layout_files() if os.path.normcase(r) != os.path.normcase(ruta)]
        self._set_layout_files([ruta, *rutas])
        marcadas = [*self.selected_layouts(), ('fichero', ruta)]
        self.load_layouts_tree()
        self.check_layouts(marcadas)

    def remove_layout_file(self):
        """Quita de la lista la plantilla .qpt en la que se ha hecho clic (no borra el fichero)."""
        item = self.layoutsTree.currentItem()
        clave = item.data(0, LAYOUT_ROLE) if item is not None else None
        if not clave or clave[0] != 'fichero' or clave[1] not in self._layout_files():
            return self.warn("Haz clic en una plantilla de «Mis plantillas .qpt» para quitarla de la lista")
        self._set_layout_files([r for r in self._layout_files() if r != clave[1]])
        self.load_layouts_tree()

    def prepare_layouts(self):
        """
        Al pulsar Crear: lista de (plantilla .qpt, nombre) a añadir. Las composiciones del proyecto abierto se copian
        ya a una plantilla temporal, por si mientras se exportan las capas se cambia de proyecto en QGIS.
        """
        trabajos = []
        for tipo, valor in self.selected_layouts():
            if tipo == 'proyecto':
                trabajos.append((layouts.snapshot_layout(QgsProject.instance(), valor), valor))
            else:
                trabajos.append((valor, None))
        return trabajos

    # ------------------------------------------------------------------ Configuraciones guardadas (4.9)

    def setup_configs(self):
        """Línea de arriba del panel: elegir, guardar y borrar configuraciones."""
        self.saveConfigButton.setIcon(QgsApplication.getThemeIcon('/mActionFileSave.svg'))
        self.deleteConfigButton.setIcon(QgsApplication.getThemeIcon('/mActionDeleteSelected.svg'))
        self.saveConfigButton.clicked.connect(self.save_current_config)
        self.deleteConfigButton.clicked.connect(self.delete_current_config)
        self.configCombo.activated.connect(self.config_chosen)  #activated: solo cuando la elige el usuario
        self.refresh_configs()

    def refresh_configs(self, select=None):
        """Rellena el desplegable con las configuraciones guardadas (y deja elegida select, si se indica)."""
        self.configCombo.blockSignals(True)
        self.configCombo.clear()
        self.configCombo.addItem("— Elegir una configuración guardada —", None)
        for nombre, ruta in configs.list_configs():
            self.configCombo.addItem(nombre, ruta)
        indice = self.configCombo.findText(select) if select else 0
        self.configCombo.setCurrentIndex(max(indice, 0))
        self.configCombo.blockSignals(False)
        self.deleteConfigButton.setEnabled(self.configCombo.count() > 1)

    def ask_name(self, actual):
        """Pide el nombre con el que guardar la configuración (método aparte para poder probarlo sin ventanas)."""
        nombre, ok = QInputDialog.getText(self, "Guardar configuración", "Nombre de la configuración:", text=actual)
        return nombre.strip() if ok else ''

    def confirm(self, pregunta):
        """Pregunta Sí/No al usuario."""
        botones = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        return QMessageBox.question(self, "ProjectBuilder", pregunta, botones) == QMessageBox.StandardButton.Yes

    def save_current_config(self):
        actual = self.configCombo.currentText() if self.configCombo.currentData() else ''
        nombre = self.ask_name(actual)
        if not nombre:
            return
        if os.path.isfile(configs.config_path(nombre)) and nombre != actual \
                and not self.confirm(f"Ya hay una configuración llamada «{nombre}». ¿Sustituirla?"):
            return
        try:
            configs.save_config(nombre, self.config_to_dict())
        except configs.ConfigError as e:
            return self.warn(str(e))
        self.refresh_configs(select=nombre)
        self.iface.messageBar().pushMessage("ProjectBuilder", f"Configuración «{nombre}» guardada",
                                            level=Qgis.MessageLevel.Success, duration=5)

    def delete_current_config(self):
        if not self.configCombo.currentData():
            return self.warn("Elige primero en el desplegable la configuración que quieres borrar")
        nombre = self.configCombo.currentText()
        if self.confirm(f"¿Borrar la configuración «{nombre}»?"):
            configs.delete_config(nombre)
            self.refresh_configs()

    def config_chosen(self, indice):
        ruta = self.configCombo.itemData(indice)
        if not ruta:
            return
        try:
            avisos = self.apply_config(configs.load_config(ruta))
        except configs.ConfigError as e:
            return self.warn(str(e))
        self.configCombo.setCurrentIndex(indice)  #apply_config limpia antes el panel (y con él el desplegable)
        if avisos:
            self.warn("Configuración cargada, pero con estos avisos:\n\n- " + "\n- ".join(avisos))

    def _checked_items(self):
        """
        Lo marcado en el árbol de capas, de la forma más corta posible: una carpeta marcada entera se guarda como
        carpeta (así, si mañana tiene un fichero nuevo, también se incluirá); un fichero multicapa a medias, con sus capas.
        """
        marcadas = []

        def recorrer(item):
            estado = item.checkState(0)
            if estado == Qt.CheckState.Checked:
                marcadas.append({'ruta': item.data(0, PATH_ROLE), 'capas': None})
            elif estado == Qt.CheckState.PartiallyChecked:
                if item.data(0, KIND_ROLE) == MULTILAYER:
                    capas = [item.child(i).data(0, LAYER_ROLE) for i in range(item.childCount())
                             if item.child(i).checkState(0) == Qt.CheckState.Checked]
                    marcadas.append({'ruta': item.data(0, PATH_ROLE), 'capas': capas})
                else:
                    for i in range(item.childCount()):
                        recorrer(item.child(i))

        for i in range(self.treeWidget.topLevelItemCount()):
            if self.treeWidget.topLevelItem(i).data(0, KIND_ROLE) == FOLDER:  #Proyecto abierto y bases de datos: aparte
                recorrer(self.treeWidget.topLevelItem(i))
        return marcadas

    def _databases_config(self):
        """Conexiones del árbol y sus tablas marcadas, para guardarlas en una configuración."""
        marcadas = self.selected_db_tables()
        lista = []
        for raiz in self._roots(DB_ROOT):
            provider, nombre = raiz.data(0, PATH_ROLE).split(':', 1)
            lista.append({'proveedor': provider, 'conexion': nombre,
                          'tablas': [[t['esquema'], t['tabla']] for t in marcadas if t['conexion'] == nombre and t['proveedor'] == provider]})
        return lista

    def config_to_dict(self):
        """Todo lo que se guarda de una configuración (menos el nombre y la carpeta del proyecto, que cambian cada vez)."""
        capa = self.zoneLayer.currentLayer()
        rectangulo = self.zoneExtent.outputExtent()
        crs = self.selectProjection.crs()
        return {
            'capas': {'carpetas': self.source_folders(), 'marcadas': self._checked_items()},
            'formato': self.outputFormat.currentData(),
            'reproyectar': self.reprojectCheck.isChecked(),
            'src': crs.authid() or crs.toWkt(),
            'servicios': {'activo': self.addWMS.isChecked(), 'lista': [s.to_dict() for s in self.selected_services()]},
            'zona': {
                'activa': self.groupZone.isChecked(),
                'tipo': 'capa' if self.zoneByLayer.isChecked() else 'rectangulo',
                'capa': {'fuente': capa.source(), 'proveedor': capa.providerType(), 'nombre': capa.name()} if capa else None,
                'seleccion': capa.selectedFeatureIds() if capa and self.zoneSelected.isChecked() else [],
                'solo_seleccion': self.zoneSelected.isChecked(),
                'rectangulo': [rectangulo.xMinimum(), rectangulo.yMinimum(), rectangulo.xMaximum(), rectangulo.yMaximum()]
                if not rectangulo.isNull() else None,
                'src_rectangulo': self.zoneExtent.outputCrs().authid(),
                'margen': self.zoneMargin.value(),
                'anadir_capa': self.zoneAddLayer.isChecked(),
            },
            'composiciones': [list(c) for c in self.selected_layouts()],
            'bases_datos': self._databases_config(),
            'proyecto_abierto': [{'id': capa.id(), 'nombre': capa.name(), 'fuente': capa.source()}
                                 for _, capa in self.selected_project_layers()],
        }

    def _zone_layer_from_config(self, datos):
        """La capa de la zona: si ya está abierta en QGIS se usa esa; si no, se abre desde su fichero."""
        for capa in QgsProject.instance().mapLayers().values():
            if capa.source() == datos.get('fuente'):
                return capa, None
        if datos.get('proveedor') == 'memory':  #Las capas temporales no se guardan en disco: no se pueden volver a abrir
            return None, f"La capa de la zona «{datos.get('nombre')}» era temporal y ya no está abierta en QGIS"
        capa = QgsVectorLayer(datos.get('fuente', ''), datos.get('nombre') or 'zona', datos.get('proveedor') or 'ogr')
        if not capa.isValid():
            return None, f"No se encuentra la capa de la zona de trabajo: {datos.get('fuente')}"
        QgsProject.instance().addMapLayer(capa)
        return capa, None

    def apply_config(self, datos):
        """Rellena el panel con una configuración. Devuelve la lista de avisos (lo que ya no existe)."""
        avisos = []
        self.reset_form()
        capas = datos.get('capas', {})
        for carpeta in capas.get('carpetas', []):
            if os.path.isdir(carpeta):
                self.add_source_folder(carpeta)
            else:
                avisos.append(f"Ya no existe la carpeta {carpeta}")
        elementos = {}  #ruta -> elemento del árbol

        def indexar(item):
            for i in range(item.childCount()):
                hijo = item.child(i)
                if hijo.data(0, LAYER_ROLE) is None:  #Las capas internas comparten ruta con su fichero
                    elementos[os.path.normcase(hijo.data(0, PATH_ROLE))] = hijo
                indexar(hijo)

        indexar(self.treeWidget.invisibleRootItem())
        for marcada in capas.get('marcadas', []):
            item = elementos.get(os.path.normcase(marcada.get('ruta') or ''))
            if item is None:
                avisos.append(f"Ya no existe {marcada.get('ruta')}")
            elif marcada.get('capas') is None:
                item.setCheckState(0, Qt.CheckState.Checked)
            else:
                for i in range(item.childCount()):
                    if item.child(i).data(0, LAYER_ROLE) in marcada['capas']:
                        item.child(i).setCheckState(0, Qt.CheckState.Checked)

        indice = self.outputFormat.findData(datos.get('formato'))
        if indice >= 0:
            self.outputFormat.setCurrentIndex(indice)
        self.reprojectCheck.setChecked(datos.get('reproyectar', True))
        crs = QgsCoordinateReferenceSystem(datos.get('src', ''))
        if crs.isValid():
            self.selectProjection.setCrs(crs)

        servicios = datos.get('servicios', {})
        claves = {svc.Service.from_dict(s).key(): s for s in servicios.get('lista', [])}
        encontradas = set()
        for item in self._service_leaves():
            clave = svc.Service.from_dict(item.data(0, SERVICE_ROLE)).key()
            if clave in claves:
                item.setCheckState(0, Qt.CheckState.Checked)
                encontradas.add(clave)
        # Las capas que venían de desplegar un servicio no están en el árbol hasta desplegarlo: se muestran aparte
        self.config_services = [svc.Service.from_dict(s) for k, s in claves.items() if k not in encontradas]
        if self.config_services:
            self.load_services_tree()
        self.addWMS.setChecked(servicios.get('activo', False))

        zona = datos.get('zona', {})
        self.zoneByLayer.setChecked(zona.get('tipo', 'capa') == 'capa')
        self.zoneByExtent.setChecked(zona.get('tipo') == 'rectangulo')
        if zona.get('capa'):
            capa, aviso = self._zone_layer_from_config(zona['capa'])
            if aviso:
                avisos.append(aviso)
            else:
                self.zoneLayer.setLayer(capa)
                if zona.get('solo_seleccion'):
                    capa.selectByIds(zona.get('seleccion', []))
        self.zoneSelected.setChecked(zona.get('solo_seleccion', False))
        if zona.get('rectangulo'):
            self.zoneExtent.setOutputExtentFromUser(QgsRectangle(*zona['rectangulo']),
                                                    QgsCoordinateReferenceSystem(zona.get('src_rectangulo', '')))
        self.zoneMargin.setValue(zona.get('margen', 0))
        self.zoneAddLayer.setChecked(zona.get('anadir_capa', True))
        self.groupZone.setChecked(zona.get('activa', False))

        abiertas = datos.get('proyecto_abierto', [])
        if abiertas:  #Capas del proyecto abierto: se buscan por su identificador o, si se abrió otra vez el proyecto, por su fuente
            self.load_project_layers()
            ids, fuentes = {c.get('id') for c in abiertas}, {c.get('fuente') for c in abiertas}
            encontradas = set()
            for item in self._project_leaves():
                capa = QgsProject.instance().mapLayer(item.data(0, LAYER_ROLE))
                if capa is not None and (capa.id() in ids or capa.source() in fuentes):
                    item.setCheckState(0, Qt.CheckState.Checked)
                    encontradas |= {capa.id(), capa.source()}
            for c in abiertas:
                if c.get('id') not in encontradas and c.get('fuente') not in encontradas:
                    avisos.append(f"La capa «{c.get('nombre')}» no está en el proyecto abierto en QGIS")

        for bd in datos.get('bases_datos', []):  #Conexiones a bases de datos y sus tablas marcadas
            raiz = self.add_database(bd.get('proveedor'), bd.get('conexion'), avisos=avisos)
            if raiz is None:
                continue
            marcadas = {tuple(t) for t in bd.get('tablas', [])}
            encontradas = set()
            for item in _items_de(raiz):
                info = item.data(0, DB_ROLE)
                if item.data(0, KIND_ROLE) == DB_TABLE and (info['esquema'], info['tabla']) in marcadas:
                    item.setCheckState(0, Qt.CheckState.Checked)
                    encontradas.add((info['esquema'], info['tabla']))
            avisos += [f"Ya no existe la tabla {'.'.join(p for p in t if p)} en «{bd.get('conexion')}»" for t in marcadas - encontradas]

        composiciones = [tuple(c) for c in datos.get('composiciones', [])]
        for tipo, valor in composiciones:
            if tipo == 'fichero' and os.path.isfile(valor) and valor not in self._layout_files() \
                    and valor not in layouts.qgis_templates():
                self._set_layout_files([valor, *self._layout_files()])  #Plantilla de otra carpeta: se añade a la lista
        self.load_layouts_tree()
        self.check_layouts(composiciones)
        disponibles = {tuple(item.data(0, LAYOUT_ROLE)) for item in self._layout_items()}
        for tipo, valor in composiciones:
            if (tipo, valor) not in disponibles:
                avisos.append(f"No se encuentra la composición «{valor}»" if tipo == 'proyecto'
                              else f"Ya no existe la plantilla {valor}")
        self.update_summary()
        return avisos

    # ------------------------------------------------------------------ Zona de trabajo (recorte)

    def setup_zone(self):
        """Prepara la sección 3: capa de polígonos o rectángulo (con el selector de extensión nativo de QGIS)."""
        filtro = getattr(Qgis, 'LayerFilter', None)  #QGIS 3.34+; en versiones anteriores estaba en QgsMapLayerProxyModel
        if filtro is None:
            from qgis.core import QgsMapLayerProxyModel
            filtro = QgsMapLayerProxyModel.Filter
        self.zoneLayer.setFilters(filtro.PolygonLayer)  #Solo capas de polígonos
        self.zoneLayer.setAllowEmptyLayer(True)
        # Selector de rectángulo: extensión actual del mapa, de una capa o dibujado en el mapa (menú del botón ▾)
        self.zoneExtent = QgsExtentWidget(self, QgsExtentWidget.WidgetStyle.CondensedStyle)
        self.zoneExtentLayout.addWidget(self.zoneExtent)
        lienzo = self.iface.mapCanvas()
        if lienzo is not None:
            self.zoneExtent.setMapCanvas(lienzo)
            crs = lienzo.mapSettings().destinationCrs()
            if not crs.isValid():  #Mapa sin SRC (p. ej. QGIS recién abierto, sin capas): el del proyecto o EPSG:4326
                crs = QgsProject.instance().crs() if QgsProject.instance().crs().isValid() else QgsCoordinateReferenceSystem('EPSG:4326')
            self.zoneExtent.setOutputCrs(crs)
            self.zoneExtent.setCurrentExtent(lienzo.extent(), crs)
            self.zoneExtent.setOriginalExtent(lienzo.extent(), crs)
        self.zoneExtent.extentChanged.connect(self.schedule_summary)
        self.zoneMargin.setClearValue(0)
        self.zoneByLayer.toggled.connect(self.update_zone_widgets)
        self.update_zone_widgets()

    def schedule_summary(self, *args):
        """
        Pide recalcular el resumen (con un pequeño retardo). Es un método y no un lambda a propósito: Qt desconecta
        solo los métodos cuando el panel se cierra; un lambda podría ejecutarse con el panel ya destruido y cerrar QGIS 4.
        """
        if hasattr(self, 'summaryTimer'):
            self.summaryTimer.start()

    def update_zone_widgets(self):
        """Activa solo los campos del tipo de zona elegido (capa o rectángulo)."""
        por_capa = self.zoneByLayer.isChecked()
        for widget in (self.zoneLayerLabel, self.zoneLayer, self.zoneSelected):
            widget.setEnabled(por_capa)
        for widget in (self.zoneExtentLabel, self.zoneExtentHolder):
            widget.setEnabled(not por_capa)

    def build_zone(self):
        """
        Calcula la zona de trabajo (con su margen) y la guarda en un GeoPackage temporal.
        Se hace antes de exportar, en primer plano: hay que leer la capa abierta en QGIS.
        Devuelve (GeoPackage de la zona, extensión inicial del proyecto) o (None, None) si la sección no está activada.
        Lanza ZoneError si falta algo.
        """
        if not self.groupZone.isChecked():
            return None, None
        if self.zoneByLayer.isChecked():
            geometria, crs = geometry_from_layer(self.zoneLayer.currentLayer(), self.zoneSelected.isChecked())
        else:
            if not self.zoneExtent.outputCrs().isValid():
                raise ZoneError("El rectángulo de la zona no tiene sistema de coordenadas: vuelve a elegirlo")
            geometria, crs = geometry_from_extent(self.zoneExtent.outputExtent(), self.zoneExtent.outputCrs())
        geometria, crs = apply_margin(geometria, crs, self.zoneMargin.value(), self.selectProjection.crs())
        return write_zone(geometria, crs), view_extent(geometria, crs, self.selectProjection.crs())

    def warn(self, message):
        """Muestra un aviso al usuario."""
        QMessageBox.warning(self, "Error", message)

    def reset_form(self):
        """Vacía el formulario: carpetas, capas marcadas, nombre, destino, WMS y formato. Se mantiene el SRC."""
        self.treeWidget.clear()
        self.load_project_layers()  #El bloque del proyecto abierto vuelve a aparecer, sin nada marcado
        self.filterBox.clear()
        self.nameProject.clear()
        self.pathFolderProject.clear()
        self.outputFormat.setCurrentIndex(0)  #Modo recomendado
        self.reprojectCheck.setChecked(True)
        self.addWMS.setChecked(False)
        self.groupZone.setChecked(False)
        self.zoneByLayer.setChecked(True)
        self.zoneSelected.setChecked(False)
        self.zoneMargin.setValue(0)
        self.zoneAddLayer.setChecked(True)
        self.servicesFilter.clear()
        for item in self._service_leaves():
            item.setCheckState(0, Qt.CheckState.Unchecked)
        if self.config_services:
            self.config_services = []
            self.load_services_tree()
        self.check_layouts([])
        self.configCombo.setCurrentIndex(0)  #«Elegir una configuración guardada»
        self.apply_favorites_default()
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
        """Rutas de las carpetas de capas añadidas (las raíces del árbol, menos el bloque del proyecto abierto)."""
        raices = (self.treeWidget.topLevelItem(i) for i in range(self.treeWidget.topLevelItemCount()))
        return [r.data(0, PATH_ROLE) for r in raices if r.data(0, KIND_ROLE) == FOLDER]

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
        if item.data(0, KIND_ROLE) == PROJECT_ROOT:
            return self.warn("El bloque «Proyecto abierto en QGIS» no se puede quitar: desmarca las capas que no quieras")
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
            if raiz.data(0, KIND_ROLE) == FOLDER:  #Proyecto abierto y bases de datos van aparte (selected_project_layers...)
                recorrer(raiz, raiz.data(0, PATH_ROLE))
        return sources

    def count_layers(self):
        """Número de capas que se van a exportar (las de los ficheros multicapa cuentan una a una)."""
        total = 0
        for _raiz, path, layers in self.selected_sources():
            if os.path.isdir(path):
                continue
            total += len(layers) if layers is not None else len(self._item_layers(path)) or 1
        return total + len(self.selected_project_layers()) + len(self.selected_db_tables())

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
        wms = len(self.selected_services()) if self.addWMS.isChecked() else 0
        partes = [f"{capas} capa{'s' if capas != 1 else ''}"]
        if wms:
            partes.append(f"{wms} servicio{'s' if wms != 1 else ''} web")
        if capas:
            partes.append(MODE_NAMES.get(self.outputFormat.currentData(), ''))
            if self.reprojectCheck.isChecked():  #Deja claro qué se hace con el SRC de las capas
                partes.append(f"reproyectadas a {self.selectProjection.crs().authid() or 'SRC del proyecto'}")
            else:
                partes.append("en su SRC original")
            composiciones = len(self.selected_layouts()) if hasattr(self, 'layoutsTree') else 0
            if composiciones:
                partes.append(f"{composiciones} composici{'ones' if composiciones != 1 else 'ón'}")
            if self.groupZone.isChecked():
                margen = int(self.zoneMargin.value())
                partes.append("recortadas a la zona" + (f" (+{margen} m)" if margen else ""))
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

    # ------------------------------------------------------------------ Servicios web

    def _node(self, parent, text, node, service=None, icon=None, checkable=False):
        """Crea un elemento del árbol de servicios."""
        item = QTreeWidgetItem(parent, [text])
        item.setData(0, NODE_ROLE, node)
        if service is not None:
            item.setData(0, SERVICE_ROLE, service.to_dict())
            item.setToolTip(0, f"{service.type.upper()} · {service.url}" + (f"\nCapa: {service.layer}" if service.layer else ''))
        if icon:
            item.setIcon(0, QgsApplication.getThemeIcon(icon))
        if checkable:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
        if node == 'servicio':  #Servicio completo: se muestra la flecha para desplegarlo aunque aún no tenga capas
            item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        return item

    def _root(self, text):
        raiz = self._node(self.servicesTree, text, 'raiz')
        fuente = QFont(raiz.font(0))
        fuente.setBold(True)
        raiz.setFont(0, fuente)
        return raiz

    def _add_service_node(self, parent, service):
        """Una capa concreta (casilla) o un servicio completo (desplegable para ver sus capas)."""
        estado = self.health.get('servicios', {}).get(service.key())
        if estado and estado.get('ok') and estado.get('url') and estado['url'] != service.url:
            original = service.key()
            service = svc.Service.from_dict({**service.to_dict(), 'url': estado['url']})  #Dirección corregida automáticamente
            self.health.setdefault('servicios', {})[service.key()] = {**estado, 'original': original}
        icono = SERVICE_ICONS.get(service.type, '/mIconWms.svg')
        if service.layer:
            item = self._node(parent, service.name, 'capa', service, icono, checkable=True)
        else:
            item = self._node(parent, service.name, 'servicio', service, icono)
        estado = self.health.get('servicios', {}).get(service.key())
        if estado and not estado.get('ok'):  #Servicio caído en la última comprobación: desactivado temporalmente
            if item.data(0, NODE_ROLE) == 'capa':
                item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setDisabled(True)
            item.setText(0, f"⛔ {service.name}")
            item.setToolTip(0, item.toolTip(0) + f"\n⛔ No respondía en la comprobación del {self.health.get('fecha', '')}: "
                                                  f"{estado.get('detalle', '')}\nSe volverá a comprobar automáticamente (o pulsa ⟳).")
        if service.heavy:  #Aviso: descarga muchos datos (conviene usarlo con una zona de trabajo)
            item.setText(0, f"{service.name}  ⚠")
            item.setToolTip(0, item.toolTip(0) + "\n⚠ Servicio pesado: descarga muchos datos y puede ralentizar QGIS.\n"
                                                  "Úsalo en proyectos de una zona concreta.")
        return item

    def load_services_tree(self):
        """Rellena el árbol de servicios: ★ Favoritos, Mis conexiones de QGIS y Catálogo ProjectBuilder."""
        self.health = svc.load_health(svc.health_path())  #Resultado de la última comprobación automática
        marcadas = {s.key() for s in self.selected_services()} if self.servicesTree.topLevelItemCount() else set()
        self.servicesTree.clear()
        try:
            self.favorites = svc.load_favorites(svc.favorites_path())
        except svc.ServicesError as e:
            self.favorites = []
            self.iface.messageBar().pushMessage("ProjectBuilder", str(e), level=Qgis.MessageLevel.Warning, duration=10)

        favoritos = self._root("★ Favoritos")
        for servicio in self.favorites:
            self._add_service_node(favoritos, servicio)
        if not self.favorites:
            self._node(favoritos, "Haz clic en una capa y pulsa ★ para añadirla aquí", 'aviso').setDisabled(True)

        conexiones = self._root("Mis conexiones de QGIS")
        lista = svc.qgis_connections()
        for titulo, tipos in (("WMS / WMTS", (svc.WMS, svc.WMTS)), ("WFS", (svc.WFS,))):  #Agrupadas por tipo: puede haber muchas
            del_tipo = sorted((s for s in lista if s.type in tipos), key=lambda s: s.name.lower())
            if del_tipo:
                grupo = self._node(conexiones, f"{titulo} ({len(del_tipo)})", 'grupo', icon='/mIconFolder.svg')
                for servicio in del_tipo:
                    self._add_service_node(grupo, servicio)
        if not lista:
            self._node(conexiones, "No hay conexiones: usa el botón + para crear una", 'aviso').setDisabled(True)

        if self.config_services:  #Capas de una configuración guardada que no se ven en los bloques de arriba
            de_config = self._root("Servicios de la configuración")
            for servicio in self.config_services:
                self._add_service_node(de_config, servicio).setCheckState(0, Qt.CheckState.Checked)
            de_config.setExpanded(True)

        catalogo = self._root("Catálogo ProjectBuilder")
        try:
            for nombre, servicios in svc.load_catalog(svc.best_catalog_path()):  #El más reciente: el del plugin o el de GitHub
                grupo = self._node(catalogo, nombre, 'grupo', icon='/mIconFolder.svg')
                for servicio in servicios:
                    self._add_service_node(grupo, servicio)
        except svc.ServicesError as e:  #Si services.json tiene un error, se avisa y el plugin sigue funcionando sin catálogo
            self.iface.messageBar().pushMessage("ProjectBuilder", str(e), level=Qgis.MessageLevel.Critical, duration=0)

        favoritos.setExpanded(True)
        conexiones.setExpanded(True)
        for item in self._service_leaves():  #Se conservan las capas que ya estaban marcadas
            if svc.Service.from_dict(item.data(0, SERVICE_ROLE)).key() in marcadas:
                item.setCheckState(0, Qt.CheckState.Checked)
        self._mark_favorites()
        self.apply_services_filter(self.servicesFilter.text())

    def load_service_layers(self, item):
        """Al desplegar un servicio, se piden sus capas al servidor (GetCapabilities) sin bloquear QGIS."""
        if item.data(0, NODE_ROLE) != 'servicio' or item.childCount():
            return
        servicio = svc.Service.from_dict(item.data(0, SERVICE_ROLE))
        self._node(item, "Cargando capas…", 'aviso').setDisabled(True)
        peticion = QNetworkRequest(QUrl(svc.capabilities_url(servicio.url, servicio.type)))
        peticion.setTransferTimeout(45000)  #45 s como máximo (algunos, como el IGME, tardan más de 20 s): no bloquea, es en segundo plano
        if servicio.authcfg:
            QgsApplication.authManager().updateNetworkRequest(peticion, servicio.authcfg)
        respuesta = QgsNetworkAccessManager.instance().get(peticion)
        self.pending[id(respuesta)] = respuesta
        respuesta.finished.connect(lambda: self._service_layers_received(item, servicio, respuesta))

    def _service_layers_received(self, item, servicio, respuesta):
        if sip.isdeleted(self):  #La respuesta llega tarde y el panel ya se ha cerrado
            return
        self.pending.pop(id(respuesta), None)
        datos = bytes(respuesta.readAll())
        # Se compara con NoError: en PyQt6 (QGIS 4) los enum siempre valen True en un if, aunque no haya error
        error = respuesta.errorString() if respuesta.error() != QNetworkReply.NetworkError.NoError else None
        respuesta.deleteLater()
        try:
            item.takeChildren()  #Se quita el "Cargando capas…"
        except RuntimeError:  #El elemento ya no existe (se ha recargado el árbol mientras tanto)
            return
        try:
            if error:
                raise ValueError(f"No responde: {error}")
            tipo = detect_type(datos, servicio.type)  #Una conexión "WMS" de QGIS puede ser un WMTS
            capas = parse_capabilities(datos, tipo)
        except ValueError as e:
            self._node(item, str(e)[:150], 'aviso').setDisabled(True)
            return
        for capa in capas:
            hija = svc.Service(capa['title'], servicio.url, capa['layer'], tipo, format=capa['format'] or servicio.format,
                               style=capa['style'], tilematrixset=capa['tilematrixset'], authcfg=servicio.authcfg,
                               crs_list=capa['crs'])
            self._add_service_node(item, hija)
        if not capas:
            self._node(item, "El servicio no ofrece capas", 'aviso').setDisabled(True)
        self._mark_favorites()
        self.apply_services_filter(self.servicesFilter.text())

    def start_health_check(self, force=False):
        """
        Comprueba en segundo plano el catálogo y los favoritos (como mucho una vez por semana, o al pulsar ⟳)
        y descarga el catálogo más reciente de GitHub. No bloquea QGIS.
        """
        if self.health_task is not None or (not force and not check_due(self.health)):
            return
        try:
            servicios = [s for _, lista in svc.load_catalog(svc.best_catalog_path()) for s in lista]
        except svc.ServicesError:
            servicios = []
        self.health_task = HealthTask(servicios + list(self.favorites))
        self.health_task.taskCompleted.connect(self._health_finished)
        self.health_task.taskTerminated.connect(lambda: setattr(self, 'health_task', None))
        QgsApplication.taskManager().addTask(self.health_task)

    def _health_finished(self):
        if sip.isdeleted(self):  #La revisión termina cuando el panel ya se ha cerrado: no hay nada que actualizar
            return
        task, self.health_task = self.health_task, None
        svc.save_health({'fecha': datetime.date.today().isoformat(), 'servicios': task.resultados}, svc.health_path())
        avisos = []
        if task.catalogo_remoto:  #Catálogo de GitHub: se guarda solo si es más reciente y se puede leer entero
            destino = os.path.join(svc.profile_dir(), 'services_remoto.json')
            anterior = svc.catalog_version(svc.best_catalog_path())
            os.makedirs(svc.profile_dir(), exist_ok=True)
            with open(destino, 'wb') as f:
                f.write(task.catalogo_remoto)
            if svc.catalog_version(destino) > anterior and svc.best_catalog_path() == destino:
                avisos.append(f"Catálogo de servicios actualizado (versión {svc.catalog_version(destino)})")
        caidos = [f.name for f in self.favorites if not task.resultados.get(f.key(), {}).get('ok', True)]
        if caidos:
            self.iface.messageBar().pushMessage("ProjectBuilder", "Favoritos que no responden ahora mismo: " + ", ".join(caidos),
                                                level=Qgis.MessageLevel.Warning, duration=15)
        if avisos:
            self.iface.messageBar().pushMessage("ProjectBuilder", " · ".join(avisos), level=Qgis.MessageLevel.Info, duration=10)
        self.load_services_tree()

    def _service_leaves(self, parent=None):
        """Todas las capas (con casilla) del árbol de servicios."""
        parent = parent or self.servicesTree.invisibleRootItem()
        hojas = []
        for i in range(parent.childCount()):
            hijo = parent.child(i)
            if hijo.data(0, NODE_ROLE) == 'capa':
                hojas.append(hijo)
            hojas += self._service_leaves(hijo)
        return hojas

    def selected_services(self):
        """Capas de servicios marcadas (sin repetir: una capa puede estar en Favoritos y en su servicio)."""
        vistos, servicios = set(), []
        for item in self._service_leaves():
            if item.checkState(0) == Qt.CheckState.Checked and not item.isDisabled():
                servicio = svc.Service.from_dict(item.data(0, SERVICE_ROLE))
                if servicio.key() not in vistos:
                    vistos.add(servicio.key())
                    servicios.append(servicio)
        return servicios

    def toggle_favorite(self):
        """Añade a Favoritos (o quita) la capa en la que se ha hecho clic. Se guarda en el perfil de QGIS."""
        item = self.servicesTree.currentItem()
        if item is None or item.data(0, NODE_ROLE) != 'capa':
            return self.warn("Haz clic en una capa de un servicio y pulsa ★")
        servicio = svc.Service.from_dict(item.data(0, SERVICE_ROLE))
        claves = [f.key() for f in self.favorites]
        if servicio.key() in claves:
            self.favorites.pop(claves.index(servicio.key()))
        else:
            self.favorites.append(servicio)
        svc.save_favorites(self.favorites, svc.favorites_path())
        self.load_services_tree()

    def _mark_favorites(self):
        """Las capas que son favoritas se ven en negrita en todo el árbol."""
        claves = {f.key() for f in self.favorites}
        for item in self._service_leaves():
            fuente = QFont(item.font(0))
            fuente.setBold(svc.Service.from_dict(item.data(0, SERVICE_ROLE)).key() in claves)
            item.setFont(0, fuente)

    def apply_favorites_default(self):
        """Si está activada la opción, se marcan los favoritos (y la sección de servicios) al empezar un proyecto."""
        if not (self.favoritesDefault.isChecked() and self.favorites):
            return
        self.addWMS.setChecked(True)
        raiz = self.servicesTree.topLevelItem(0)  #★ Favoritos
        for item in self._service_leaves(raiz):
            item.setCheckState(0, Qt.CheckState.Checked)

    def apply_services_filter(self, texto):
        """Muestra solo los servicios y capas cuyo nombre contiene el texto."""
        texto = normalizar(texto.strip())

        def filtrar(item, padre_coincide):
            coincide = padre_coincide or texto in normalizar(item.text(0))
            hijos = [filtrar(item.child(i), coincide) for i in range(item.childCount())]
            visible = coincide or any(hijos)
            item.setHidden(not visible)
            if texto and any(hijos):
                item.setExpanded(True)
            return visible

        for i in range(self.servicesTree.topLevelItemCount()):
            raiz = self.servicesTree.topLevelItem(i)
            for j in range(raiz.childCount()):  #Los tres bloques principales siempre se ven
                filtrar(raiz.child(j), not texto)

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
        if self.addWMS.isChecked() and not self.selected_services():
            return "No has marcado ningún servicio web (o desmarca la sección 2)"
        if not (self.selected_sources() or self.selected_project_layers() or self.selected_db_tables() or self.addWMS.isChecked()):  #Hace falta al menos una capa o un servicio WMS
            return "No se ha marcado ninguna capa ni ningún servicio web"
        # Evitar sobrescribir los datos de origen: el proyecto no puede estar en ninguna carpeta de capas ni dentro de ella
        for _, capa in self.selected_project_layers():  #Tampoco puede sobrescribir los ficheros de las capas del proyecto abierto
            fichero = open_project.file_path(capa)
            if fichero and dentro_de(fichero, folder_project):
                return f"La capa «{capa.name()}» está dentro de la carpeta del proyecto: elige otra carpeta de destino"
        for carpeta in self.source_folders():
            if dentro_de(folder_project, carpeta):
                return f"La carpeta del proyecto no puede ser una carpeta de capas ni estar dentro de ella:\n{carpeta}"
        return None

    @staticmethod
    def _source_styles(path_source, names=None):
        """
        Estilos guardados DENTRO de un GeoPackage (o SpatiaLite) de origen: {capa: .qml temporal}. Al abrir la capa,
        QGIS carga su estilo por defecto guardado en el fichero; se guarda en un .qml para aplicarlo a la copia.
        """
        if extension(path_source) not in CONTAINER_EXTENSIONS:
            return None
        estilos = {}
        for subcapa in vector_sublayers(path_source):
            if names is not None and subcapa.name() not in names:
                continue
            capa = QgsVectorLayer(subcapa.uri(), subcapa.name(), 'ogr')
            try:
                cuantos = capa.listStylesInDatabase()[0]
            except Exception:  # noqa: BLE001
                cuantos = 0
            if capa.isValid() and cuantos and cuantos > 0:
                qml = open_project.save_style(capa)
                if qml:
                    estilos[subcapa.name()] = qml
        return estilos or None

    def build_jobs(self, folder_project, name, mode, zone=None):
        """
        Prepara la lista de trabajos (Job) a partir de lo marcado en el árbol.
        - Cada carpeta añadida es un grupo del proyecto (y, en los modos de ficheros sueltos, una subcarpeta).
        - En el modo "un solo GeoPackage", todos los vectoriales van como tablas de <nombre>.gpkg.
        - zone: GeoPackage de la zona de trabajo; si se pide, se añade como primera capa (sin recortarla).
        """
        gpkg = os.path.join(folder_project, name + '.gpkg')
        nombres_raiz = {}  #Carpeta raíz -> nombre de grupo/subcarpeta (único, por si dos carpetas se llaman igual)
        raices_usadas, tablas_usadas, rutas_usadas = set(), set(), set()
        jobs = []
        if zone and self.zoneAddLayer.isChecked():  #La zona va en la raíz del proyecto, con su estilo de contorno rojo
            tablas_usadas.add(ZONE_TABLE)
            rutas_usadas.add(os.path.join(folder_project, ZONE_TABLE).lower())
            if mode == SINGLE:
                jobs.append(Job(zone, gpkg, (), tables={ZONE_TABLE: ZONE_TABLE}, qml=style_path(zone), clip=False, zone=True))
            else:
                jobs.append(Job(zone, os.path.join(folder_project, ZONE_TABLE + '.gpkg'), (), clip=False, zone=True))
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
                jobs.append(Job(path_source, gpkg, group, tables=tablas, qml=style_path(path_source) if una_capa else None,
                                styles=self._source_styles(path_source, capas)))
                continue

            # Misma estructura de subcarpetas que el origen, dentro de la carpeta del proyecto
            # (en el modo "un solo GeoPackage" solo llegan aquí los ráster, que salen en GeoTIFF)
            path_target = output_path(os.path.join(folder_project, nombres_raiz[raiz], rel), kind, CONVERT if mode == SINGLE else mode)
            base, ext = os.path.splitext(path_target)
            path_target = nombre_unico(base, rutas_usadas) + ext  #p. ej. rios.shp y rios.geojson convertidos ambos a rios.gpkg
            estilos = self._source_styles(path_source, layers) if kind != RASTER else None
            jobs.append(Job(path_source, path_target, group, layers=layers, styles=estilos))
        return (jobs + self.build_project_jobs(folder_project, gpkg, mode, tablas_usadas, rutas_usadas)
                + self.build_db_jobs(folder_project, gpkg, mode, tablas_usadas, rutas_usadas))

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
        try:
            zone, self.zone_extent = self.build_zone()  #Zona de trabajo (None si la sección 3 no está activada)
        except ZoneError as e:
            return self.warn(str(e))
        try:
            self.layout_jobs = self.prepare_layouts()  #Composiciones a añadir al terminar
        except layouts.LayoutError as e:
            return self.warn(str(e))
        jobs = self.build_jobs(folder_project, name, self.outputFormat.currentData(), zone)

        crs = self.selectProjection.crs() if self.reprojectCheck.isChecked() else None  #None: se copian en su SRC original
        self.task = ExportTask(jobs, crs, zone)
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
        if sip.isdeleted(self):  #El panel se cerró mientras se exportaban las capas
            return
        self.createProject.setEnabled(True)
        self.resetButton.setEnabled(True)
        task, self.task = self.task, None
        if not completed:
            return self.iface.messageBar().pushMessage("ProjectBuilder", "Creación del proyecto cancelada",
                                                       level=Qgis.MessageLevel.Warning, duration=5)

        project = qgis_project.create_project(self.pathFolderProject.text(), self.nameProject.text().strip(),
                                              self.selectProjection.crs())
        errors = list(task.errors)  #Se acumulan los errores para mostrarlos todos juntos al final
        anadidas = []  #Capas añadidas (para centrar los mapas de las composiciones si no hay zona de trabajo)
        for output in task.outputs:
            try:
                if output.tables:  #Tablas del GeoPackage común
                    capas = qgis_project.add_geopackage_tables(project, output.path, output.tables, output.group, output.qml,
                                                               output.styles)
                else:
                    capas = qgis_project.add_layer(project, output.path, output.group, output.qml, output.name, output.styles)
                anadidas += capas
                if output.zone:
                    qgis_project.put_on_top(project, capas)  #El contorno de la zona, visible y por encima de todo
            except ValueError as e:
                errors.append(str(e))

        for grupos, capa in getattr(self, 'project_links', []):  #Capas del proyecto abierto que no se copian (servicios web...)
            try:
                qgis_project.add_linked_layer(project, capa, grupos)
            except ValueError as e:
                errors.append(str(e))
        self.project_links = []
        errors += getattr(self, 'prepare_errors', [])

        servicios = self.selected_services() if self.addWMS.isChecked() else []
        if servicios:  #Si la sección de servicios está activada, se crea el grupo y se añaden las capas marcadas
            group = qgis_project.add_group(project, 'Servicios web')
            for servicio in servicios:
                try:
                    qgis_project.add_service(project, group, servicio)
                except ValueError as e:
                    errors.append(str(e))

        # Iconos (SVG e imágenes) de los estilos: se copian a iconos/ para que el proyecto se pueda llevar a otro sitio
        # Dónde buscar por su nombre los iconos que no estén en la ruta guardada en el estilo: las carpetas de capas
        # (con la carpeta de iconos que suelen entregar), la del proyecto abierto y las carpetas de SVG de QGIS
        buscar_en = [*self.source_folders(), *[os.path.dirname(c) for c in self.source_folders()],
                     QgsProject.instance().absolutePath(), *QgsApplication.svgPaths()]
        cambiadas, faltan = icons.localize(project, self.pathFolderProject.text(), search_dirs=buscar_en)
        gpkg_comun = os.path.normcase(os.path.abspath(os.path.join(self.pathFolderProject.text(), self.nameProject.text().strip() + '.gpkg')))
        for capa in cambiadas:  #El estilo guardado dentro del GeoPackage común también apunta ya a los iconos copiados
            if os.path.normcase(os.path.abspath(capa.source().split('|')[0])) == gpkg_comun:
                qgis_project.save_style_in_geopackage(capa)
        errors += [f"No se encuentra el icono {icono} (capa {capa})" for capa, icono in faltan]

        if getattr(self, 'zone_extent', None) is not None:
            qgis_project.set_view_extent(project, self.zone_extent)  #Al abrirlo se ve la zona (y los WFS solo piden esa zona)

        trabajos = getattr(self, 'layout_jobs', [])
        if trabajos:  #Composiciones: sus mapas, centrados en la zona de trabajo o en todas las capas
            extension = self.zone_extent if getattr(self, 'zone_extent', None) is not None \
                else layouts.layers_extent(project, anadidas)
            for plantilla, nombre in trabajos:
                try:
                    layouts.add_layout(project, plantilla, nombre, extension)
                except layouts.LayoutError as e:
                    errors.append(str(e))
        try:
            path_file = qgis_project.save_project(project)
        except OSError as e:
            return self.warn(str(e))

        if errors:
            self.warn("El proyecto se ha creado, pero con estos problemas:\n\n- " + "\n- ".join(errors))
        self.show_success(path_file, task.empty)

    def show_success(self, path_file, empty=()):
        """Mensaje de que se ha creado el proyecto, con un botón para abrirlo en QGIS."""
        bar = self.iface.messageBar()
        texto = f"Proyecto creado: {path_file}"
        if empty:  #Capas sin nada dentro de la zona de trabajo: no se han añadido (no es un error)
            texto += f"  ·  {len(empty)} capa{'s' if len(empty) != 1 else ''} sin datos en la zona: {', '.join(empty)}"
        message = bar.createMessage("ProjectBuilder", texto)
        button = QPushButton("Abrir proyecto")
        button.clicked.connect(lambda: self.iface.addProject(path_file))  #QGIS pregunta antes si hay que guardar el proyecto actual
        message.layout().addWidget(button)
        bar.pushWidget(message, Qgis.MessageLevel.Success, 15)
