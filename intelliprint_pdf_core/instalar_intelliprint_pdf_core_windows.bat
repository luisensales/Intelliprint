@echo off
setlocal
chcp 65001 >nul

echo ==============================================
echo IntelliPrint - Librerias PDF principales
echo ==============================================
echo.

py -m pip install --upgrade pip
if errorlevel 1 goto :error

py -m pip install PyMuPDF==1.28.2 pypdf==6.21.1 pikepdf==10.17.0
if errorlevel 1 goto :error

echo.
echo Verificando instalaciones...
py -c "import pymupdf; print('OK PyMuPDF:', pymupdf.VersionBind)"
if errorlevel 1 goto :error
py -c "import pypdf; print('OK pypdf:', pypdf.__version__)"
if errorlevel 1 goto :error
py -c "import pikepdf; print('OK pikepdf:', pikepdf.__version__)"
if errorlevel 1 goto :error

echo.
echo ==============================================
echo Instalacion correcta.
echo CairoSVG no se instala en este paquete porque
echo no es necesario para el nucleo PDF de IntelliPrint.
echo ==============================================
pause
exit /b 0

:error
echo.
echo Ha ocurrido un error durante la instalacion.
echo Copia el mensaje que aparece arriba para revisarlo.
pause
exit /b 1
