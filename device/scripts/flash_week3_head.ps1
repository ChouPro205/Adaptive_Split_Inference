param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(?i:COM)[0-9]+$')]
    [string]$Port,
    [string]$ToolchainRoot = 'D:\ncs\toolchains\dcbdc366a1'
)

$ErrorActionPreference = 'Stop'
$DeviceDir = Split-Path -Parent $PSScriptRoot
$DfuZipPath = Join-Path $DeviceDir 'artifacts\adaptive_split_week3_fp32_v2.zip'
$NrfutilDir = Join-Path $ToolchainRoot 'nrfutil\bin'
if (-not (Test-Path -LiteralPath $DfuZipPath)) { throw "Week 3 DFU ZIP not found: $DfuZipPath" }
if (-not (Test-Path -LiteralPath (Join-Path $NrfutilDir 'nrfutil.exe'))) {
    throw "nrfutil not found in $NrfutilDir"
}
$env:Path = "$NrfutilDir;$env:Path"
$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
    Write-Output "Flashing Week 3 FP32 ZIP through bootloader port $Port ..."
    & nrfutil nrf5sdk-tools dfu usb-serial --package $DfuZipPath --port $Port
    $dfuExitCode = $LASTEXITCODE
} finally {
    if ($null -ne $savedNrfutilHome) { $env:NRFUTIL_HOME = $savedNrfutilHome }
}
if ($dfuExitCode -ne 0) { throw "Week 3 DFU failed with exit code $dfuExitCode" }
Write-Output 'DFU succeeded (exit code 0). Rediscover the application USB CDC port.'
