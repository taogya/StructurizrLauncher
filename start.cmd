@echo off
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 "%~dp0launcher.py" start %*
) else (
  python "%~dp0launcher.py" start %*
)
exit /b %errorlevel%
