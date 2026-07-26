@echo off
setlocal EnableExtensions EnableDelayedExpansion

set ROOT_DIR=%~dp0\..
cd /d "%ROOT_DIR%"

REM ASCII Art Banner
echo.
echo                     IIIII                                                                                                                  
echo                     II II                                                                                                                  
echo                     II II                                                                                                                  
echo                 III       III                                                                                                              
echo                II  IIIIIII  II                                                                                                             
echo               I  IIIIIIIIIII  II                                                                                                           
echo              I  IIIIIIIIIIIII  I                                                                                                           
echo              I  IIIIIIIIIIIII  I                                                                                                           
echo           III   IIIIIIIIIIIII    II                                                                                                        
echo         II   II  IIIIIIIIIII  II   II                                                                                                      
echo       II  IIIIII   IIIIIII   IIIIII  II                                                                                                    
echo      II  IIIIIIIIII       IIIIIIIIIII  I       IIIIIIIIII                                                                                  
echo     I  IIIIIIIIIII  IIIII  IIIIIIIIIII  I      IIIIIIIIII                                                                                  
echo    I  IIIIIIIIIIII IIIIIII IIIIIIIIIIII  I     III                                                                                         
echo   II IIIIIIIIIIII  IIIIIII  IIIIIIIIIIII II    III       IIIIIIII IIIIIIII    IIIIIIIII   IIIIIIII    IIIIIIII   III IIIIII   IIIIIIII    
echo   I  IIIIIIIIIII  IIIIIIIII  IIIIIIIIIII  I    IIIIIIIII IIIII   III    IIII IIII   III IIII    III IIIII   IIII IIII   IIII III    III   
echo  II  IIIII  IIII IIIIIIIIIII  III  IIIII  II   III       IIII   IIIIIIIIIIIIIIIIIIIIIIII  IIIIIIII  III      III III     III   IIIIIIII  
echo  II  IIIII I       IIIIIII       I IIIII  II   III       IIII   III         IIII            IIIIIII III      III III     III IIII  IIII  
echo  II  IIII  IIIIIIIIIIIIIIIIIIIIIII  IIII  II   III       IIII    IIII  IIII  IIII   IIII IIII   III  IIII  IIIII III     III III   IIIII 
echo  II  IIII IIIIIIIIIIIIIIIIIIIIIIIII IIII  I    III       IIII     IIIIIIII     IIIIIII    IIIIIIII    IIIIIIII   III     III IIIIIII III 
echo.
echo =====================================================
echo   Freesona - Self-Hosted Discord AI Framework Setup  
echo =====================================================
echo.

REM If .env exists, load it for defaults
if exist .env (
  call :LoadEnv
)

REM Interactive prompts for required values
echo --- Required Configuration ---
echo.

REM BOT_TOKEN
set /p BOT_TOKEN="Discord Bot Token [%BOT_TOKEN%]: "
if "%BOT_TOKEN%"=="" set "BOT_TOKEN=%BOT_TOKEN%"

REM CHANNEL_ID
set /p CHANNEL_ID="Log Channel ID (numeric Discord snowflake) [%CHANNEL_ID%]: "
if "%CHANNEL_ID%"=="" set "CHANNEL_ID=%CHANNEL_ID%"

REM BOT_NAME
set /p BOT_NAME="Bot Name [%BOT_NAME%]: "
if "%BOT_NAME%"=="" set "BOT_NAME=%BOT_NAME%"

REM AI_PROVIDER
echo.
echo Available AI Providers: gemini, openai, ollama, nim, azure, groq, openrouter
set /p AI_PROVIDER="AI Provider [%AI_PROVIDER%]: "
if "%AI_PROVIDER%"=="" set "AI_PROVIDER=%AI_PROVIDER%"

REM Provider-specific configuration
echo.
echo --- Provider Configuration ---
echo For each provider, you'll need an API key. Here's where to get them:
echo   gemini:    https://aistudio.google.com/app/apikey (Google AI Studio)
echo   openai:    https://platform.openai.com/api-keys (OpenAI Platform)
echo   ollama:    Run locally - no API key needed (default: http://localhost:11434)
echo   nim:       https://build.nvidia.com/ (NVIDIA NIM API keys)
echo   azure:     https://portal.azure.com/ (Azure AI Foundry / OpenAI Service)
echo   groq:      https://console.groq.com/keys (Groq Console)
echo   openrouter: https://openrouter.ai/keys (OpenRouter)
echo.
if /I "%AI_PROVIDER%"=="gemini" (
  set /p GOOGLE_API_KEY="Google API Key (Gemini) [%GOOGLE_API_KEY%]: "
  if "%GOOGLE_API_KEY%"=="" set "GOOGLE_API_KEY=%GOOGLE_API_KEY%"
) else if /I "%AI_PROVIDER%"=="openai" (
  set /p OPENAI_API_KEY="OpenAI API Key [%OPENAI_API_KEY%]: "
  if "%OPENAI_API_KEY%"=="" set "OPENAI_API_KEY=%OPENAI_API_KEY%"
  set /p OPENAI_BASE_URL="OpenAI Base URL [%OPENAI_BASE_URL%]: "
  if "%OPENAI_BASE_URL%"=="" set "OPENAI_BASE_URL=https://api.openai.com/v1/chat/completions"
) else if /I "%AI_PROVIDER%"=="ollama" (
  set /p OLLAMA_BASE_URL="Ollama Base URL [%OLLAMA_BASE_URL%]: "
  if "%OLLAMA_BASE_URL%"=="" set "OLLAMA_BASE_URL=http://localhost:11434/api/chat"
) else if /I "%AI_PROVIDER%"=="nim" (
  set /p NVIDIA_API_KEY="NVIDIA API Key [%NVIDIA_API_KEY%]: "
  if "%NVIDIA_API_KEY%"=="" set "NVIDIA_API_KEY=%NVIDIA_API_KEY%"
  set /p NVIDIA_NIM_BASE_URL="NVIDIA NIM Base URL [%NVIDIA_NIM_BASE_URL%]: "
  if "%NVIDIA_NIM_BASE_URL%"=="" set "NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1/chat/completions"
) else if /I "%AI_PROVIDER%"=="azure" (
  set /p AZURE_AI_KEY="Azure AI Key [%AZURE_AI_KEY%]: "
  if "%AZURE_AI_KEY%"=="" set "AZURE_AI_KEY=%AZURE_AI_KEY%"
  set /p AZURE_AI_BASE_URL="Azure AI Base URL [%AZURE_AI_BASE_URL%]: "
  if "%AZURE_AI_BASE_URL%"=="" set "AZURE_AI_BASE_URL=%AZURE_AI_BASE_URL%"
) else if /I "%AI_PROVIDER%"=="groq" (
  set /p GROQ_API_KEY="Groq API Key [%GROQ_API_KEY%]: "
  if "%GROQ_API_KEY%"=="" set "GROQ_API_KEY=%GROQ_API_KEY%"
) else if /I "%AI_PROVIDER%"=="openrouter" (
  set /p OPENROUTER_API_KEY="OpenRouter API Key [%OPENROUTER_API_KEY%]: "
  if "%OPENROUTER_API_KEY%"=="" set "OPENROUTER_API_KEY=%OPENROUTER_API_KEY%"
  set /p OPENROUTER_SITE_URL="OpenRouter Site URL [%OPENROUTER_SITE_URL%]: "
  if "%OPENROUTER_SITE_URL%"=="" set "OPENROUTER_SITE_URL=%OPENROUTER_SITE_URL%"
  set /p OPENROUTER_SITE_NAME="OpenRouter Site Name [%OPENROUTER_SITE_NAME%]: "
  if "%OPENROUTER_SITE_NAME%"=="" set "OPENROUTER_SITE_NAME=Freesona"
) else (
  echo Unsupported AI_PROVIDER: %AI_PROVIDER%
  exit /b 1
)

REM Optional: Model override
set /p MODEL_NAME="Model Name (override default for provider) [%MODEL_NAME%]: "
if "%MODEL_NAME%"=="" set "MODEL_NAME=%MODEL_NAME%"

REM Optional: Model Temperature (0.0 = deterministic, 1.0 = creative, 2.0 = very creative)
set /p MODEL_TEMPERATURE="Model Temperature 0.0-2.0 [%MODEL_TEMPERATURE%]: "
if "%MODEL_TEMPERATURE%"=="" set "MODEL_TEMPERATURE=0.7"

REM Optional: ChromaDB
set /p CHROMA_COLLECTION="ChromaDB Collection [%CHROMA_COLLECTION%]: "
if "%CHROMA_COLLECTION%"=="" set "CHROMA_COLLECTION=freesona"
set /p CHROMA_PERSIST_DIRECTORY="ChromaDB Persist Directory [%CHROMA_PERSIST_DIRECTORY%]: "
if "%CHROMA_PERSIST_DIRECTORY%"=="" set "CHROMA_PERSIST_DIRECTORY=./.chroma"

REM Optional: Knowledge Base
set /p KB_ENABLED="Enable Knowledge Base? (true/false) [%KB_ENABLED%]: "
if "%KB_ENABLED%"=="" set "KB_ENABLED=true"
if /I "%KB_ENABLED%"=="true" (
  echo   (KB Top K = how many knowledge base entries to retrieve; higher = more context, lower = faster)
  set /p KB_TOP_K="Knowledge Base Results Count [%KB_TOP_K%]: "
  if "%KB_TOP_K%"=="" set "KB_TOP_K=5"
)

REM Optional: Complimentary tokens
echo.
echo --- Optional Integrations (press Enter to skip) ---
set /p LOGOKIT_TOKEN="Logokit Token [%LOGOKIT_TOKEN%]: "
if "%LOGOKIT_TOKEN%"=="" set "LOGOKIT_TOKEN=YOUR_LOGOKIT_KEY_HERE"
set /p MVSEP_API_KEY="MVSEP API Key [%MVSEP_API_KEY%]: "
if "%MVSEP_API_KEY%"=="" set "MVSEP_API_KEY=YOUR_MVSEP_API_KEY"
set /p MVSEP_WEBHOOK_URL="MVSEP Webhook URL [%MVSEP_WEBHOOK_URL%]: "
if "%MVSEP_WEBHOOK_URL%"=="" set "MVSEP_WEBHOOK_URL=https://your-public-host.example.com/webhooks/mvsep"
set /p WOLFRAM_APPID_SHORT="Wolfram AppID Short [%WOLFRAM_APPID_SHORT%]: "
if "%WOLFRAM_APPID_SHORT%"=="" set "WOLFRAM_APPID_SHORT=YOUR_WOLFRAM_APPID_SHORT"
set /p WOLFRAM_APPID_LLM="Wolfram AppID LLM [%WOLFRAM_APPID_LLM%]: "
if "%WOLFRAM_APPID_LLM%"=="" set "WOLFRAM_APPID_LLM=YOUR_WOLFRAM_APPID_LLM"

REM Write .env file
echo.
echo Writing configuration to .env...
(
echo # HTTP Server
echo HTTP_PORT=10000
echo.
echo # Discord
echo BOT_TOKEN=%BOT_TOKEN%
echo CHANNEL_ID=%CHANNEL_ID%
echo BOT_NAME=%BOT_NAME%
echo.
echo # AI Provider
echo AI_PROVIDER=%AI_PROVIDER%
echo AI_PROVIDER_MODEL=%MODEL_NAME%
echo MODEL_NAME=%MODEL_NAME%
echo MODEL_TEMPERATURE=%MODEL_TEMPERATURE%
echo GOOGLE_API_KEY=%GOOGLE_API_KEY%
echo.
echo # Provider API keys (set the one matching your AI_PROVIDER)
echo OPENAI_API_KEY=%OPENAI_API_KEY%
echo OPENAI_BASE_URL=%OPENAI_BASE_URL%
echo OLLAMA_BASE_URL=%OLLAMA_BASE_URL%
echo NVIDIA_API_KEY=%NVIDIA_API_KEY%
echo NVIDIA_NIM_BASE_URL=%NVIDIA_NIM_BASE_URL%
echo AZURE_AI_KEY=%AZURE_AI_KEY%
echo AZURE_AI_BASE_URL=%AZURE_AI_BASE_URL%
echo GROQ_API_KEY=%GROQ_API_KEY%
echo OPENROUTER_API_KEY=%OPENROUTER_API_KEY%
echo OPENROUTER_SITE_URL=%OPENROUTER_SITE_URL%
echo OPENROUTER_SITE_NAME=%OPENROUTER_SITE_NAME%
echo.
echo # ChromaDB (optional -- required for knowledge base retrieval)
echo CHROMA_COLLECTION=%CHROMA_COLLECTION%
echo CHROMA_PERSIST_DIRECTORY=%CHROMA_PERSIST_DIRECTORY%
echo.
echo # Knowledge Base (optional)
echo KB_ENABLED=%KB_ENABLED%
echo KB_TOP_K=%KB_TOP_K%
echo.
echo # Complimentary tokens
echo LOGOKIT_TOKEN=%LOGOKIT_TOKEN%
echo MVSEP_API_KEY=%MVSEP_API_KEY%
echo MVSEP_WEBHOOK_URL=%MVSEP_WEBHOOK_URL%
echo MVSEP_WEBHOOK_SEND_MAIL_ON_ERROR=false
echo WOLFRAM_APPID_SHORT=%WOLFRAM_APPID_SHORT%
echo WOLFRAM_APPID_LLM=%WOLFRAM_APPID_LLM%
echo.
echo # File paths (local)
echo AI_PERSONA_FILE=persona.txt
echo AI_PERSONA_JSON_FILE=persona.json
echo AI_PERSONAS_FILE=personas.json
echo AI_PERSONA=""
echo CONFIG_FILE_PATH=config.json
echo MEMORY_FILE_PATH=memory.db
echo WARNINGS_FILE_PATH=warnings.db
echo ANNIVERSARIES_FILE_PATH=anniversaries.db
echo CANON_FILE_PATH=canon.db
echo CHARACTER_MEMORY_FILE_PATH=character_memory.db
) > .env

echo Configuration saved to .env
echo.

REM Validate required fields
if "%BOT_TOKEN%"=="YOUR_DISCORD_BOT_TOKEN" (
  echo Warning: BOT_TOKEN not set. The bot will not start without a valid token.
)
echo %CHANNEL_ID% | findstr /R "^[0-9][0-9]*$" >nul || (
  echo Warning: CHANNEL_ID must be a numeric Discord channel snowflake.
)

if /I "%AI_PROVIDER%"=="gemini" if "%GOOGLE_API_KEY%"=="" if "%GOOGLE_API_KEY%"=="YOUR_GEMINI_API_KEY" (
  echo Warning: GOOGLE_API_KEY not set for Gemini provider.
)
if /I "%AI_PROVIDER%"=="openai" if "%OPENAI_API_KEY%"=="" (
  echo Warning: OPENAI_API_KEY not set for OpenAI provider.
)
if /I "%AI_PROVIDER%"=="nim" if "%NVIDIA_API_KEY%"=="" (
  echo Warning: NVIDIA_API_KEY not set for NIM provider.
)
if /I "%AI_PROVIDER%"=="azure" if "%AZURE_AI_KEY%"=="" if "%AZURE_AI_BASE_URL%"=="" (
  echo Warning: AZURE_AI_KEY and AZURE_AI_BASE_URL required for Azure provider.
)
if /I "%AI_PROVIDER%"=="groq" if "%GROQ_API_KEY%"=="" (
  echo Warning: GROQ_API_KEY not set for Groq provider.
)
if /I "%AI_PROVIDER%"=="openrouter" if "%OPENROUTER_API_KEY%"=="" (
  echo Warning: OPENROUTER_API_KEY not set for OpenRouter provider.
)

echo.
echo Setting up Python environment...
if not exist .venv (
  py -3 -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt >nul

echo.
echo Running project checks...
python scripts\check_project.py

echo.
echo =====================================================
echo   Setup complete! Starting Freesona...
echo =====================================================
echo.
python main.py
exit /b %ERRORLEVEL%

:LoadEnv
for /f "tokens=1,* delims==" %%A in ('findstr /R /V /C:"^#" /C:"^$" .env') do (
  set "key=%%A"
  set "value=%%B"
  for /f "tokens=1,* delims=#" %%X in ("!value!") do set "!key!=%%X"
)
exit /b 0
