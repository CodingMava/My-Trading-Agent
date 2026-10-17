# Registers the five Windows scheduled tasks that run the trading agent unattended. Review it, then run it
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

# 21:00 every day: a Telegram alert if the run didn't happen, failed or halted. If the PC was asleep or off
# at 21:00, it runs as soon as the PC is back, but first gives the daily run's own catch-up 10 minutes to
# finish (--scheduled), so it can't raise a false alarm while that run is still to come.
$healthSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "Trading agent - health check" -Force `
    -Description "Alerts on silence (python -m trader.ops.health --notify)." `
    -Action (New-ScheduledTaskAction -Execute $pythonw -Argument "-m trader.ops.health --notify --scheduled" -WorkingDirectory $root) `
    -Trigger (New-ScheduledTaskTrigger -Daily -At "21:00") -Settings $healthSettings | Out-Null

# Always on, from logon: answers your Telegram commands (/status, /positions, /trades, /kill, /login). It
# runs without a console window and is restarted if it stops. It is (re)started right away, so a running
# bot picks up the current code.
$botSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "Trading agent - Telegram commands" -Force `
    -Description "Answers Telegram commands (python -m trader.notify.bot). No command can trade or release the kill switch." `
    -Action (New-ScheduledTaskAction -Execute $pythonw -Argument "-m trader.notify.bot" -WorkingDirectory $root) `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME") -Settings $botSettings | Out-Null
Stop-ScheduledTask -TaskName "Trading agent - Telegram commands"
Start-ScheduledTask -TaskName "Trading agent - Telegram commands"

# Every 15 minutes, all day: NSE's corporate announcements, collected for research (Phase 9). The repetition
# never ends, so it doesn't hang on one daily start: with a 07:00 daily trigger, a laptop asleep at 07:00 ran
# nothing all day (14 Oct 2026). A start missed while the PC slept runs as soon as it wakes, and each run
# fetches whole from NSE's announcement API every recent day it hasn't seen whole, so nothing is lost.
$newsStart = (Get-Date).Date.AddHours((Get-Date).Hour + 1)  # the next full hour
$newsTrigger = New-ScheduledTaskTrigger -Once -At $newsStart -RepetitionInterval (New-TimeSpan -Minutes 15)  # no end
$newsSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "Trading agent - news" -Force `
    -Description "Collects NSE announcements for research (python -m trader.research.news collect). Never trades." `
    -Action (New-ScheduledTaskAction -Execute $pythonw -Argument "-m trader.research.news collect" -WorkingDirectory $root) `
    -Trigger $newsTrigger -Settings $newsSettings | Out-Null

# 19:30 every evening: the forward tests, in paper mode (research only), one after the other in one task so they never
# rebuild the data at the same time.
# 1. Forward test 2, round 8's N2 (docs/research/forward2-preregistration.md): downloads the evening's NSE file and
#    corporate actions, rebuilds the adjusted history when something changed, records the month's picks and the closed
#    paper positions.
# 2. Forward test 3, round 10's E2 (docs/research/forward3-preregistration.md): fetches NSE's board-meeting notices,
#    records new results-reaction signals, paper entries and exits on forward test 2's rebuilt history.
# 3. Paper trial 1, E2 x3 + V2 x2 in one paper account (docs/research/trial1-definition.md): entries, exits and brakes
#    on the same rebuilt history. Not evidence; it changes no strategy's status.
# All send messages labelled paper only. If the PC was asleep or off at 19:30, the task runs as soon as it is back and
# each catches up every day it missed.
$forwardSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 60) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
if (Get-ScheduledTask -TaskName "Trading agent - forward test 2" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName "Trading agent - forward test 2" -Confirm:$false  # now part of "forward tests"
}
Register-ScheduledTask -TaskName "Trading agent - forward tests" -Force `
    -Description "Forward tests 2 (N2) and 3 (E2), then paper trial 1 (E2 x3 + V2 x2), in paper mode on new NSE sessions (python -m trader.research.forward2 daily, forward3 daily, trial daily). Research only; never trades." `
    -Action @((New-ScheduledTaskAction -Execute $pythonw -Argument "-m trader.research.forward2 daily" -WorkingDirectory $root),
              (New-ScheduledTaskAction -Execute $pythonw -Argument "-m trader.research.forward3 daily" -WorkingDirectory $root),
              (New-ScheduledTaskAction -Execute $pythonw -Argument "-m trader.research.trial daily" -WorkingDirectory $root)) `
    -Trigger (New-ScheduledTaskTrigger -Daily -At "19:30") -Settings $forwardSettings | Out-Null

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
