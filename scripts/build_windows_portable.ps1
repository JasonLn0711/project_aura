Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$DistRoot = Join-Path $RepoRoot "dist"
$PortableRoot = Join-Path $DistRoot "aura-windows-portable"

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path $PortableRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot "scripts") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot "docs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot "sample_audio") | Out-Null

Copy-Item "README.md" $PortableRoot -Force
Copy-Item "pyproject.toml" $PortableRoot -Force
Copy-Item "docs\windows_setup.md" (Join-Path $PortableRoot "docs") -Force
Copy-Item "docs\windows_known_issues.md" (Join-Path $PortableRoot "docs") -Force
Copy-Item "scripts\runtime_report.py" (Join-Path $PortableRoot "scripts") -Force
Copy-Item "scripts\windows_gpu_smoke.py" (Join-Path $PortableRoot "scripts") -Force
Copy-Item "scripts\check_windows_runtime.ps1" (Join-Path $PortableRoot "scripts") -Force
Copy-Item "scripts\run_aura_windows.ps1" (Join-Path $PortableRoot "scripts") -Force

@"
# Project AURA Windows Portable Developer Release

1. Install Python 3.11 and FFmpeg.
2. Follow docs/windows_setup.md.
3. Run scripts/check_windows_runtime.ps1.
4. Run scripts/run_aura_windows.ps1.

This portable folder is a developer release layout. It is not a full installer.
"@ | Set-Content -Encoding UTF8 (Join-Path $PortableRoot "WINDOWS_PORTABLE_README.md")

@"
Place a short WAV or MP3 sample here for release smoke testing.
Large media files should not be committed to git.
"@ | Set-Content -Encoding UTF8 (Join-Path $PortableRoot "sample_audio\README.txt")

Write-Host "Portable developer release prepared at $PortableRoot"
