@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
echo Gmail для Fasad Flow: koallalenivaa@gmail.com
echo После успешного подключения будет включена только очередь Fasad Flow.
echo VPN не отключать. Пароли и коды не отправлять в чат.
python scripts\connect_fasad_gmail.py
if errorlevel 1 goto failed
python serbia_outreach.py mail-check
if errorlevel 1 goto failed
python serbia_outreach.py activate --confirm-live
if errorlevel 1 goto failed
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_serbia_outreach_task.ps1 -Enable
if errorlevel 1 goto failed
echo Кампания включена. Отправка: будни 10:00-17:00 по Белграду, 5 писем в день.
pause
exit /b 0
:failed
python serbia_outreach.py pause >nul
powershell -NoProfile -Command "Disable-ScheduledTask -TaskName 'Fasad Flow Serbia Outreach' -ErrorAction SilentlyContinue | Out-Null"
echo Подключение или запуск не завершены. Не повторяйте неопределённую отправку.
pause
exit /b 1
