@echo off
setlocal
title DLSS 5 AIO - DLL Refresher
cd /d "%~dp0"

rem Arguments given? Forward them straight to the PowerShell tool and exit (no menu).
if not "%~1"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DLSS-DLL-Refresher.ps1" %*
  exit /b %errorlevel%
)

:menu
cls
echo ============================================================
echo   DLSS 5 AIO  -  DLL Refresher
echo   Brings every DLSS file on this PC up to the pack's
echo   official version: nvngx_dlss*, Streamline, the DLSS 5
echo   add-on, the feeder. No injection, no hooks - file swap only.
echo ============================================================
set "NRSTATE=included"
if defined NR set "NRSTATE=SKIPPED"
set "ONSTATE=skipped (anti-cheat)"
if defined ONLINE set "ONSTATE=INCLUDED - ban risk!"
echo   DLSS 5 runtime (nvngx_dlssnr.dll): %NRSTATE%
echo   Online games (kernel anti-cheat):  %ONSTATE%
echo.
echo   [1]  Scan only        (dry run, writes nothing)
echo   [2]  Update all       (keeps the original of every file it replaces)
echo   [3]  Restore          (put the originals back)
echo   [4]  Skip the DLSS 5 runtime (nvngx_dlssnr.dll) in 1/2/3
echo   [5]  Scan a single folder
echo   [6]  Self test        (proves the tool works)
echo   [7]  Include online games  (Fortnite, Marvel Rivals, ... - anti-cheat risk)
echo   [0]  Exit
echo.
set /p CHOICE=  Choose: 

if "%CHOICE%"=="1" goto scan
if "%CHOICE%"=="2" goto apply
if "%CHOICE%"=="3" goto restore
if "%CHOICE%"=="4" goto nr
if "%CHOICE%"=="5" goto folder
if "%CHOICE%"=="6" goto selftest
if "%CHOICE%"=="7" goto online
if "%CHOICE%"=="0" exit /b 0
goto menu

:nr
if defined NR (set "NR=") else (set "NR=-SkipNR")
echo.
set "NRSTATE=included"
if defined NR set "NRSTATE=SKIPPED"
echo   DLSS 5 runtime will be %NRSTATE%.
timeout /t 2 >nul
goto menu

:online
if defined ONLINE (set "ONLINE=") else (set "ONLINE=-ForceOnline")
echo.
set "ONSTATE=skipped (anti-cheat)"
if defined ONLINE set "ONSTATE=INCLUDED - ban risk!"
echo   Online games will be %ONSTATE%.
timeout /t 2 >nul
goto menu

:scan
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DLSS-DLL-Refresher.ps1" %NR% %ONLINE%
goto done

:apply
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DLSS-DLL-Refresher.ps1" -Apply %NR% %ONLINE%
goto done

:restore
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DLSS-DLL-Refresher.ps1" -Restore %NR% %ONLINE%
goto done

:folder
echo.
set /p FOLDER=  Folder to scan (example: D:\Games): 
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DLSS-DLL-Refresher.ps1" -Roots "%FOLDER%" %NR% %ONLINE%
goto done

:selftest
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DLSS-DLL-Refresher.ps1" -SelfTest %NR% %ONLINE%
goto done

:done
echo.
pause
goto menu
