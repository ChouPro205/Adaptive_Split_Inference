[CmdletBinding(DefaultParameterSetName='Build')]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^(?i:COM)[0-9]+$')][string]$Port,
    [Parameter(Mandatory=$true, ParameterSetName='Build')][string]$ReportDir,
    [Parameter(Mandatory=$true, ParameterSetName='Reference')][string]$Package,
    [Parameter(Mandatory=$true)][string]$ReceiptDir,
    [string]$ToolchainRoot='D:\ncs\toolchains\dcbdc366a1',
    [Parameter(ParameterSetName='Build')][switch]$AllowDirty
)
# DEVICE STEP: USB DFU of a build_week8.ps1 output whose static check PASSED, or (-Package) of a
# reference image ZIP from device/artifacts (week 1 Active / week 2 Idle for PPK2 session A).
# $Port must be the bootloader port (nRF52 SDFU USB, VID_1915&PID_521F), found right before use
# (press the dongle's RESET button; the red LED pulses). An image built from a dirty tree is
# refused unless -AllowDirty (bench/debug only, never the image of a PPK2 session, TC8).
$ErrorActionPreference = 'Stop'
if ($PSCmdlet.ParameterSetName -eq 'Build') {
    $ReportDir = [IO.Path]::GetFullPath($ReportDir)
    $check = Get-Content -LiteralPath (Join-Path $ReportDir 'week8_build_check.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($check.status -ne 'PASS') { throw 'Static build check is not PASS; no DFU attempted' }
    $source = Get-Content -LiteralPath (Join-Path $ReportDir 'source.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($source.dirty -and -not $AllowDirty) { throw "Image $($source.build_id) was built from a dirty tree" }
    $zip = Join-Path $ReportDir ('adaptive_split_week8_' + $check.variant + '_' + $check.kernel + '.zip')
    $variant = $check.variant; $kernel = $check.kernel; $buildId = $check.build_id; $dirty = $source.dirty
    $binSha = $check.bin_sha256; $elfSha = $check.elf_sha256; $setSha = $check.set_sha256
} else {
    $zip = [IO.Path]::GetFullPath($Package)
    $artifacts = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $PSScriptRoot) 'artifacts'))
    if (-not $zip.StartsWith($artifacts + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Reference packages come from $artifacts only"
    }
    $variant = 'reference-' + [IO.Path]::GetFileNameWithoutExtension($zip); $kernel = 'none'
    $buildId = $null; $dirty = $null; $binSha = $null; $elfSha = $null; $setSha = $null; $ReportDir = $null
}
if (-not (Test-Path -LiteralPath $zip)) { throw "DFU package missing: $zip" }
$nrfutilExe = Join-Path $ToolchainRoot 'nrfutil\bin\nrfutil.exe'
if (-not (Test-Path -LiteralPath $nrfutilExe)) { throw 'nrfutil unavailable' }
$stamp = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(7)).ToString('yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Path $ReceiptDir -Force | Out-Null
$name = "dfu-$stamp-" + $variant + '-' + $kernel
$receiptPath = Join-Path $ReceiptDir ($name + '.json')
$logPath = Join-Path $ReceiptDir ($name + '.log')
if ((Test-Path -LiteralPath $receiptPath) -or (Test-Path -LiteralPath $logPath)) { throw 'DFU receipt exists' }
$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
    $ErrorActionPreference = 'Continue'
    $arguments = @('nrf5sdk-tools','dfu','usb-serial','--package',$zip,'--port',$Port)
    $output = & $nrfutilExe @arguments 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    $output | Set-Content -LiteralPath $logPath -Encoding UTF8
    $output | Write-Output
    [ordered]@{ origin='REAL_USB_DFU'; port=$Port; variant=$variant; kernel=$kernel;
        build_id=$buildId; dirty=$dirty; report_dir=$ReportDir;
        zip=$zip; zip_sha256=(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower();
        bin_sha256=$binSha; elf_sha256=$elfSha; set_sha256=$setSha;
        executable=$nrfutilExe; arguments=$arguments; exit_code=$code;
        timestamp=[DateTimeOffset]::UtcNow.ToString('o') } |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
} finally { if ($null -ne $savedNrfutilHome) { $env:NRFUTIL_HOME = $savedNrfutilHome } }
if ($code -ne 0) { throw "USB DFU failed: exit=$code; log=$logPath" }
Write-Output "DFU completed ($variant/$kernel, $buildId); receipt=$receiptPath."
