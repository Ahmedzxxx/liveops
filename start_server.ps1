$Host.UI.RawUI.WindowTitle = "LiveOps Management App"
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host " Starting LiveOps Workforce Management Server...    " -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Cyan
Set-Location -Path $PSScriptRoot
& "C:\Users\Ahmed\AppData\Local\Python\bin\python.exe" run_server.py
