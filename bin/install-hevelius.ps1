param(
    [string]$ShortcutName = "Hevelius Runner"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$binDir = Join-Path $repoRoot "bin"

$runnerCmdPath = Join-Path $binDir "hevelius-runner.cmd"
$openShellPath = Join-Path $binDir "open-hevelius.ps1"

$missing = @()
if (-not (Test-Path $runnerCmdPath)) { $missing += $runnerCmdPath }
if (-not (Test-Path $openShellPath))  { $missing += $openShellPath }
if ($missing.Count -gt 0) {
    Write-Error "Required launcher file(s) missing from the repository:`n  $($missing -join "`n  ")`nRun 'git restore bin/' to restore them, then re-run this script."
    exit 1
}

$startMenuPrograms = [Environment]::GetFolderPath("Programs")
$shortcutPath = Join-Path $startMenuPrograms "$ShortcutName.lnk"
$powershellExe = "powershell.exe"
$shortcutArgs = "-NoExit -ExecutionPolicy Bypass -File `"$openShellPath`""

$wshShell = New-Object -ComObject WScript.Shell
$shortcut = $wshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powershellExe
$shortcut.Arguments = $shortcutArgs
$shortcut.WorkingDirectory = $repoRoot
$shortcut.IconLocation = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe,0"
$shortcut.Save()

Write-Host "Start Menu shortcut created:" -ForegroundColor Green
Write-Host "  $shortcutPath"
Write-Host ""
Write-Host "Open Start Menu, find '$ShortcutName', and pin it if desired."
