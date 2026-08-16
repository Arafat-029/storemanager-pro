@echo off
REM Lanceur StoreManager Pro.
REM Se place dans le dossier du script, active l'environnement Python
REM puis demarre l'application. A utiliser via un raccourci sur le Bureau.

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo   ERREUR : l'environnement Python n'est pas installe.
    echo   Consultez INSTALLATION.md, etape 3.
    echo.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
python main.py

REM En cas d'arret anormal, laisser la fenetre ouverte pour lire le message.
if errorlevel 1 (
    echo.
    echo   L'application s'est arretee avec une erreur.
    echo   Consultez data\logs\erreurs.log
    echo.
    pause
)
