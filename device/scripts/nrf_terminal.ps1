$ErrorActionPreference = 'Stop'

$NcsRoot = 'D:\ncs\v3.4.0'
$ToolchainRoot = 'D:\ncs\toolchains\dcbdc366a1'
$EspressifRoot = 'D:\HUST\esp\Espressif'
$WorkspaceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path -LiteralPath $NcsRoot)) {
	throw "NCS root not found: $NcsRoot"
}
if (-not (Test-Path -LiteralPath $ToolchainRoot)) {
	throw "NCS toolchain not found: $ToolchainRoot"
}

# Remove ESP-IDF state inherited from VS Code, then put the selected NCS
# toolchain first. This affects only this terminal process.
foreach ($variableName in @(
	'IDF_PATH',
	'IDF_TOOLS_PATH',
	'IDF_PYTHON_ENV_PATH',
	'ESP_IDF_VERSION',
	'OPENOCD_SCRIPTS',
	'PYTHONHOME'
)) {
	Remove-Item -LiteralPath "Env:$variableName" -ErrorAction SilentlyContinue
}

$existingPaths = @($env:Path -split ';' | Where-Object {
	$_ -and -not $_.StartsWith(
		$EspressifRoot,
		[System.StringComparison]::OrdinalIgnoreCase
	)
})
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

$env:Path = (@($toolchainPaths) + $existingPaths | Select-Object -Unique) -join ';'
$env:PYTHONPATH = @(
	(Join-Path $ToolchainRoot 'opt\bin'),
	(Join-Path $ToolchainRoot 'opt\bin\Lib'),
	(Join-Path $ToolchainRoot 'opt\bin\Lib\site-packages')
) -join ';'
$env:ZEPHYR_BASE = Join-Path $NcsRoot 'zephyr'
$env:ZEPHYR_TOOLCHAIN_VARIANT = 'zephyr/gnu'
$env:ZEPHYR_SDK_INSTALL_DIR = Join-Path $ToolchainRoot 'opt\zephyr-sdk'
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue

Set-Location -LiteralPath $WorkspaceRoot
$westCommand = Get-Command west -ErrorAction Stop
$pythonCommand = Get-Command python -ErrorAction Stop

$Host.UI.RawUI.WindowTitle = 'nRF Connect SDK v3.4.0 - Adaptive Split Inference'
Write-Host ''
Write-Host 'nRF Connect SDK terminal ready' -ForegroundColor Green
Write-Host "Workspace:   $WorkspaceRoot"
Write-Host "NCS:         $NcsRoot"
Write-Host "ZEPHYR_BASE: $env:ZEPHYR_BASE"
Write-Host "west:        $($westCommand.Source)"
Write-Host "python:      $($pythonCommand.Source)"
Write-Host ''
