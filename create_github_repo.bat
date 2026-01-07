@echo off
REM Create GitHub Repository Script (Windows)
REM Usage: create_github_repo.bat [repository-name] [public|private]

setlocal

set REPO_NAME=%~1
if "%REPO_NAME%"=="" set REPO_NAME=ai-council

set VISIBILITY=%~2
if "%VISIBILITY%"=="" set VISIBILITY=public

echo ==========================================
echo Creating GitHub Repository: %REPO_NAME%
echo Visibility: %VISIBILITY%
echo ==========================================
echo.

REM Check if GitHub token is set
if "%GITHUB_TOKEN%"=="" (
    echo ERROR: GITHUB_TOKEN environment variable is not set.
    echo.
    echo To create a Personal Access Token:
    echo 1. Go to: https://github.com/settings/tokens
    echo 2. Click 'Generate new token' -^> 'Generate new token (classic)'
    echo 3. Name it 'AI Council Repo Creation'
    echo 4. Select scope: 'repo' (full control of private repositories)
    echo 5. Click 'Generate token' and copy it
    echo.
    echo Then run:
    echo   set GITHUB_TOKEN=your_token_here
    echo   create_github_repo.bat
    echo.
    exit /b 1
)

REM Set private flag
set PRIVATE_FLAG=false
if /i "%VISIBILITY%"=="private" set PRIVATE_FLAG=true

echo Creating repository on GitHub...
echo.

REM Create repository via GitHub API
for /f "tokens=*" %%a in ('curl -s -w "\n%%{http_code}" -X POST -H "Authorization: token %GITHUB_TOKEN%" -H "Accept: application/vnd.github.v3+json" https://api.github.com/user/repos -d "{\"name\":\"%REPO_NAME%\",\"description\":\"Local multi-agent LLM debate system with persona-driven workers\",\"private\":%PRIVATE_FLAG%,\"auto_init\":false}"') do set RESPONSE=%%a

REM Note: This is a simplified version. For full functionality, use the .sh script in Git Bash
echo.
echo Repository creation attempted. Please check the response above.
echo.
echo If successful, add remote and push with:
echo   git remote add origin https://github.com/YOUR_USERNAME/%REPO_NAME%.git
echo   git push -u origin main
echo.
echo Or use the Git Bash script: ./create_github_repo.sh

endlocal

