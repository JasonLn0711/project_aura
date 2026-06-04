Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$DistRoot = Join-Path $RepoRoot "dist"
$PortableRoot = Join-Path $DistRoot "aura-windows-portable"

Set-Location $RepoRoot
if (Test-Path ".\.venv\Scripts\python.exe") {
    $Python = ".\.venv\Scripts\python.exe"
} else {
    $Python = "python"
}

$PyProjectText = Get-Content "pyproject.toml" -Raw
if ($PyProjectText -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
    throw "Could not read package version from pyproject.toml"
}
$Version = $Matches[1]
$ZipPath = Join-Path $DistRoot "aura-windows-portable-v$Version.zip"

if (Test-Path $PortableRoot) {
    Remove-Item $PortableRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $PortableRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot "app") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot "scripts") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot "docs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PortableRoot "sample_audio") | Out-Null

Copy-Item "README.md" $PortableRoot -Force
Copy-Item "Start-AURA.ps1" $PortableRoot -Force
Copy-Item "Start-AURA.bat" $PortableRoot -Force
Copy-Item "Check-AURA.ps1" $PortableRoot -Force
Copy-Item "Check-AURA.bat" $PortableRoot -Force
Copy-Item "pyproject.toml" (Join-Path $PortableRoot "app") -Force
Copy-Item "README.md" (Join-Path $PortableRoot "app") -Force
Copy-Item "LICENSE" (Join-Path $PortableRoot "app") -Force
Copy-Item "src" (Join-Path $PortableRoot "app") -Recurse -Force
Copy-Item "config" (Join-Path $PortableRoot "app") -Recurse -Force
Copy-Item "docs\windows_setup.md" (Join-Path $PortableRoot "docs") -Force
Copy-Item "docs\windows_known_issues.md" (Join-Path $PortableRoot "docs") -Force
Copy-Item "scripts\runtime_report.py" (Join-Path $PortableRoot "scripts") -Force
Copy-Item "scripts\windows_gpu_smoke.py" (Join-Path $PortableRoot "scripts") -Force
Copy-Item "scripts\windows_asr_artifact_smoke.py" (Join-Path $PortableRoot "scripts") -Force
Copy-Item "scripts\check_windows_runtime.ps1" (Join-Path $PortableRoot "scripts") -Force
Copy-Item "scripts\run_aura_windows.ps1" (Join-Path $PortableRoot "scripts") -Force

@"
# Project AURA Windows Portable Release

Version: v$Version

1. Install or update the NVIDIA driver.
2. Double-click Check-AURA.bat.
3. Double-click Start-AURA.bat.

Check-AURA.bat and Start-AURA.bat create .venv, install Project AURA dependencies,
write diagnostic_report.txt, run the RTX/CUDA smoke check, and keep failures visible.

This portable folder is the supported Windows onboarding artifact before a full installer.
"@ | Set-Content -Encoding UTF8 (Join-Path $PortableRoot "WINDOWS_PORTABLE_README.md")

@"
Project AURA diagnostic_report.txt

This file is replaced by Check-AURA.bat or Start-AURA.bat.
"@ | Set-Content -Encoding UTF8 (Join-Path $PortableRoot "diagnostic_report.txt")

$SamplePath = Join-Path $PortableRoot "sample_audio\aura_smoke_1s.wav"
$SampleGenerator = Join-Path $PortableRoot "sample_audio\_make_sample.py"
@"
import math
import struct
import sys
import wave

path = sys.argv[1]
sample_rate = 16000
with wave.open(path, "wb") as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(sample_rate)
    frames = bytearray()
    for index in range(sample_rate):
        value = int(0.18 * 32767 * math.sin(2 * math.pi * 440 * index / sample_rate))
        frames.extend(struct.pack("<h", value))
    wav_file.writeframes(bytes(frames))
"@ | Set-Content -Encoding UTF8 $SampleGenerator
& $Python $SampleGenerator $SamplePath
Remove-Item $SampleGenerator -Force

@"
This folder includes aura_smoke_1s.wav, a tiny generated WAV for packaging and import smoke checks.
Use real speech samples outside git for release validation.
"@ | Set-Content -Encoding UTF8 (Join-Path $PortableRoot "sample_audio\README.txt")

Write-Host "Portable developer release prepared at $PortableRoot"

if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}
Compress-Archive -Path (Join-Path $PortableRoot "*") -DestinationPath $ZipPath -Force
Write-Host "Portable ZIP prepared at $ZipPath"
