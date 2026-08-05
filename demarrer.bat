@echo off
title KSP Mission Control
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
    echo.
    echo   L'environnement Python n'existe pas encore.
    echo   Lance ces deux commandes une seule fois :
    echo.
    echo      cd backend
    echo      python -m venv .venv
    echo      .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "backend\.env" (
    echo.
    echo   Fichier backend\.env manquant.
    echo   Copie backend\.env.example en backend\.env et renseigne GEMINI_API_KEY.
    echo.
    pause
    exit /b 1
)

REM Sans argument, le lanceur attend que KSP demarre avant d'ouvrir la
REM fenetre. Avec --maintenant, il ouvre tout de suite sur le simulateur.
backend\.venv\Scripts\python.exe lanceur.py %*

if errorlevel 1 pause
