@echo off
rem Gera dist\NorteiaLia\NorteiaLia.exe (pasta que roda sem precisar de Python instalado).
cd /d "%~dp0.."
if not exist .venv (
    python -m venv .venv || goto erro
)
.venv\Scripts\python -m pip install --upgrade pip || goto erro
.venv\Scripts\python -m pip install PySide6 python-dateutil pyinstaller || goto erro
.venv\Scripts\pyinstaller --noconfirm --clean --windowed --name NorteiaLia ^
    --icon windows\norteia.ico ^
    --add-data "norteia\ui\assets;norteia\ui\assets" ^
    --hidden-import PySide6.QtSvg ^
    main.py || goto erro
echo.
echo Pronto: dist\NorteiaLia\NorteiaLia.exe
echo Para criar um instalador, abra windows\3-instalador.iss no Inno Setup (gratuito) e clique em Compile.
pause
exit /b 0
:erro
echo.
echo Deu erro. Copie a mensagem acima e me mande para eu ajustar.
pause
exit /b 1
