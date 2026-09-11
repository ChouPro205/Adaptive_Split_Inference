param(
	[string]$NcsRoot = 'D:\ncs\v3.4.0',
	[string]$ToolchainRoot = 'D:\ncs\toolchains\dcbdc366a1'
)

$ErrorActionPreference = 'Continue'
$script:Failed = 0

function Write-Check {
	param(
		[bool]$Passed,
		[string]$Name,
		[string]$Detail
	)

	if ($Passed) {
		Write-Output "[PASS] $Name - $Detail"
	} else {
		Write-Output "[FAIL] $Name - $Detail"
		$script:Failed++
	}
}

function Test-Tool {
	param(
		[string]$Name,
		[string[]]$VersionArgs = @('--version')
	)

	$command = Get-Command $Name -ErrorAction SilentlyContinue
	if (-not $command) {
		Write-Check $false $Name 'Not found in PATH.'
		return
	}

	$output = (& $command.Source @VersionArgs 2>&1 | Out-String).Trim()
	Write-Check ($LASTEXITCODE -eq 0) $Name "$($command.Source); $($output -split "`r?`n" | Select-Object -First 1)"
}

if ((Test-Path -LiteralPath $NcsRoot) -and (Test-Path -LiteralPath $ToolchainRoot)) {
	$toolchainPaths = @(
		$ToolchainRoot,
		(Join-Path $ToolchainRoot 'mingw64\bin'),
		(Join-Path $ToolchainRoot 'bin'),
		(Join-Path $ToolchainRoot 'opt\bin'),
		(Join-Path $ToolchainRoot 'opt\bin\Scripts'),
		(Join-Path $ToolchainRoot 'opt\nanopb\generator-bin'),
		(Join-Path $ToolchainRoot 'nrfutil\bin'),
		(Join-Path $ToolchainRoot 'opt\zephyr-sdk\gnu\arm-zephyr-eabi\bin')
	)
	$env:Path = ($toolchainPaths -join ';') + ';' + $env:Path
	$env:PYTHONPATH = "$(Join-Path $ToolchainRoot 'opt\bin');$(Join-Path $ToolchainRoot 'opt\bin\Lib');$(Join-Path $ToolchainRoot 'opt\bin\Lib\site-packages')"
	$env:ZEPHYR_BASE = Join-Path $NcsRoot 'zephyr'
	$env:ZEPHYR_TOOLCHAIN_VARIANT = 'zephyr/gnu'
	$env:ZEPHYR_SDK_INSTALL_DIR = Join-Path $ToolchainRoot 'opt\zephyr-sdk'
	Write-Check $true 'NCS root' $NcsRoot
} else {
	Write-Check $false 'NCS root' "Missing $NcsRoot or $ToolchainRoot."
}

Test-Tool 'west'
Test-Tool 'cmake'
Test-Tool 'ninja'
Test-Tool 'arm-zephyr-eabi-gcc'
Test-Tool 'python'
Test-Tool 'git'

$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
Test-Tool 'nrfutil'

$nrf5Help = (& nrfutil nrf5sdk-tools --help 2>&1 | Out-String)
$nrf5Ok = ($LASTEXITCODE -eq 0) -and ($nrf5Help -match '(?m)^\s*pkg\s') -and ($nrf5Help -match '(?m)^\s*dfu\s')
Write-Check $nrf5Ok 'nrf5sdk-tools' 'Command provides pkg and dfu.'

if ($null -ne $savedNrfutilHome) {
	$env:NRFUTIL_HOME = $savedNrfutilHome
}

if (Get-Command west -ErrorAction SilentlyContinue) {
	Push-Location $NcsRoot
	$boardOutput = (& west boards -f '{name}|{qualifiers}' 2>&1 | Out-String)
	$boardFile = Join-Path $env:ZEPHYR_BASE 'boards\nordic\nrf52840dongle\nrf52840dongle_nrf52840_defconfig'
	$dongleLine = $boardOutput -split "`r?`n" | Where-Object { $_ -like 'nrf52840dongle|*' } | Select-Object -First 1
	$qualifiers = if ($dongleLine) { (($dongleLine -split '\|', 2)[1]) -split ',' } else { @() }
	$boardOk = ($LASTEXITCODE -eq 0) -and ($qualifiers -contains 'nrf52840') -and (Test-Path -LiteralPath $boardFile)
	Write-Check $boardOk 'Board target' 'nrf52840dongle/nrf52840 (not /bare).'
	Pop-Location
} else {
	Write-Check $false 'Board target' 'Unable to run west boards.'
}

$pythonChecks = @(
	@('pyserial', "import serial; print(serial.__version__)"),
	@('numpy', "import numpy; print(numpy.__version__)"),
	@('ppk2-api', "from ppk2_api.ppk2_api import PPK2_API; import importlib.metadata as m; print(m.version('ppk2-api'))")
)

foreach ($check in $pythonChecks) {
	$output = (& python -c $check[1] 2>&1 | Out-String).Trim()
	Write-Check ($LASTEXITCODE -eq 0) "Python package $($check[0])" $output
}

if ($script:Failed -eq 0) {
	Write-Output 'RESULT: PASS'
	exit 0
}

Write-Output "RESULT: FAIL ($script:Failed failed checks)"
exit 1
