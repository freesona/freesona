@echo off
REM run.cmd - Run Freesona bot without activating .venv manually
REM Assumes setup_local.cmd has been run and .venv exists with dependencies installed.

setlocal EnableExtensions

set ROOT_DIR=%~dp0
cd /d "%ROOT_DIR%"

REM Check if setup has been completed
if not exist config.json (
    echo Error: config.json not found. Please run .\scripts\setup_local.cmd first.
    exit /b 1
)

REM Check if .venv exists
if not exist .venv (
    echo Error: .venv directory not found. Please run .\scripts\setup_local.cmd first.
    exit /b 1
)

REM Activate virtual environment and run
call .venv\Scripts\activate.bat
python main.py
