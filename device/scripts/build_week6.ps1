param(
    [Parameter(Mandatory=$true)][string]$ReportDir,
    [ValidateSet('default','mtu23')][string]$Variant = 'default',
    [string]$NcsRoot='D:\ncs\v3.4.0',
    [string]$ToolchainRoot='D:\ncs\toolchains\dcbdc366a1',
    [string]$Package='',
    # Trusted anchor from the SV3 handoff receipt (verified on the SV1 host 2026-10-17).
    [string]$ExpectedManifestSha256='d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36'
)
# Authenticate the SV3 P1 package + generate vector tables, build, static checks
# (Flash end before 0xDC000, ATT MTU), pkg generate/display.
# No device or serial access; DFU is a separate step.
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$AppDir = Join-Path $RepoRoot 'device\week6'
$MlPython = Join-Path $RepoRoot 'ml\.venv\Scripts\python.exe'
$ReportDir = [IO.Path]::GetFullPath($ReportDir)
$BuildDir = Join-Path $ReportDir 'build'
$Zip = Join-Path $ReportDir ('adaptive_split_week6_' + $Variant + '.zip')
if ((Test-Path -LiteralPath $BuildDir) -or (Test-Path -LiteralPath $Zip)) {
    throw 'Use a fresh report/build directory; preserve all prior firmware'
}
foreach ($path in @($NcsRoot,$ToolchainRoot,$MlPython,$AppDir)) {
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
    if ($code -ne 0) { throw "Week 6 build failed: $Name exit=$code" }
}
$env:Path = (@($ToolchainRoot,(Join-Path $ToolchainRoot 'mingw64\bin'),(Join-Path $ToolchainRoot 'bin'),
    (Join-Path $ToolchainRoot 'opt\bin'),(Join-Path $ToolchainRoot 'opt\bin\Scripts'),
    (Join-Path $ToolchainRoot 'nrfutil\bin'),(Join-Path $ToolchainRoot 'opt\zephyr-sdk\gnu\arm-zephyr-eabi\bin')) -join ';') + ';' + $env:Path
$env:PYTHONPATH = (Join-Path $ToolchainRoot 'opt\bin') + ';' + (Join-Path $ToolchainRoot 'opt\bin\Lib') + ';' + (Join-Path $ToolchainRoot 'opt\bin\Lib\site-packages')
$env:ZEPHYR_BASE = Join-Path $NcsRoot 'zephyr'
$env:ZEPHYR_TOOLCHAIN_VARIANT = 'zephyr/gnu'
$env:ZEPHYR_SDK_INSTALL_DIR = Join-Path $ToolchainRoot 'opt\zephyr-sdk'
$westExe = (Get-Command west -ErrorAction Stop).Source
# Build ID binds a CDC capture to this report directory (source commit, dirty flag, variant, time).
$gitExe = (Get-Command git -ErrorAction Stop).Source
$commit = (& $gitExe -C $RepoRoot rev-parse HEAD).Trim()
$porcelain = @(& $gitExe -C $RepoRoot status --porcelain --untracked-files=all)
$dirty = if ($porcelain.Count -gt 0) { '-dirty' } else { '' }
$stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$buildId = $commit.Substring(0, 12) + $dirty + '-' + $Variant + '-' + $stamp
[ordered]@{ build_id=$buildId; commit=$commit; dirty=($dirty -ne ''); status_porcelain=$porcelain;
    variant=$Variant; expected_manifest_sha256=$ExpectedManifestSha256 } |
    ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $ReportDir 'source.json') -Encoding UTF8
$GeneratedDir = Join-Path $ReportDir 'generated'
$generatorArgs = @('-B',(Join-Path $PSScriptRoot 'generate_week6_vectors.py'),
    '--expected-manifest-sha256',$ExpectedManifestSha256,'--build-id',$buildId,'--variant',$Variant,
    '--output',$GeneratedDir)
if ($Package -ne '') { $generatorArgs += @('--package',[IO.Path]::GetFullPath($Package)) }
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
Invoke-Logged 'generate' $MlPython $generatorArgs
$env:PYTHONPATH = (Join-Path $ToolchainRoot 'opt\bin') + ';' + (Join-Path $ToolchainRoot 'opt\bin\Lib') + ';' + (Join-Path $ToolchainRoot 'opt\bin\Lib\site-packages')
$cmakeArgs = @('-DWEEK6_GENERATED_DIR=' + ($GeneratedDir -replace '\\','/'))
if ($Variant -eq 'mtu23') { $cmakeArgs += '-DEXTRA_CONF_FILE=overlay-mtu23.conf' }
Push-Location $NcsRoot
try {
    Invoke-Logged 'build' $westExe (@('build','--no-sysbuild','-b','nrf52840dongle/nrf52840','-d',$BuildDir,
        $AppDir,'--') + $cmakeArgs)
} finally { Pop-Location }
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
Invoke-Logged 'check' $MlPython @('-B',(Join-Path $PSScriptRoot 'check_week6_build.py'),'--build',$BuildDir,
    '--variant',$Variant,'--build-id',$buildId,'--output',(Join-Path $ReportDir 'week6_build_check.json'))
$nrfutilExe = Join-Path $ToolchainRoot 'nrfutil\bin\nrfutil.exe'
$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
    Invoke-Logged 'pkg-generate' $nrfutilExe @('nrf5sdk-tools','pkg','generate','--hw-version','52','--sd-req=0x00',
        '--application',(Join-Path $BuildDir 'zephyr\zephyr.hex'),'--application-version','6',$Zip)
    Invoke-Logged 'pkg-display' $nrfutilExe @('nrf5sdk-tools','pkg','display',$Zip)
} finally {
    if ($null -ne $savedNrfutilHome) { $env:NRFUTIL_HOME = $savedNrfutilHome }
}
Write-Output "BUILD AND STATIC CHECK COMPLETE ($Variant): $ReportDir; build_id=$buildId; MCU=PENDING"
