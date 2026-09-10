param(
	[Parameter(Mandatory = $true)]
	[ValidatePattern('^(?i:COM)[0-9]+$')]
	[string]$Port,
	[int]$BaudRate = 115200,
	[string]$ToolchainRoot = 'D:\ncs\toolchains\dcbdc366a1'
)

$ErrorActionPreference = 'Stop'
$PythonExe = Join-Path $ToolchainRoot 'opt\bin\python.exe'

if (-not (Test-Path -LiteralPath $PythonExe)) {
	throw "NCS Python not found: $PythonExe"
}

$env:PYTHONPATH = "$(Join-Path $ToolchainRoot 'opt\bin');$(Join-Path $ToolchainRoot 'opt\bin\Lib');$(Join-Path $ToolchainRoot 'opt\bin\Lib\site-packages')"
Write-Output "Opening USB CDC $Port at $BaudRate baud. Press Ctrl+] to exit."
& $PythonExe -m serial.tools.miniterm $Port $BaudRate
$monitorExitCode = $LASTEXITCODE

if ($monitorExitCode -ne 0) {
	throw "Serial Monitor exited with code $monitorExitCode."
}
exit 0
