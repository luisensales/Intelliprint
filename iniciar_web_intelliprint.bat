@echo off
chcp 65001 >nul
title IntelliPrint Preflight Web
echo =======================================================
echo          INTELLIPRINT - PREFLIGHT WEB v1.2.0
echo   Sistema Avanzado de Preflight & Verificacion PDF
echo =======================================================
echo.
echo Iniciando servidor en http://localhost:8000 ...
echo Puedes acceder desde este equipo o desde cualquier dispositivo
echo en la misma red local.
echo.

start "" http://localhost:8000
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
pause

