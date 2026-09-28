param(
    [string]$NcsRoot = 'D:\ncs\v3.4.0',
    [string]$ToolchainRoot = 'D:\ncs\toolchains\dcbdc366a1'
)

# Build and package only. Never flash from this script.
$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$DeviceDir = Join-Path $RepoRoot 'device'
$BuildDir = Join-Path $DeviceDir 'build-week3'
$HexPath = Join-Path $BuildDir 'zephyr\zephyr.hex'
$ElfPath = Join-Path $BuildDir 'zephyr\zephyr.elf'
$DfuZipPath = Join-Path $DeviceDir 'artifacts\adaptive_split_week3_fp32_v2.zip'
$BoardTarget = 'nrf52840dongle/nrf52840'
$MlPython = Join-Path $RepoRoot 'ml\.venv\Scripts\python.exe'
$HostScript = Join-Path $DeviceDir 'scripts\verify_week3_host.py'
$OverlayPath = Join-Path $DeviceDir 'overlay-week3.conf'

if (-not (Test-Path -LiteralPath $NcsRoot) -or -not (Test-Path -LiteralPath $ToolchainRoot)) {
    throw "NCS or toolchain not found: $NcsRoot ; $ToolchainRoot"
}
if (-not (Test-Path -LiteralPath $MlPython)) {
    throw "ML Python not found: $MlPython"
}

Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
& $MlPython -B $HostScript --repo-root $RepoRoot
if ($LASTEXITCODE -ne 0) { throw "Host sample 0 validation failed: $LASTEXITCODE" }

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

Write-Output "Building Week 3 FP32 target $BoardTarget ..."
Push-Location $NcsRoot
try {
    $westExe = (Get-Command west -ErrorAction Stop).Source
    $confArgument = '-DEXTRA_CONF_FILE=' + ($OverlayPath -replace '\\', '/')
    $buildCommand = '"' + $westExe + '" build --no-sysbuild -p always -b "' +
        $BoardTarget + '" -d "' + $BuildDir + '" "' + $DeviceDir +
        '" -- "' + $confArgument + '" 2>&1'
    $buildOutput = & $env:ComSpec /d /s /c $buildCommand
    $buildExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
$buildOutput | Write-Output
if ($buildExitCode -ne 0) { throw "West Week 3 build failed with exit code $buildExitCode" }

$memoryLines = @($buildOutput | ForEach-Object { $_.ToString() } |
    Where-Object { $_ -match '^\s*(FLASH|RAM):' })
if ($memoryLines.Count -lt 2) { throw 'Missing Zephyr FLASH/RAM linker report' }
Write-Output 'Authoritative Zephyr linker memory usage:'
$memoryLines | Write-Output
foreach ($path in @($HexPath, $ElfPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing build output: $path" }
}

$sizeTool = Join-Path $ToolchainRoot 'opt\zephyr-sdk\gnu\arm-zephyr-eabi\bin\arm-zephyr-eabi-size.exe'
$sizeOutput = & $sizeTool $ElfPath 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Unable to read Week 3 ELF size' }
$sizeOutput | Write-Output

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DfuZipPath) | Out-Null
if (Test-Path -LiteralPath $DfuZipPath) { Remove-Item -LiteralPath $DfuZipPath -Force }
$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
    & nrfutil nrf5sdk-tools pkg generate --hw-version 52 --sd-req=0x00 `
        --application $HexPath --application-version 1 $DfuZipPath
    $packageExitCode = $LASTEXITCODE
    if ($packageExitCode -eq 0) {
        & nrfutil nrf5sdk-tools pkg display $DfuZipPath
        $displayExitCode = $LASTEXITCODE
    }
} finally {
    if ($null -ne $savedNrfutilHome) { $env:NRFUTIL_HOME = $savedNrfutilHome }
}
if ($packageExitCode -ne 0 -or $displayExitCode -ne 0 -or
    -not (Test-Path -LiteralPath $DfuZipPath)) {
    throw 'Week 3 DFU ZIP creation or validation failed'
}
Write-Output "HEX SHA-256: $((Get-FileHash -Algorithm SHA256 -LiteralPath $HexPath).Hash)"
Write-Output "DFU ZIP SHA-256: $((Get-FileHash -Algorithm SHA256 -LiteralPath $DfuZipPath).Hash)"
Write-Output "DFU ZIP: $DfuZipPath"
Write-Output 'RESULT: PASS (Week 3 FP32 build + DFU package)'
exit 0
