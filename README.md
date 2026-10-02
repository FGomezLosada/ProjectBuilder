# ProjectBuilder

Plugin de QGIS que crea un proyecto (`.qgz`) a partir de una selección de capas locales y servicios WMS.
Las capas se **copian y reproyectan** al SRC elegido dentro de la carpeta del proyecto, conservando la
estructura de subcarpetas y sus estilos `.qml`.

- Compatible con **QGIS 3.34+ y QGIS 4.x**
- Formatos: Shapefile, GeoPackage (todas sus capas) y GeoTIFF
- Servicios WMS configurables en [`services.json`](services.json)
- Exportación en segundo plano, con progreso y cancelación

## Uso
1. **Capas**: elige la carpeta de origen y marca las capas o carpetas (☑) que quieras incluir.
2. **WMS** (opcional): marca *Añadir WMS* y elige los servicios.
3. **Proyecto**: nombre, SRC y carpeta de destino (no puede ser la de origen ni estar dentro de ella).
4. Pulsa **Crear proyecto**. Al terminar, el mensaje verde permite abrirlo directamente.

Las capas se añaden ocultas para que el proyecto abra rápido.

## Añadir servicios WMS
Edita `services.json` y añade un bloque con `name`, `url`, `layer` y `crs`.
El valor de `layer` se consulta en QGIS: *Administrador de fuentes de datos → WMS/WMTS → Conectar*, columna *Nombre*.

## Desarrollo
Ver [`docs/DESARROLLO.md`](docs/DESARROLLO.md). Prueba rápida desde la consola de Python de QGIS:
```python
exec(open(r"RUTA\ProjectBuilder\tests\smoke_test.py", encoding="utf-8").read())
```

## Autor y licencia
Francisco Gómez Losada · pgomezlosada@gmail.com · GNU GPL v2 o posterior.
Origen: Trabajo Fin de Máster (2023).
