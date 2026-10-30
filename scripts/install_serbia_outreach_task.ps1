param(
    [switch]$Enable
)
$ErrorActionPreference = 'Stop'
$campaignRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$taskName = 'Fasad Flow Serbia Outreach'
$campaignScript = Join-Path $campaignRoot 'serbia_outreach.py'
$campaignConfig = Join-Path $campaignRoot 'sales\serbia\campaign.json'
if (-not (Test-Path -LiteralPath $campaignScript -PathType Leaf)) {
    throw 'Campaign script not found.'
}
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$campaign = Get-Content -LiteralPath $campaignConfig -Encoding UTF8 -Raw | ConvertFrom-Json
$agentPythonw = Join-Path $campaign.openclaw_root '.venv\Scripts\pythonw.exe'
if ($existingTask) {
    $existingAction = @($existingTask.Actions)[0]
    if ($existingAction.Arguments -notlike ('*' + $campaignScript + '*')) {
        throw 'A task with this name belongs to a different action; refusing to overwrite it.'
    }
    if ($Enable) {
        $campaign = Get-Content -LiteralPath $campaignConfig -Encoding UTF8 -Raw | ConvertFrom-Json
        if (-not $campaign.enabled -or -not $campaign.allow_live_on_draft_mailbox) {
            throw 'Activate the approved campaign first with --confirm-live.'
        }
        if ($campaign.mailbox_profile) {
            if (-not (Test-Path -LiteralPath $agentPythonw -PathType Leaf)) {
                throw 'The selected Open Claw Python environment is unavailable.'
            }
            $agentAction = New-ScheduledTaskAction -Execute $agentPythonw -Argument ('"' + $campaignScript + '" cycle') -WorkingDirectory $campaignRoot
            Set-ScheduledTask -TaskName $taskName -Action $agentAction | Out-Null
        }
        Enable-ScheduledTask -TaskName $taskName | Out-Null
    }
    Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State | ConvertTo-Json -Compress
    exit 0
}
$pythonExecutable = (& python -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    throw 'Python interpreter not found.'
}
$hiddenPython = Join-Path (Split-Path $pythonExecutable -Parent) 'pythonw.exe'
if ($campaign.mailbox_profile) {
    $hiddenPython = $agentPythonw
}
if (-not (Test-Path -LiteralPath $hiddenPython -PathType Leaf)) {
    throw 'pythonw.exe is required for a hidden scheduled worker.'
}
if ($Enable) {
    $campaign = Get-Content -LiteralPath $campaignConfig -Encoding UTF8 -Raw | ConvertFrom-Json
    if (-not $campaign.enabled -or -not $campaign.allow_live_on_draft_mailbox) {
        throw 'Activate the approved campaign first with --confirm-live.'
    }
}
$taskArguments = '"' + $campaignScript + '" cycle'
$action = New-ScheduledTaskAction -Execute $hiddenPython -Argument $taskArguments -WorkingDirectory $campaignRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 30)
$settingsArguments = @{
    Hidden = $true
    StartWhenAvailable = $true
    AllowStartIfOnBatteries = $true
    DontStopIfGoingOnBatteries = $true
    ExecutionTimeLimit = (New-TimeSpan -Minutes 10)
    MultipleInstances = 'IgnoreNew'
    Disable = (-not $Enable.IsPresent)
}
$settings = New-ScheduledTaskSettingsSet @settingsArguments
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$definition = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Isolated Serbian Fasad Flow campaign; consent and campaign authorization required.'
Register-ScheduledTask -TaskName $taskName -InputObject $definition | Out-Null
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State | ConvertTo-Json -Compress
