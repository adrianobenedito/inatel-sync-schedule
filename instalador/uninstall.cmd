@echo off
rem Remove o inatel-sync do usuario atual. Os eventos ja criados no Google Agenda ficam.
setlocal
chcp 65001 >nul
set "PROG=%LOCALAPPDATA%\inatel-sync"

echo === inatel-sync: desinstalar ===
choice /c sn /n /m "Manter a configuracao para reinstalar depois? [s/n] "
if errorlevel 2 (set "MANTER=") else (set "MANTER=--manter-dados")
choice /c sn /n /m "Remover o inatel-sync agora? [s/n] "
if errorlevel 2 exit /b 0

if exist "%PROG%\bin\inatel-sync.exe" "%PROG%\bin\inatel-sync.exe" desinstalar --sim %MANTER%

powershell -NoProfile -Command "$b='%PROG%\bin'; $p=[Environment]::GetEnvironmentVariable('Path','User'); if ($p) { [Environment]::SetEnvironmentVariable('Path', (($p -split ';' | Where-Object { $_ -and $_ -ne $b }) -join ';'), 'User') }"

echo Pronto. Os eventos que ja estavam no Google Agenda continuam la.
pause
cd /d "%TEMP%"
rem Este .cmd pode estar dentro da pasta: apaga a pasta num processo separado, depois que ele fechar
start "" /min cmd /c "timeout /t 2 >nul & rmdir /s /q "%PROG%""
