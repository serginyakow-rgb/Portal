@echo off
rem ============================================================
rem  Портал нотариальной конторы - запуск вне VS Code
rem  Двойной щелчок по файлу поднимает сервер и открывает браузер.
rem
rem  start.bat            - запуск на порту 8000, доступ с других ПК сети
rem  start.bat 8010       - запуск на другом порту
rem  start.bat local      - доступ только с этого ПК
rem  start.bat 8010 local - другой порт, доступ только с этого ПК
rem  start.bat admin      - создать администратора портала
rem
rem  Переменная окружения PORTAL_NO_BROWSER=1 - браузер не открывается
rem ============================================================
chcp 65001 >nul
setlocal enableextensions
title Портал нотариальной конторы
cd /d "%~dp0"

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PY=%ROOT%\venv\Scripts\python.exe"
set "PORT=8000"
set "HOST=0.0.0.0"

if /i "%~1"=="admin" goto :admin

:args
if "%~1"=="" goto :args_done
if /i "%~1"=="local" (set "HOST=127.0.0.1") else if /i "%~1"=="lan" (set "HOST=0.0.0.0") else (set "PORT=%~1")
shift
goto :args
:args_done

echo ============================================================
echo   Портал нотариальной конторы
echo   папка: %ROOT%
echo ============================================================

rem --- 0. проверка, что файл лежит рядом с папкой app ---
if exist "%ROOT%\app\main.py" goto :layout_ok
echo.
echo Ошибка: start.bat должен лежать в папке проекта Portal - рядом с папкой app.
goto :fail
:layout_ok

rem --- 1. виртуальное окружение ---
if exist "%PY%" goto :venv_ok
echo [1/5] venv не найден - создаю виртуальное окружение...
set "PYEXE=python"
where python >nul 2>nul
if errorlevel 1 set "PYEXE=py -3"
call %PYEXE% -m venv "%ROOT%\venv"
if exist "%PY%" goto :venv_created
echo.
echo Ошибка: не удалось создать venv.
echo Установите Python 3.11+ с python.org и отметьте "Add python.exe to PATH".
goto :fail
:venv_created
echo [1/5] виртуальное окружение создано: venv
goto :deps
:venv_ok
echo [1/5] виртуальное окружение найдено: venv

rem --- 2. зависимости ---
:deps
"%PY%" -c "import fastapi, uvicorn, sqlalchemy, jinja2, alembic" >nul 2>nul
if not errorlevel 1 goto :deps_ok
echo [2/5] устанавливаю зависимости из requirements.txt...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r "%ROOT%\requirements.txt"
if errorlevel 1 goto :deps_failed
echo [2/5] зависимости установлены
goto :env
:deps_failed
echo.
echo Ошибка: не удалось установить зависимости.
goto :fail
:deps_ok
echo [2/5] зависимости на месте

rem --- 3. файл настроек ---
:env
if exist "%ROOT%\.env" goto :env_ok
echo [3/5] файла .env нет - копирую из .env.example
copy /y "%ROOT%\.env.example" "%ROOT%\.env" >nul
goto :db
:env_ok
echo [3/5] файл настроек .env найден

rem --- 4. первый администратор, только пока нет базы ---
:db
if exist "%ROOT%\portal.db" goto :db_ok
echo [4/5] базы данных нет - создайте администратора, вход по имени сотрудника
"%PY%" "%ROOT%\scripts\create_admin.py"
if errorlevel 1 goto :fail
goto :port
:db_ok
echo [4/5] база данных найдена: portal.db

rem --- 5. свободен ли порт ---
:port
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>nul
if errorlevel 1 goto :port_ok
echo.
echo Ошибка: порт %PORT% уже занят другой программой.
echo Закройте ту программу или запустите портал иначе: start.bat 8010
goto :fail
:port_ok
echo [5/5] порт %PORT% свободен

rem --- 6. запуск сервера ---
echo.
echo Адрес:     http://127.0.0.1:%PORT%/auth/login
if /i "%HOST%"=="0.0.0.0" echo Сеть:      http://%COMPUTERNAME%:%PORT%/auth/login - нужен доступ Python в брандмауэре
echo Остановка: Ctrl+C в этом окне
echo.

if defined PORTAL_NO_BROWSER goto :serve
rem Браузер открывается только когда сервер реально слушает порт
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "$u='http://127.0.0.1:%PORT%/auth/login'; for($i=0;$i -lt 120;$i++){ try { $c=New-Object Net.Sockets.TcpClient('127.0.0.1',%PORT%); $c.Close(); Start-Process $u; break } catch { Start-Sleep -Milliseconds 500 } }"

:serve
"%PY%" -m uvicorn app.main:app --host %HOST% --port %PORT%
if errorlevel 1 goto :serve_failed
echo.
echo Сервер остановлен.
goto :end
:serve_failed
echo.
echo Ошибка: сервер завершился с ошибкой. Подробности выше в этом окне.
goto :fail

:admin
if exist "%PY%" goto :admin_run
echo.
echo Ошибка: сначала запустите start.bat без параметров - он создаст venv и зависимости.
goto :fail
:admin_run
echo ============================================================
echo   Создание администратора портала
echo ============================================================
"%PY%" "%ROOT%\scripts\create_admin.py"
goto :end

:fail
echo.
pause
exit /b 1

:end
echo.
pause
exit /b 0
