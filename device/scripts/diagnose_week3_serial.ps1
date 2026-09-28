param(
    [Parameter(Mandatory = $true)][ValidatePattern('^(?i:COM)[0-9]+$')][string]$Port,
    [ValidatePattern('^(BAD|(?:RUN|TRACE) (?:[0-9]|1[0-9]))$')][string]$CommandText = 'BAD',
    [switch]$DrainCommandBanner,
    [string]$Output = 'device\artifacts\week3_capture_diag.txt'
)

# Read and write a single bounded command on the application CDC port.
$ErrorActionPreference = 'Stop'
$Output = [System.IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Output) | Out-Null
$writer = New-Object System.IO.StreamWriter($Output, $false, [System.Text.Encoding]::ASCII)
$writer.AutoFlush = $true
$serial = New-Object System.IO.Ports.SerialPort($Port, 115200)
$serial.NewLine = "`n"
$serial.ReadTimeout = 5000
$serial.WriteTimeout = 10000
$serial.DtrEnable = $true
$failed = $false
$lineCount = 0
function Log([string]$message) {
    $record = "$(Get-Date -Format o) $message"
    $writer.WriteLine($record)
    if ($message -notmatch '^RX [0-9a-f]{8}') { Write-Output $record }
}
try {
    Log "OPEN $Port DTR=$($serial.DtrEnable) RTS=$($serial.RtsEnable)"
    $serial.Open()
    Log "OPENED IsOpen=$($serial.IsOpen) BytesToRead=$($serial.BytesToRead)"
    $ready = $false
    for ($i = 0; $i -lt 10; $i++) {
        $line = $serial.ReadLine().Trim()
        Log "RX $line"
        if ($line.StartsWith('READY WEEK3 ')) { $ready = $true; break }
    }
    if (-not $ready) { throw 'READY not received' }
    if ($DrainCommandBanner) {
        $line = $serial.ReadLine().Trim()
        Log "RX $line"
    }
    $payload = "$CommandText`n"
    Log "PRE_WRITE payload=$($payload.Replace("`n",'\\n')) bytes=$([System.Text.Encoding]::ASCII.GetByteCount($payload)) BytesToRead=$($serial.BytesToRead) BytesToWrite=$($serial.BytesToWrite)"
    $started = Get-Date
    $serial.Write($payload)
    Log "WRITE_OK elapsed_ms=$([int]((Get-Date)-$started).TotalMilliseconds) BytesToWrite=$($serial.BytesToWrite)"
    $terminal = if ($CommandText -eq 'BAD') { 'ERROR ' } else { "DONE $($CommandText.Split(' ')[1])" }
    while ($true) {
        $line = $serial.ReadLine().Trim()
        $lineCount++
        Log "RX $line"
        if ($line.StartsWith($terminal)) { break }
    }
    Log "COMPLETE lines=$lineCount"
} catch {
    $failed = $true
    Log "EXCEPTION type=$($_.Exception.GetType().FullName) hresult=$($_.Exception.HResult) message=$($_.Exception.Message)"
    if ($_.Exception.InnerException) { Log "INNER $($_.Exception.InnerException.ToString())" }
    Log "STATE IsOpen=$($serial.IsOpen)"
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    $writer.Dispose()
}
if ($failed) { exit 1 }
exit 0
