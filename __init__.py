"""
ProjectBuilder - Plugin de QGIS
Crea un proyecto de QGIS a partir de una selección de capas y servicios WMS.

copyright : (C) 2023 by Francisco Gómez Losada
email     : pgomezlosada@gmail.com
license   : GNU GPL v2 or later
"""


def classFactory(iface):  # noqa: N802 (nombre impuesto por QGIS)
    """Punto de entrada que QGIS llama al cargar el plugin."""
    from .project_builder import ProjectBuilder

    return ProjectBuilder(iface)
