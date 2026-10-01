@echo off
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 "%~dp0launcher.py" build %*
) else (
  python "%~dp0launcher.py" build %*
)
exit /b %errorlevel%
