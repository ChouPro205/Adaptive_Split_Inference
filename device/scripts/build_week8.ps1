param(
    [Parameter(Mandatory=$true)][string]$ReportDir,
    [Parameter(Mandatory=$true)][ValidateSet('energy-usb','energy')][string]$Variant,
    [Parameter(Mandatory=$true)][string]$Samples,
    [ValidateSet('fast','week4')][string]$Kernel = 'fast',
    [string]$NcsRoot='D:\ncs\v3.4.0',
    [string]$ToolchainRoot='D:\ncs\toolchains\dcbdc366a1'
)
# Week 8 firmware (device/week8, W8-D2 + W8-D6): authenticate the R3 inputs (same SHA-256 as the
# week 4/5 evidence) and the W8-D3 sample set ($Samples = an output directory of
# generate_week8_samples.py; its week8_inputs.h is copied into the build's generated directory),
# write the build ID, build one radio variant, static checks (check_week8_build.py),
# pkg generate/display. No device or serial access; DFU is a separate step (flash_week8.ps1).
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$AppDir = Join-Path $RepoRoot 'device\week8'
$HostPython = Join-Path $RepoRoot 'device\host\.venv\Scripts\python.exe'
$ReportDir = [IO.Path]::GetFullPath($ReportDir)
$Samples = [IO.Path]::GetFullPath($Samples)
$BuildDir = Join-Path $ReportDir 'build'
$Zip = Join-Path $ReportDir ('adaptive_split_week8_' + $Variant + '_' + $Kernel + '.zip')
if ((Test-Path -LiteralPath $BuildDir) -or (Test-Path -LiteralPath $Zip)) {
    throw 'Use a fresh report/build directory; preserve all prior firmware'
}
foreach ($path in @($NcsRoot,$ToolchainRoot,$HostPython,$AppDir,$Samples)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required environment missing: $path" }
}
# Trust anchors: identical to results/week4/week4_mcu_validation.json and results/week5.
$Anchors = [ordered]@{
    'ml/results/week4-r3/firmware/head_parameters.h' = '3f811758ca6fc6a8fdefa74ff50ccb48031c006e9a12b617604dad033657487b'
    'device/generated/week4_graph.h' = 'b91b5cd664cae32f03e49b91669bb337fbea950c575d2b0a0da8959818d37b6c'
    'device/generated/week4_inputs.h' = '82a752cff0ef1ae5ed1c8d8bd596f89163e4af3c1a0c3bbac14f6cff262178c6'
}
foreach ($rel in $Anchors.Keys) {
    $file = Join-Path $RepoRoot $rel
    if (-not (Test-Path -LiteralPath $file)) { throw "Missing R3 input $rel (build_week4_head.ps1 generates it)" }
    $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $Anchors[$rel]) { throw "R3 input $rel SHA-256 $hash differs from the week 4/5 anchor" }
}
# W8-D3 set (amended 23/10, samples-20261023-c): deterministic generator output, so a regenerated
# directory must give the same bytes. The manifest is checked for status and its own hashes.
$SetSha256 = '7cfecbb213eb7226b30ac0872239806f8435c093451951be7c77d12f3cc31639'
$SampleAnchors = [ordered]@{
    'week8_inputs.h' = '4091e4613e0680aebd7c656c408311534a5645bf4ab30ef3faf0d7e896d41317'
    'samples.csv' = 'd77e8c662d03818f94c345c2c2f6d385c431768da20899b88ac54227857b5e20'
    'reference_s2.npz' = 'e7407378e7870afbfa94b850f809c85165a1d640673d1f01bbd32f6d1aab76d5'
}
$manifest = Get-Content -LiteralPath (Join-Path $Samples 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.status -ne 'PASS' -or $manifest.set_sha256 -ne $SetSha256) {
    throw "Sample set $Samples is not the PASS W8-D3 set $SetSha256"
}
foreach ($name in $SampleAnchors.Keys) {
    $hash = (Get-FileHash -LiteralPath (Join-Path $Samples $name) -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $SampleAnchors[$name] -or $hash -ne $manifest.outputs_sha256.$name) {
        throw "Sample file $name SHA-256 $hash differs from the W8-D3 anchor or its manifest"
    }
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
    if ($code -ne 0) { throw "Week 8 build failed: $Name exit=$code" }
}
$gitExe = (Get-Command git -ErrorAction Stop).Source
$commit = (& $gitExe -C $RepoRoot rev-parse HEAD).Trim()
$porcelain = @(& $gitExe -C $RepoRoot status --porcelain --untracked-files=all)
$dirty = if ($porcelain.Count -gt 0) { '-dirty' } else { '' }
$stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$buildId = $commit.Substring(0, 12) + $dirty + '-week8-' + $Variant + '-' + $Kernel + '-' + $stamp
[ordered]@{ app='week8'; build_id=$buildId; commit=$commit; dirty=($dirty -ne ''); status_porcelain=$porcelain;
    variant=$Variant; kernel=$Kernel; r3_anchors=$Anchors; samples_dir=$Samples; set_sha256=$SetSha256;
    sample_anchors=$SampleAnchors } |
    ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $ReportDir 'source.json') -Encoding UTF8
$GeneratedDir = Join-Path $ReportDir 'generated'
New-Item -ItemType Directory -Path $GeneratedDir | Out-Null
$header = "/* GENERATED by device/scripts/build_week8.ps1 - do not edit. */`n#ifndef WEEK8_BUILD_H`n" +
    "#define WEEK8_BUILD_H`n#define WEEK8_BUILD_ID `"$buildId`"`n#define WEEK8_VARIANT `"$Variant`"`n#endif`n"
[IO.File]::WriteAllText((Join-Path $GeneratedDir 'week8_build.h'), $header, (New-Object Text.UTF8Encoding($false)))
Copy-Item -LiteralPath (Join-Path $Samples 'week8_inputs.h') -Destination $GeneratedDir
$copied = (Get-FileHash -LiteralPath (Join-Path $GeneratedDir 'week8_inputs.h') -Algorithm SHA256).Hash.ToLower()
if ($copied -ne $SampleAnchors['week8_inputs.h']) { throw 'week8_inputs.h copy differs' }

$env:Path = (@($ToolchainRoot,(Join-Path $ToolchainRoot 'mingw64\bin'),(Join-Path $ToolchainRoot 'bin'),
    (Join-Path $ToolchainRoot 'opt\bin'),(Join-Path $ToolchainRoot 'opt\bin\Scripts'),
    (Join-Path $ToolchainRoot 'nrfutil\bin'),(Join-Path $ToolchainRoot 'opt\zephyr-sdk\gnu\arm-zephyr-eabi\bin')) -join ';') + ';' + $env:Path
$env:PYTHONPATH = (Join-Path $ToolchainRoot 'opt\bin') + ';' + (Join-Path $ToolchainRoot 'opt\bin\Lib') + ';' + (Join-Path $ToolchainRoot 'opt\bin\Lib\site-packages')
$env:ZEPHYR_BASE = Join-Path $NcsRoot 'zephyr'
$env:ZEPHYR_TOOLCHAIN_VARIANT = 'zephyr/gnu'
$env:ZEPHYR_SDK_INSTALL_DIR = Join-Path $ToolchainRoot 'opt\zephyr-sdk'
$westExe = (Get-Command west -ErrorAction Stop).Source
# Relative to APPLICATION_CONFIG_DIR = device/week7 (set in week8/CMakeLists.txt).
$extra = switch ($Variant) {
    'energy-usb' { 'overlay-radio.conf;overlay-energy-usb.conf' }
    'energy' { 'overlay-radio.conf;overlay-energy.conf' }
}
$cmakeArgs = @(('-DWEEK8_GENERATED_DIR=' + ($GeneratedDir -replace '\\','/')), "-DEXTRA_CONF_FILE=$extra",
    '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON')
if ($Kernel -eq 'week4') { $cmakeArgs += '-DCONFIG_WEEK7_KERNEL_WEEK4=y' }
Push-Location $NcsRoot
try {
    Invoke-Logged 'build' $westExe (@('build','--no-sysbuild','-b','nrf52840dongle/nrf52840','-d',$BuildDir,
        $AppDir,'--') + $cmakeArgs)
} finally { Pop-Location }
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
Invoke-Logged 'check' $HostPython @('-B',(Join-Path $PSScriptRoot 'check_week8_build.py'),'--build',$BuildDir,
    '--variant',$Variant,'--kernel',$Kernel,'--build-id',$buildId,'--set-sha256',$SetSha256,
    '--output',(Join-Path $ReportDir 'week8_build_check.json'))
$nrfutilExe = Join-Path $ToolchainRoot 'nrfutil\bin\nrfutil.exe'
$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
    Invoke-Logged 'pkg-generate' $nrfutilExe @('nrf5sdk-tools','pkg','generate','--hw-version','52','--sd-req=0x00',
        '--application',(Join-Path $BuildDir 'zephyr\zephyr.hex'),'--application-version','8',$Zip)
    Invoke-Logged 'pkg-display' $nrfutilExe @('nrf5sdk-tools','pkg','display',$Zip)
} finally {
    if ($null -ne $savedNrfutilHome) { $env:NRFUTIL_HOME = $savedNrfutilHome }
}
Write-Output "BUILD AND STATIC CHECK COMPLETE ($Variant/$Kernel): $ReportDir; build_id=$buildId; MCU=PENDING"
