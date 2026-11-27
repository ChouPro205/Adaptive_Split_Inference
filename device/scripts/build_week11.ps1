param(
    [Parameter(Mandatory=$true)][string]$ReportDir,
    [Parameter(Mandatory=$true)][ValidateSet('link-usb','link')][string]$Variant,
    [Parameter(Mandatory=$true)][ValidateSet(0,1)][int]$Session,
    [Parameter(Mandatory=$true)][string]$Samples,
    [Parameter(Mandatory=$true)][string]$Plan,
    [string]$NcsRoot='D:\ncs\v3.4.0',
    [string]$ToolchainRoot='D:\ncs\toolchains\dcbdc366a1'
)
# Week 11 firmware (W11-D2/W11-D3): authenticate the W8-D3 sample set ($Samples = generate_week8_samples.py
# output; its week8_inputs.h is copied into the build's generated directory) and the week 11 plan directory
# ($Plan = generate_week11_plan.py output: manifest PASS, file hashes = manifest, and the generator regenerated
# into a temporary directory gives the same bytes), write the build ID, build one variant for one session
# (week11_link_plan_s<Session>.h -> week11_link_plan.h), static checks (check_week11_build.py), pkg
# generate/display.
#   link-usb, link   device/week11: week7/overlay-radio.conf + week11/overlay-link-radio.conf +
#                    week11/overlay-<variant>.conf
# No device or serial access; DFU is a separate step (flash_week11.ps1).
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$AppDir = Join-Path $RepoRoot 'device\week11'
$HostPython = Join-Path $RepoRoot 'device\host\.venv\Scripts\python.exe'
$ReportDir = [IO.Path]::GetFullPath($ReportDir)
$Samples = [IO.Path]::GetFullPath($Samples)
$Plan = [IO.Path]::GetFullPath($Plan)
$BuildDir = Join-Path $ReportDir 'build'
$Zip = Join-Path $ReportDir ('adaptive_split_week11_' + $Variant + '_s' + $Session + '.zip')
if ((Test-Path -LiteralPath $BuildDir) -or (Test-Path -LiteralPath $Zip)) {
    throw 'Use a fresh report/build directory; preserve all prior firmware'
}
foreach ($path in @($NcsRoot,$ToolchainRoot,$HostPython,$AppDir,$Samples,$Plan)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required environment missing: $path" }
}
# W8-D3 set (samples-20261023-c): the anchors of build_week10.ps1.
$SetSha256 = '7cfecbb213eb7226b30ac0872239806f8435c093451951be7c77d12f3cc31639'
$SampleAnchors = [ordered]@{
    'week8_inputs.h' = '4091e4613e0680aebd7c656c408311534a5645bf4ab30ef3faf0d7e896d41317'
    'samples.csv' = 'd77e8c662d03818f94c345c2c2f6d385c431768da20899b88ac54227857b5e20'
    'reference_s2.npz' = 'e7407378e7870afbfa94b850f809c85165a1d640673d1f01bbd32f6d1aab76d5'
}
$manifest = Get-Content -LiteralPath (Join-Path $Samples 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.status -ne 'PASS' -or $manifest.set_sha256 -ne $SetSha256) { throw "Sample set $Samples is not the PASS set $SetSha256" }
foreach ($name in $SampleAnchors.Keys) {
    $hash = (Get-FileHash -LiteralPath (Join-Path $Samples $name) -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $SampleAnchors[$name] -or $hash -ne $manifest.outputs_sha256.$name) {
        throw "Sample set file $name SHA-256 $hash differs from its anchor or its manifest"
    }
}
$PlanHeader = "week11_link_plan_s$Session.h"
$planManifest = Get-Content -LiteralPath (Join-Path $Plan 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($planManifest.status -ne 'PASS') { throw "Plan $Plan is not a PASS week 11 plan directory" }
$PlanSha256 = $planManifest.sessions."s$Session".plan_sha256
foreach ($name in @($PlanHeader, "link_plan_s$Session.csv")) {
    $hash = (Get-FileHash -LiteralPath (Join-Path $Plan $name) -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $planManifest.outputs_sha256.$name) { throw "Plan file $name SHA-256 $hash differs from its manifest" }
}
# The generator must give the same bytes again (deterministic plan, W11-D3).
$regen = Join-Path ([IO.Path]::GetTempPath()) ('week11_plan_regen_' + [Guid]::NewGuid().ToString('N'))
& $HostPython -B (Join-Path $PSScriptRoot 'generate_week11_plan.py') --output $regen | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Plan generator FAILED on regeneration' }
foreach ($name in @($PlanHeader, "link_plan_s$Session.csv", 'echo_vectors.json')) {
    $a = (Get-FileHash -LiteralPath (Join-Path $Plan $name) -Algorithm SHA256).Hash
    $b = (Get-FileHash -LiteralPath (Join-Path $regen $name) -Algorithm SHA256).Hash
    if ($a -ne $b) { throw "Plan file $name differs from a regenerated plan (generator or sources changed)" }
}
Remove-Item -LiteralPath $regen -Recurse -Force
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
    if ($code -ne 0) { throw "Week 11 build failed: $Name exit=$code" }
}
$gitExe = (Get-Command git -ErrorAction Stop).Source
$commit = (& $gitExe -C $RepoRoot rev-parse HEAD).Trim()
$porcelain = @(& $gitExe -C $RepoRoot status --porcelain --untracked-files=all)
$dirty = if ($porcelain.Count -gt 0) { '-dirty' } else { '' }
$stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$tag = $Variant + '-s' + $Session
$buildId = $commit.Substring(0, 12) + $dirty + '-week11-' + $tag + '-' + $stamp
[ordered]@{ app='week11'; build_id=$buildId; commit=$commit; dirty=($dirty -ne ''); status_porcelain=$porcelain;
    variant=$Variant; session=$Session; samples_dir=$Samples; set_sha256=$SetSha256; sample_anchors=$SampleAnchors;
    plan_dir=$Plan; plan_sha256=$PlanSha256; plan_outputs_sha256=$planManifest.outputs_sha256 } |
    ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $ReportDir 'source.json') -Encoding UTF8
$GeneratedDir = Join-Path $ReportDir 'generated'
New-Item -ItemType Directory -Path $GeneratedDir | Out-Null
$header = "/* GENERATED by device/scripts/build_week11.ps1 - do not edit. */`n#ifndef WEEK11_BUILD_H`n" +
    "#define WEEK11_BUILD_H`n#define WEEK11_BUILD_ID `"$buildId`"`n#define WEEK11_VARIANT `"$Variant`"`n" +
    "#define WEEK11_SESSION ${Session}U`n#endif`n"
[IO.File]::WriteAllText((Join-Path $GeneratedDir 'week11_build.h'), $header, (New-Object Text.UTF8Encoding($false)))
Copy-Item -LiteralPath (Join-Path $Samples 'week8_inputs.h') -Destination $GeneratedDir
Copy-Item -LiteralPath (Join-Path $Plan $PlanHeader) -Destination (Join-Path $GeneratedDir 'week11_link_plan.h')
foreach ($pair in @(@('week8_inputs.h', $SampleAnchors['week8_inputs.h']), @('week11_link_plan.h', $planManifest.outputs_sha256.$PlanHeader))) {
    $copied = (Get-FileHash -LiteralPath (Join-Path $GeneratedDir $pair[0]) -Algorithm SHA256).Hash.ToLower()
    if ($copied -ne $pair[1]) { throw "$($pair[0]) copy differs" }
}

$env:Path = (@($ToolchainRoot,(Join-Path $ToolchainRoot 'mingw64\bin'),(Join-Path $ToolchainRoot 'bin'),
    (Join-Path $ToolchainRoot 'opt\bin'),(Join-Path $ToolchainRoot 'opt\bin\Scripts'),
    (Join-Path $ToolchainRoot 'nrfutil\bin'),(Join-Path $ToolchainRoot 'opt\zephyr-sdk\gnu\arm-zephyr-eabi\bin')) -join ';') + ';' + $env:Path
$env:PYTHONPATH = (Join-Path $ToolchainRoot 'opt\bin') + ';' + (Join-Path $ToolchainRoot 'opt\bin\Lib') + ';' + (Join-Path $ToolchainRoot 'opt\bin\Lib\site-packages')
$env:ZEPHYR_BASE = Join-Path $NcsRoot 'zephyr'
$env:ZEPHYR_TOOLCHAIN_VARIANT = 'zephyr/gnu'
$env:ZEPHYR_SDK_INSTALL_DIR = Join-Path $ToolchainRoot 'opt\zephyr-sdk'
$westExe = (Get-Command west -ErrorAction Stop).Source
# Relative to APPLICATION_CONFIG_DIR = the app directory; prj.conf, app.overlay and overlay-radio.conf are week 7's.
$radioConf = (Join-Path $RepoRoot 'device\week7\overlay-radio.conf') -replace '\\','/'
$cmakeArgs = @(('-DWEEK11_GENERATED_DIR=' + ($GeneratedDir -replace '\\','/')),
    "-DEXTRA_CONF_FILE=$radioConf;overlay-link-radio.conf;overlay-$Variant.conf", '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON')
Push-Location $NcsRoot
try {
    Invoke-Logged 'build' $westExe (@('build','--no-sysbuild','-b','nrf52840dongle/nrf52840','-d',$BuildDir,
        $AppDir,'--') + $cmakeArgs)
} finally { Pop-Location }
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
Invoke-Logged 'check' $HostPython @('-B',(Join-Path $PSScriptRoot 'check_week11_build.py'),'--build',$BuildDir,
    '--variant',$Variant,'--session',"$Session",'--build-id',$buildId,'--set-sha256',$SetSha256,'--plan-sha256',$PlanSha256,
    '--output',(Join-Path $ReportDir 'week11_build_check.json'))
$nrfutilExe = Join-Path $ToolchainRoot 'nrfutil\bin\nrfutil.exe'
$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
    Invoke-Logged 'pkg-generate' $nrfutilExe @('nrf5sdk-tools','pkg','generate','--hw-version','52','--sd-req=0x00',
        '--application',(Join-Path $BuildDir 'zephyr\zephyr.hex'),'--application-version','11',$Zip)
    Invoke-Logged 'pkg-display' $nrfutilExe @('nrf5sdk-tools','pkg','display',$Zip)
} finally {
    if ($null -ne $savedNrfutilHome) { $env:NRFUTIL_HOME = $savedNrfutilHome }
}
Write-Output "BUILD AND STATIC CHECK COMPLETE ($tag): $ReportDir; build_id=$buildId; MCU=PENDING"
