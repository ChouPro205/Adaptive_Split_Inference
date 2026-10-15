# Parse script syntax only. Never instantiate SerialPort or execute DFU.
$ErrorActionPreference = 'Stop'
foreach ($name in @('build_week5_head.ps1','flash_week5_head.ps1')) {
    $parseErrors = $null
    $parseTokens = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $PSScriptRoot $name), [ref]$parseTokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
    Write-Output "POWERSHELL SYNTAX PASS: $name"
}
