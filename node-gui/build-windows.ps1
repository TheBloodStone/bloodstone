# Build Bloodstone Node GUI on Windows (PowerShell 5+)
# Prerequisites: Node.js 18+ LTS from https://nodejs.org/
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Bloodstone Node GUI — Windows build" -ForegroundColor Cyan
node -v
npm -v

$hasDaemon = Test-Path "bin\win64\bloodstoned.exe"
if (-not $hasDaemon) {
    Write-Host ""
    Write-Host "Place bloodstoned.exe and bloodstone-cli.exe in bin\win64\" -ForegroundColor Yellow
    Write-Host "Download from https://bloodstonewallet.mytunnel.org/downloads/ or build from source." -ForegroundColor Yellow
}

npm install --no-audit --no-fund
npm run dist

Write-Host ""
Write-Host "Artifacts in .\dist\" -ForegroundColor Green
Get-ChildItem dist\*.exe | Format-Table Name, Length, LastWriteTime