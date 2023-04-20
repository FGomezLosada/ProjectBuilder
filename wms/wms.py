
# La estructura es: cada item del diciconario tiene un nombre ('Nombre del WMS fácil de reconocer') y cada item tiene un diccionario con name (nombre del layer del wms) y la url (del servicio wms)
dict_wms = {'Unidad administrativa': {'name': 'Unidad administrativa', 'url': 'crs=EPSG:25830&dpiMode=7&format=image/png&layers=AU.AdministrativeUnit&styles&url=https://www.ign.es/wms-inspire/unidades-administrativas', 'crs': 25830, 'type': 'wms'},
            'Nombres geográficos':{'name':'Nombres geográficos','url':'crs=EPSG:25830&dpiMode=7&format=image/png&layers=GN.GeographicalNames&styles&url=https://www.ign.es/wms-inspire/ngbe','crs': 25830, 'type': 'wms'},
            'Ortoimagen_PNOA_ma':{'name':'Ortoimagen__PNOA_ma','url':'crs=EPSG:25830&dpiMode=7&format=image/png&layers=OI.OrthoimageCoverage&styles&url=https://www.ign.es/wms-inspire/pnoa-ma','crs': 25830, 'type': 'wms'}
            }