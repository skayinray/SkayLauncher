param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Target,
    [Parameter(Mandatory=$true)][string]$Backup,
    [Parameter(Mandatory=$true)][int]$LauncherPid
)

$ErrorActionPreference = "Stop"
while (Get-Process -Id $LauncherPid -ErrorAction SilentlyContinue) {
    Start-Sleep -Milliseconds 200
}

$parent = Split-Path -Parent $Target
if (-not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
Copy-Item -LiteralPath $Target -Destination $Backup -Force
Copy-Item -LiteralPath $Source -Destination $Target -Force
Remove-Item -LiteralPath $Source -Force -ErrorAction SilentlyContinue
Start-Process -FilePath $Target
