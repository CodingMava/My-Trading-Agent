# Registers the two Windows scheduled tasks that run the trading agent unattended. Review it, then run it
# once from the project folder in PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1
# The times are this PC's local time, which must be India time (IST). The tasks run while you are logged
# in to Windows. To remove them:
#   Unregister-ScheduledTask -TaskName "Trading agent*" -Confirm:$false

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "No virtual environment at ${python}: create it first (see README.md)." }

# 18:00 every day, once the session's data has settled; a day without a new session does nothing.
# If the PC was off or asleep at 18:00, the run starts as soon as it is back and catches up.
$runSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName "Trading agent - daily run" -Force `
    -Description "End-of-day paper trading (python -m trader.execution.eod). Never places a real order." `
    -Action (New-ScheduledTaskAction -Execute $python -Argument "-m trader.execution.eod" -WorkingDirectory $root) `
    -Trigger (New-ScheduledTaskTrigger -Daily -At "18:00") -Settings $runSettings | Out-Null

# 21:00 every day: a Telegram alert if the run didn't happen, failed or halted. It deliberately doesn't
# start late after the PC was off, so it can't raise a false alarm before the catch-up run has finished.
$healthSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName "Trading agent - health check" -Force `
    -Description "Alerts on silence (python -m trader.ops.health --notify)." `
    -Action (New-ScheduledTaskAction -Execute $python -Argument "-m trader.ops.health --notify" -WorkingDirectory $root) `
    -Trigger (New-ScheduledTaskTrigger -Daily -At "21:00") -Settings $healthSettings | Out-Null

Get-ScheduledTask -TaskName "Trading agent*" | Select-Object TaskName, State
