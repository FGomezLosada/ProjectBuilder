"""
Genera el ZIP del plugin listo para subir al repositorio oficial de QGIS (plugins.qgis.org).

Uso (desde la carpeta del proyecto, con cualquier Python 3):
    python tools/package.py

Crea dist/project_builder-<versión>.zip con una carpeta project_builder/ dentro (lo que exige QGIS)
y SOLO los ficheros del plugin: ni pruebas, ni documentación de desarrollo, ni .git, ni __pycache__.
Comprueba además que metadata.txt tiene los campos obligatorios.
"""
import configparser
import os
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = 'project_builder'  #Nombre de la carpeta del plugin dentro de QGIS
FICHEROS = ['__init__.py', 'project_builder.py', 'project_builder_dockwidget.py', 'project_builder_dockwidget_base.ui',
            'metadata.txt', 'icon.png', 'LICENSE', 'README.md', 'services.json']
CARPETAS = {'core': ('.py',), 'styles': ('.qml',)}  #Subcarpetas incluidas y extensiones admitidas en ellas
OBLIGATORIOS = ['name', 'qgisMinimumVersion', 'description', 'about', 'version', 'author', 'email', 'repository']
LIMITE_MB = 25


def leer_metadata():
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.read(os.path.join(RAIZ, 'metadata.txt'), encoding='utf-8')
    general = metadata['general']
    faltan = [campo for campo in OBLIGATORIOS if not general.get(campo, '').strip()]
    if faltan:
        sys.exit(f"Faltan campos obligatorios en metadata.txt: {', '.join(faltan)}")
    return general


def ficheros():
    """Lista de (ruta en disco, ruta dentro del ZIP)."""
    lista = []
    for nombre in FICHEROS:
        ruta = os.path.join(RAIZ, nombre)
        if not os.path.isfile(ruta):
            sys.exit(f"Falta el fichero {nombre}")
        lista.append((ruta, f"{CARPETA}/{nombre}"))
    for carpeta, extensiones in CARPETAS.items():
        for actual, subcarpetas, nombres in os.walk(os.path.join(RAIZ, carpeta)):
            subcarpetas[:] = [s for s in subcarpetas if not s.startswith(('.', '__'))]  #Fuera __pycache__ y ocultas
            for nombre in sorted(nombres):
                if nombre.lower().endswith(extensiones):
                    ruta = os.path.join(actual, nombre)
                    lista.append((ruta, f"{CARPETA}/" + os.path.relpath(ruta, RAIZ).replace(os.sep, '/')))
    return lista


def main():
    general = leer_metadata()
    version = general['version'].strip()
    etiqueta = os.environ.get('GITHUB_REF_NAME', '')  #En GitHub Actions: la etiqueta que lanza la publicación
    if etiqueta.startswith('v') and etiqueta[1:] != version:
        sys.exit(f"La etiqueta {etiqueta} no coincide con version={version} de metadata.txt")
    os.makedirs(os.path.join(RAIZ, 'dist'), exist_ok=True)
    destino = os.path.join(RAIZ, 'dist', f"{CARPETA}-{version}.zip")
    with zipfile.ZipFile(destino, 'w', zipfile.ZIP_DEFLATED) as zip_:
        for ruta, dentro in ficheros():
            zip_.write(ruta, dentro)
    megas = os.path.getsize(destino) / 1024 / 1024
    if megas > LIMITE_MB:
        sys.exit(f"El ZIP ocupa {megas:.1f} MB: el límite del repositorio de QGIS es {LIMITE_MB} MB")
    print(f"Creado {destino} ({megas * 1024:.0f} KB, {len(ficheros())} ficheros)")


if __name__ == '__main__':
    main()
