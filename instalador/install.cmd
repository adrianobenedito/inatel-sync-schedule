@echo off
rem Instala ou atualiza o inatel-sync para o usuario atual (sem admin). Pode rodar de novo.
setlocal
chcp 65001 >nul
set "AQUI=%~dp0"
set "PROG=%LOCALAPPDATA%\inatel-sync"
set "UV_PYTHON_INSTALL_DIR=%PROG%\python"
set "UV_TOOL_DIR=%PROG%\tools"
set "UV_TOOL_BIN_DIR=%PROG%\bin"
set "UV_CACHE_DIR=%PROG%\cache"
set "UV_NO_MODIFY_PATH=1"

echo.
echo === inatel-sync: instalacao ===
echo Pasta do programa: %PROG%
echo.

if not exist "%PROG%\bin" mkdir "%PROG%\bin"
copy /y "%AQUI%uv.exe" "%PROG%\bin\uv.exe" >nul || goto :erro
copy /y "%AQUI%uninstall.cmd" "%PROG%\uninstall.cmd" >nul || goto :erro

echo Baixando o Python e as bibliotecas (precisa de internet; 1 a 3 minutos na primeira vez)...
for %%W in ("%AQUI%pacote\inatel_sync-*.whl") do set "RODA=%%~fW"
"%PROG%\bin\uv.exe" tool install --quiet --force --reinstall --python 3.12 --managed-python "%RODA%" || goto :erro

rem PATH do usuario, so se ainda nao tiver (INATEL_SYNC_TESTE: instalacao de teste nao mexe no PATH real)
if not defined INATEL_SYNC_TESTE powershell -NoProfile -Command "$p=[Environment]::GetEnvironmentVariable('Path','User'); $b='%PROG%\bin'; if (($p -split ';') -notcontains $b) { [Environment]::SetEnvironmentVariable('Path', ($(if ($p) { $p.TrimEnd(';') + ';' }) + $b), 'User') }"
set "PATH=%PROG%\bin;%PATH%"

if exist "%APPDATA%\inatel-sync\config.toml" (
    echo.
    echo Atualizado. A sua configuracao foi mantida.
    "%PROG%\bin\inatel-sync.exe" agendar
    choice /c sn /n /m "Quer revisar as respostas (assistente)? [s/n] "
    if errorlevel 2 goto :fim
)
"%PROG%\bin\inatel-sync.exe" setup
goto :fim

:erro
echo.
echo A instalacao falhou. Confira a internet e rode o install.cmd de novo.
echo Se continuar, mande a mensagem acima para quem te passou o inatel-sync.
pause
exit /b 1

:fim
echo.
echo Para usar os comandos neste terminal, abra um novo Prompt de Comando.
pause
