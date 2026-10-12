# Registers the three Windows scheduled tasks that run the trading agent unattended. Review it, then run it
# once from the project folder in PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1
# The times are this PC's local time, which must be India time (IST). The tasks run while you are logged
# in to Windows, on battery too: by default Windows skips a task that comes due while a laptop is on
# battery (without counting it as missed, so it never catches up) and stops a running one when the
# charger is unplugged. To remove them:
#   Unregister-ScheduledTask -TaskName "Trading agent*" -Confirm:$false
#
# With -Live it also registers the three live-trading jobs (Phase 11). Do that only when going live
# (docs/runbook.md, "Before the first real order"); they send nothing while live trading is locked.
param([switch]$Live)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
# Every task runs pythonw.exe, so no console window opens: a window that pops up when the PC wakes can be
# closed by accident, or catch a Ctrl+C typed into it, and that kills the run. The output goes to logs/.
$pythonw = Join-Path $root "venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "No virtual environment at ${pythonw}: create it first (see README.md)." }

# 18:00 every day, once the session's data has settled; a day without a new session does nothing.
# If the PC was off or asleep at 18:00, the run starts as soon as it is back and catches up.
$runSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "Trading agent - daily run" -Force `
    -Description "End-of-day paper trading (python -m trader.execution.eod). Never places a real order." `
    -Action (New-ScheduledTaskAction -Execute $pythonw -Argument "-m trader.execution.eod" -WorkingDirectory $root) `
    -Trigger (New-ScheduledTaskTrigger -Daily -At "18:00") -Settings $runSettings | Out-Null

# 21:00 every day: a Telegram alert if the run didn't happen, failed or halted. It deliberately doesn't
# start late after the PC was off, so it can't raise a false alarm before the catch-up run has finished.
$healthSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "Trading agent - health check" -Force `
    -Description "Alerts on silence (python -m trader.ops.health --notify)." `
    -Action (New-ScheduledTaskAction -Execute $pythonw -Argument "-m trader.ops.health --notify" -WorkingDirectory $root) `
    -Trigger (New-ScheduledTaskTrigger -Daily -At "21:00") -Settings $healthSettings | Out-Null

# Always on, from logon: answers your Telegram commands (/status, /positions, /trades, /kill). It runs
# without a console window and is restarted if it stops; it is also started right away.
$botSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "Trading agent - Telegram commands" -Force `
    -Description "Answers Telegram commands (python -m trader.notify.bot). No command can trade or release the kill switch." `
    -Action (New-ScheduledTaskAction -Execute $pythonw -Argument "-m trader.notify.bot" -WorkingDirectory $root) `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME") -Settings $botSettings | Out-Null
Start-ScheduledTask -TaskName "Trading agent - Telegram commands"

# Live trading through Zerodha Kite: 18:30 after the daily run (orders for the next open), 09:20 after the
# open (stops), 15:15 before the close (time exits). The morning job may start late, since a stop placed late
# beats none; the others don't, and each job refuses to send outside its own window anyway.
if ($Live) {
    $weekdays = "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"
    $jobs = @(
        @{ Name = "evening"; Trigger = (New-ScheduledTaskTrigger -Daily -At "18:30"); Late = $false },
        @{ Name = "morning"; Trigger = (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "09:20"); Late = $true },
        @{ Name = "preclose"; Trigger = (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At "15:15"); Late = $false })
    foreach ($job in $jobs) {
        $jobSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable:$job.Late
        Register-ScheduledTask -TaskName "Trading agent - live $($job.Name)" -Force `
            -Description "Live trading through Zerodha Kite (python -m trader.execution.live $($job.Name)). Sends nothing while locked." `
            -Action (New-ScheduledTaskAction -Execute $pythonw -Argument "-m trader.execution.live $($job.Name)" -WorkingDirectory $root) `
            -Trigger $job.Trigger -Settings $jobSettings | Out-Null
    }
}

Get-ScheduledTask -TaskName "Trading agent*" | Select-Object TaskName, State
