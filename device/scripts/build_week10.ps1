param(
    [Parameter(Mandatory=$true)][string]$ReportDir,
    [Parameter(Mandatory=$true)][ValidateSet('ble-usb','ble')][string]$Variant,
    [Parameter(Mandatory=$true)][string]$Samples,
    [Parameter(Mandatory=$true)][string]$Plan,
    [string]$NcsRoot='D:\ncs\v3.4.0',
    [string]$ToolchainRoot='D:\ncs\toolchains\dcbdc366a1'
)
# Week 10 firmware (device/week10, W10-D4/W10-D8): authenticate the R3 inputs (same SHA-256 as the
# week 4/5 evidence), the W8-D3 sample set ($Samples = generate_week8_samples.py output; its
# week8_inputs.h is copied into the build's generated directory) and the W10 plan directory ($Plan =
# generate_week10_plan.py output; week10_ble_plan.h copied likewise), write the build ID, build one
# variant (fast kernel, W7-D8; radio set = week7/overlay-radio.conf), static checks
# (check_week10_build.py), pkg generate/display. The prot variants (W10-D1) come with step 6.
# No device or serial access; DFU is a separate step (flash_week10.ps1).
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$AppDir = Join-Path $RepoRoot 'device\week10'
$HostPython = Join-Path $RepoRoot 'device\host\.venv\Scripts\python.exe'
$ReportDir = [IO.Path]::GetFullPath($ReportDir)
$Samples = [IO.Path]::GetFullPath($Samples)
$Plan = [IO.Path]::GetFullPath($Plan)
$BuildDir = Join-Path $ReportDir 'build'
$Zip = Join-Path $ReportDir ('adaptive_split_week10_' + $Variant + '.zip')
if ((Test-Path -LiteralPath $BuildDir) -or (Test-Path -LiteralPath $Zip)) {
    throw 'Use a fresh report/build directory; preserve all prior firmware'
}
foreach ($path in @($NcsRoot,$ToolchainRoot,$HostPython,$AppDir,$Samples,$Plan)) {
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
function Assert-Generated([string]$Dir, [string]$What, [string]$Field, [string]$Expected, $FileAnchors) {
    $manifest = Get-Content -LiteralPath (Join-Path $Dir 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.status -ne 'PASS' -or $manifest.$Field -ne $Expected) {
        throw "$What $Dir is not the PASS set $Expected"
    }
    foreach ($name in $FileAnchors.Keys) {
        $hash = (Get-FileHash -LiteralPath (Join-Path $Dir $name) -Algorithm SHA256).Hash.ToLower()
        if ($hash -ne $FileAnchors[$name] -or $hash -ne $manifest.outputs_sha256.$name) {
            throw "$What file $name SHA-256 $hash differs from its anchor or its manifest"
        }
    }
}
# W8-D3 set (samples-20261023-c, rounds use set_index 0..49) and the W10 plan directory
# (plan-20261112): deterministic generator outputs, so a regenerated directory gives the same bytes
# (week8_common.py / week10_common.py).
$SetSha256 = '7cfecbb213eb7226b30ac0872239806f8435c093451951be7c77d12f3cc31639'
$SampleAnchors = [ordered]@{
    'week8_inputs.h' = '4091e4613e0680aebd7c656c408311534a5645bf4ab30ef3faf0d7e896d41317'
    'samples.csv' = 'd77e8c662d03818f94c345c2c2f6d385c431768da20899b88ac54227857b5e20'
    'reference_s2.npz' = 'e7407378e7870afbfa94b850f809c85165a1d640673d1f01bbd32f6d1aab76d5'
}
$PlanSha256 = '27e20954494cdecdfaf45246cd00a16a5e113ef24e617b57e925a9783c415d33'
$PlanAnchors = [ordered]@{
    'ble_plan.csv' = 'b7b33815c7c2bcb90b5c3dcea89611a3a140e3710289b43098ce08419aa2293b'
    'week10_ble_plan.h' = 'bfe3d7165735f07da748f5a5b9b1e54afce3ffdd54d84560c46c207e807c5749'
}
Assert-Generated $Samples 'Sample set' 'set_sha256' $SetSha256 $SampleAnchors
$planManifest = Get-Content -LiteralPath (Join-Path $Plan 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($planManifest.status -ne 'PASS' -or $planManifest.ble.plan_sha256 -ne $PlanSha256) {
    throw "Plan $Plan is not the PASS W10-D4 plan $PlanSha256"
}
foreach ($name in $PlanAnchors.Keys) {
    $hash = (Get-FileHash -LiteralPath (Join-Path $Plan $name) -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $PlanAnchors[$name] -or $hash -ne $planManifest.outputs_sha256.$name) {
        throw "Plan file $name SHA-256 $hash differs from its anchor or its manifest"
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
    if ($code -ne 0) { throw "Week 10 build failed: $Name exit=$code" }
}
$gitExe = (Get-Command git -ErrorAction Stop).Source
$commit = (& $gitExe -C $RepoRoot rev-parse HEAD).Trim()
$porcelain = @(& $gitExe -C $RepoRoot status --porcelain --untracked-files=all)
$dirty = if ($porcelain.Count -gt 0) { '-dirty' } else { '' }
$stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$tag = $Variant
$buildId = $commit.Substring(0, 12) + $dirty + '-week10-' + $tag + '-' + $stamp
[ordered]@{ app='week10'; build_id=$buildId; commit=$commit; dirty=($dirty -ne ''); status_porcelain=$porcelain;
    variant=$Variant; kernel='fast'; r3_anchors=$Anchors; samples_dir=$Samples; set_sha256=$SetSha256;
    sample_anchors=$SampleAnchors; plan_dir=$Plan; plan_sha256=$PlanSha256; plan_anchors=$PlanAnchors } |
    ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $ReportDir 'source.json') -Encoding UTF8
$GeneratedDir = Join-Path $ReportDir 'generated'
New-Item -ItemType Directory -Path $GeneratedDir | Out-Null
$header = "/* GENERATED by device/scripts/build_week10.ps1 - do not edit. */`n#ifndef WEEK10_BUILD_H`n" +
    "#define WEEK10_BUILD_H`n#define WEEK10_BUILD_ID `"$buildId`"`n#define WEEK10_VARIANT `"$Variant`"`n#endif`n"
[IO.File]::WriteAllText((Join-Path $GeneratedDir 'week10_build.h'), $header, (New-Object Text.UTF8Encoding($false)))
foreach ($copy in @(@($Samples,'week8_inputs.h',$SampleAnchors['week8_inputs.h']), @($Plan,'week10_ble_plan.h',$PlanAnchors['week10_ble_plan.h']))) {
    Copy-Item -LiteralPath (Join-Path $copy[0] $copy[1]) -Destination $GeneratedDir
    $copied = (Get-FileHash -LiteralPath (Join-Path $GeneratedDir $copy[1]) -Algorithm SHA256).Hash.ToLower()
    if ($copied -ne $copy[2]) { throw "$($copy[1]) copy differs" }
}

$env:Path = (@($ToolchainRoot,(Join-Path $ToolchainRoot 'mingw64\bin'),(Join-Path $ToolchainRoot 'bin'),
    (Join-Path $ToolchainRoot 'opt\bin'),(Join-Path $ToolchainRoot 'opt\bin\Scripts'),
    (Join-Path $ToolchainRoot 'nrfutil\bin'),(Join-Path $ToolchainRoot 'opt\zephyr-sdk\gnu\arm-zephyr-eabi\bin')) -join ';') + ';' + $env:Path
$env:PYTHONPATH = (Join-Path $ToolchainRoot 'opt\bin') + ';' + (Join-Path $ToolchainRoot 'opt\bin\Lib') + ';' + (Join-Path $ToolchainRoot 'opt\bin\Lib\site-packages')
$env:ZEPHYR_BASE = Join-Path $NcsRoot 'zephyr'
$env:ZEPHYR_TOOLCHAIN_VARIANT = 'zephyr/gnu'
$env:ZEPHYR_SDK_INSTALL_DIR = Join-Path $ToolchainRoot 'opt\zephyr-sdk'
$westExe = (Get-Command west -ErrorAction Stop).Source
# Relative to APPLICATION_CONFIG_DIR = device/week10; prj.conf, overlay-radio.conf and app.overlay are
# week 7's (week10/CMakeLists.txt).
$radioConf = (Join-Path $RepoRoot 'device\week7\overlay-radio.conf') -replace '\\','/'
$cmakeArgs = @(('-DWEEK10_GENERATED_DIR=' + ($GeneratedDir -replace '\\','/')),
    "-DEXTRA_CONF_FILE=$radioConf;overlay-$Variant.conf", '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON')
Push-Location $NcsRoot
try {
    Invoke-Logged 'build' $westExe (@('build','--no-sysbuild','-b','nrf52840dongle/nrf52840','-d',$BuildDir,
        $AppDir,'--') + $cmakeArgs)
} finally { Pop-Location }
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
Invoke-Logged 'check' $HostPython @('-B',(Join-Path $PSScriptRoot 'check_week10_build.py'),'--build',$BuildDir,
    '--variant',$Variant,'--build-id',$buildId,'--set-sha256',$SetSha256,'--plan-sha256',$PlanSha256,
    '--output',(Join-Path $ReportDir 'week10_build_check.json'))
$nrfutilExe = Join-Path $ToolchainRoot 'nrfutil\bin\nrfutil.exe'
$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
    Invoke-Logged 'pkg-generate' $nrfutilExe @('nrf5sdk-tools','pkg','generate','--hw-version','52','--sd-req=0x00',
        '--application',(Join-Path $BuildDir 'zephyr\zephyr.hex'),'--application-version','10',$Zip)
    Invoke-Logged 'pkg-display' $nrfutilExe @('nrf5sdk-tools','pkg','display',$Zip)
} finally {
    if ($null -ne $savedNrfutilHome) { $env:NRFUTIL_HOME = $savedNrfutilHome }
}
Write-Output "BUILD AND STATIC CHECK COMPLETE ($tag): $ReportDir; build_id=$buildId; MCU=PENDING"
