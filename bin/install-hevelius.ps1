param(
    [string]$ShortcutName = "Hevelius Runner"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$binDir = Join-Path $repoRoot "bin"

if (-not (Test-Path $binDir)) {
    New-Item -Path $binDir -ItemType Directory | Out-Null
}

$runnerCmdPath = Join-Path $binDir "hevelius-runner.cmd"
$openShellPath = Join-Path $binDir "open-hevelius.ps1"

$runnerCmdContent = @'
@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
"%PROJECT_ROOT%\venv\Scripts\python.exe" "%PROJECT_ROOT%\src\hevelius-runner.py" %*
'@

$openShellContent = @'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$activateScript = Join-Path $repoRoot "venv\Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    . $activateScript
}
else {
    Write-Warning "Virtual environment activation script not found at: $activateScript"
}

$runnerCmd = Join-Path $repoRoot "bin\hevelius-runner.cmd"
Set-Alias -Name hevelius-runner -Value $runnerCmd -Scope Global

Write-Host "Hevelius runner shell ready. Use: hevelius-runner <args>" -ForegroundColor Green
'@

Set-Content -Path $runnerCmdPath -Value $runnerCmdContent -Encoding ascii
Set-Content -Path $openShellPath -Value $openShellContent -Encoding utf8

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

Write-Host "Installed launcher scripts:" -ForegroundColor Green
Write-Host "  $runnerCmdPath"
Write-Host "  $openShellPath"
Write-Host ""
Write-Host "Start Menu shortcut created:" -ForegroundColor Green
Write-Host "  $shortcutPath"
Write-Host ""
Write-Host "Open Start Menu, find '$ShortcutName', and pin it if desired."
