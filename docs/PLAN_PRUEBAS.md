# Plan de pruebas de ProjectBuilder

Objetivo: adelantarse a los fallos que pueda encontrar un usuario para que no caiga la confianza en el plugin.
Cada herramienta del panel tiene su **batería de casos** automática, que se ejecuta en QGIS 3.40 y en QGIS 4.2 con
`tools\probar.bat` (cada batería en un QGIS propio, sin ventana).

## Reglas

1. **Ninguna herramienta, nueva o ya hecha, se da por terminada sin su batería de casos pasando en 3.40 y 4.2.**
2. **Cada fallo que se encuentre a mano se convierte primero en un caso de la batería y después se corrige**; así no vuelve.
   (Ver «Registro de fallos» al final: cada fallo con su caso.)
3. **Ningún caso, por absurdo que sea, puede dar un error de Python o abrir una ventana: tiene que dar un mensaje claro
   en el panel.**
4. **Los mensajes también se prueban: deben decir qué pasa y qué hacer.**

## Estado por herramienta

| Herramienta | Batería | Casos | 3.40 | 4.2 |
|---|---|---|---|---|
| H01 Panel y plugin | `casos_panel_test.py` | 12 | ✅ | ✅ |
| H02 Árbol de capas | `casos_arbol_test.py` | 18 | ✅ | ✅ |
| H03 Proyecto abierto · H04 Bases de datos · H13 Estilos | `casos_origenes_test.py` | 14 | ✅ | ✅ |
| H05 Servicios web | `casos_servicios_test.py` | 11 | ✅ | ✅ |
| H06 Zona de trabajo | `casos_zona_test.py` | 12 | ✅ | ✅ |
| H07 Formato y SRC · H08 Nombre y carpeta | `casos_destino_test.py` | 14 | ✅ | ✅ |
| H09 Crear · H10 Informes | `casos_crear_test.py`, `casos_fondo_test.py` | 14 | ✅ | ✅ |
| H11 Composiciones | `casos_composiciones_test.py` | 6 | ✅ | ✅ |
| H12 Configuraciones | `casos_configuraciones_test.py` | 13 | ✅ | ✅ |
| H14 Formatos y datos de entrada | `casos_formatos_test.py` | 7 | ✅ | ✅ |
| H15 Mensajes | `auditoria_mensajes_test.py` | 3 | ✅ | ✅ |

Última pasada completa: 20/10/2026, QGIS 3.40.13 y 4.2.2, **TODO CORRECTO** (estas 12 baterías y las 12 pruebas anteriores
del uso normal: `smoke_test.py`, `zone_test.py`, `robustez_test.py`...).

## Cómo se vigilan las reglas 3 y 4 en todos los casos

Las baterías nuevas (`tests/casos_*_test.py`) usan `tests/comun.py`, que en **cada** caso, además de lo que el caso
compruebe, vigila:

- **Errores de Python**: cualquier error que llegara a Qt (lo que en QGIS abre la ventana de error de Python) hace fallar
  el caso. `tools/run_tests.py` además marca como fallida cualquier prueba en cuya salida aparezca un error de Python.
- **Ventanas**: si algo intenta abrir una ventana de aviso (QMessageBox de aviso, error o información), el caso falla.
  Las ventanas «normales» (elegir un fichero, confirmar un borrado) se contestan solas según el caso.
- **Mensajes**: cada aviso del panel (y cada problema del informe final) pasa por `revisar_mensaje`:
  - sin restos técnicos: nada de errores de Python o del sistema en inglés (`Permission denied`, `[WinError 5]`,
    `NoneType`, `Could not`...);
  - los avisos (amarillos o rojos) tienen que decir **qué hacer** («elige», «comprueba», «cierra», «vuelve a»...) o que
    **no hace falta hacer nada**.
- Además, `auditoria_mensajes_test.py` revisa **todos los mensajes escritos en el código**, aunque ningún caso llegue a
  provocarlos (M01), y que los errores del sistema y de QGIS se traducen a palabras del usuario (M02, `core/mensajes.py`).

En el propio plugin, todo lo que el usuario puede lanzar (botones, menús, arrastrar, temporizadores) pasa por
`protegido()`: si algo imprevisto fallara, en lugar de la ventana de error de Python sale un aviso claro en el panel y el
detalle queda en *Ver → Paneles → Registro de mensajes* (pestaña ProjectBuilder) para poder enviarlo. Las pruebas
comprueban que eso **no pase nunca** (`ERRORES_INESPERADOS` vacío).

## Tipos de caso

- **N** · uso normal · **L** · límite (vacío, muy grande, repetido, nombres raros) · **A** · absurdo o maltrato (ficheros
  dañados, borrados a mitad, sin permiso, datos editados a mano) · **M** · mensaje (qué dice y si se entiende).

## Herramientas y casos

Las pruebas que ya existían cubren el uso normal de cada herramienta; las baterías `casos_*` cubren los casos límite,
absurdos y los mensajes. Entre paréntesis, el fichero de la batería.

### H01 · Panel y plugin (`casos_panel_test.py`)
| ID | Caso | Tipo |
|---|---|---|
| P01 | Abrir el panel con el perfil vacío (primera vez) | N |
| P02 | `estado_servicios.json` estropeado de seis formas (no JSON, lista, fecha numérica, servicios como lista...) | A |
| P03 | `favoritos.json` con datos raros: se conservan los buenos, se quitan los dañados (con copia) y se avisa | A |
| P04 | Catálogo descargado más nuevo pero con servicios rotos: se usa el del plugin | A |
| P05 | Opciones guardadas de QGIS con valores raros (SRC, plantillas, carpetas recordadas) | A |
| P06 | Abrir y cerrar el plugin varias veces, pulsar dos veces su botón, recargarlo | L |
| P07 | Pulsar **todos** los botones y menús con el panel vacío | A, M |
| P08 | Con un proyecto creándose: no se puede cambiar nada, ni lanzar otro, ni arrastrar | L, M |
| P09 | Cerrar el panel con temporizadores pendientes | L |
| P10 | Botón de ayuda: abre el manual | N |
| P11 | Plugin instalado en un perfil de Windows con tildes y eñes (C:\Users\José Muñoz\...) | L |
| R01 | Resumen en vivo: plurales, sin capas, con nombre y carpeta, SRC sin código EPSG | N, L |

### H02 · Árbol de capas (`casos_arbol_test.py`, además de `tree_test.py`)
| ID | Caso | Tipo |
|---|---|---|
| A01 | Añadir una carpeta que no existe | A, M |
| A02 | Carpeta vacía: al crear se pide marcar alguna capa | L, M |
| A03 | La misma carpeta dos veces, o una subcarpeta de una ya añadida | L |
| A04 | Subcarpeta con capas marcadas y luego su carpeta madre: se integran sin perder lo marcado | L |
| A05 | Nombres raros: mayúsculas, tildes, espacios, apóstrofo, emoji, «#», «%» (y crear con ellos) | L |
| A06 | Ficheros dañados o que no son capas (GeoPackage vacío, «.tif» de texto, JSON que no es GeoJSON, shapefile sin .dbf...) | A |
| A07 | Carpeta con miles de ficheros que no son capas: se añade en poco tiempo | L |
| A08 | Carpeta enorme (como añadir C:\ o Documentos): el recorrido se corta a tiempo y se explica qué hacer | A, M |
| A09 | Buscar: tildes, mayúsculas, sin resultados y caracteres especiales | L |
| A10 | Quitar carpeta sin hacer clic antes, y sobre el bloque del proyecto abierto | A, M |
| A11 | Arrastrar cosas raras: rutas que no existen, .dbf suelto, proyecto .qgz, texto, multicapa con capa inexistente | A, M |
| A12 | Arrastrar datos sin rutas, una URL web o capas del panel Capas de QGIS: no se aceptan | A |
| A13 | Información al pasar el ratón por cada tipo de elemento y por una capa borrada después de añadirla | L |
| A14 | «Ver en el mapa»: capa borrada, ráster sin SRC, capa vacía, un solo punto | A, M |
| A15 | Menú del clic derecho en cada tipo de elemento; «Quitar» y «Abrir la carpeta» | N |
| A16 | Capa marcada que se borra del disco antes de crear: se avisa antes de empezar, diciendo cuál y qué hacer | A, M |
| A17 | Carpeta de capas renombrada después de añadirla: se avisa antes de empezar | A, M |
| A18 | Multicapa con solo algunas capas internas marcadas, en los tres formatos | L |

### H03 · Proyecto abierto en QGIS · H04 · Bases de datos · H13 · Estilos e iconos (`casos_origenes_test.py`, además de `open_project_test.py`, `db_test.py`, `icons_test.py`)
| ID | Caso | Tipo |
|---|---|---|
| O01 | Capa rota del proyecto abierto (su fichero ya no está) marcada: se avisa antes de empezar | A, M |
| O02 | Capas temporales: vacía, con elementos y tabla sin geometría | L |
| O03 | Nombres raros, reservados de Windows (CON) o repetidos en grupos distintos, en dos formatos | L |
| O04 | Capa marcada que se quita de QGIS antes de crear | A |
| O05 | Teselas XYZ (sin internet) y capa con un filtro que no deja nada | L |
| O06 | Capa en edición con cambios sin guardar (del proyecto abierto o desde su carpeta): se avisa antes de empezar | A, M |
| O07 | Capas de texto delimitado (CSV con coordenadas, con tildes) y capas virtuales del proyecto abierto | N |
| B01 | Configuración con una conexión que ya no existe y con un proveedor desconocido | A, M |
| B02 | La misma conexión dos veces; base de datos sin tablas con geometría | L, M |
| B03 | Conexión a un GeoPackage borrado o movido | A, M |
| B04 | Tabla marcada que se borra de la base de datos antes de crear | A, M |
| B05 | PostGIS con el servidor apagado: aviso claro y rápido, sin mostrar la contraseña | A, M |
| E01 | Estilo .qml dañado, vacío o de otra geometría junto a la capa | A |
| E02 | Estilo con un icono SVG que no existe: se crea el proyecto y se explica qué hacer | A, M |

### H05 · Servicios web (`casos_servicios_test.py`, sin internet: las respuestas se simulan)
| ID | Caso | Tipo |
|---|---|---|
| S01 | ★ sin haber hecho clic en una capa | A, M |
| S02 | ★ cuando no se puede guardar `favoritos.json` | A, M |
| S03 | Desplegar un servicio que responde vacío, una página web, un error, sin capas, error de red, tiempo agotado, basura | A, M |
| S04 | Recargar el árbol antes de que llegue la respuesta del servidor | L |
| S05 | Sección de servicios activada sin ninguno marcado | A, M |
| S06 | Un servicio marcado no responde al crear: el proyecto se crea con el resto y se explica qué hacer | A, M |
| S07 | Revisión semanal: un favorito caído se avisa y queda desactivado (⛔) | N, M |
| S08 | «Marcar favoritos por defecto» al empezar un proyecto nuevo | N |
| S09 | Catálogo `services.json` estropeado: el panel sigue y explica qué hacer | A, M |
| S10 | Servicio con comillas, «&» y tildes en el nombre, la capa y la dirección | L |
| S11 | Conexiones de QGIS sin dirección, repetidas o con nombres raros | A |

### H06 · Zona de trabajo (`casos_zona_test.py`, además de `zone_test.py`)
| ID | Caso | Tipo |
|---|---|---|
| Z01 | Zona activada sin elegir capa | A, M |
| Z02 | Capa de zona sin elementos | A, M |
| Z03 | «Solo los seleccionados» sin nada seleccionado | A, M |
| Z04 | Capa de zona sin SRC | A, M |
| Z05 | La capa de la zona se quita de QGIS después de elegirla (no debe saltar sola a otra capa) | A, M |
| Z06 | Rectángulo sin indicar | A, M |
| Z07 | Margen máximo permitido | L |
| Z08 | Zona que no toca ninguna capa: se explica que no hay datos en la zona | L, M |
| Z09 | Zona y proyecto en grados con margen (el margen se mide en metros) | L |
| Z10 | Zona imposible de pasar al SRC del proyecto (polo sur con UTM 30N) | A, M |
| Z11 | Rectángulo en un SRC distinto al del mapa y al del proyecto | L |
| Z12 | Zona de una capa temporal y configuración guardada con ella | L, M |

### H07 · Formato, SRC y reproyección · H08 · Nombre y carpeta del proyecto (`casos_destino_test.py`, además de `smoke_test.py`)
| ID | Caso | Tipo |
|---|---|---|
| D01 | Nombre vacío o solo con espacios | A, M |
| D02 | Nombres no válidos (\ / : * ? " < > \|, .qgz, CON, acabado en punto) | A, M |
| D03 | Ruta tan larga que Windows no podría guardar las capas | A, M |
| D04 | Carpeta vacía, relativa, que es un fichero, en una unidad que no existe | A, M |
| D05 | Carpeta sin permiso de escritura | A, M |
| D06 | Volver a crear un proyecto con el mismo nombre (sin mezclar tablas del anterior) | L |
| D07 | GeoPackage del proyecto anterior abierto en QGIS | A, M |
| D08 | Carpeta de red que no existe | A, M |
| F01 | Los tres formatos de salida × con/sin reproyección, con todos los tipos de capa de prueba | N |
| F02 | SRC del proyecto sin elegir | A, M |
| F03 | SRC geográfico (EPSG:4326) y SRC personalizado sin código EPSG | L |
| F04 | Capas con el mismo nombre en carpetas distintas o con distinta extensión | L |
| F05 | Dos carpetas de origen con el mismo nombre | L |
| D10 | Carpeta pegada entre comillas («Copiar como ruta de acceso» del Explorador), con espacios o con barras «/» | L, M |

### H09 · Crear el proyecto · H10 · Informes (`casos_crear_test.py`, `casos_fondo_test.py`, además de `stats_test.py` y `messages_test.py`)
| ID | Caso | Tipo |
|---|---|---|
| C01 | El .qgz no se puede escribir (hay una carpeta con ese nombre) | A, M |
| C02 | Un ráster dañado entre las capas: el resto se crea y se explica | A, M |
| C03 | Dos proyectos seguidos desde el mismo panel | N |
| C04 | Solo con capas del proyecto abierto | N |
| C05 | Doble clic en «Crear proyecto» (en segundo plano) | L, M |
| C06 | Cancelar la creación | N, M |
| C07 | Copiar la carpeta del proyecto creado a otro sitio (pendrive, otro ordenador): capas, iconos y logos se ven | N |
| C08 | Nombre y carpeta con tildes, eñes, espacios, apóstrofo y paréntesis (válidos) | L |
| I01 | «Abrir proyecto», «Abrir carpeta» e «Informe…» con el proyecto ya borrado | A, M |
| I02 | Nombres con <, >, & y comillas en el informe (HTML) | L |
| I03 | Guardar el informe en una carpeta que no existe, sin permiso, con extensión desconocida, cancelar | A, M |
| I04 | «Copiar» deja la tabla para Excel y para Word | N |
| I05 | Informe de capas sin nada marcado y con una capa que ya no existe | A, M |
| I06 | Problemas y capas sin datos aparecen en el informe final | N |

### H11 · Composiciones (`casos_composiciones_test.py`, además de `layout_test.py`)
| ID | Caso | Tipo |
|---|---|---|
| L01 | Añadir una plantilla que no existe | A, M |
| L02 | Plantillas dañadas (texto, vacía, XML de otra cosa): se avisa al añadirlas | A, M |
| L03 | Plantilla borrada del disco antes de crear | A, M |
| L04 | Composición del proyecto abierto borrada después de marcarla | A |
| L05 | Quitar plantilla sin hacer clic y sobre una composición del proyecto | A, M |
| L06 | Plantilla con un logo: el logo viaja con el proyecto | N |

### H12 · Configuraciones (`casos_configuraciones_test.py`, además de `config_test.py`)
| ID | Caso | Tipo |
|---|---|---|
| K01 | Guardar: cancelar, nombre vacío, nombre solo con símbolos | L |
| K02 | Guardar con un nombre que ya existe (Sí / No) | N |
| K03 | Cargar configuraciones editadas a mano con datos de tipos equivocados | A, M |
| K04 | Cargar una configuración cuyas carpetas ya no existen | A, M |
| K05 | Importar ficheros que no son configuraciones (no JSON, GeoJSON, vacío, binario, inexistente) | A, M |
| K06 | Importar la misma configuración dos veces | L |
| K07 | Exportar sin elegir y a una carpeta sin permiso | A, M |
| K08 | Borrar sin elegir y una cuyo fichero ya no está | A, M |
| K09 | Carpeta de configuraciones con ficheros estropeados | A |
| K10 | Configuración de una versión más nueva del plugin | L, M |
| K11 | Guardar, cargar y volver a guardar no cambia nada | N |
| K12 | Perfil de QGIS de solo lectura | A, M |
| K13 | Arrastrar al panel una configuración .json (válida y estropeada) y plantillas .qpt (válida y dañada) | A, M |

### H14 · Formatos y datos de entrada (`casos_formatos_test.py`)
| ID | Caso | Tipo |
|---|---|---|
| F10 | Todos los formatos vectoriales admitidos (shp, geojson, json, kml, gml, fgb, tab, mif, dxf, gpx, sqlite, gpkg) en los tres formatos de salida | N |
| F11 | Tildes, eñes y «€» se conservan desde UTF-8, ISO-8859-15 y Windows-1252 (con su .cpg), en los tres formatos | L |
| F12 | Geometrías 3D (Z, M), multiparte y curvas, con zona de trabajo | L |
| F13 | GeoPackage con una tabla sin geometría, con y sin zona | L |
| F14 | Ráster VRT (apunta a otro fichero), multibanda con «sin datos» y JPG con world file | L |
| F15 | Capa grande (50.000 polígonos) con zona, en segundo plano: termina en un tiempo razonable | L |
| F16 | Capas internas de un GeoPackage con espacios, tildes, guiones y mayúsculas | L |

### H15 · Mensajes (`auditoria_mensajes_test.py`)
| ID | Caso | Tipo |
|---|---|---|
| M01 | Todos los mensajes escritos en el código dicen qué pasa y qué hacer, sin restos técnicos | M |
| M02 | Los errores del sistema, de GDAL y de PostgreSQL se explican en palabras del usuario | M |
| M03 | Las indicaciones guardadas en constantes dicen qué hacer | M |

## Cómo se añade un caso

1. Elegir la batería de la herramienta (`tests/casos_<herramienta>_test.py`) y el siguiente ID libre.
2. Escribir el caso con `@caso('ID', 'qué pasa')`: preparar la situación, hacer lo que haría el usuario y devolver
   `(ok, detalle)`. Las reglas 3 y 4 se comprueban solas.
3. Ejecutarlo **antes** de corregir nada (debe fallar: así se sabe que el caso detecta el fallo).
4. Corregir, ejecutar `tools\probar.bat` (las dos versiones de QGIS) y anotar el fallo en el registro de abajo.

## Lo que no se puede automatizar

Las baterías comprueban que el mensaje **dice** qué hacer, pero no si **se entiende**. Para eso, antes de cada versión
importante conviene una prueba con dos o tres personas que no conozcan el plugin (por ejemplo, alumnos del máster): se
les pide crear un proyecto sin explicaciones y se apunta dónde dudan. Cada duda es un texto o un paso que cambiar, y se
convierte en un caso como cualquier otro fallo.

## Cómo se ejecutan

`tools\probar.bat` (las dos versiones de QGIS, todas las baterías) o `tools\probar.bat casos_zona_test.py` (una sola).
Cada batería se ejecuta en un QGIS propio sin ventana; el resultado queda en `tests\resultados_qgis<versión>.txt` y, si
algo falla, el detalle completo en `tests\detalle_<batería>_qgis<versión>.txt`.

## Registro de fallos encontrados

Cada fallo se convirtió primero en un caso (que falló con el código de entonces) y después se corrigió.

| Caso | Fallo encontrado | Corrección |
|---|---|---|
| P02 | Un `estado_servicios.json` estropeado daba un error de Python al abrir el panel | Se ignora lo que no sirve (se vuelve a comprobar) |
| P03 | Un favorito sin nombre o sin dirección impedía abrir el panel | Se quitan los dañados (con copia del fichero) y se avisa |
| P05 | Opciones guardadas con valores raros (plantillas, carpetas) daban errores | Se ignoran los valores que no son rutas |
| P08 | Pulsar «Crear» con un proyecto en marcha daba un aviso de validación en vez de «ya se está creando» | Esa comprobación va primero |
| A08 | Añadir una carpeta enorme (C:\, Documentos) dejaba QGIS parado minutos | Tope de 20.000 elementos o 20 s, con aviso de qué hacer |
| A14 | «Ver en el mapa» de una capa vacía llevaba el mapa a la coordenada 0,0 (en mitad del océano) | Las capas sin elementos avisan de que no hay nada que ver |
| A16, A17 | Una capa borrada o movida después de añadirla fallaba a mitad de la exportación | Se avisa antes de empezar, diciendo cuál |
| D03 | Rutas de más de 260 caracteres fallaban a mitad | Se avisa antes de empezar |
| D05 | Una carpeta sin permiso se descubría al exportar; y la comprobación nueva se quedaba 5 minutos parada en Windows | Se comprueba antes, con un único intento de escritura |
| Z05 | Al quitar de QGIS la capa de la zona, el desplegable saltaba solo a otra capa y se recortaba por la zona equivocada | El desplegable se queda vacío y se avisa |
| Z10 | Una zona imposible de pasar al SRC del proyecto daba un error técnico | Mensaje claro |
| S02 | ★ con el perfil sin permiso daba un error de Python | Aviso con qué hacer |
| S03, S09, B03, B05 | Errores del servidor, de GDAL o de PostgreSQL salían en inglés y con códigos | `core/mensajes.py` los explica en palabras del usuario |
| K03 | Una configuración editada a mano con datos de otro tipo daba un error de Python | Se normaliza, se ignora lo raro y se avisa |
| K13 | Un .json estropeado arrastrado al panel decía «no es una capa» (confuso si era una configuración) | El aviso menciona las dos posibilidades |
| L02 | Las plantillas dañadas se aceptaban y fallaban al crear | Se comprueban al añadirlas |
| L06 | Los logos de las composiciones no viajaban con el proyecto | Se copian a la carpeta «iconos» del proyecto |
| F11 | Con «conservar el formato», los shapefiles perdían las tildes («M�laga») | Todo lo que se escribe va en UTF-8 |
| F10 | Con «conservar el formato», un GeoJSON con extensión .json salía como un fichero que QGIS no abre | Se guarda como .geojson |
| F10 | Con «conservar el formato», las capas MapInfo .mif se perdían | Se convierten a GeoPackage (como DXF y GPX) |
| F10 | Las tablas internas de SpatiaLite (KNN2, data_licenses) aparecían como capas y se copiaban | Se ocultan |
| O06 | Una capa en edición con cambios sin guardar se copiaba sin esos cambios, sin avisar | Se avisa antes de empezar, diciendo qué capas |
| D10 | Una carpeta pegada entre comillas («Copiar como ruta de acceso») se rechazaba con un aviso confuso | Se quitan las comillas y espacios sobrantes |
| (pruebas) | Las pruebas modificaban `tests/data/vectorial/multicapa.gpkg` (QGIS abre los GeoPackage en modo escritura) | `run_tests.py` deja `tests/data` como estaba después de cada batería |
| I02, O03 | En un solo GeoPackage, las capas del proyecto abierto perdían su nombre («Plano 1:5000» → «Plano 1_5000») | Conservan su nombre; solo la tabla lleva el nombre «seguro» |
| C06 | El aviso de cancelar no decía qué hacer | Explica que no se ha guardado y cómo volver a empezar |
| (pruebas) | Las pruebas de QGIS 4.2 se quedaban paradas al arrancar por miles de claves de registro que dejan otras baterías | Las pruebas arrancan QGIS con una organización propia |
