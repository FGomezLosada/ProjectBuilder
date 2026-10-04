@echo off
rem Lanza todas las pruebas de ProjectBuilder en QGIS 3.40 y en QGIS 4.2, cada una en un QGIS propio sin ventana.
rem Uso: doble clic en este fichero, o desde CMD:  tools\probar.bat   (o  tools\probar.bat zone_test.py  para una sola)
rem Si cambias de versión de QGIS, actualiza las dos rutas de abajo.
cd /d "%~dp0.."
echo.
echo ===== QGIS 3.40 =====
call "C:\Program Files\QGIS 3.40.13\bin\python-qgis-ltr.bat" tools\run_tests.py %*
echo.
echo ===== QGIS 4.2 =====
call "C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat" tools\run_tests.py %*
echo.
echo Resultados guardados en tests\resultados_qgis3.40.txt y tests\resultados_qgis4.2.txt
if "%PB_SIN_PAUSA%"=="" pause
