param(
    [Parameter(Mandatory = $true)][ValidatePattern('^(?i:COM)[0-9]+$')][string]$Port,
    [string]$Output = 'results\week4\logs\week4_capture.txt',
    [string]$Report = 'results\week4\week4_mcu_validation.json',
    [ValidateRange(0,19)][int]$BenchSample = 0,
    [switch]$NoTiming,
    [ValidateRange(1,3600)][int]$CommandTimeoutSeconds = 600
)

# Later device stage ONLY. Build scripts never invoke this script.
# Uses the existing .NET SerialPort workflow; no new Python dependency.
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Output = [System.IO.Path]::GetFullPath($Output)
$Report = [System.IO.Path]::GetFullPath($Report)
$MlPython = Join-Path $RepoRoot 'ml\.venv\Scripts\python.exe'
if ((Test-Path -LiteralPath $Output) -or (Test-Path -LiteralPath $Report)) {
    throw 'Capture/report already exists; choose new evidence filenames'
}
# Authenticate before any serial access; generator writes ignored headers only.
Remove-Item Env:PYTHONHOME,Env:PYTHONPATH -ErrorAction SilentlyContinue
& $MlPython -B (Join-Path $PSScriptRoot 'generate_week4_inputs.py') --repo-root $RepoRoot
if ($LASTEXITCODE -ne 0) { throw 'R3 authentication failed' }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Output) | Out-Null
$serial = New-Object System.IO.Ports.SerialPort($Port, 115200)
$serial.NewLine = "`n"
$serial.ReadTimeout = 1000
$serial.WriteTimeout = 10000
$serial.DtrEnable = $true
$serial.RtsEnable = $true
$serial.Handshake = [System.IO.Ports.Handshake]::None
$writer = New-Object System.IO.StreamWriter($Output, $false, [System.Text.Encoding]::ASCII)

function Read-Until([string]$Expected, [int]$TimeoutSeconds, [switch]$Prefix) {
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    # ReadExisting preserves partial lines across timeout intervals. A long
    # BENCH can produce no output until all 120 head runs have completed.
    $pending = $script:pendingSerial
    $script:pendingSerial = ''
    while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $pending += $serial.ReadExisting()
        $newline = $pending.IndexOf("`n")
        while ($newline -ge 0) {
            $line = $pending.Substring(0, $newline).TrimEnd("`r")
            $pending = $pending.Substring($newline + 1)
            $writer.WriteLine($line)
            if ($line.StartsWith('ERROR ')) { throw "Device error: $line" }
            if (($Prefix -and $line.StartsWith($Expected)) -or (-not $Prefix -and $line -eq $Expected)) {
                # A banner is immediately followed by COMMAND; retain any
                # remainder so the next wait does not drop protocol data.
                $script:pendingSerial = $pending
                $writer.Flush()
                return $line
            }
            if ($line.StartsWith('DONE ')) { throw "Unexpected completion: $line; expected $Expected" }
            $newline = $pending.IndexOf("`n")
        }
        if ($pending.Length -gt 4096) { throw 'CDC line too long' }
        Start-Sleep -Milliseconds 5
    }
    $writer.Flush()
    throw "Dongle timed out waiting for $Expected; partial evidence retained"
}

# Carry partial/chunked input between waits without losing complete lines.
$script:pendingSerial = ''

function Check-Captured([string]$Stage, [switch]$Mixed, [switch]$Timing) {
    $writer.Flush()
    # Windows StreamWriter shares the capture for read access; the checker
    # sees only fully flushed commands and must PASS before timing starts.
    $stageReport = Join-Path (Split-Path -Parent $Report) ($Stage + '.json')
    if (Test-Path -LiteralPath $stageReport) { throw "Stage report exists: $stageReport" }
    $arguments = @('-B', (Join-Path $PSScriptRoot 'check_week4_capture.py'), '--repo-root', $RepoRoot,
        '--capture', $Output, '--report', $stageReport)
    if ($Mixed) { $arguments += '--mixed-order' }
    if ($Timing) { $arguments += @('--bench-sample', "$BenchSample") }
    & $MlPython @arguments
    if ($LASTEXITCODE -ne 0) { throw "MCU $Stage checker failed: $LASTEXITCODE" }
}

try {
    $serial.Open()
    $banner = Read-Until 'READY ' 20 -Prefix
    $manifest = '80e4cea3b70bdafef1b6925b208d4951a87bba4ff8cf10dbb6a671e36439635c'
    if (-not $banner.StartsWith("READY WEEK4 R3 $manifest samples=20 splits=11 ")) {
        throw "Wrong Week 4 firmware: $banner"
    }
    if (-not $NoTiming -and -not $banner.EndsWith('DWT=READY')) { throw 'DWT unavailable' }
    Write-Output "CONFIRMED: $banner"
    $commandBanner = Read-Until 'COMMAND ' 5 -Prefix
    if ($commandBanner -ne 'COMMAND RUN n s or BENCH n s (n=0..19 s=0..10)') {
        throw "Unexpected protocol: $commandBanner"
    }
    for ($sample = 0; $sample -lt 20; $sample++) {
        for ($split = 0; $split -lt 11; $split++) {
            $serial.Write("RUN $sample $split`n")
            $null = Read-Until "DONE $sample $split RUN" $CommandTimeoutSeconds
            Write-Output "CAPTURED: RUN $sample $split"
        }
    }
    Check-Captured 'primary-validation'
    $sequenceJson = & $MlPython -B -c "import sys,json; sys.path.insert(0,sys.argv[1]); from check_week4_capture import MIXED_SEQUENCE; print(json.dumps(MIXED_SEQUENCE))" $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw 'Cannot load authoritative mixed command sequence' }
    $mixedSequence = $sequenceJson | ConvertFrom-Json
    foreach ($pair in $mixedSequence) {
        $sample = $pair[0]
        $split = $pair[1]
        $serial.Write("RUN $sample $split`n")
        $null = Read-Until "DONE $sample $split RUN" $CommandTimeoutSeconds
        Write-Output "CAPTURED MIXED: RUN $sample $split"
    }
    Check-Captured 'mixed-validation' -Mixed
    if (-not $NoTiming) {
        for ($split = 0; $split -lt 11; $split++) {
            $serial.Write("BENCH $BenchSample $split`n")
            $null = Read-Until "DONE $BenchSample $split BENCH" $CommandTimeoutSeconds
            Write-Output "CAPTURED: BENCH $BenchSample $split"
        }
    }
} finally {
    if ($script:pendingSerial.Length -gt 0) { $writer.Write($script:pendingSerial) }
    $writer.Dispose()
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
}
$checkArgs = @('-B', (Join-Path $PSScriptRoot 'check_week4_capture.py'), '--repo-root', $RepoRoot,
    '--capture', $Output, '--report', $Report, '--mixed-order')
if (-not $NoTiming) { $checkArgs += @('--bench-sample', "$BenchSample") }
& $MlPython @checkArgs
if ($LASTEXITCODE -ne 0) { throw "MCU capture checker failed: $LASTEXITCODE" }
Write-Output "CAPTURE: $Output"
Write-Output "REPORT: $Report"
