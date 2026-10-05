"""Tarea en segundo plano para exportar las capas sin bloquear QGIS."""

import os
from dataclasses import dataclass, field

from qgis.core import QgsProcessingFeedback, QgsTask

from qgis.core import QgsProcessingUtils, QgsVectorLayer

from .clip import zone_uri
from .database import DatabaseError, download
from .exporter import EmptyLayer, ExportError, export_layer, export_to_shared_geopackage


@dataclass
class Job:
    """Una capa (o fichero multicapa) que hay que exportar."""

    source: str  #Fichero de origen
    target: str  #Fichero de destino (o el GeoPackage común del proyecto si tables no es None)
    group: tuple  #Grupos del árbol de capas del proyecto donde irá, p. ej. ('vectorial', 'subcarpeta')
    layers: list = None  #Capas internas a exportar de un fichero multicapa (None = todas)
    tables: dict = None  #Solo en el modo "un solo GeoPackage": {capa de origen: tabla en el GeoPackage}
    qml: str = None  #Estilo .qml a aplicar (capas de un fichero de una sola capa o del proyecto abierto en QGIS)
    clip: bool = True  #Recortar por la zona de trabajo (la propia zona no se recorta)
    zone: bool = False  #Es la capa de la zona de trabajo (va arriba del todo en el proyecto)
    name: str = None  #Nombre de la capa en el proyecto (las del proyecto abierto conservan el suyo)
    provider: str = None  #Tabla de base de datos ('postgres', 'spatialite'): source es su uri y se descarga antes
    db_layer: str = None  #Nombre de la capa en el GeoPackage temporal de la descarga


@dataclass
class Output:
    """Una capa ya exportada, lista para añadirla al proyecto."""

    path: str  #Fichero exportado (o el GeoPackage común)
    group: tuple
    tables: list = field(default_factory=list)  #Tablas del GeoPackage común (vacío si es un fichero propio)
    qml: str = None
    zone: bool = False
    name: str = None


class ExportTask(QgsTask):
    """
    Exporta una lista de Job reproyectándolos al SRC indicado y, si hay zona de trabajo, recortándolos por ella.
    QGIS la ejecuta en segundo plano y muestra su progreso en la barra de estado (abajo a la derecha).
    Al terminar, el panel recoge el resultado en self.outputs, self.errors y self.empty.
    """

    def __init__(self, jobs, crs, zone=None):
        super().__init__("ProjectBuilder: exportando capas", QgsTask.Flag.CanCancel)
        self.jobs = jobs
        self.crs = crs
        self.zone = zone  #GeoPackage de la zona de trabajo (None = sin recorte)
        self.empty = []  #Capas que no tienen nada dentro de la zona (no se añaden al proyecto)
        self.outputs = []  #Output de las capas exportadas correctamente
        self.errors = []  #Mensajes de error de las capas que fallen
        self.feedback = QgsProcessingFeedback()  #Permite cancelar el algoritmo de Processing que esté en marcha

    def run(self):
        """Se ejecuta en segundo plano: aquí NO se puede tocar la interfaz ni el proyecto."""
        total = len(self.jobs) or 1
        for i, job in enumerate(self.jobs):
            if self.isCanceled():
                return False
            zone = self.zone if job.clip else None
            try:
                if job.provider:  #Tabla de base de datos: se descarga a un GeoPackage temporal y sigue como un fichero más
                    job.source = self._download(job, zone)
                if job.tables is not None:  #Modo "un solo GeoPackage"
                    vacias = export_to_shared_geopackage(job.source, job.target, job.tables, self.crs,
                                                         feedback=self.feedback, zone=zone)
                    self.empty += [job.tables[capa] for capa in vacias]
                    tablas = [tabla for capa, tabla in job.tables.items() if capa not in vacias]
                    if tablas:
                        self.outputs.append(Output(job.target, job.group, tablas, job.qml, job.zone))
                else:
                    vacias = []
                    final = export_layer(job.source, job.target, self.crs, feedback=self.feedback, layers=job.layers,
                                         zone=zone, empty=vacias)
                    self.empty += vacias
                    self.outputs.append(Output(final, job.group, qml=job.qml, zone=job.zone, name=job.name))  #Ruta final (puede haber cambiado de formato)
            except DatabaseError as e:
                self.errors.append(str(e))
            except EmptyLayer:
                self.empty.append(os.path.splitext(os.path.basename(job.source))[0])  #No es un error: se avisa al final
            except ExportError as e:
                self.errors.append(str(e))  #Si una capa falla se anota y se sigue con las demás
            self.setProgress((i + 1) * 100 / total)
        return True

    @staticmethod
    def _download(job, zone):
        """Descarga la tabla (solo lo que cae en el rectángulo de la zona, si la hay). Devuelve el GeoPackage temporal."""
        destino = QgsProcessingUtils.generateTempFilename(f"{job.db_layer}.gpkg")
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        extension = None
        if zone:
            capa_zona = QgsVectorLayer(zone_uri(zone), 'zona', 'ogr')
            extension = (capa_zona.extent(), capa_zona.crs())
        download(job.source, job.provider, destino, job.db_layer, extension)
        return destino

    def cancel(self):
        self.feedback.cancel()  #Detiene también el algoritmo que se esté ejecutando en ese momento
        super().cancel()
