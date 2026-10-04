# Offline tests of chunked text draining. No SerialPort and no MCU tensors.
$ErrorActionPreference = 'Stop'
$parseErrors = $null
$tokens = $null
$path = Join-Path $PSScriptRoot 'collect_week4.ps1'
$ast = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) { throw 'Collector syntax failed' }
$functionAst = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Read-Until'
}, $true)
Invoke-Expression $functionAst.Extent.Text

$writer = New-Object System.IO.StringWriter
$serial = [PSCustomObject]@{ Chunks = New-Object 'System.Collections.Generic.Queue[string]' }
$serial | Add-Member -MemberType ScriptMethod -Name ReadExisting -Value {
    if ($this.Chunks.Count -gt 0) { return $this.Chunks.Dequeue() }
    return ''
}
$script:pendingSerial = ''
$serial.Chunks.Enqueue("PING`r`nPO")
$serial.Chunks.Enqueue("NG`r`n")
if ((Read-Until 'PING' 1) -ne 'PING' -or $script:pendingSerial -ne 'PO') {
    throw 'Chunk remainder was lost after first matching line'
}
if ((Read-Until 'PONG' 1) -ne 'PONG' -or $script:pendingSerial -ne '') {
    throw 'Partial line was lost between waits'
}
if ($writer.ToString() -ne ("PING" + [Environment]::NewLine + "PONG" + [Environment]::NewLine)) {
    throw 'Stream output mismatch'
}
$serial.Chunks.Enqueue("DONE unexpected`r`n")
$rejected = $false
try { $null = Read-Until 'expected' 1 } catch {
    if ($_.Exception.Message -like 'Unexpected completion:*') { $rejected = $true } else { throw }
}
if (-not $rejected) { throw 'Unexpected completion was accepted' }
$serial.Chunks.Enqueue("ERROR invalid`r`n")
$rejected = $false
try { $null = Read-Until 'expected' 1 } catch {
    if ($_.Exception.Message -like 'Device error:*') { $rejected = $true } else { throw }
}
if (-not $rejected) { throw 'Error line was accepted' }
$serial.Chunks.Enqueue('x' * 4097)
$rejected = $false
try { $null = Read-Until 'expected' 1 } catch {
    if ($_.Exception.Message -eq 'CDC line too long') { $rejected = $true } else { throw }
}
if (-not $rejected) { throw 'Overlong incomplete line was accepted' }
$writer.Dispose()
Write-Output 'OFFLINE_COLLECTOR: PASS (split chunks, carry between waits, DONE/error/overflow rejection); no serial access'
