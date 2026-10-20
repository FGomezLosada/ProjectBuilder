"""
ProjectBuilder - Clase principal del plugin (menú, barra de herramientas y panel).

copyright : (C) 2023 by Francisco Gómez Losada
email     : pgomezlosada@gmail.com
license   : GNU GPL v2 or later
"""

import os
import traceback

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .core.mensajes import explicar
from .project_builder_dockwidget import ProjectBuilderDockWidget

PLUGIN_DIR = os.path.dirname(__file__)
MENU_NAME = "&ProjectBuilder"


class ProjectBuilder:
    """Implementación del plugin para QGIS."""

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.toolbar = None
        self.dockwidget = None

    @staticmethod
    def tr(message):
        return QCoreApplication.translate("ProjectBuilder", message)

    def initGui(self):  # noqa: N802 (nombre impuesto por QGIS)
        """Crea el botón en la barra de herramientas y la entrada de menú."""
        self.toolbar = self.iface.addToolBar("ProjectBuilder")
        self.toolbar.setObjectName("ProjectBuilder")

        icon = QIcon(os.path.join(PLUGIN_DIR, "icon.svg"))  #Vectorial: se ve nítido a cualquier tamaño
        self.action = QAction(icon, self.tr("Project Builder"), self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        self.toolbar.addAction(self.action)
        self.iface.addPluginToMenu(self.tr(MENU_NAME), self.action)

    def unload(self):
        """Elimina todo lo que el plugin ha añadido a QGIS (necesario para recargarlo)."""
        self.iface.removePluginMenu(self.tr(MENU_NAME), self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.dockwidget is not None:
            for tarea in (self.dockwidget.task, self.dockwidget.health_task):  #Las tareas en marcha se cancelan
                if tarea is not None:
                    try:
                        tarea.cancel()
                    except RuntimeError:  #Ya había terminado
                        pass
            self.iface.removeDockWidget(self.dockwidget)
            self.dockwidget.deleteLater()
            self.dockwidget = None
        if self.toolbar is not None:
            self.toolbar.deleteLater()
            self.toolbar = None

    def run(self):
        """Muestra el panel. Se crea una sola vez y se reutiliza."""
        if self.dockwidget is None:
            try:
                self.dockwidget = ProjectBuilderDockWidget(self.iface)
            except Exception as e:  # noqa: BLE001 (sin panel no hay dónde avisar: se avisa en la barra de QGIS, sin ventana de error)
                detalle = traceback.format_exc()
                QgsMessageLog.logMessage(detalle, 'ProjectBuilder', Qgis.MessageLevel.Critical)
                self.iface.messageBar().pushMessage(
                    "ProjectBuilder", f"No se ha podido abrir el panel: {explicar(e)}. Si vuelve a pasar, copia el detalle de "
                    "Ver → Paneles → Registro de mensajes (pestaña ProjectBuilder) y envíaselo al autor del plugin",
                    level=Qgis.MessageLevel.Critical, duration=0)
                return
            self.dockwidget.setWindowIcon(QIcon(os.path.join(PLUGIN_DIR, "icon.svg")))
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dockwidget)
        self.dockwidget.show()
        self.dockwidget.raise_()
