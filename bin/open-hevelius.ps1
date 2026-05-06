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
