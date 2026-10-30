[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'

$sendArgv = @($pythonPath, 'main.py', '--env-file', '.env', 'send-new') | ConvertTo-Json -Compress
$syncArgv = @($pythonPath, 'main.py', '--env-file', '.env', 'sync-replies') | ConvertTo-Json -Compress

Write-Output '# The commands below are examples only. This script does not execute them.'
Write-Output ('openclaw automations create ''0 10 * * 1-5'' --name ''fasad-send-new'' --command-argv ''{0}'' --command-cwd ''{1}'' --tz ''Europe/Moscow'' --no-deliver' -f $sendArgv, $projectRoot)
Write-Output ('openclaw automations create ''15 * * * *'' --name ''fasad-sync-replies'' --command-argv ''{0}'' --command-cwd ''{1}'' --tz ''Europe/Moscow'' --no-deliver' -f $syncArgv, $projectRoot)
