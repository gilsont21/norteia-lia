@echo off
rem Abre o app direto do código (precisa do Python 3.11 ou mais novo, de python.org).
cd /d "%~dp0.."
if not exist .venv (
    echo Criando o ambiente na primeira vez, pode levar uns minutos...
    python -m venv .venv || goto erro
    .venv\Scripts\python -m pip install --upgrade pip || goto erro
    .venv\Scripts\python -m pip install PySide6 python-dateutil || goto erro
)
start "" .venv\Scripts\pythonw.exe main.py
exit /b 0
:erro
echo.
echo Deu erro. Confira se o Python esta instalado (python --version) e tente de novo.
pause
exit /b 1
