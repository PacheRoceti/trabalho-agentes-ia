@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Demonstracao - Agente de Triagem
timeout /t 5 /nobreak >nul
".venv\Scripts\python.exe" demonstrar_apresentacao.py --sem-pausa
echo.
echo Fim da demonstracao.
pause
