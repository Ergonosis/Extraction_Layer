# Local production build of the React portal (output: portal/dist).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "portal")
bun install --frozen-lockfile
bun run build
Write-Host "Built $(Join-Path $root 'portal\dist')"
