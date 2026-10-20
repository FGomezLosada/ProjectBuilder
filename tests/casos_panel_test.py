"""
Plan de pruebas · H01 Panel y plugin (abrir, cerrar, botones en cualquier estado, ayuda, resumen) y H14 Resumen en vivo.
Ver docs/PLAN_PRUEBAS.md. Uso: tools\\probar.bat (o tools\\run_tests.py casos_panel_test.py)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
from comun import caso, panel  # noqa: E402

import qgis.utils  # noqa: E402
from qgis.core import QgsCoordinateReferenceSystem, QgsTask  # noqa: E402
from qgis.PyQt.QtCore import QMimeData, QSettings, QUrl  # noqa: E402

import project_builder  # noqa: E402

dock, svc = comun.dock, comun.svc


def _escribir(ruta, contenido):
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(contenido if isinstance(contenido, str) else json.dumps(contenido))


@caso('P01', 'Abrir el panel con el perfil vacío (primera vez)')
def _():
    dw = panel()
    return dw.treeWidget is not None and not comun.avisos(), comun.avisos()


class TareaFalsa(QgsTask):
    """Revisión de servicios sin internet: termina al momento sin comprobar nada."""

    def __init__(self, servicios):
        super().__init__("prueba: revisión de servicios", QgsTask.Flag.CanCancel)
        self.resultados, self.catalogo_remoto = {}, None

    def run(self):
        return True


@caso('P02', 'Abrir el panel con estado_servicios.json estropeado de varias formas')
def _():
    malos = ['no es json', '[]', '{"fecha": 5}', '{"servicios": []}', '{"servicios": {"x": "texto"}}',
             '{"fecha": "2020-13-45", "servicios": {"wms|http://a|b": {"ok": false, "url": 3}}}']
    fallos = []
    tarea_real = comun.dock.HealthTask
    comun.dock.HealthTask = TareaFalsa  #Sin internet: solo se comprueba que la revisión semanal se lanza sin errores
    try:
        for contenido in malos:
            _escribir(svc.health_path(), contenido)
            try:
                dw = panel()
                dw.load_services_tree()
                comun.START_HEALTH_CHECK(dw)  #La revisión semanal lee la fecha de ese fichero
                comun.procesar_eventos(0.5)
            except Exception as e:  # noqa: BLE001
                fallos.append(f"{contenido}: {e!r}")
    finally:
        comun.dock.HealthTask = tarea_real
        if os.path.exists(svc.health_path()):
            os.remove(svc.health_path())
    return not fallos, fallos


@caso('P03', 'Abrir el panel con favoritos.json con datos raros: se conservan los buenos y se avisa')
def _():
    bueno = {'name': 'Ortofoto', 'url': 'https://www.ign.es/wms-inspire/pnoa-ma', 'layer': 'OI.OrthoimageCoverage'}
    malos = [{'favoritos': [bueno, {'name': 'x', 'url': None}]}, {'favoritos': [bueno, {'name': 5, 'url': 7, 'layer': 3}]},
             {'favoritos': [bueno, 'texto', 3]}, {'favoritos': 'no es una lista'}]
    fallos = []
    try:
        for datos in malos:
            _escribir(svc.favorites_path(), datos)
            comun.MENSAJES.clear()
            dw = dock.ProjectBuilderDockWidget(qgis.utils.iface)
            comun.PANELES.append(dw)
            nombres = [f.name for f in dw.favorites]
            if not comun.avisos():
                fallos.append(f"sin aviso con {datos}")
            if isinstance(datos['favoritos'], list) and 'Ortofoto' not in nombres:
                fallos.append(f"se ha perdido el favorito bueno con {datos}")
            dw.toggle_favorite()  #Pulsar ★ después no debe fallar
            dw.load_services_tree()  #Y la segunda vez ya no hay nada que avisar (se guardó limpio)
    finally:
        for f in os.listdir(comun.PERFIL):
            if f.startswith('favoritos'):
                os.remove(os.path.join(comun.PERFIL, f))
    return not fallos, fallos


@caso('P04', 'Catálogo descargado más nuevo pero con servicios rotos: se usa el del plugin')
def _():
    ruta = os.path.join(comun.PERFIL, 'services_remoto.json')
    _escribir(ruta, {'version': '2999-01-01', 'grupos': [{'nombre': 'Roto', 'servicios': [{'name': 'x', 'url': None}]}]})
    try:
        dw = panel()
        dw.load_services_tree()
    finally:
        os.remove(ruta)
    grupos = [dw.servicesTree.topLevelItem(i).text(0) for i in range(dw.servicesTree.topLevelItemCount())]
    catalogo = next((dw.servicesTree.topLevelItem(i) for i in range(dw.servicesTree.topLevelItemCount())
                     if dw.servicesTree.topLevelItem(i).text(0) == 'Catálogo ProjectBuilder'), None)
    hijos = [catalogo.child(i).text(0) for i in range(catalogo.childCount())] if catalogo else []
    return catalogo is not None and 'Roto' not in hijos and len(hijos) > 3, (grupos, hijos)


@caso('P05', 'Opciones guardadas de QGIS con valores raros (SRC, plantillas, carpetas)')
def _():
    ajustes = QSettings()
    for clave, valor in (('last_crs', 'no es un SRC'), ('layout_files', 5), ('favorites_default', 'quizá'),
                         ('last_project_dir', ['x', 'y']), ('last_layers_dir', 3), ('last_layout_dir', None)):
        ajustes.setValue('project_builder/' + clave, valor)
    try:
        dw = panel()
        dw.select_project_folder()
        dw.select_layers_folder()
        dw.add_layout_file()
        dw.import_config_file()
        crs = dw.selectProjection.crs()
        return crs.isValid(), crs.authid()
    finally:
        ajustes.remove('project_builder')


@caso('P06', 'Abrir y cerrar el plugin varias veces (también recargarlo)')
def _():
    for _vez in range(3):
        plugin = project_builder.classFactory(qgis.utils.iface)
        plugin.initGui()
        plugin.run()
        plugin.run()  #Pulsar dos veces el botón del plugin
        plugin.dockwidget.update_summary()
        plugin.unload()
        comun.procesar_eventos(0.1)
    return True


@caso('P07', 'Pulsar todos los botones con el panel vacío: nada falla y cada aviso dice qué hacer')
def _():
    dw = panel()
    acciones = [
        ('Crear proyecto', lambda: dw.create_project(background=False)),
        ('Informe de capas', dw.show_layers_report),
        ('Quitar carpeta', dw.remove_current_folder),
        ('★ favorito', dw.toggle_favorite),
        ('Quitar plantilla', dw.remove_layout_file),
        ('Añadir plantilla (cancelar)', dw.add_layout_file),
        ('Guardar configuración (cancelar)', dw.save_current_config),
        ('Borrar configuración', dw.delete_current_config),
        ('Exportar configuración', dw.export_current_config),
        ('Importar configuración (cancelar)', dw.import_config_file),
        ('Abrir carpeta de configuraciones', dw.open_configs_folder),
        ('Añadir carpeta (cancelar)', dw.select_layers_folder),
        ('Carpeta del proyecto (cancelar)', dw.select_project_folder),
        ('Nuevo', dw.reset_form),
        ('Ayuda', dw.open_help),
        ('⟳ servicios', dw.load_services_tree),
        ('Menú de bases de datos', dw.fill_database_menu),
        ('Abrir proyecto creado', dw.open_created_project),
        ('Abrir carpeta creada', dw.open_created_folder),
        ('Informe final', dw.show_final_report),
        ('Ver en el mapa (nada)', lambda: dw.show_on_map(None)),
        ('Doble clic (nada)', lambda: dw.tree_double_clicked(None)),
        ('Menú contextual (vacío)', lambda: dw.tree_menu(None)),
        ('Buscar «(»', lambda: dw.apply_filter('(*[\\')),
        ('Buscar servicios «*»', lambda: dw.apply_services_filter('*?)')),
        ('Soltar nada', lambda: dw.add_dropped([])),
        ('Soltar rutas vacías', lambda: dw.add_dropped(['', None, ('', None)])),
        ('Elegir «— Elegir —» en configuraciones', lambda: dw.config_chosen(0)),
        ('Elegir índice inexistente', lambda: dw.config_chosen(99)),
    ]
    fallos = []
    for nombre, accion in acciones:
        try:
            accion()
            comun.procesar_eventos(0.02)
        except Exception as e:  # noqa: BLE001
            fallos.append(f"{nombre}: {e!r}")
    return not fallos, fallos


@caso('P08', 'Con un proyecto creándose: el panel no deja cambiar nada ni lanzar otro')
def _():
    dw = panel()
    dw.task = object()  #Como si hubiera una exportación en marcha
    dw.set_busy(True)
    bloqueado = not dw.createProject.isEnabled() and not dw.scrollArea.isEnabled() and not dw.configCombo.isEnabled()
    dw.nameProject.setText('x')
    dw.pathFolderProject.setText(comun.carpeta('ocupado'))
    dw.addWMS.setChecked(True)
    dw.create_project()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(comun.DATA)])
    acepta = dw.drop_paths(mime) is not None and dw.task is None
    dw.task = None
    dw.set_busy(False)
    return bloqueado and not acepta and comun.avisado('ya se está creando'), comun.avisos()


@caso('P09', 'Cerrar el panel con temporizadores pendientes (resumen, árbol del proyecto)')
def _():
    dw = dock.ProjectBuilderDockWidget(qgis.utils.iface)
    dw.schedule_summary()
    dw.schedule_project_layers()
    dw.dropTimer.start()
    dw.deleteLater()
    comun.procesar_eventos(0.6)
    return True


@caso('P10', 'Botón de ayuda: abre el manual')
def _():
    dw = panel()
    dw.open_help()
    return any('MANUAL.md' in u for u in comun.ABIERTOS), comun.ABIERTOS


@caso('R01', 'Resumen en vivo: plurales, sin capas, con nombre y carpeta, SRC sin código')
def _():
    dw = panel()
    textos = [dw.summaryLabel.text()]
    dw.add_source_folder(os.path.join(comun.DATA, 'vectorial'))
    comun.marcar(dw, 'zonas_4326.shp')
    dw.update_summary()
    textos.append(dw.summaryLabel.text())
    comun.marcar(dw, 'lugares_4326.geojson')
    dw.nameProject.setText('resumen')
    dw.pathFolderProject.setText('C:/Proyectos')
    dw.selectProjection.setCrs(QgsCoordinateReferenceSystem.fromProj('+proj=tmerc +lon_0=-4 +ellps=GRS80 +units=m'))
    dw.update_summary()
    textos.append(dw.summaryLabel.text())
    ok = (textos[0].startswith('0 capas') and textos[1].startswith('1 capa ·') and textos[2].startswith('2 capas')
          and 'resumen.qgz' in textos[2] and 'None' not in ''.join(textos))
    return ok, textos


@caso('P11', 'Plugin instalado en un perfil de Windows con tildes y eñes (C:\\Users\\José Muñoz\\...): todo funciona')
def _():
    import importlib.util
    import shutil
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    perfil = os.path.join(comun.carpeta("Perfil de José Muñoz Peña"), 'python', 'plugins', 'project_builder')
    origen = comun.PLUGIN
    shutil.copytree(origen, perfil, ignore=shutil.ignore_patterns('tests', 'docs', 'tools', 'dist', '.git', '__pycache__'))
    spec = importlib.util.spec_from_file_location('pb_tildes', os.path.join(perfil, '__init__.py'),
                                                  submodule_search_locations=[perfil])
    modulo = importlib.util.module_from_spec(spec)
    sys.modules['pb_tildes'] = modulo
    spec.loader.exec_module(modulo)
    import pb_tildes.core.services as svc_copia
    import pb_tildes.project_builder_dockwidget as dock_copia
    svc_copia.profile_dir = lambda: comun.PERFIL
    svc_copia.favorites_path = lambda: os.path.join(comun.PERFIL, 'favoritos.json')
    svc_copia.health_path = lambda: os.path.join(comun.PERFIL, 'estado_servicios.json')
    dock_copia.ProjectBuilderDockWidget.start_health_check = lambda self, force=False: None
    avisos = []
    dock_copia.ProjectBuilderDockWidget.warn = lambda self, mensaje: avisos.append(mensaje)
    zona = QgsVectorLayer('Polygon?crs=EPSG:4326', 'zona José', 'memory')
    f = QgsFeature()
    f.setGeometry(QgsGeometry.fromWkt('POLYGON((-3.89 36.73,-3.85 36.73,-3.85 36.77,-3.89 36.77,-3.89 36.73))'))
    zona.dataProvider().addFeatures([f])
    QgsProject.instance().addMapLayer(zona)
    try:
        dw = dock_copia.ProjectBuilderDockWidget(qgis.utils.iface)
        comun.PANELES.append(dw)
        catalogo = dw.servicesTree.topLevelItemCount()
        comun.preparar(dw, [os.path.join(comun.DATA, 'vectorial')], ['zonas_4326.shp', 'lugares_4326.geojson'],
                       comun.carpeta('dest_perfil_tildes'), 'perfil_tildes')
        dw.groupZone.setChecked(True)
        dw.zoneByLayer.setChecked(True)
        dw.zoneLayer.setLayer(zona)
        dw.last_result = None
        dw.create_project(background=False)
        comun.procesar_eventos()
        resultado = dw.last_result
        capas, malas = comun.proyecto_valido(resultado['proyecto']) if resultado else (0, ['sin proyecto'])
    finally:
        QgsProject.instance().removeMapLayer(zona.id())
    return catalogo > 0 and resultado is not None and capas >= 3 and not malas and not avisos, (catalogo, capas, malas,
                                                                                                 avisos)


comun.terminar('H01 Panel y plugin')
