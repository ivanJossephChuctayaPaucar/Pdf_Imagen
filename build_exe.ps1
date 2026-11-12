$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$PyInstaller = Join-Path $ProjectRoot ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $PyInstaller)) {
    Write-Error "No se encontró PyInstaller en .venv\Scripts\pyinstaller.exe"
}

& $PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "PDFaImagen" `
    --version-file "version_info.txt" `
    --paths $ProjectRoot `
    --collect-all customtkinter `
    --collect-all tkinterdnd2 `
    --exclude-module matplotlib `
    --exclude-module scipy `
    --exclude-module pandas `
    "src\main.py"

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller falló con código de salida $LASTEXITCODE."
}

Write-Host ""
Write-Host "Ejecutable generado en: $ProjectRoot\dist\PDFaImagen.exe"
