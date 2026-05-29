Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (Test-Path ".\.venv\Scripts\python.exe") {
    $Python = ".\.venv\Scripts\python.exe"
} else {
    $Python = "py"
}

Write-Host "== nvidia-smi =="
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    nvidia-smi
} else {
    Write-Host "nvidia-smi is not available on PATH."
}

Write-Host ""
Write-Host "== Runtime report =="
& $Python "scripts\runtime_report.py"

Write-Host ""
Write-Host "== Windows GPU smoke =="
& $Python "scripts\windows_gpu_smoke.py"
