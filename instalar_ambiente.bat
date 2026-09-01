@echo off
chcp 65001 >nul
setlocal

echo.
echo ==========================================================
echo   Instalacao do ambiente - Grupo de Estudo Geoprocessamento
echo ==========================================================
echo.
echo IMPORTANTE: este arquivo precisa ser executado pelo
echo "Anaconda Prompt (miniconda3)", e nao pelo duplo clique.
echo.
echo Se voce chegou aqui por duplo clique e viu um erro dizendo
echo que "conda nao e reconhecido", feche esta janela, abra o
echo menu Iniciar, digite "Anaconda Prompt", e a partir dele
echo navegue ate esta pasta e rode:  instalar_ambiente.bat
echo.
pause

REM ---------- 1. Verifica se o conda existe ----------
where conda >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ERRO] O conda nao foi encontrado.
    echo Instale o Miniconda antes de continuar. Veja a Aula 00.
    echo.
    pause
    exit /b 1
)

REM ---------- 2. Configura o solver rapido ----------
echo.
echo [1/4] Configurando o solver libmamba (deixa a instalacao muito mais rapida)...
call conda config --set solver libmamba
call conda config --set channel_priority strict

REM ---------- 3. Cria o ambiente ----------
echo.
echo [2/4] Criando o ambiente "geoproc".
echo       Isso pode levar de 10 a 25 minutos. NAO feche a janela.
echo.
call conda env create -f env\environment.yml
if errorlevel 1 (
    echo.
    echo [AVISO] A criacao falhou. Se a mensagem diz que o ambiente
    echo         ja existe, rode o comando abaixo para recriar:
    echo.
    echo         conda env remove -n geoproc
    echo.
    pause
    exit /b 1
)

REM ---------- 4. Registra o kernel no Jupyter ----------
echo.
echo [3/4] Registrando o ambiente no Jupyter...
call conda run -n geoproc python -m ipykernel install --user --name geoproc --display-name "Python (geoproc)"

REM ---------- 5. Testa ----------
echo.
echo [4/4] Verificando se tudo foi instalado corretamente...
echo.
call conda run -n geoproc python verificar_ambiente.py

echo.
echo ==========================================================
echo   Pronto. Para usar o ambiente, sempre digite antes:
echo.
echo       conda activate geoproc
echo.
echo ==========================================================
echo.
pause
endlocal
