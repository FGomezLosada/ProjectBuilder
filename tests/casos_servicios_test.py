"""
Plan de pruebas · H05 Servicios web: favoritos, desplegar un servicio (respuestas raras del servidor), revisión semanal,
catálogo estropeado y servicios que no cargan al crear el proyecto. Sin internet: las respuestas se simulan.
Ver docs/PLAN_PRUEBAS.md. Uso: tools\\probar.bat (o tools\\run_tests.py casos_servicios_test.py)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import caso, panel  # noqa: E402

from qgis.PyQt.QtCore import QByteArray, Qt  # noqa: E402
from qgis.PyQt.QtNetwork import QNetworkReply  # noqa: E402

svc = comun.svc
VECTORIAL = os.path.join(comun.DATA, 'vectorial')
CAIDO = svc.Service('Servicio caído', 'http://127.0.0.1:9/wms', 'capa', svc.WMS)  #Puerto cerrado: no responde nunca
WMS_OK = b"""<?xml version="1.0"?><WMS_Capabilities version="1.3.0"><Capability><Layer><Title>Raiz</Title>
<CRS>EPSG:25830</CRS><Layer><Name>uno</Name><Title>Capa uno</Title></Layer></Layer></Capability></WMS_Capabilities>"""


class Respuesta:
    """Respuesta de red simulada (lo mínimo que usa el panel)."""

    def __init__(self, datos, error=QNetworkReply.NetworkError.NoError, texto=''):
        self.datos, self._error, self.texto = datos, error, texto

    def readAll(self):
        return QByteArray(self.datos)

    def error(self):
        return self._error

    def errorString(self):
        return self.texto

    def deleteLater(self):
        pass


def _servicio_desplegable(dw):
    """Un servicio completo (sin capa) en el árbol, como una conexión de QGIS."""
    raiz = dw._root("Pruebas")
    return dw._add_service_node(raiz, svc.Service('Servidor de prueba', 'http://127.0.0.1:9/wms', '', svc.WMS))


@caso('S01', '★ sin haber hecho clic en una capa de servicio')
def _():
    dw = panel()
    dw.toggle_favorite()
    return comun.avisado('haz clic'), comun.avisos()


@caso('S02', '★ cuando no se puede guardar favoritos.json (perfil sin permiso)')
def _():
    dw = panel()
    original = svc.favorites_path
    fichero = os.path.join(comun.carpeta('perfil_roto'), 'soy_un_fichero')
    with open(fichero, 'w') as f:
        f.write('x')
    svc.favorites_path = lambda: os.path.join(fichero, 'favoritos.json')
    try:
        hoja = dw._add_service_node(dw._root('Pruebas'), svc.Service('Capa', 'http://x/wms', 'c', svc.WMS))
        dw.servicesTree.setCurrentItem(hoja)
        dw.toggle_favorite()
    finally:
        svc.favorites_path = original
    return comun.avisado('favorito'), comun.avisos()


@caso('S03', 'Desplegar un servicio: respuestas raras del servidor se ven como un texto claro en el árbol')
def _():
    dw = panel()
    respuestas = {
        'vacía': Respuesta(b''),
        'página web': Respuesta(b'<html><body>Mantenimiento</body></html>'),
        'error del servidor': Respuesta(b'<ServiceExceptionReport><ServiceException>Capa no encontrada'
                                        b'</ServiceException></ServiceExceptionReport>'),
        'sin capas': Respuesta(b'<WMS_Capabilities><Capability><Layer><Title>Nada</Title></Layer></Capability></WMS_Capabilities>'),
        'error de red': Respuesta(b'', QNetworkReply.NetworkError.ConnectionRefusedError, 'Connection refused'),
        'tiempo agotado': Respuesta(b'', QNetworkReply.NetworkError.OperationCanceledError, 'Operation canceled'),
        'binario': Respuesta(os.urandom(300)),
        'correcta': Respuesta(WMS_OK),
    }
    textos = {}
    for nombre, respuesta in respuestas.items():
        item = _servicio_desplegable(dw)
        dw._service_layers_received(item, svc.Service.from_dict(item.data(0, comun.dock.SERVICE_ROLE)), respuesta)
        textos[nombre] = [item.child(i).text(0) for i in range(item.childCount())]
    problemas = {n: comun.revisar_mensaje(t[0]) for n, t in textos.items() if n != 'correcta' and t}
    problemas = {n: p for n, p in problemas.items() if p}
    return textos['correcta'] == ['Capa uno'] and not problemas and all(textos.values()), (textos, problemas)


@caso('S04', 'Desplegar un servicio y recargar el árbol antes de que llegue la respuesta')
def _():
    dw = panel()
    item = _servicio_desplegable(dw)
    servicio = svc.Service.from_dict(item.data(0, comun.dock.SERVICE_ROLE))
    dw.load_services_tree()  #El elemento deja de existir
    dw._service_layers_received(item, servicio, Respuesta(WMS_OK))
    return True


@caso('S05', 'Sección de servicios activada sin ningún servicio marcado')
def _():
    dw = panel()
    comun.preparar(dw, [VECTORIAL], ['zonas_4326.shp'], comun.carpeta('dest_serv'), 'servicios')
    dw.addWMS.setChecked(True)
    dw.create_project(background=False)
    return comun.avisado('servicio'), comun.avisos()


@caso('S06', 'Un servicio marcado no responde al crear: el proyecto se crea con el resto y se explica qué hacer')
def _():
    dw = panel()
    comun.preparar(dw, [VECTORIAL], ['zonas_4326.shp'], comun.carpeta('dest_caido'), 'caido')
    dw.config_services = [CAIDO]
    dw.load_services_tree()
    dw.addWMS.setChecked(True)
    resultado = comun.crear(dw)
    return resultado is not None and any('Servicio caído' in p for p in resultado['problemas']), (
        resultado and resultado['problemas'], comun.avisos())


@caso('S07', 'Revisión semanal: un favorito caído se avisa (con qué hacer) y queda desactivado con ⛔')
def _():
    svc.save_favorites([CAIDO], svc.favorites_path())
    dw = panel()

    class Tarea:
        resultados = {CAIDO.key(): {'ok': False, 'url': CAIDO.url, 'detalle': 'no responde'}}
        catalogo_remoto = None

    dw.health_task = Tarea()
    dw._health_finished()
    hoja = next(it for it in comun.todo(dw.servicesTree.invisibleRootItem()) if 'Servicio caído' in it.text(0))
    os.remove(svc.favorites_path())
    os.remove(svc.health_path())
    return comun.avisado('Servicio caído') and hoja.isDisabled() and '⛔' in hoja.text(0), comun.avisos()


@caso('S08', '«Marcar favoritos por defecto»: al empezar un proyecto nuevo salen marcados')
def _():
    svc.save_favorites([svc.Service('Fav', 'http://x/wms', 'c')], svc.favorites_path())
    dw = panel()
    dw.favoritesDefault.setChecked(True)
    dw.reset_form()
    marcados = dw.selected_services()
    dw.favoritesDefault.setChecked(False)
    os.remove(svc.favorites_path())
    return dw.addWMS.isChecked() and len(marcados) == 1, marcados


@caso('S09', 'Catálogo de servicios estropeado: el panel sigue funcionando y explica qué hacer')
def _():
    roto = os.path.join(comun.carpeta('catalogo_roto'), 'services.json')
    with open(roto, 'w', encoding='utf-8') as f:
        f.write('{"grupos": [ esto no es json')
    original = svc.best_catalog_path
    svc.best_catalog_path = lambda: roto
    try:
        dw = comun.dock.ProjectBuilderDockWidget(comun.qgis.utils.iface)
        comun.PANELES.append(dw)
        dw.load_services_tree()
    finally:
        svc.best_catalog_path = original
    return comun.avisado('services.json'), comun.avisos()


@caso('S10', 'Servicio con nombre, capa y dirección con caracteres raros (comillas, &, tildes)')
def _():
    raro = svc.Service("Mapa \"raro\" & 'cía' — Málaga", "https://ejemplo.es/wms?map=a&b=c'd", "capa:con&raros'", svc.WMS)
    dw = panel()
    comun.preparar(dw, [VECTORIAL], ['zonas_4326.shp'], comun.carpeta('dest_raro'), 'raro')
    dw.config_services = [raro]
    dw.load_services_tree()
    dw.addWMS.setChecked(True)
    resultado = comun.crear(dw)
    return resultado is not None, (resultado and resultado['problemas'])


@caso('S11', 'Conexiones de QGIS con datos incompletos o repetidas no rompen el árbol')
def _():
    from qgis.core import QgsSettings
    ajustes = QgsSettings()
    for nombre, url in (('Sin url', ''), ('Repetida', 'https://www.ign.es/wms-inspire/pnoa-ma'),
                        ('Repetida 2', 'https://www.ign.es/wms-inspire/pnoa-ma'), ('Rara & "x"', 'no es una url')):
        ajustes.setValue(f'qgis/connections-wms/{nombre}/url', url)
    try:
        dw = panel()
        dw.load_services_tree()
        textos = [it.text(0) for it in comun.todo(dw.servicesTree.invisibleRootItem())]
    finally:
        ajustes.remove('qgis/connections-wms')
    return True, textos


comun.terminar('H05 Servicios web')
