"""
ProjectBuilder - Panel (dock) con la interfaz y la lógica de creación del proyecto.

copyright : (C) 2023 by Francisco Gómez Losada
email     : pgomezlosada@gmail.com
license   : GNU GPL v2 or later
"""

import os

import processing
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsLayerTreeLayer,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QTreeWidgetItem

from .wms.wms import dict_wms

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'project_builder_dockwidget_base.ui'))
pathplugin = os.path.dirname(__file__)


class ProjectBuilderDockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()

    def __init__(self, iface, parent=None):
        """Constructor."""
        super().__init__(parent)
        self.setupUi(self)

        self.iface = iface


        # Disparadores
        self.selectFolder.clicked.connect(lambda: self.SELECT_FOLDER_AND_PROJECT(self.pathFolder))
        self.selectFolderProject.clicked.connect(lambda: self.SELECT_FOLDER(self.pathFolderProject))
        self.createProject.clicked.connect(lambda: self.CREATE_PROJECT())
        self.treeWidget.itemActivated.connect(self.selectTreeChilds) #Función selección hijos en el árbol (con el doble click)
        self.treeWidget.clear()
        self.addWMStoCombo() #Llamar a funcion añade wms a combo al inicio


    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()
    
    
    def SELECT_FOLDER(self,qt_element):
        folder = QFileDialog.getExistingDirectory(None, "Selecciona Carpeta", "", QFileDialog.Option.DontResolveSymlinks)
        qt_element.setText(folder)
 


    def SELECT_FOLDER_AND_PROJECT(self,qt_element):
        folder = QFileDialog.getExistingDirectory(None, "Selecciona Carpeta", "", QFileDialog.Option.DontResolveSymlinks)
        qt_element.setText(folder)
        self.treeWidget.clear()
        if os.path.isdir(folder):
            self.load_project_structure(folder,self.treeWidget) # pathFolder seleccionar la ruta


    def selectTreeChilds(self, item, column, select = 0):
        # Recorrer todos los elementos secundarios y seleccionarlos
        if select == 0:
            if item.isSelected():
                select == 1 #False
                selectBool = True
            else:
                select == 2
                selectBool = False
        else:
            if select == 1:
                selectBool = True
            else:
                selectBool = False
        for i in range(item.childCount()):
            child_item = item.child(i)
            child_item.setSelected(selectBool)
            self.selectTreeChilds(child_item, column, select=selectBool) #AttributeError: 'QTreeWidget' object has no attribute 'selectTreeChilds'
    


    def load_project_structure(self, startpath, tree):
        """
        Load Project structure tree
        :param startpath: 
        :param tree: 
        :return: 
        """
        lista_vectoriales = ('.shp','.gpkg')
        lista_raster = ('.tif','.ecw')
        lista_todos = ('.shp','.gpkg','.tif','.ecw')
        for element in os.listdir(startpath):
            path_info = startpath + "/" + element
            si_formato = 0
            for ext in lista_todos:
                if element.endswith(ext):
                    si_formato = 1
            if si_formato == 1 or os.path.isdir(path_info):
                parent_itm = QTreeWidgetItem(tree, [os.path.basename(element)])
                parent_itm.setData(0, Qt.ItemDataRole.UserRole, path_info) #Se le guarda la ruta al objeto internamente (se ve en el panel el nombre, pero no la ruta)
            if os.path.isdir(path_info): #Se comprueba si es un directorio
                self.load_project_structure(path_info, parent_itm)
                parent_itm.setIcon(0, QIcon(os.path.join(pathplugin,'icon','folder.png')))
            else: #Si no es un directorio...
                definido = 0
                for ext in lista_vectoriales:
                    if element.endswith(ext): #Comprobar si es extensión vectorial y añade icono
                        parent_itm.setIcon(0, QIcon(os.path.join(pathplugin,'icon','file_vectorial.png')))
                        definido = 1
                        break
                if definido == 0: #Si es 0 no es vectorial y ñade icono raster
                    for ext in lista_raster:
                        if element.endswith(ext):
                            parent_itm.setIcon(0, QIcon(os.path.join(pathplugin,'icon','file_raster.png')))
                            definido = 1
                            break
    


    def CREATE_PROJECT(self):
        # Comprobar nombre proyecto
        if self.nameProject.text() != '':
            nameProject =  self.nameProject.text()
            pass 
        else: 
            return QMessageBox.warning(self,"Error","No se ha introducido un nombre para el proyecto")
        
        # Comprobar directorio proyecto
        if os.path.isdir(self.pathFolderProject.text()):
            pathFolderProject = self.pathFolderProject.text()
            pass 
        else: 
            return QMessageBox.warning(self,"Error","Carpeta de proyecto no válida")

        # Comprobar directorio capas
        if os.path.isdir(self.pathFolder.text()):
            pathFolder = self.pathFolder.text()
            pass 
        else: 
            return QMessageBox.warning(self,"Error","Acceso a capas no válido")
        
        if self.addWMS.isChecked() and len(self.wmsComboBox.checkedItems()) == 0:
            return QMessageBox.warning(self,"Error",f"No ha seleccionado ningún WMS")

        # Comprobar que elementos del árbol estan seleccionados
        selected_items = self.treeWidget.selectedItems()
        paths_source = [] #Esta será la lista donde se añaden las rutas de los elementos seleccionados
        for item in selected_items: #Comprueba los items seleccionados y añade la ruta a paths_source
            # Haz algo con el elemento seleccionado
            paths_source.append(item.data(0, Qt.ItemDataRole.UserRole)) #Recupera la ruta guardada internamente con Data de la línea 151

        paths_target = [f.replace(pathFolder,pathFolderProject) for f in paths_source] #Reemplaza las rutas de origen de las capas por las nuevas rutas de destino (carpeta proyecto elegida)
        
        # Comprobar CRS seleccionado
        selected_CRS = self.selectProjection.crs()
        
        project = self.createProjectQGIS(pathFolderProject, nameProject, selected_CRS)

        for path_source, path_target in zip(paths_source, paths_target):# bucle con dos variables a la vez
            if os.path.isdir(path_source): #Comprobar si es un directorio
                os.makedirs(path_target, exist_ok=True) #Crear directorio si lo es y de forma recursiva (creando las carpetas y subcarpetas donde este el archivo)
            else:
                os.makedirs(os.path.dirname(path_target), exist_ok=True)
                filename = os.path.basename(path_target)
                name_layer = os.path.splitext(filename)[0]
                ext_layer = os.path.splitext(filename)[1]

                if ext_layer.endswith('.shp'):
                    type_layer = 'shp'
                    qml_layer = path_source.replace('.shp','.qml')
                elif ext_layer.endswith('.gpkg'):
                    type_layer = 'shp'
                    qml_layer = None
                else:
                    type_layer = 'raster'
                    qml_layer = path_source.replace('.tif','.qml')

                #Función exportar y reproyectar capa. Requiere crs en estructura EPSG:25830
                export_result = self.exportLayerToFolder(ext_layer, path_source, path_target, self.selectProjection.crs())
                if export_result == False:
                    continue

                self.addLayerToProject(project, path_target, ext_layer, name_layer, qml_layer)

        
        if self.addWMS.isChecked(): #Si el boton de wms esta activado.. comprobar wms, 
            if len(self.wmsComboBox.checkedItems()) > 0:
                self.createGroupLayer( project, 'WMS') # Crear el grupo si hay alguno seleccionado
                for wms in self.wmsComboBox.checkedItems(): #Recorrer wms seleccionados y obtener name y url del diccionario
                     self.addWmsToProject(project, wms, dict_wms[wms]['name'], dict_wms[wms]['url'])

        self.saveProject(project)
        
        #Mensaje de que se ha creado el proyecto
        success_message = f"Proyecto creado en la ruta: <a href='file:///{pathFolderProject}'>{pathFolderProject} </a> "
        self.iface.messageBar().pushMessage("Success", success_message, level=Qgis.MessageLevel.Success, duration=10)
        
                

    def createProjectQGIS(self, path, filename, crs):
        """
        Create project QGIS with path and filename
        """
        path_file = os.path.join(path, filename+'.qgs')
        project = QgsProject()
        project.setFileName(filename)
        project.setCrs(crs)
        self.saveProject(project, path_file)
        return project


    def saveProject(self, project, path_save=None):
        """
        Save project:  path_save automatic when None from current path
        """
        if path_save==None:
            project.write(project.absoluteFilePath())
        else:
            project.write(path_save)
        return project


    #Función de exportación de capa con reproyección
    def exportLayerToFolder(self, ext, path_source, path_target, src):
        try:
            if ext in ('.shp', '.gpkg'):
                processing.run("native:reprojectlayer", {'INPUT':path_source,
                                                            'TARGET_CRS':QgsCoordinateReferenceSystem(src),
                                                            'OUTPUT':path_target})
            elif ext in ('.tif'):
                processing.run("gdal:warpreproject", {'INPUT':path_source,
                                                        'SOURCE_CRS':None,
                                                        'TARGET_CRS':QgsCoordinateReferenceSystem(src),
                                                        'RESAMPLING':0,
                                                        'NODATA':None,
                                                        'TARGET_RESOLUTION':None,
                                                        'OPTIONS':'',
                                                        'DATA_TYPE':0,
                                                        'TARGET_EXTENT':None,
                                                        'TARGET_EXTENT_CRS':None,
                                                        'MULTITHREADING':False,
                                                        'EXTRA':'',
                                                        'OUTPUT':path_target})
            else:
                QMessageBox.warning(self,"Error",f"El formato: {ext} no está disponible en la exportación")
                return False
        except Exception as e:
            QMessageBox.warning(self,"Error",f"Excepción {e}")
            return False
        else:
            return True
            


    def addLayerToProject(self, project, path_layer, extension, name_layer, qml_path=None):
        """
        Add vector/raster layers to project 
        """

        if extension in ('.shp'):
            provider = 'ogr'
            layer = QgsVectorLayer(path_layer,name_layer,provider)
            layer.setProviderEncoding(u'UTF-8')
            self.addLayerToRoot(project, layer, qml_path)
        elif extension in ('.gpkg'):
            for sublayer in QgsProviderRegistry.instance().querySublayers(path_layer):
                if sublayer.type() != Qgis.LayerType.Vector:
                    continue
                sub_layer = QgsVectorLayer(sublayer.uri(), sublayer.name(), 'ogr')
                self.addLayerToRoot(project, sub_layer, qml_path)
        elif extension in ('.tif'):
            layer = QgsRasterLayer(path_layer,name_layer)
            self.addLayerToRoot(project, layer, qml_path)
        else:
            return QMessageBox.warning(self,"Error",f"Error en la capa: {name_layer}. No se reconoce el tipo")
        


    def addLayerToRoot(self, project, layer, qml_path):
        #Add qml
        if qml_path != None:
            layer.loadNamedStyle(qml_path)

        project.addMapLayer(layer,False) #Se añade al mapa pero no aparece en el árbol
        root = project.layerTreeRoot()
        root.insertChildNode(0, QgsLayerTreeLayer(layer)) #Se añade al árbol de capas. el índice 0 indica la posición en el árbol de capas
        root.findLayer(layer.id()).setExpanded(False) #La capa aparece sin expandir
        root.findLayer(layer.id()).setItemVisibilityChecked(False) #La capa aparece no visible

    
    def createGroupLayer(self, project, group_name):
        """Función que crea un grupo"""

        root = project.layerTreeRoot()
        group = root.addGroup(group_name)
        group.setIsMutuallyExclusive(False) #True (permite activar una sola capa), False (permite activar varias capas a la vez)
        group.setExpanded(False)
        group.setItemVisibilityChecked(False)

    
    def addWMStoCombo(self):
        """Añadir nombres wms a combo"""
        lista_wms = dict_wms.keys()
        self.wmsComboBox.clear()
        self.wmsComboBox.addItems(lista_wms)


    def addWmsToProject(self, project, name_tree, name_layer, url):
        """
        Add wms layers
        """
        root = project.layerTreeRoot() #Se lee el arbol de capas
        layer = QgsRasterLayer(url, name_layer, 'wms')
        if not layer.isValid():
            return QMessageBox.warning(self,"Error",f"El servicio {name_tree} no se ha podido cargar")
        layer.setName(name_tree)
        project.addMapLayer(layer,False)
        rg = root.findGroup('WMS')
        rg.insertChildNode(-1, QgsLayerTreeLayer(layer)) #Crear capa dentro de grupo (se le cambia el valor 0 por -1 para que el orden del combowms sea el mismo en el grupo de capas creado)
        rg.findLayer(layer.id()).setExpanded(False)
        rg.findLayer(layer.id()).setItemVisibilityChecked(False)
