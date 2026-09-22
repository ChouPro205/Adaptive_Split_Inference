param(
	[string]$NcsRoot = 'D:\ncs\v3.4.0',
	[string]$ToolchainRoot = 'D:\ncs\toolchains\dcbdc366a1'
)

# Build and package only. This script never flashes or accesses hardware.
$ErrorActionPreference = 'Continue'
$DeviceDir = Split-Path -Parent $PSScriptRoot
$BuildDir = Join-Path $DeviceDir 'build-idle'
$IdleConfPath = Join-Path $DeviceDir 'overlay-idle.conf'
$HexPath = Join-Path $BuildDir 'zephyr\zephyr.hex'
$ElfPath = Join-Path $BuildDir 'zephyr\zephyr.elf'
$ArtifactDir = Join-Path $DeviceDir 'artifacts'
$DfuZipPath = Join-Path $ArtifactDir 'adaptive_split_week2_idle.zip'
$BoardTarget = 'nrf52840dongle/nrf52840'

function Set-NcsEnvironment {
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
}

if (-not (Test-Path -LiteralPath $NcsRoot) -or
	-not (Test-Path -LiteralPath $ToolchainRoot)) {
	throw "NCS or toolchain not found: $NcsRoot ; $ToolchainRoot"
}
if (-not (Test-Path -LiteralPath $IdleConfPath)) {
	throw "Idle configuration not found: $IdleConfPath"
}

Set-NcsEnvironment
New-Item -ItemType Directory -Force -Path $ArtifactDir | Out-Null

Write-Output "Building pristine Idle target $BoardTarget ..."
Push-Location $NcsRoot
try {
	# Use CONF_FILE rather than EXTRA_CONF_FILE: Active-only USB and benchmark
	# settings in prj.conf must not leak into the idle-current measurement.
	$westExe = (Get-Command west -ErrorAction Stop).Source
	$confArgument = '-DCONF_FILE=' + ($IdleConfPath -replace '\\', '/')
	$buildCommand = '"' + $westExe + '" build --no-sysbuild -p always -b "' +
		$BoardTarget + '" -d "' + $BuildDir + '" "' + $DeviceDir +
		'" -- "' + $confArgument + '" 2>&1'
	$buildOutput = & $env:ComSpec /d /s /c $buildCommand
	$buildExitCode = $LASTEXITCODE
} finally {
	Pop-Location
}
$buildOutput | Write-Output
if ($buildExitCode -ne 0) {
	throw "West Idle build failed with exit code $buildExitCode."
}

foreach ($requiredFile in @($HexPath, $ElfPath)) {
	if (-not (Test-Path -LiteralPath $requiredFile)) {
		throw "Missing Idle build output: $requiredFile"
	}
}

if (Test-Path -LiteralPath $DfuZipPath) {
	Remove-Item -LiteralPath $DfuZipPath -Force
}

$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
	Write-Output 'Creating PCA10059 Idle USB DFU package ...'
	& nrfutil nrf5sdk-tools pkg generate --hw-version 52 --sd-req=0x00 `
		--application $HexPath --application-version 1 $DfuZipPath
	$packageExitCode = $LASTEXITCODE
	if ($packageExitCode -eq 0) {
		& nrfutil nrf5sdk-tools pkg display $DfuZipPath
		$displayExitCode = $LASTEXITCODE
	}
} finally {
	if ($null -ne $savedNrfutilHome) {
		$env:NRFUTIL_HOME = $savedNrfutilHome
	}
}
if ($packageExitCode -ne 0) {
	throw "Idle DFU package creation failed with exit code $packageExitCode."
}
if ($displayExitCode -ne 0) {
	throw "Idle DFU package validation failed with exit code $displayExitCode."
}
if (-not (Test-Path -LiteralPath $DfuZipPath)) {
	throw "nrfutil succeeded but the Idle DFU ZIP is missing: $DfuZipPath"
}

$hexHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $HexPath).Hash
$zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $DfuZipPath).Hash
Write-Output "HEX: $HexPath"
Write-Output "HEX SHA-256: $hexHash"
Write-Output "DFU ZIP: $DfuZipPath"
Write-Output "DFU ZIP SHA-256: $zipHash"
Write-Output 'RESULT: PASS (Idle build + validated DFU package)'
exit 0
