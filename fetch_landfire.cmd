@echo off
REM Double-click to download the LANDFIRE clips for a resort: vegetation type (EVT) into raw\<slug>\landfire\,
REM vegetation cover (EVC) and height (EVH) into landfire\evc\ and landfire\evh\ (DATA-010).
REM LFPS asks for an email address for its usage statistics: set LANDFIRE_EMAIL to skip the question. It is passed to
REM the script in the environment, so no command line or log holds it.
REM Optional: fetch_landfire.cmd <slug> [raw folder that holds <slug>\] (default: asks for the slug; SBA_RAW_ROOT,
REM else raw\ in this checkout).
cd /d "%~dp0"
set SLUG=%~1
if "%SLUG%"=="" set /p SLUG=Resort (vail, breckenridge, bigsky):
if "%SLUG%"=="" set SLUG=vail
if "%LANDFIRE_EMAIL%"=="" set /p LANDFIRE_EMAIL=Email address for the LANDFIRE service:
set RAWOPT=
if not "%~2"=="" set RAWOPT=--raw "%~2"
for %%P in (EVT EVC EVH) do node "%~dp0pipeline\fetch_landfire.mjs" %SLUG% %%P %RAWOPT%
echo.
echo Done. You can close this window.
pause
