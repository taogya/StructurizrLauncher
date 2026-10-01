@echo off
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 "%~dp0launcher.py" status %*
) else (
  python "%~dp0launcher.py" status %*
)
exit /b %errorlevel%
