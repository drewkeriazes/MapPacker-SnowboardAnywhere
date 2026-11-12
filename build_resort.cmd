@echo off
REM Double-click to build a resort end to end (FEAT-175): node lists, manifest, fetch, LANDFIRE, grooming,
REM build, the start and main menu (gen_content.py; with the game: the menu still, ghosts and proposed compare spots),
REM packs\index.json and the DATA-022 report. Finished stages are skipped, so it is safe to re-run.
REM Optional: build_resort.cmd <slug> [raw folder that holds <slug>\] (default: asks for the slug; raw data in
REM SBA_RAW_ROOT, else raw\ in the main checkout). The pack goes to packs\<slug>\ here.
REM Set LANDFIRE_EMAIL to skip the email prompt. More: python pipeline\build_resort.py --help
cd /d "%~dp0"
set SLUG=%~1
if "%SLUG%"=="" set /p SLUG=Resort slug (vail, breckenridge, bigsky, or one resort.py made):
if "%SLUG%"=="" goto :eof
set RAWARG=
if not "%~2"=="" set RAWARG="%~2\%SLUG%"
python pipeline\build_resort.py %SLUG% %RAWARG%
echo.
echo Done. The pack is in packs\%SLUG%. To ride it, copy that folder into the game's packs\ (SnowboardAnywhere),
echo or publish it and run npm run get %SLUG% in the game.
pause
