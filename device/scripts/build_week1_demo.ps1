param(
	[string]$NcsRoot = 'D:\ncs\v3.4.0',
	[string]$ToolchainRoot = 'D:\ncs\toolchains\dcbdc366a1'
)

# Windows PowerShell 5 wraps native stderr as ErrorRecord. Keep it visible and
# use each native program's exit code as the authoritative result.
$ErrorActionPreference = 'Continue'
$DeviceDir = Split-Path -Parent $PSScriptRoot
$BuildDir = Join-Path $DeviceDir 'build'
$HexPath = Join-Path $BuildDir 'zephyr\zephyr.hex'
$ElfPath = Join-Path $BuildDir 'zephyr\zephyr.elf'
$ArtifactDir = Join-Path $DeviceDir 'artifacts'
$DfuZipPath = Join-Path $ArtifactDir 'adaptive_split_week1_demo.zip'
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

Set-NcsEnvironment
New-Item -ItemType Directory -Force -Path $ArtifactDir | Out-Null

Write-Output "Building pristine target $BoardTarget ..."
Push-Location $NcsRoot
try {
	# Route native stderr through cmd.exe so Windows PowerShell 5 does not
	# decorate ordinary West status lines as NativeCommandError records.
	$westExe = (Get-Command west -ErrorAction Stop).Source
	$buildCommand = '"' + $westExe + '" build --no-sysbuild -p always -b "' +
		$BoardTarget + '" -d "' + $BuildDir + '" "' + $DeviceDir + '" 2>&1'
	$buildOutput = & $env:ComSpec /d /s /c $buildCommand
	$buildExitCode = $LASTEXITCODE
} finally {
	Pop-Location
}
$buildOutput | Write-Output
if ($buildExitCode -ne 0) {
	throw "West build failed with exit code $buildExitCode."
}

$memoryLines = @($buildOutput | ForEach-Object { $_.ToString() } |
	Where-Object { $_ -match '^\s*(FLASH|RAM):' })
if ($memoryLines.Count -lt 2) {
	throw 'Unable to find the Zephyr linker FLASH/RAM report in build output.'
}
Write-Output 'Authoritative Zephyr linker memory usage:'
$memoryLines | Write-Output

foreach ($requiredFile in @($HexPath, $ElfPath)) {
	if (-not (Test-Path -LiteralPath $requiredFile)) {
		throw "Missing build output: $requiredFile"
	}
}

$sizeTool = Join-Path $ToolchainRoot 'opt\zephyr-sdk\gnu\arm-zephyr-eabi\bin\arm-zephyr-eabi-size.exe'
$sizeOutput = & $sizeTool $ElfPath 2>&1
$sizeExitCode = $LASTEXITCODE
$sizeOutput | Write-Output
if ($sizeExitCode -ne 0) {
	throw "Unable to read ELF size (exit code $sizeExitCode)."
}

$sizeLine = $sizeOutput | Select-Object -Last 1
$sizeFields = ($sizeLine.Trim() -split '\s+')
if ($sizeFields.Count -lt 3) {
	throw 'Unable to parse arm-zephyr-eabi-size output.'
}
$elfLoadBytes = [uint64]$sizeFields[0] + [uint64]$sizeFields[1]
$elfDataBssBytes = [uint64]$sizeFields[1] + [uint64]$sizeFields[2]
Write-Output "ELF text + data: $elfLoadBytes bytes"
Write-Output "ELF data + bss:  $elfDataBssBytes bytes"

if (Test-Path -LiteralPath $DfuZipPath) {
	Remove-Item -LiteralPath $DfuZipPath -Force
}

$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
	Write-Output 'Creating PCA10059 USB DFU package ...'
	& nrfutil nrf5sdk-tools pkg generate --hw-version 52 --sd-req=0x00 `
		--application $HexPath --application-version 1 $DfuZipPath
	$packageExitCode = $LASTEXITCODE
} finally {
	if ($null -ne $savedNrfutilHome) {
		$env:NRFUTIL_HOME = $savedNrfutilHome
	}
}
if ($packageExitCode -ne 0) {
	throw "DFU package creation failed with exit code $packageExitCode."
}
if (-not (Test-Path -LiteralPath $DfuZipPath)) {
	throw "nrfutil succeeded but the DFU ZIP is missing: $DfuZipPath"
}

$hexHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $HexPath).Hash
$zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $DfuZipPath).Hash
Write-Output "HEX: $HexPath"
Write-Output "HEX SHA-256: $hexHash"
Write-Output "DFU ZIP: $DfuZipPath"
Write-Output "DFU ZIP SHA-256: $zipHash"
Write-Output 'RESULT: PASS (build + DFU package)'
exit 0
