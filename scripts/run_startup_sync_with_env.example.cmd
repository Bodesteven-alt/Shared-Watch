@echo off
REM Copy to run_startup_sync_with_env.cmd and set your values (do not commit real secrets).
REM Task Scheduler can also set TMDB_* in the task's Environment tab or system User variables.

REM set TMDB_READ_ACCESS_TOKEN=your_read_access_token_here
REM set TMDB_API_KEY=your_v3_api_key_here

cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0startup_sync.ps1"
