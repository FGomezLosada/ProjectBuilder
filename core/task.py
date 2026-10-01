"""Tarea en segundo plano para exportar las capas sin bloquear QGIS."""

from qgis.core import QgsProcessingFeedback, QgsTask

from .exporter import ExportError, export_layer


class ExportTask(QgsTask):
    """
    Exporta una lista de capas (origen -> destino) reproyectándolas al SRC indicado.
    QGIS la ejecuta en segundo plano y muestra su progreso en la barra de estado (abajo a la derecha).
    Al terminar, el panel recoge el resultado en self.exported y self.errors.
    """

    def __init__(self, jobs, crs):
        super().__init__("ProjectBuilder: exportando capas", QgsTask.Flag.CanCancel)
        self.jobs = jobs  #Lista de pares (ruta_origen, ruta_destino)
        self.crs = crs
        self.exported = []  #Rutas de destino exportadas correctamente
        self.errors = []  #Mensajes de error de las capas que fallen
        self.feedback = QgsProcessingFeedback()  #Permite cancelar el algoritmo de Processing que esté en marcha

    def run(self):
        """Se ejecuta en segundo plano: aquí NO se puede tocar la interfaz ni el proyecto."""
        total = len(self.jobs) or 1
        for i, (path_source, path_target) in enumerate(self.jobs):
            if self.isCanceled():
                return False
            try:
                export_layer(path_source, path_target, self.crs, feedback=self.feedback)
                self.exported.append(path_target)
            except ExportError as e:
                self.errors.append(str(e))  #Si una capa falla se anota y se sigue con las demás
            self.setProgress((i + 1) * 100 / total)
        return True

    def cancel(self):
        self.feedback.cancel()  #Detiene también el algoritmo que se esté ejecutando en ese momento
        super().cancel()
