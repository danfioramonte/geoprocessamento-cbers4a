@echo off
chcp 65001 >nul
setlocal

echo.
echo ==========================================================
echo   Instalacao do ambiente
echo ==========================================================
echo.
echo Este projeto usa o pixi para montar o ambiente Python.
echo O pixi le o arquivo pixi.toml, baixa o proprio Python e
echo todas as bibliotecas, e grava tudo num pixi.lock. Voce nao
echo precisa instalar Python, Miniforge nem Anaconda a parte.
echo.
echo IMPORTANTE: rode este arquivo a partir de um terminal, de
echo dentro da pasta do projeto. Se preferir, siga a Aula 00 e
echo rode os comandos manualmente - sao poucos.
echo.
pause

REM ---------- 1. Verifica se o pixi existe ----------
where pixi >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERRO] O pixi nao foi encontrado no PATH.
    echo.
    echo Instale o pixi antes de continuar. Em um PowerShell, rode:
    echo.
    echo     powershell -ExecutionPolicy ByPass -c "irm -useb https://pixi.sh/install.ps1 ^| iex"
    echo.
    echo Depois FECHE e reabra o terminal (para o PATH atualizar) e
    echo rode este arquivo de novo. Veja a Aula 00 para os detalhes.
    echo.
    pause
    exit /b 1
)

REM ---------- 2. Cria o ambiente a partir do pixi.toml ----------
echo.
echo [1/2] Criando o ambiente com "pixi install".
echo       Na primeira vez leva alguns minutos (baixa Python, GDAL,
echo       PyTorch etc.). NAO feche a janela.
echo.
call pixi install
if errorlevel 1 (
    echo.
    echo [AVISO] A instalacao falhou. Se a mensagem citar rede ou
    echo canal, tente de novo com a internet estavel. Para comecar
    echo do zero, apague a pasta oculta .pixi e rode de novo:
    echo.
    echo     rmdir /s /q .pixi
    echo     pixi install
    echo.
    pause
    exit /b 1
)

REM ---------- 3. Testa ----------
echo.
echo [2/2] Verificando se tudo foi instalado corretamente...
echo.
call pixi run check

echo.
echo ==========================================================
echo   Pronto.
echo.
echo   Para trabalhar, nesta pasta rode:
echo.
echo       pixi run lab        (abre o Jupyter Lab)
echo.
echo ==========================================================
echo.
pause
endlocal
