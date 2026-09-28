param(
    [string]$NcsRoot = 'D:\ncs\v3.4.0',
    [string]$ToolchainRoot = 'D:\ncs\toolchains\dcbdc366a1'
)

# Compile only; preserve the existing Week 1/2 build directories and DFU ZIPs.
$ErrorActionPreference = 'Continue'
$DeviceDir = Split-Path -Parent $PSScriptRoot
$paths = @($ToolchainRoot, (Join-Path $ToolchainRoot 'mingw64\bin'),
    (Join-Path $ToolchainRoot 'bin'), (Join-Path $ToolchainRoot 'opt\bin'),
    (Join-Path $ToolchainRoot 'opt\bin\Scripts'),
    (Join-Path $ToolchainRoot 'opt\zephyr-sdk\gnu\arm-zephyr-eabi\bin'))
$env:Path = ($paths -join ';') + ';' + $env:Path
$env:PYTHONPATH = "$(Join-Path $ToolchainRoot 'opt\bin');$(Join-Path $ToolchainRoot 'opt\bin\Lib');$(Join-Path $ToolchainRoot 'opt\bin\Lib\site-packages')"
$env:ZEPHYR_BASE = Join-Path $NcsRoot 'zephyr'
$env:ZEPHYR_TOOLCHAIN_VARIANT = 'zephyr/gnu'
$env:ZEPHYR_SDK_INSTALL_DIR = Join-Path $ToolchainRoot 'opt\zephyr-sdk'
$westExe = (Get-Command west -ErrorAction Stop).Source

foreach ($mode in @('active', 'idle')) {
    $buildDir = Join-Path $DeviceDir "build-$mode-check"
    $buildCommand = '"' + $westExe + '" build --no-sysbuild -p always -b "nrf52840dongle/nrf52840" -d "' +
        $buildDir + '" "' + $DeviceDir + '"'
    if ($mode -eq 'idle') {
        $config = (Join-Path $DeviceDir 'overlay-idle.conf') -replace '\\', '/'
        $buildCommand += ' -- "-DCONF_FILE=' + $config + '"'
    }
    $buildCommand += ' 2>&1'
    Push-Location $NcsRoot
    try {
        $output = & $env:ComSpec /d /s /c $buildCommand
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($code -ne 0) {
        $output | Select-Object -Last 80 | Write-Output
        throw "$mode regression build failed with exit code $code"
    }
    Write-Output "MODE ${mode}: PASS"
    $output | ForEach-Object { $_.ToString() } |
        Where-Object { $_ -match '^\s*(FLASH|RAM):' } | Write-Output
}
Write-Output 'RESULT: PASS (existing Active and Idle compile)'
