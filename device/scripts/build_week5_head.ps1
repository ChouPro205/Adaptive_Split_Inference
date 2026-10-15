param(
    [Parameter(Mandatory=$true)][string]$ReportDir,
    [string]$NcsRoot='D:\ncs\v3.4.0',
    [string]$ToolchainRoot='D:\ncs\toolchains\dcbdc366a1'
)
# Build + audit + pkg generate/display only. No device or serial access.
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$MlPython = Join-Path $RepoRoot 'ml\.venv\Scripts\python.exe'
$ReportDir = [IO.Path]::GetFullPath($ReportDir)
$BuildDir = Join-Path $ReportDir 'build'
if ((Test-Path -LiteralPath $BuildDir) -or (Test-Path -LiteralPath (Join-Path $ReportDir 'adaptive_split_week5.zip'))) {
    throw 'Use a fresh report/build directory; preserve all prior firmware'
}
foreach ($path in @($NcsRoot,$ToolchainRoot,$MlPython)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required environment missing: $path" }
}
New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null
function Invoke-Logged([string]$Name, [string]$Exe, [string[]]$Arguments) {
    $started = [DateTimeOffset]::UtcNow.ToString('o')
    $ErrorActionPreference = 'Continue'
    $output = & $Exe @Arguments 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    $output | Set-Content -LiteralPath (Join-Path $ReportDir ($Name + '.log')) -Encoding UTF8
    $output | Write-Output
    [ordered]@{ executable=$Exe; arguments=$Arguments; cwd=(Get-Location).Path; started_utc=$started;
        finished_utc=[DateTimeOffset]::UtcNow.ToString('o'); exit_code=$code } |
        ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $ReportDir ($Name + '.command.json')) -Encoding UTF8
    if ($code -ne 0) { throw "Preparation failed: $Name exit=$code" }
}
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
Invoke-Logged 'binding' $MlPython @('-B',(Join-Path $PSScriptRoot 'bind_week5_build.py'),'--output',(Join-Path $ReportDir 'generated'))
$env:Path = (@($ToolchainRoot,(Join-Path $ToolchainRoot 'mingw64\bin'),(Join-Path $ToolchainRoot 'bin'),
    (Join-Path $ToolchainRoot 'opt\bin'),(Join-Path $ToolchainRoot 'opt\bin\Scripts'),
    (Join-Path $ToolchainRoot 'nrfutil\bin'),(Join-Path $ToolchainRoot 'opt\zephyr-sdk\gnu\arm-zephyr-eabi\bin')) -join ';') + ';' + $env:Path
$env:PYTHONPATH = (Join-Path $ToolchainRoot 'opt\bin') + ';' + (Join-Path $ToolchainRoot 'opt\bin\Lib') + ';' + (Join-Path $ToolchainRoot 'opt\bin\Lib\site-packages')
$env:ZEPHYR_BASE = Join-Path $NcsRoot 'zephyr'
$env:ZEPHYR_TOOLCHAIN_VARIANT = 'zephyr/gnu'
$env:ZEPHYR_SDK_INSTALL_DIR = Join-Path $ToolchainRoot 'opt\zephyr-sdk'
$westExe = (Get-Command west -ErrorAction Stop).Source
Push-Location $NcsRoot
try {
    # Fresh directory: no pristine deletion or historical build writes.
    Invoke-Logged 'build' $westExe @('build','--no-sysbuild','-b','nrf52840dongle/nrf52840','-d',$BuildDir,
        (Join-Path $RepoRoot 'device\week5'),'--',
        ('-DWEEK5_GENERATED_DIR=' + ((Join-Path $ReportDir 'generated') -replace '\\','/')),
        '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON')
} finally { Pop-Location }
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
Invoke-Logged 'memory' $MlPython @('-B',(Join-Path $PSScriptRoot 'inspect_week5_memory.py'),'--build',$BuildDir,'--output',$ReportDir,'--toolchain',$ToolchainRoot)
$nrfutilExe = Join-Path $ToolchainRoot 'nrfutil\bin\nrfutil.exe'
$zip = Join-Path $ReportDir 'adaptive_split_week5.zip'
$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
    Invoke-Logged 'pkg-generate' $nrfutilExe @('nrf5sdk-tools','pkg','generate','--hw-version','52','--sd-req=0x00',
        '--application',(Join-Path $BuildDir 'zephyr\zephyr.hex'),'--application-version','5',$zip)
    Invoke-Logged 'pkg-display' $nrfutilExe @('nrf5sdk-tools','pkg','display',$zip)
} finally {
    if ($null -ne $savedNrfutilHome) { $env:NRFUTIL_HOME = $savedNrfutilHome }
}
Write-Output "BUILD AND PACKAGE COMPLETE: $ReportDir; MCU=PENDING"
