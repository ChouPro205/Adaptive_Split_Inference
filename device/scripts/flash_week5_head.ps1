param(
    [Parameter(Mandatory=$true)][ValidatePattern('^(?i:COM)[0-9]+$')][string]$Port,
    [Parameter(Mandatory=$true)][string]$Preparation,
    [Parameter(Mandatory=$true)][string]$ReceiptDir,
    [string]$ToolchainRoot='D:\ncs\toolchains\dcbdc366a1'
)
# LATER DEVICE STEP ONLY. Preparation never invokes this script.
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$MlPython = Join-Path $RepoRoot 'ml\.venv\Scripts\python.exe'
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
& $MlPython -B (Join-Path $PSScriptRoot 'verify_week5_package.py') --preparation $Preparation
if ($LASTEXITCODE -ne 0) { throw 'Package/source preflight failed; no DFU attempted' }
$Prepared = Get-Content -LiteralPath $Preparation -Raw -Encoding UTF8 | ConvertFrom-Json
$nrfutilExe = Join-Path $ToolchainRoot 'nrfutil\bin\nrfutil.exe'
if (-not (Test-Path -LiteralPath $nrfutilExe)) { throw 'Existing nrfutil unavailable' }
$stamp = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(7)).ToString('yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Path $ReceiptDir -Force | Out-Null
$receiptPath = Join-Path $ReceiptDir ("dfu-$stamp.json")
$logPath = Join-Path $ReceiptDir ("dfu-$stamp.log")
if ((Test-Path -LiteralPath $receiptPath) -or (Test-Path -LiteralPath $logPath)) { throw 'DFU receipt exists' }
$savedNrfutilHome = $env:NRFUTIL_HOME
Remove-Item Env:NRFUTIL_HOME -ErrorAction SilentlyContinue
try {
    $ErrorActionPreference = 'Continue'
    $arguments = @('nrf5sdk-tools','dfu','usb-serial','--package',$Prepared.artifacts.zip.path,'--port',$Port)
    $output = & $nrfutilExe @arguments 2>&1
    $code = $LASTEXITCODE
    $output | Set-Content -LiteralPath $logPath -Encoding UTF8
    [ordered]@{ origin='REAL_USB_DFU'; port=$Port; preparation=$Preparation;
        preparation_sha256=(Get-FileHash -LiteralPath $Preparation -Algorithm SHA256).Hash.ToLower();
        package=$Prepared.artifacts.zip; application=$Prepared.application;
        executable=$nrfutilExe; arguments=$arguments; exit_code=$code;
        timestamp=[DateTimeOffset]::UtcNow.ToString('o') } |
        ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
} finally { if ($null -ne $savedNrfutilHome) { $env:NRFUTIL_HOME=$savedNrfutilHome } }
if ($code -ne 0) { throw "USB DFU failed: exit=$code; log=$logPath" }
Write-Output "DFU completed; receipt=$receiptPath. Rediscover application port before collection."
