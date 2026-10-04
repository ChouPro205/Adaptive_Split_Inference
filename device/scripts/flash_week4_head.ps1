param(
    [Parameter(Mandatory = $true)][ValidatePattern('^(?i:COM)[0-9]+$')][string]$Port,
    [string]$ToolchainRoot = 'D:\ncs\toolchains\dcbdc366a1',
    [string]$WorkDir = 'D:\HUST\SV3_week4_R3\mcu-week4-work'
)

# Explicit USB DFU application stage, separate from build and collector.
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$DfuZipPath = Join-Path $RepoRoot 'device\artifacts\adaptive_split_week4_r3_fp32.zip'
$NrfutilExe = Join-Path $ToolchainRoot 'nrfutil\bin\nrfutil.exe'
$Prepared = Get-Content -Raw -LiteralPath 'D:\HUST\SV3_week4_R3\firmware-build\preparation_summary.json' | ConvertFrom-Json
$Memory = Get-Content -Raw -LiteralPath 'D:\HUST\SV3_week4_R3\firmware-build\week4_memory.json' | ConvertFrom-Json
if (-not (Test-Path -LiteralPath $NrfutilExe)) { throw 'Existing nrfutil not found' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $DfuZipPath).Hash.ToLower() -ne $Prepared.dfu.sha256) {
    throw 'DFU ZIP differs from the inspected build'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Memory.elf).Hash.ToLower() -ne $Memory.elf_sha256) {
    throw 'ELF differs from memory inspection'
}
foreach ($source in @('device/CMakeLists.txt','device/Kconfig','device/overlay-week4.conf',
    'device/src/main_week4.c','device/src/week4_head.c','device/src/week4_head.h',
    'device/src/week4_protocol.c','device/src/week4_protocol.h')) {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $RepoRoot $source)).Hash.ToLower()
    if ($actual -ne $Prepared.source_sha256.$source) { throw "Firmware source differs from package: $source" }
}
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
$stamp = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(7)).ToString('yyyyMMdd-HHmmss')
$log = Join-Path $WorkDir ("dfu-$stamp.log")
$receiptPath = Join-Path $WorkDir ("dfu-$stamp.json")
$receipt = [ordered]@{
    timestamp = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(7)).ToString('o')
    port = $Port
    usb_bootloader = 'VID_1915 PID_521F'
    package = $DfuZipPath
    package_sha256 = $Prepared.dfu.sha256
    application_sha256 = $Prepared.dfu.application_sha256
    elf_sha256 = $Memory.elf_sha256
    source_sha256 = $Prepared.source_sha256
    week4_manifest_sha256 = '80e4cea3b70bdafef1b6925b208d4951a87bba4ff8cf10dbb6a671e36439635c'
    all_split_manifest_sha256 = 'a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6'
    command = "nrfutil nrf5sdk-tools dfu usb-serial --package $DfuZipPath --port $Port"
    exit_code = $null
}
$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
    # Native stderr can be progress output under Windows PowerShell 5.1.
    $ErrorActionPreference = 'Continue'
    $output = & $NrfutilExe nrf5sdk-tools dfu usb-serial --package $DfuZipPath --port $Port 2>&1
    $dfuExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    $output | Set-Content -Encoding UTF8 -LiteralPath $log
    $output | Write-Output
    $receipt.exit_code = $dfuExit
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $receiptPath
} finally {
    if ($null -ne $savedNrfutilHome) { $env:NRFUTIL_HOME = $savedNrfutilHome }
}
if ($dfuExit -ne 0) { throw "Week 4 USB DFU failed: $dfuExit; log=$log" }
Write-Output "DFU: PASS exit=0; receipt=$receiptPath"
Write-Output 'Rediscover the application CDC port before collecting.'
