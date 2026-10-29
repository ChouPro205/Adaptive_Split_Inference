param(
    [Parameter(Mandatory=$true)][string]$ReportDir,
    [Parameter(Mandatory=$true)][ValidateSet('dev-usb','dev')][string]$Variant,
    [Parameter(Mandatory=$true)][string]$Samples,
    [Parameter(Mandatory=$true)][string]$Plan,
    [ValidateSet('board','reg0-ldo','reg1-ldo')][string]$Regulator='board',
    [string]$NcsRoot='D:\ncs\v3.4.0',
    [string]$ToolchainRoot='D:\ncs\toolchains\dcbdc366a1'
)
# Week 9 firmware (device/week9, W9-D4/W9-D5): authenticate the R3 inputs (same SHA-256 as the
# week 4/5 evidence), the W8-D3 sample set ($Samples = generate_week8_samples.py output; its
# week8_inputs.h is copied into the build's generated directory) and the W9-D4 plan ($Plan =
# generate_week9_plan.py output; week9_plan.h copied likewise), write the build ID, build one
# variant (fast kernel, W7-D8), static checks (check_week9_build.py), pkg generate/display.
# -Regulator reg0-ldo|reg1-ldo (regulator experiment of 29/10, dev only): week9/overlay-<mode>.overlay
# puts REG0 or REG1 in LDO mode; the board default (both DC/DC) is 'board'.
# No device or serial access; DFU is a separate step (flash_week9.ps1).
$ErrorActionPreference = 'Stop'
if ($Regulator -ne 'board' -and $Variant -ne 'dev') { throw 'Regulator experiments use the dev variant' }
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$AppDir = Join-Path $RepoRoot 'device\week9'
$HostPython = Join-Path $RepoRoot 'device\host\.venv\Scripts\python.exe'
$ReportDir = [IO.Path]::GetFullPath($ReportDir)
$Samples = [IO.Path]::GetFullPath($Samples)
$Plan = [IO.Path]::GetFullPath($Plan)
$BuildDir = Join-Path $ReportDir 'build'
$Zip = Join-Path $ReportDir ('adaptive_split_week9_' + $Variant + '.zip')
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
# W8-D3 set (samples-20261023-c, W9-D3 uses set_index 0..49) and W9-D4 plan: deterministic
# generator outputs, so a regenerated directory must give the same bytes (week8/week9_common.py).
$SetSha256 = '7cfecbb213eb7226b30ac0872239806f8435c093451951be7c77d12f3cc31639'
$SampleAnchors = [ordered]@{
    'week8_inputs.h' = '4091e4613e0680aebd7c656c408311534a5645bf4ab30ef3faf0d7e896d41317'
    'samples.csv' = 'd77e8c662d03818f94c345c2c2f6d385c431768da20899b88ac54227857b5e20'
    'reference_s2.npz' = 'e7407378e7870afbfa94b850f809c85165a1d640673d1f01bbd32f6d1aab76d5'
}
$PlanSha256 = '5b1fcfe85b7057f5ea4ef52db4b6b3aa1b819a07d5af7a3c55bdb985f6eb4a9f'
$PlanAnchors = [ordered]@{
    'plan.csv' = 'dc12ee727d9df7bf6548345f6c61dd6afdbde9a2a68146a89dfcb2c95dbafa8f'
    'week9_plan.h' = '5652a76a367ee357b043f900b2cff18193bb1d65c2e224c03b83e7aa5c14706e'
}
Assert-Generated $Samples 'Sample set' 'set_sha256' $SetSha256 $SampleAnchors
Assert-Generated $Plan 'Plan' 'plan_sha256' $PlanSha256 $PlanAnchors
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
    if ($code -ne 0) { throw "Week 9 build failed: $Name exit=$code" }
}
$gitExe = (Get-Command git -ErrorAction Stop).Source
$commit = (& $gitExe -C $RepoRoot rev-parse HEAD).Trim()
$porcelain = @(& $gitExe -C $RepoRoot status --porcelain --untracked-files=all)
$dirty = if ($porcelain.Count -gt 0) { '-dirty' } else { '' }
$stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$tag = if ($Regulator -eq 'board') { $Variant } else { $Variant + '-' + $Regulator }
$buildId = $commit.Substring(0, 12) + $dirty + '-week9-' + $tag + '-' + $stamp
[ordered]@{ app='week9'; build_id=$buildId; commit=$commit; dirty=($dirty -ne ''); status_porcelain=$porcelain;
    variant=$Variant; regulator=$Regulator; kernel='fast'; r3_anchors=$Anchors; samples_dir=$Samples; set_sha256=$SetSha256;
    sample_anchors=$SampleAnchors; plan_dir=$Plan; plan_sha256=$PlanSha256; plan_anchors=$PlanAnchors } |
    ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $ReportDir 'source.json') -Encoding UTF8
$GeneratedDir = Join-Path $ReportDir 'generated'
New-Item -ItemType Directory -Path $GeneratedDir | Out-Null
$header = "/* GENERATED by device/scripts/build_week9.ps1 - do not edit. */`n#ifndef WEEK9_BUILD_H`n" +
    "#define WEEK9_BUILD_H`n#define WEEK9_BUILD_ID `"$buildId`"`n#define WEEK9_VARIANT `"$Variant`"`n#endif`n"
[IO.File]::WriteAllText((Join-Path $GeneratedDir 'week9_build.h'), $header, (New-Object Text.UTF8Encoding($false)))
foreach ($copy in @(@($Samples,'week8_inputs.h',$SampleAnchors['week8_inputs.h']), @($Plan,'week9_plan.h',$PlanAnchors['week9_plan.h']))) {
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
# Relative to APPLICATION_CONFIG_DIR = device/week9; prj.conf and app.overlay come from week7
# (week9/CMakeLists.txt).
$cmakeArgs = @(('-DWEEK9_GENERATED_DIR=' + ($GeneratedDir -replace '\\','/')), "-DEXTRA_CONF_FILE=overlay-$Variant.conf",
    '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON')
if ($Regulator -ne 'board') { $cmakeArgs += "-DEXTRA_DTC_OVERLAY_FILE=overlay-$Regulator.overlay" }
Push-Location $NcsRoot
try {
    Invoke-Logged 'build' $westExe (@('build','--no-sysbuild','-b','nrf52840dongle/nrf52840','-d',$BuildDir,
        $AppDir,'--') + $cmakeArgs)
} finally { Pop-Location }
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
Invoke-Logged 'check' $HostPython @('-B',(Join-Path $PSScriptRoot 'check_week9_build.py'),'--build',$BuildDir,
    '--variant',$Variant,'--build-id',$buildId,'--set-sha256',$SetSha256,'--plan-sha256',$PlanSha256,
    '--regulator',$Regulator,'--output',(Join-Path $ReportDir 'week9_build_check.json'))
$nrfutilExe = Join-Path $ToolchainRoot 'nrfutil\bin\nrfutil.exe'
$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
    Invoke-Logged 'pkg-generate' $nrfutilExe @('nrf5sdk-tools','pkg','generate','--hw-version','52','--sd-req=0x00',
        '--application',(Join-Path $BuildDir 'zephyr\zephyr.hex'),'--application-version','9',$Zip)
    Invoke-Logged 'pkg-display' $nrfutilExe @('nrf5sdk-tools','pkg','display',$Zip)
} finally {
    if ($null -ne $savedNrfutilHome) { $env:NRFUTIL_HOME = $savedNrfutilHome }
}
Write-Output "BUILD AND STATIC CHECK COMPLETE ($tag): $ReportDir; build_id=$buildId; MCU=PENDING"
