@echo off
echo ==========================================
echo   OBSIDIAN AI - Starting...
echo ==========================================
echo.
echo Step 1: Making sure Ollama is running...
start "" ollama serve

echo Step 2: Waiting 3 seconds...
timeout /t 3 /nobreak > nul

echo Step 3: Starting backend...
cd backend
start cmd /k "uvicorn main:app --reload --port 8000"

echo Step 4: Opening frontend...
timeout /t 2 /nobreak > nul
start frontend\index.html

echo.
echo ==========================================
echo   Obsidian AI is running!
echo   - Backend: http://localhost:8000
echo   - Frontend opened in browser
echo ==========================================
pause