@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT_DIR=%~dp0\..
cd /d "%ROOT_DIR%"

if not exist .env (
  copy .env.sample .env >nul
  echo Created .env from .env.sample. Review it and fill in your real IDs and provider keys before running the bot.
)

call :LoadEnv

if "%BOT_TOKEN%"=="" set "BOT_TOKEN_PLACEHOLDER=1"
if /I "%BOT_TOKEN%"=="YOUR_DISCORD_BOT_TOKEN" set "BOT_TOKEN_PLACEHOLDER=1"
if "%BOT_TOKEN_PLACEHOLDER%"=="1" (
  echo Missing or placeholder value for BOT_TOKEN in .env.
  exit /b 1
)

if "%CHANNEL_ID%"=="" set "CHANNEL_ID_PLACEHOLDER=1"
if /I "%CHANNEL_ID%"=="YOUR_LOG_CHANNEL_ID" set "CHANNEL_ID_PLACEHOLDER=1"
if "%CHANNEL_ID_PLACEHOLDER%"=="1" (
  echo Missing or placeholder value for CHANNEL_ID in .env.
  exit /b 1
)

if "%AI_PROVIDER%"=="" (
  echo Missing or placeholder value for AI_PROVIDER in .env.
  exit /b 1
)

if /I not "%AI_PROVIDER%"=="gemini" if /I not "%AI_PROVIDER%"=="openai" if /I not "%AI_PROVIDER%"=="ollama" if /I not "%AI_PROVIDER%"=="nim" if /I not "%AI_PROVIDER%"=="azure" if /I not "%AI_PROVIDER%"=="groq" if /I not "%AI_PROVIDER%"=="openrouter" (
  echo Unsupported AI_PROVIDER value: %AI_PROVIDER%
  exit /b 1
)

if "%CHANNEL_ID%"=="" (
  echo CHANNEL_ID must be a numeric Discord channel snowflake.
  exit /b 1
)

echo %CHANNEL_ID% | findstr /R "^[0-9][0-9]*$" >nul || (
  echo CHANNEL_ID must be a numeric Discord channel snowflake.
  exit /b 1
)

if /I "%AI_PROVIDER%"=="gemini" if "%GOOGLE_API_KEY%"=="" if "%GOOGLE_API_KEY%"=="YOUR_GEMINI_API_KEY" (
  echo GOOGLE_API_KEY is required when AI_PROVIDER=gemini.
  exit /b 1
)

if /I "%AI_PROVIDER%"=="openai" if "%OPENAI_API_KEY%"=="" (
  echo OPENAI_API_KEY is required when AI_PROVIDER=openai.
  exit /b 1
)

if /I "%AI_PROVIDER%"=="ollama" if "%OLLAMA_BASE_URL%"=="" (
  set "OLLAMA_BASE_URL=http://localhost:11434/api/chat"
)

if /I "%AI_PROVIDER%"=="nim" if "%NVIDIA_API_KEY%"=="" if "%NIM_API_KEY%"=="" (
  echo NVIDIA_API_KEY or NIM_API_KEY is required when AI_PROVIDER=nim.
  exit /b 1
)

if /I "%AI_PROVIDER%"=="azure" if "%AZURE_AI_KEY%"=="" if "%AZURE_AI_BASE_URL%"=="" (
  echo AZURE_AI_KEY and AZURE_AI_BASE_URL are required when AI_PROVIDER=azure.
  exit /b 1
)

if /I "%AI_PROVIDER%"=="groq" if "%GROQ_API_KEY%"=="" (
  echo GROQ_API_KEY is required when AI_PROVIDER=groq.
  exit /b 1
)

if /I "%AI_PROVIDER%"=="openrouter" if "%OPENROUTER_API_KEY%"=="" (
  echo OPENROUTER_API_KEY is required when AI_PROVIDER=openrouter.
  exit /b 1
)

if not exist .venv (
  py -3 -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt >nul
python scripts\check_project.py
python main.py
exit /b %ERRORLEVEL%

:LoadEnv
for /f "tokens=1,* delims==" %%A in ('findstr /R /V /C:"^#" /C:"^$" .env') do (
  set "key=%%A"
  set "value=%%B"
  for /f "tokens=1,* delims=#" %%X in ("!value!") do set "!key!=%%X"
)
exit /b 0
