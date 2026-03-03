@echo off
chcp 65001 >nul
title Interview Assistant

echo ==========================================
echo   Real-Time Interview Assistant
echo ==========================================
echo.

:: Python kontrolü
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadı! Python 3.10+ kurulu olmalı.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

:: .env dosyası kontrolü
if not exist ".env" (
    echo [HATA] .env dosyasi bulunamadi!
    echo .env.example dosyasini .env olarak kopyalayip API key'lerinizi girin.
    echo.
    echo   copy .env.example .env
    echo   notepad .env
    echo.
    pause
    exit /b 1
)

:: Bağımlılık kontrolü - fastapi yüklü mü?
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo [BILGI] Bagimliliklar kuruluyor...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [HATA] Bagimlilik kurulumu basarisiz!
        pause
        exit /b 1
    )
    echo.
)

echo [BILGI] Uygulama baslatiliyor...
echo.
python main.py

pause
