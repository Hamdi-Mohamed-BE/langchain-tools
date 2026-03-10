@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT_DIR=%~dp0"
set "MOBILE_DIR=%ROOT_DIR%mobile"
set "MIN_NODE_VERSION=20.19.4"

if not exist "%MOBILE_DIR%" (
  echo [setup-mobile] mobile directory not found at: %MOBILE_DIR%
  exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
  echo [setup-mobile] Node.js is not installed. Attempting Node.js LTS install...
  goto :install_node
)

set "NODE_VERSION_RAW="
for /f %%v in ('node -v 2^>nul') do set "NODE_VERSION_RAW=%%v"
set "NODE_VERSION=%NODE_VERSION_RAW:v=%"

if not defined NODE_VERSION (
  echo [setup-mobile] Could not detect Node.js version.
  goto :install_node
)

powershell -NoProfile -Command "if ([version]'%NODE_VERSION%' -ge [version]'%MIN_NODE_VERSION%') { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
  echo [setup-mobile] Node.js %NODE_VERSION% detected. Required: %MIN_NODE_VERSION% or newer.
  echo [setup-mobile] Upgrading Node.js...
  goto :install_node
)

goto :after_node_ready

:install_node
where winget >nul 2>&1
if not errorlevel 1 (
  winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
) else (
  where choco >nul 2>&1
  if not errorlevel 1 (
    choco upgrade nodejs-lts -y
    if errorlevel 1 (
      choco install nodejs-lts -y
    )
  ) else (
    echo [setup-mobile] Could not find winget or choco.
    echo [setup-mobile] Install Node.js %MIN_NODE_VERSION%+ manually, then run setup_mobile.bat again.
    exit /b 1
  )
)

where node >nul 2>&1
if errorlevel 1 (
  echo [setup-mobile] Node.js still not found after installation attempt.
  echo [setup-mobile] Open a new terminal and run setup_mobile.bat again.
  exit /b 1
)

set "NODE_VERSION_RAW="
for /f %%v in ('node -v 2^>nul') do set "NODE_VERSION_RAW=%%v"
set "NODE_VERSION=%NODE_VERSION_RAW:v=%"
powershell -NoProfile -Command "if ([version]'%NODE_VERSION%' -ge [version]'%MIN_NODE_VERSION%') { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
  echo [setup-mobile] Node.js upgrade completed but version is still %NODE_VERSION%.
  echo [setup-mobile] Please install Node.js %MIN_NODE_VERSION%+ manually and retry.
  exit /b 1
)

:after_node_ready
echo [setup-mobile] Node.js version OK: %NODE_VERSION% (required: %MIN_NODE_VERSION%+)

where yarn >nul 2>&1
if errorlevel 1 (
  echo [setup-mobile] yarn is not installed. Trying Corepack activation...
  call corepack enable
  if errorlevel 1 (
    echo [setup-mobile] corepack enable failed.
    echo [setup-mobile] Install Yarn manually and rerun setup_mobile.bat.
    exit /b 1
  )
  call corepack prepare yarn@1.22.22 --activate
  if errorlevel 1 (
    echo [setup-mobile] Could not activate yarn via Corepack.
    echo [setup-mobile] Install Yarn manually and rerun setup_mobile.bat.
    exit /b 1
  )
)

pushd "%MOBILE_DIR%"

if exist "package-lock.json" (
  echo [setup-mobile] removing package-lock.json to keep Yarn-only workflow
  del /f /q "package-lock.json" >nul 2>&1
)

if not exist ".env" if exist ".env.example" (
  echo [setup-mobile] creating .env from .env.example
  copy /Y ".env.example" ".env" >nul
)

echo [setup-mobile] installing mobile dependencies
call yarn install
if errorlevel 1 (
  popd
  exit /b 1
)

echo [setup-mobile] syncing Expo-compatible package versions
if exist "node_modules\.bin\expo.cmd" (
  call "node_modules\.bin\expo.cmd" install --fix
) else (
  echo [setup-mobile] Local Expo CLI not found after yarn install.
  popd
  exit /b 1
)
if errorlevel 1 (
  popd
  exit /b 1
)

popd

echo [setup-mobile] done
echo [setup-mobile] next: run_mobile.bat
exit /b 0
