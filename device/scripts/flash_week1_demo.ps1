param(
	[Parameter(Mandatory = $true)]
	[ValidatePattern('^(?i:COM)[0-9]+$')]
	[string]$Port,
	[string]$ToolchainRoot = 'D:\ncs\toolchains\dcbdc366a1'
)

$ErrorActionPreference = 'Stop'
$DeviceDir = Split-Path -Parent $PSScriptRoot
$DfuZipPath = Join-Path $DeviceDir 'artifacts\adaptive_split_week1_demo.zip'
$NrfutilDir = Join-Path $ToolchainRoot 'nrfutil\bin'

if (-not (Test-Path -LiteralPath $DfuZipPath)) {
	throw "DFU ZIP not found: $DfuZipPath. Run build_week1_demo.ps1 first."
}
if (-not (Test-Path -LiteralPath (Join-Path $NrfutilDir 'nrfutil.exe'))) {
	throw "nrfutil not found in $NrfutilDir"
}

$env:Path = "$NrfutilDir;$env:Path"
$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
	Write-Output "Flashing $DfuZipPath through bootloader port $Port ..."
	& nrfutil nrf5sdk-tools dfu usb-serial --package $DfuZipPath --port $Port
	$dfuExitCode = $LASTEXITCODE
} finally {
	if ($null -ne $savedNrfutilHome) {
		$env:NRFUTIL_HOME = $savedNrfutilHome
	}
}

if ($dfuExitCode -ne 0) {
	Write-Error "DFU failed (exit code $dfuExitCode)."
	exit $dfuExitCode
}

Write-Output 'DFU succeeded (exit code 0). Rediscover the firmware COM port.'
exit 0
