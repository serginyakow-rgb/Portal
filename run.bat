@echo off
rem ============================================================
rem  ортал нотариальной конторы - быстрый запуск из папки
rem  VS Code не нужен: двойной щелчок по файлу поднимает портал.
rem
rem  run.bat          - запуск на порту 8000
rem  run.bat 8010     - запуск на другом порту
rem  run.bat admin    - создать администратора портала
rem ============================================================
chcp 65001 >nul
setlocal enableextensions
cd /d "%~dp0"

set "PY=%~dp0venv\Scripts\python.exe"
set "PORT=8000"
set "HOST=0.0.0.0"

if /i "%~1"=="admin" goto :admin
if not "%~1"=="" set "PORT=%~1"

echo ============================================================
echo   ортал нотариальной конторы
echo ============================================================

rem --- 1. иртуальное окружение ---
if not exist "%PY%" (
  echo [1/4] venv не найден - создаю виртуальное окружение...
  set "PYEXE=python"
  where python >nul 2>nul
  if errorlevel 1 set "PYEXE=py -3"
  %PYEXE% -m venv venv
  if not exist "%PY%" (
    echo.
    echo Ш: не удалось создать venv.
    echo становите Python 3.11+ с python.org и отметьте "Add python.exe to PATH".
    goto :fail
  )
) else (
  echo [1/4] иртуальное окружение найдено: venv
)

rem --- 2. ависимости ---
"%PY%" -c "import fastapi, uvicorn, sqlalchemy, jinja2" >nul 2>nul
if errorlevel 1 (
  echo [2/4] станавливаю зависимости из requirements.txt...
  "%PY%" -m pip install --upgrade pip
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo Ш: не удалось установить зависимости.
    goto :fail
  )
) else (
  echo [2/4] ависимости на месте
)

rem --- 3. астройки .env ---
if not exist ".env" (
  echo [3/4] айла .env нет - копирую из .env.example
  copy /y ".env.example" ".env" >nul
) else (
  echo [3/4] айл настроек .env найден
)

rem --- 4. ервый администратор (только пока нет базы) ---
if not exist "portal.db" (
  echo [4/4] азы данных нет - создайте администратора (вход по имени сотрудника)
  "%PY%" scripts\create_admin.py
  if errorlevel 1 goto :fail
) else (
  echo [4/4] аза данных найдена: portal.db
)

rem --- апуск сервера ---
echo.
echo ортал:    http://127.0.0.1:%PORT%/auth/login
echo становка: Ctrl+C в этом окне
echo.
if not defined PORTAL_NO_BROWSER start "" /min cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:%PORT%/auth/login"
"%PY%" -m uvicorn app.main:app --host %HOST% --port %PORT%
echo.
echo Сервер остановлен.
goto :end

:admin
if not exist "%PY%" (
  echo Ш: сначала запустите run.bat без параметров - он создаст venv и зависимости.
  goto :fail
)
"%PY%" scripts\create_admin.py
goto :end

:fail
echo.
pause
exit /b 1

:end
pause