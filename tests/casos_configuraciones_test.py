"""
Plan de pruebas · H12 Configuraciones guardadas: guardar, cargar, borrar, importar, exportar y ficheros estropeados.
Ver docs/PLAN_PRUEBAS.md. Uso: tools\\probar.bat (o tools\\run_tests.py casos_configuraciones_test.py)
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import caso, panel  # noqa: E402

from qgis.PyQt.QtWidgets import QMessageBox  # noqa: E402

from project_builder.core import configs  # noqa: E402

VECTORIAL = os.path.join(comun.DATA, 'vectorial')


def _guardar(dw, nombre):
    dw.ask_name = lambda actual: nombre
    dw.save_current_config()


def _escribir(ruta, contenido):
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(contenido if isinstance(contenido, str) else json.dumps(contenido))
    return ruta


def _elegir(dw, nombre):
    indice = dw.configCombo.findText(nombre)
    dw.configCombo.setCurrentIndex(indice)
    dw.config_chosen(indice)


@caso('K01', 'Guardar: cancelar, nombre vacío y nombre solo con símbolos')
def _():
    dw = panel()
    _guardar(dw, '')
    antes = dw.configCombo.count()
    _guardar(dw, '***???')
    return dw.configCombo.count() == antes + 1 and dw.configCombo.findText('***???') > 0, comun.avisos()


@caso('K02', 'Guardar con un nombre que ya existe: se pregunta y se respeta la respuesta')
def _():
    dw = panel()
    dw.add_source_folder(VECTORIAL)
    _guardar(dw, 'repetida')
    dw.reset_form()
    _guardar(dw, 'otra')
    comun.RESPUESTAS['question'] = QMessageBox.StandardButton.No
    _guardar(dw, 'repetida')
    conservada = configs.load_config(configs.config_path('repetida'))['capas']['carpetas'] == [VECTORIAL]
    comun.RESPUESTAS['question'] = QMessageBox.StandardButton.Yes
    _guardar(dw, 'repetida')
    sustituida = configs.load_config(configs.config_path('repetida'))['capas']['carpetas'] == []
    return conservada and sustituida, comun.VENTANAS


@caso('K03', 'Cargar configuraciones con datos de tipos equivocados (editadas a mano): avisa y no falla')
def _():
    raras = [
        {'capas': 'texto', 'formato': 5, 'src': 12345, 'servicios': 'x', 'zona': [], 'composiciones': 'abc'},
        {'capas': {'carpetas': 'C:/x', 'sueltos': [None, 3], 'marcadas': [None, 'texto', {'ruta': None}]},
         'zona': {'activa': 'sí', 'tipo': 7, 'capa': 'x', 'rectangulo': [1, 2, 3], 'margen': 'mucho', 'seleccion': 'x'}},
        {'servicios': {'activo': True, 'lista': [None, 'x', {'name': 'sin url'}, {'name': 'a', 'url': None}]},
         'composiciones': [None, 'x', ['proyecto'], ['fichero', None]], 'bases_datos': ['x', {'proveedor': None}],
         'proyecto_abierto': ['x', None, {'id': None}]},
        {'zona': {'activa': True, 'tipo': 'rectangulo', 'rectangulo': ['a', 'b', 'c', 'd'], 'src_rectangulo': None}},
    ]
    fallos = []
    dw = panel()
    for i, datos in enumerate(raras):
        datos.update({'nombre': f'rara_{i}', 'version': 1})
        _escribir(configs.config_path(f'rara_{i}'), datos)
    dw.refresh_configs()
    for i in range(len(raras)):
        comun.MENSAJES.clear()
        try:
            _elegir(dw, f'rara_{i}')
        except Exception as e:  # noqa: BLE001
            fallos.append(f"rara_{i}: {e!r}")
        if not comun.avisos():
            fallos.append(f"rara_{i}: no avisa de que la configuración tiene datos raros")
    for i in range(len(raras)):
        os.remove(configs.config_path(f'rara_{i}'))
    return not fallos, fallos


@caso('K04', 'Cargar una configuración cuyas carpetas, capas y plantillas ya no existen: avisos claros')
def _():
    datos = comun.copia_datos('config_borrada')
    dw = panel()
    dw.add_source_folder(os.path.join(datos, 'vectorial'))
    comun.marcar(dw, 'zonas_4326.shp')
    _guardar(dw, 'con_borrados')
    import shutil
    shutil.rmtree(datos)
    comun.MENSAJES.clear()
    _elegir(dw, 'con_borrados')
    return comun.avisado('ya no existe'), comun.avisos()


@caso('K05', 'Importar ficheros que no son configuraciones: no JSON, GeoJSON, vacío, binario, inexistente')
def _():
    carpeta = comun.carpeta('importar')
    ficheros = {
        'texto.json': 'esto no es json',
        'geo.json': {'type': 'FeatureCollection', 'features': []},
        'vacio.json': '',
        'lista.json': [1, 2, 3],
    }
    rutas = [_escribir(os.path.join(carpeta, n), c) for n, c in ficheros.items()]
    binario = os.path.join(carpeta, 'binario.json')
    with open(binario, 'wb') as f:
        f.write(os.urandom(500))
    rutas += [binario, os.path.join(carpeta, 'no_existe.json')]
    dw = panel()
    antes = dw.configCombo.count()
    fallos = []
    for ruta in rutas:
        comun.MENSAJES.clear()
        dw.import_config_file(ruta=ruta)
        if not comun.avisos():
            fallos.append(f"sin aviso al importar {os.path.basename(ruta)}")
    return not fallos and dw.configCombo.count() == antes, (fallos, comun.avisos())


@caso('K06', 'Importar una configuración válida dos veces: la segunda se guarda como «nombre (2)»')
def _():
    dw = panel()
    dw.add_source_folder(VECTORIAL)
    _guardar(dw, 'compartida')
    exportada = os.path.join(comun.carpeta('exportar'), 'compartida.json')
    _elegir(dw, 'compartida')
    dw.ask_config_file = lambda guardar, propuesta='': exportada
    dw.export_current_config()
    dw.import_config_file(ruta=exportada)
    return dw.configCombo.findText('compartida (2)') > 0, [dw.configCombo.itemText(i) for i in range(dw.configCombo.count())]


@caso('K07', 'Exportar: sin elegir configuración y a una carpeta sin permiso')
def _():
    dw = panel()
    dw.configCombo.setCurrentIndex(0)
    dw.export_current_config()
    primero = comun.avisado('elige')
    if os.name != 'nt':
        return primero, comun.avisos()
    _guardar(dw, 'exportable')
    _elegir(dw, 'exportable')
    bloqueada = comun.carpeta('export_sin_permiso')
    subprocess.run(['icacls', bloqueada, '/deny', '*S-1-1-0:(OI)(CI)(W,AD,WD)'], capture_output=True)
    try:
        dw.ask_config_file = lambda guardar, propuesta='': os.path.join(bloqueada, 'x.json')
        comun.MENSAJES.clear()
        dw.export_current_config()
    finally:
        subprocess.run(['icacls', bloqueada, '/remove:d', '*S-1-1-0'], capture_output=True)
    return primero and comun.avisado('exportar'), comun.avisos()


@caso('K08', 'Borrar: sin elegir, y una configuración cuyo fichero ya se había borrado a mano')
def _():
    dw = panel()
    dw.configCombo.setCurrentIndex(0)
    dw.delete_current_config()
    primero = comun.avisado('elige')
    _guardar(dw, 'efimera')
    os.remove(configs.config_path('efimera'))
    _elegir(dw, 'efimera')
    comun.RESPUESTAS['question'] = QMessageBox.StandardButton.Yes
    dw.delete_current_config()
    return primero and dw.configCombo.findText('efimera') < 0, comun.avisos()


@caso('K09', 'Carpeta de configuraciones con ficheros estropeados: la lista los ignora y el resto funciona')
def _():
    os.makedirs(configs.configs_dir(), exist_ok=True)
    _escribir(os.path.join(configs.configs_dir(), 'rota.json'), '{ no es json')
    _escribir(os.path.join(configs.configs_dir(), 'lista.json'), '[1]')
    with open(os.path.join(configs.configs_dir(), 'binaria.json'), 'wb') as f:
        f.write(os.urandom(300))
    dw = panel()
    _guardar(dw, 'sana')
    nombres = [dw.configCombo.itemText(i) for i in range(dw.configCombo.count())]
    for f in ('rota.json', 'lista.json', 'binaria.json'):
        os.remove(os.path.join(configs.configs_dir(), f))
    return 'sana' in nombres and not any(n in nombres for n in ('rota', 'lista', 'binaria')), nombres


@caso('K10', 'Configuración creada con una versión más nueva del plugin: se carga y se avisa de actualizar')
def _():
    dw = panel()
    _escribir(configs.config_path('del_futuro'), {'nombre': 'del_futuro', 'version': 99, 'capas': {'carpetas': [VECTORIAL]},
                                                 'algo_nuevo': {'x': 1}})
    dw.refresh_configs()
    _elegir(dw, 'del_futuro')
    return dw.source_folders() == [VECTORIAL] and comun.avisado('actualiza'), comun.avisos()


@caso('K11', 'Guardar, cargar y volver a guardar no cambia nada (ida y vuelta completa)')
def _():
    dw = panel()
    dw.add_source_folder(VECTORIAL)
    comun.marcar(dw, 'zonas_4326.shp')
    dw.outputFormat.setCurrentIndex(2)
    dw.reprojectCheck.setChecked(False)
    dw.zoneMargin.setValue(250)
    _guardar(dw, 'ida')
    primera = dw.config_to_dict()
    dw.reset_form()
    _elegir(dw, 'ida')
    segunda = dw.config_to_dict()
    return primera == segunda, (primera, segunda)


@caso('K12', 'Perfil de QGIS de solo lectura: guardar y abrir la carpeta de configuraciones avisan')
def _():
    if os.name != 'nt':
        return True, 'solo en Windows'
    dw = panel()
    carpeta = configs.configs_dir()
    os.makedirs(carpeta, exist_ok=True)
    subprocess.run(['icacls', carpeta, '/deny', '*S-1-1-0:(OI)(CI)(W,AD,WD)'], capture_output=True)
    try:
        _guardar(dw, 'no_se_puede')
    finally:
        subprocess.run(['icacls', carpeta, '/remove:d', '*S-1-1-0'], capture_output=True)
    return comun.avisado('configuración'), comun.avisos()


@caso('K13', 'Arrastrar al panel: una configuración .json (válida y estropeada) y plantillas .qpt (válida y dañada)')
def _():
    from qgis.core import QgsPrintLayout, QgsProject, QgsReadWriteContext
    carpeta = comun.carpeta('arrastrar_k13')
    dw = panel()
    comun.preparar(dw, [VECTORIAL], ['zonas_4326.shp'], comun.carpeta('dest_k13'), 'arrastrada')
    _guardar(dw, 'Para arrastrar')
    valida = os.path.join(carpeta, 'compartida.json')
    configs.export_config('Para arrastrar', valida)
    configs.delete_config('Para arrastrar')
    rota = _escribir(os.path.join(carpeta, 'rota.json'), '{"version": 1, "capas": ')
    composicion = QgsPrintLayout(QgsProject.instance())
    composicion.initializeDefaults()
    buena = os.path.join(carpeta, 'buena.qpt')
    composicion.saveAsTemplate(buena, QgsReadWriteContext())
    danada = _escribir(os.path.join(carpeta, 'danada.qpt'), 'esto no es una plantilla')
    otro = panel()
    otro.pending_drops = [valida]  #Como al soltar en el panel (process_drops es lo que se ejecuta al soltar)
    otro.process_drops()
    comun.procesar_eventos()
    cargada = otro.configCombo.findText('Para arrastrar') >= 0 and otro.treeWidget.topLevelItemCount() == 1
    otro.pending_drops = [rota, buena, danada]
    otro.process_drops()
    comun.procesar_eventos()
    plantillas = [r for r in otro._layout_files()]
    otro._set_layout_files([])
    configs.delete_config('Para arrastrar')
    ok = (cargada and any(os.path.normcase(r) == os.path.normcase(buena) for r in plantillas)
          and not any(os.path.normcase(r) == os.path.normcase(danada) for r in plantillas)
          and comun.avisado('rota.json') and comun.avisado('danada.qpt'))
    return ok, (cargada, plantillas, comun.avisos())


comun.terminar('H12 Configuraciones')
