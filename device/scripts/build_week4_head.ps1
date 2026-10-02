param(
    [string]$NcsRoot = 'D:\ncs\v3.4.0',
    [string]$ToolchainRoot = 'D:\ncs\toolchains\dcbdc366a1',
    [string]$ReportDir = 'D:\HUST\SV3_week4_R3\firmware-build',
    [switch]$ReuseHostValidation,
    [switch]$PackageDfu
)

# Build, memory audit and optional package ONLY. Never flash or open a port.
$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$DeviceDir = Join-Path $RepoRoot 'device'
$BuildDir = Join-Path $DeviceDir 'build-week4'
$RegressionDir = Join-Path $DeviceDir 'build-week3-regression'
$MlPython = Join-Path $RepoRoot 'ml\.venv\Scripts\python.exe'
$BoardTarget = 'nrf52840dongle/nrf52840'
$OverlayPath = Join-Path $DeviceDir 'overlay-week4.conf'
$DfuZipPath = Join-Path $DeviceDir 'artifacts\adaptive_split_week4_r3_fp32.zip'
$HexPath = Join-Path $BuildDir 'zephyr\zephyr.hex'
$ElfPath = Join-Path $BuildDir 'zephyr\zephyr.elf'

foreach ($path in @($NcsRoot, $ToolchainRoot, $MlPython)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required environment missing: $path" }
}
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
if ($ReuseHostValidation) {
    & $MlPython -B (Join-Path $PSScriptRoot 'generate_week4_inputs.py') --repo-root $RepoRoot
    if ($LASTEXITCODE -ne 0) { throw 'R3 authentication failed' }
    $reportPath = Join-Path $ReportDir 'week4_host_validation.json'
    if (-not (Test-Path -LiteralPath $reportPath)) { throw 'Missing host verification report' }
    $hostReport = Get-Content -Raw -LiteralPath $reportPath | ConvertFrom-Json
    if ($hostReport.status -ne 'PASS' -or $hostReport.primary_tensors -ne 220 -or
        $hostReport.week4_manifest_sha256 -ne '80e4cea3b70bdafef1b6925b208d4951a87bba4ff8cf10dbb6a671e36439635c') {
        throw 'Host verification report is not accepted'
    }
    foreach ($entry in $hostReport.source_sha256.PSObject.Properties) {
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $RepoRoot $entry.Name)).Hash.ToLower()
        if ($actual -ne $entry.Value) { throw "Host verification is stale: $($entry.Name)" }
    }
    Write-Output 'HOST_C: reuse PASS for identical source/generated SHA-256'
} else {
    $hostOutput = & $MlPython -B (Join-Path $PSScriptRoot 'verify_week4_host.py') --repo-root $RepoRoot --report-dir $ReportDir 2>&1
    $hostExit = $LASTEXITCODE
    $hostOutput | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $ReportDir 'host.log')
    $hostOutput | Write-Output
    if ($hostExit -ne 0) { throw "Host C validation failed: $hostExit" }
}

$toolchainPaths = @(
    $ToolchainRoot,
    (Join-Path $ToolchainRoot 'mingw64\bin'),
    (Join-Path $ToolchainRoot 'bin'),
    (Join-Path $ToolchainRoot 'opt\bin'),
    (Join-Path $ToolchainRoot 'opt\bin\Scripts'),
    (Join-Path $ToolchainRoot 'nrfutil\bin'),
    (Join-Path $ToolchainRoot 'opt\zephyr-sdk\gnu\arm-zephyr-eabi\bin')
)
$env:Path = ($toolchainPaths -join ';') + ';' + $env:Path
$env:PYTHONPATH = "$(Join-Path $ToolchainRoot 'opt\bin');$(Join-Path $ToolchainRoot 'opt\bin\Lib');$(Join-Path $ToolchainRoot 'opt\bin\Lib\site-packages')"
$env:ZEPHYR_BASE = Join-Path $NcsRoot 'zephyr'
$env:ZEPHYR_TOOLCHAIN_VARIANT = 'zephyr/gnu'
$env:ZEPHYR_SDK_INSTALL_DIR = Join-Path $ToolchainRoot 'opt\zephyr-sdk'

function Build-Head([string]$TargetDir, [string]$Overlay, [string]$LogName) {
    # West pristine may remove its build directory. Verify the absolute target
    # stays inside device before letting West do so. No shell filesystem ops.
    $resolvedTarget = [System.IO.Path]::GetFullPath($TargetDir)
    $devicePrefix = [System.IO.Path]::GetFullPath($DeviceDir).TrimEnd('\') + '\'
    if (-not $resolvedTarget.StartsWith($devicePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Build directory must be inside device'
    }
    Push-Location $NcsRoot
    try {
        $westExe = (Get-Command west -ErrorAction Stop).Source
        $confArgument = '-DEXTRA_CONF_FILE=' + ($Overlay -replace '\\', '/')
        $buildCommand = '"' + $westExe + '" build --no-sysbuild -p always -b "' +
            $BoardTarget + '" -d "' + $TargetDir + '" "' + $DeviceDir +
            '" -- "' + $confArgument + '" 2>&1'
        $output = & $env:ComSpec /d /s /c $buildCommand
        $exitCode = $LASTEXITCODE
    } finally { Pop-Location }
    $output | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $ReportDir $LogName)
    $output | Write-Output
    "COMMAND: $buildCommand`nEXIT_CODE: $exitCode" | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $ReportDir ($LogName + '.command.txt'))
    if ($exitCode -ne 0) { throw "West build failed ($LogName), exit code $exitCode" }
}

Build-Head $BuildDir $OverlayPath 'build-week4.log'
# Shared CMake/Kconfig changed: compile the original Week 3 source separately.
# Preserve build-week3, accepted reports, generated headers and old DFU ZIP.
Build-Head $RegressionDir (Join-Path $DeviceDir 'overlay-week3.conf') 'build-week3-regression.log'
foreach ($path in @($HexPath, $ElfPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing build output: $path" }
}

# Return to ML Python's environment for artifact inspection, no ML gates.
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
$auditOutput = & $MlPython -B (Join-Path $PSScriptRoot 'inspect_week4_memory.py') --repo-root $RepoRoot --report-dir $ReportDir --toolchain-root $ToolchainRoot 2>&1
$auditExit = $LASTEXITCODE
$auditOutput | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $ReportDir 'memory.log')
$auditOutput | Write-Output
if ($auditExit -ne 0) { throw "Memory/partition audit failed: $auditExit" }

if ($PackageDfu) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DfuZipPath) | Out-Null
    if (Test-Path -LiteralPath $DfuZipPath) { throw "DFU ZIP already exists; retain it or choose a new filename: $DfuZipPath" }
    $savedNrfutilHome = $env:NRFUTIL_HOME
    Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
    try {
        $pkgOutput = & nrfutil nrf5sdk-tools pkg generate --hw-version 52 --sd-req=0x00 --application $HexPath --application-version 1 $DfuZipPath 2>&1
        $packageExit = $LASTEXITCODE
        $pkgOutput | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $ReportDir 'dfu-package.log')
        $pkgOutput | Write-Output
        if ($packageExit -ne 0) { throw "DFU packaging failed: $packageExit" }
        & nrfutil nrf5sdk-tools pkg display $DfuZipPath
        if ($LASTEXITCODE -ne 0) { throw 'DFU package display failed' }
    } finally {
        if ($null -ne $savedNrfutilHome) { $env:NRFUTIL_HOME = $savedNrfutilHome }
    }
    Write-Output "DFU ZIP SHA-256: $((Get-FileHash -Algorithm SHA256 -LiteralPath $DfuZipPath).Hash)"
    Write-Output "DFU ZIP: $DfuZipPath"
}
Write-Output "ELF: $ElfPath"
Write-Output 'RESULT: PASS (build + memory audit); MCU validation/timing PENDING'
exit 0
