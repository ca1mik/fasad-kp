$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$fasadPython = (Get-Command python -ErrorAction Stop).Source
$fasadPort = 8770
$fasadListener = Get-NetTCPConnection -LocalPort $fasadPort -State Listen -ErrorAction SilentlyContinue
if (-not $fasadListener) {
    & $fasadPython -c "import fastapi, uvicorn, segno"
    if ($LASTEXITCODE -ne 0) { throw 'Install dependencies: python -m pip install -r requirements-crm.txt' }
    New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'logs') -Force | Out-Null
    Start-Process -FilePath $fasadPython -ArgumentList 'crm_server.py','serve' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'logs/product.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'logs/product.stderr.log')
}
Write-Host 'Fasad Flow: http://127.0.0.1:8770/work/'
Write-Host 'First launch: create your administrator in the browser.'
