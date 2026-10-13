"""
Casos de robustez con exportación EN SEGUNDO PLANO (los de robustez_test.py con grupo 'fondo').
Van en un QGIS propio, aparte del resto de casos.

Uso: tools\\probar.bat (o tools\\run_tests.py robustez_fondo_test.py)
"""
import os

os.environ['PB_ROBUSTEZ'] = 'fondo'
_RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'robustez_test.py')
with open(_RUTA, encoding='utf-8') as _f:
    exec(compile(_f.read(), _RUTA, 'exec'), {'__name__': '__main__', '__file__': _RUTA})
