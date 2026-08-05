@echo off
REM Place un raccourci vers demarrer.bat dans le dossier de demarrage de
REM Windows : le centre de controle sera la a chaque session, sans y penser.
REM
REM Pour annuler : supprimer le raccourci depuis
REM   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

setlocal
set CIBLE=%~dp0demarrer.bat
set DEMARRAGE=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set RACCOURCI=%DEMARRAGE%\KSP Mission Control.lnk

echo.
echo   Installation au demarrage de Windows
echo   ------------------------------------
echo   Cible    : %CIBLE%
echo   Raccourci: %RACCOURCI%
echo.

powershell -NoProfile -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%RACCOURCI%');" ^
  "$s.TargetPath = '%CIBLE%';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'Centre de controle KSP';" ^
  "$s.Save()"

if exist "%RACCOURCI%" (
    echo   Installe. Le centre de controle demarrera avec Windows.
) else (
    echo   Echec de la creation du raccourci.
)
echo.
pause
