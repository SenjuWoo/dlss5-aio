@echo off
setlocal
title DLSS 5 AIO - DLL Refresher
cd /d "%~dp0"

:menu
cls
echo ============================================================
echo   DLSS 5 AIO  -  DLL Refresher
echo   Brings every nvngx_dlss*.dll on this PC up to the pack's
echo   official version. No injection, no hooks - file swap only.
echo ============================================================
if defined NR (echo   DLSS 5 runtime (nvngx_dlssnr.dll): INCLUDED) else (echo   DLSS 5 runtime (nvngx_dlssnr.dll): not included)
echo.
echo   [1]  Scan only        (dry run, writes nothing)
echo   [2]  Update all       (keeps the original of every file it replaces)
echo   [3]  Restore          (put the originals back)
echo   [4]  Include DLSS 5 runtime (nvngx_dlssnr.dll) in 1/2/3
echo   [5]  Scan a single folder
echo   [6]  Self test        (proves the tool works)
echo   [0]  Exit
echo.
set /p CHOICE=  Choose: 

if "%CHOICE%"=="1" goto scan
if "%CHOICE%"=="2" goto apply
if "%CHOICE%"=="3" goto restore
if "%CHOICE%"=="4" goto nr
if "%CHOICE%"=="5" goto folder
if "%CHOICE%"=="6" goto selftest
if "%CHOICE%"=="0" exit /b 0
goto menu

:nr
if defined NR (set "NR=") else (set "NR=-IncludeNR")
echo.
if defined NR (echo   DLSS 5 runtime will be INCLUDED.) else (echo   DLSS 5 runtime will NOT be included.)
timeout /t 2 >nul
goto menu

:scan
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DLSS-DLL-Refresher.ps1" %NR%
goto done

:apply
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DLSS-DLL-Refresher.ps1" -Apply %NR%
goto done

:restore
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DLSS-DLL-Refresher.ps1" -Restore %NR%
goto done

:folder
echo.
set /p FOLDER=  Folder to scan (example: D:\Games): 
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DLSS-DLL-Refresher.ps1" -Roots "%FOLDER%" %NR%
goto done

:selftest
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DLSS-DLL-Refresher.ps1" -SelfTest %NR%
goto done

:done
echo.
pause
goto menu