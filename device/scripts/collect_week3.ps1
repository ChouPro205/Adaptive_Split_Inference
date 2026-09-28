param(
    [Parameter(Mandatory = $true)][string]$Port,
    [string]$Output = 'device\artifacts\week3_capture.txt'
)

$ErrorActionPreference = 'Stop'
$Output = [System.IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Output) | Out-Null
$serial = New-Object System.IO.Ports.SerialPort($Port, 115200)
$serial.NewLine = "`n"
$serial.ReadTimeout = 60000
$serial.WriteTimeout = 10000
$serial.DtrEnable = $true
$writer = New-Object System.IO.StreamWriter($Output, $false, [System.Text.Encoding]::ASCII)
try {
    $serial.Open()
    $ready = $false
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        $line = $serial.ReadLine().Trim()
        $writer.WriteLine($line)
        if ($line.StartsWith('READY WEEK3 ')) { $ready = $true; break }
    }
    if (-not $ready) { throw 'Week 3 READY banner not received' }
    for ($sample = 0; $sample -lt 20; $sample++) {
        $command = if ($sample -eq 0) { 'TRACE 0' } else { "RUN $sample" }
        $serial.Write("$command`n")
        $done = $false
        while (-not $done) {
            $line = $serial.ReadLine().Trim()
            $writer.WriteLine($line)
            if ($line.StartsWith('ERROR ')) { throw "Device error: $line" }
            if ($line -eq "DONE $sample") { $done = $true }
        }
        $writer.Flush()
        Write-Output "Captured sample $sample"
    }
} finally {
    $writer.Dispose()
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
}
Write-Output "CAPTURE: $Output"
