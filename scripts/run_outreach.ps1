[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('healthcheck', 'dry-run', 'send-new', 'sync-replies', 'state-report')]
    [string]$Command = 'state-report',

    [string]$EnvFile = '.env',

    [switch]$Sample
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($Sample -and $Command -ne 'dry-run') {
    throw '-Sample is valid only with dry-run.'
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$pythonCommand = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { 'python' }
$cliArgs = @('main.py', '--env-file', $EnvFile, $Command)
if ($Sample) {
    $cliArgs += '--sample'
}

Push-Location -LiteralPath $projectRoot
try {
    & $pythonCommand @cliArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
