Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$LaunchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $LaunchRoot "Start-AURA.ps1") -CheckOnly
