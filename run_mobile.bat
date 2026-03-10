@echo off
setlocal EnableExtensions

set "ROOT_DIR=%~dp0"
set "MOBILE_DIR=%ROOT_DIR%mobile"

if not exist "%MOBILE_DIR%" (
  echo [run-mobile] mobile directory not found at: %MOBILE_DIR%
  exit /b 1
)

where yarn >nul 2>&1
if errorlevel 1 (
  echo [run-mobile] yarn is not installed. Run setup_mobile.bat first.
  exit /b 1
)

if not exist "%MOBILE_DIR%\node_modules" (
  echo [run-mobile] dependencies not installed. Run setup_mobile.bat first.
  exit /b 1
)

pushd "%MOBILE_DIR%"
echo [run-mobile] starting Expo dev server
call yarn start
set "EXIT_CODE=%ERRORLEVEL%"
popd

exit /b %EXIT_CODE%
