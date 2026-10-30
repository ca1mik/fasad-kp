$ErrorActionPreference = 'Stop'
$campaignRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$batchScript = Join-Path $campaignRoot 'scripts\send_fasad_wave2.py'
$taskName = 'Fasad Flow Wave2 Immediate'
$campaignConfig = Join-Path $campaignRoot 'sales\serbia\campaign.json'
$campaign = Get-Content -LiteralPath $campaignConfig -Encoding UTF8 -Raw | ConvertFrom-Json
$agentPython = Join-Path $campaign.openclaw_root '.venv\Scripts\pythonw.exe'
if (-not $campaign.enabled -or -not $campaign.allow_live_on_draft_mailbox) {
    throw 'Only the enabled, owner-approved Fasad Flow campaign may run.'
}
if ($campaign.mailbox -ne 'koallalenivaa@gmail.com' -or $campaign.expected_sender -ne $campaign.mailbox) {
    throw 'The authorized Gmail sender changed; refusing to schedule.'
}
if ($campaign.daily_limit -ne 100 -or $campaign.mailbox_daily_limit -ne 100) {
    throw 'Apply the explicit 100-limit instruction before scheduling this batch.'
}
if (-not (Test-Path -LiteralPath $agentPython -PathType Leaf) -or -not (Test-Path -LiteralPath $batchScript -PathType Leaf)) {
    throw 'The existing Open Claw interpreter or bounded batch script is missing.'
}
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask -and $existingTask.Actions.Arguments -notlike ('*' + $batchScript + '*')) {
    throw 'The task name belongs to another action; refusing to overwrite it.'
}
if ($existingTask -and $existingTask.State -eq 'Running') {
    Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State | ConvertTo-Json -Compress
    exit 0
}
$action = New-ScheduledTaskAction -Execute $agentPython -Argument ('"' + $batchScript + '" --once --scheduled') -WorkingDirectory $campaignRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(3) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Hours 4)
$settings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$definition = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Owner-approved Fasad Flow wave: exactly 20 researched targets, durable receipts, opt-outs, account cap 100, pause 90s. Self-disables on completion.'
Register-ScheduledTask -TaskName $taskName -InputObject $definition -Force | Out-Null
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State | ConvertTo-Json -Compress
