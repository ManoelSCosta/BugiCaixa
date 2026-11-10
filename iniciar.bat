@echo off
rem Abre a BugiCaixa (Windows). Requer apenas Python 3.8+.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m bugicaixa %*
) else (
  python -m bugicaixa %*
)
if errorlevel 1 pause
