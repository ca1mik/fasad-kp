$ErrorActionPreference = 'Stop'
$campaignRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$script = Join-Path $campaignRoot 'russia_outreach.py'
$cfg = Get-Content -LiteralPath (Join-Path $campaignRoot 'sales\russia\campaign.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$taskName = 'Fasad Flow Russia Outreach'
$python = Join-Path $cfg.openclaw_root '.venv\Scripts\pythonw.exe'
if ($cfg.campaign_id -ne 'fasad-flow-russia-v1' -or $cfg.expected_sender -ne 'koallalenivaa@gmail.com') {
    throw 'Only the separate Russian campaign and existing Gmail may be scheduled.'
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Open Claw Pythonw is missing.' }
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and $existing.Actions.Arguments -notlike ('*' + $script + '*')) { throw 'Task name belongs to another action.' }
$action = New-ScheduledTaskAction -Execute $python -Argument ('"' + $script + '" cycle --scheduled') -WorkingDirectory $campaignRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(10) -RepetitionInterval (New-TimeSpan -Minutes 2)
$settings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 8)
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$definition = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Separate Russian Fasad Flow queue. One recipient per attempt, real PDF, confirmed Russian scope, verified public HTTPS test demo, shared locks and Gmail-wide 100/day, 100/hour, pause >=90s. Holds incomplete recipients; never retries uncertain POST.'
Register-ScheduledTask -TaskName $taskName -InputObject $definition -Force | Out-Null
$task = Get-ScheduledTask -TaskName $taskName
$info = Get-ScheduledTaskInfo -TaskName $taskName
[pscustomobject]@{TaskName=$task.TaskName;State=$task.State.ToString();Hidden=$task.Settings.Hidden;Execute=$task.Actions.Execute;Arguments=$task.Actions.Arguments;Interval=$task.Triggers.Repetition.Interval;NextRunTime=$info.NextRunTime} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $campaignRoot 'data\russia-outreach\schedule_status.json') -Encoding UTF8
Get-Content -LiteralPath (Join-Path $campaignRoot 'data\russia-outreach\schedule_status.json') -Encoding UTF8
