# Local production build of the React portal (output: portal/dist).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "portal")
npm ci
npm run build
Write-Host "Built $(Join-Path $root 'portal\dist')"
