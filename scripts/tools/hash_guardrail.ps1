param(
    [string]$TargetFile = (Join-Path $PSScriptRoot "..\..\exports\integrity_metrics_registry.csv"),
    [string]$SchemaTemplate = (Join-Path $PSScriptRoot "..\..\templates\integrity_registry_schema.json")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..") -ErrorAction Stop).Path
}

function Get-TimeStamp {
    return (Get-Date).ToUniversalTime().ToString("o")
}

function Write-GuardrailLog {
    param(
        [string]$EventName,
        [string]$Message,
        [string]$Severity = 'info',
        [hashtable]$Metadata
    )

    $logPath = Join-Path (Get-RepoRoot) 'federation\federation_error_log.jsonl'
    if (!(Test-Path -LiteralPath $logPath)) {
        New-Item -ItemType File -Path $logPath -Force | Out-Null
    }
    $payload = [ordered]@{
        timestamp = Get-TimeStamp
    event = $EventName
        severity = $Severity
        message = $Message
    }
    if ($Metadata) {
        $payload.metadata = $Metadata
    }
    ($payload | ConvertTo-Json -Compress) | Out-File -FilePath $logPath -Append -Encoding UTF8
}

function Get-PythonCandidates {
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($env:VIRTUAL_ENV) {
        $venv = Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe'
        if (Test-Path $venv) { $candidates.Add($venv) }
    }
    foreach ($candidate in @('python', 'py')) {
        try {
            $resolved = (Get-Command $candidate -ErrorAction Stop).Source
            if ($resolved) { $candidates.Add($resolved) }
        } catch { }
    }
    foreach ($fallback in @('python', 'py')) {
        if (-not $candidates.Contains($fallback)) {
            $candidates.Add($fallback)
        }
    }
    return $candidates
}

function Invoke-PythonProcess {
    param(
        [string]$Executable,
        [string[]]$ArgumentList
    )

    $stdout = [System.IO.Path]::GetTempFileName()
    $stderr = [System.IO.Path]::GetTempFileName()
    try {
        $process = Start-Process -FilePath $Executable -ArgumentList $ArgumentList -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        $outText = if (Test-Path $stdout) { Get-Content -LiteralPath $stdout -Raw } else { '' }
        $errText = if (Test-Path $stderr) { Get-Content -LiteralPath $stderr -Raw } else { '' }
        return [pscustomobject]@{
            Executable = $Executable
            Arguments = $ArgumentList
            ExitCode = $process.ExitCode
            StdOut = $outText
            StdErr = $errText
        }
    } catch {
        return [pscustomobject]@{
            Executable = $Executable
            Arguments = $ArgumentList
            ExitCode = 9009
            StdOut = ''
            StdErr = $_.Exception.Message
        }
    } finally {
        Remove-Item -LiteralPath $stdout -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stderr -ErrorAction SilentlyContinue
    }
}

function Set-SchemaHeadersIfMissing {
    param(
        [string]$FilePath,
        [string]$TemplatePath
    )

    if (!(Test-Path -LiteralPath $TemplatePath)) {
        return
    }

    $template = Get-Content -LiteralPath $TemplatePath -Raw | ConvertFrom-Json
    $expectedHeaders = ($template.headers | ForEach-Object { $_.ToString() })
    if (-not $expectedHeaders -or $expectedHeaders.Count -eq 0) {
        return
    }

    $expectedLine = ($expectedHeaders -join ',')
    $lines = Get-Content -LiteralPath $FilePath
    if ($lines.Count -eq 0) {
        Set-Content -LiteralPath $FilePath -Value $expectedLine -Encoding UTF8
    Write-GuardrailLog -EventName 'schema_headers_restored' -Message "Inserted canonical headers into empty file" -Severity 'recovery' -Metadata @{ file = $FilePath }
        return
    }

    $currentHeader = $lines[0]
    $missing = $expectedHeaders | Where-Object { $currentHeader.Split(',') -notcontains $_ }
    if ($missing.Count -eq 0 -and $currentHeader -eq $expectedLine) {
        return
    }

    $body = @()
    if ($lines.Count -gt 1) {
        $body = $lines[1..($lines.Count - 1)]
    }
    Set-Content -LiteralPath $FilePath -Value @($expectedLine) -Encoding UTF8
    if ($body.Count -gt 0) {
        Add-Content -LiteralPath $FilePath -Value $body -Encoding UTF8
    }
    Write-GuardrailLog -EventName 'schema_headers_restored' -Message "Recovered canonical headers from template" -Severity 'recovery' -Metadata @{ file = $FilePath; missing = $missing }
}

function Invoke-InlineHash {
    param(
        [string]$Code
    )

    $candidates = Get-PythonCandidates
    $lastResult = $null
    foreach ($candidate in $candidates) {
        $result = Invoke-PythonProcess -Executable $candidate -ArgumentList @('-c', $Code)
        if ($result.ExitCode -eq 0 -and $result.StdErr.Trim().Length -eq 0) {
            return $result.StdOut.Trim()
        }
        $lastResult = $result
        if ($result.StdErr -match 'SyntaxError') {
            $wrapped = "'" + ($Code -replace "'", "''") + "'"
            $retry = Invoke-PythonProcess -Executable 'py' -ArgumentList @('-3', '-c', $wrapped)
            if ($retry.ExitCode -eq 0) {
                Write-GuardrailLog -EventName 'hash_retry_py3' -Message "Recovered hash execution with py -3 -c" -Severity 'info'
                return $retry.StdOut.Trim()
            }
            $lastResult = $retry
        }
        if ($result.StdErr -match 'not recognized' -or $result.ExitCode -eq 9009) {
            continue
        }
    }

    $fallbackPath = Join-Path $PSScriptRoot '_hash_eval.py'
    Set-Content -LiteralPath $fallbackPath -Value $Code -Encoding UTF8
    Write-GuardrailLog -EventName 'hash_temp_script' -Message "Fallback to temporary _hash_eval.py" -Severity 'warning'
    try {
        foreach ($candidate in (Get-PythonCandidates)) {
            $result = Invoke-PythonProcess -Executable $candidate -ArgumentList @($fallbackPath)
            if ($result.ExitCode -eq 0) {
                return $result.StdOut.Trim()
            }
        }
    } finally {
        Remove-Item -LiteralPath $fallbackPath -ErrorAction SilentlyContinue
    }

    if ($lastResult) {
        throw "Failed to compute hash: $($lastResult.StdErr.Trim())"
    }
    throw "Failed to compute hash using available Python interpreters."
}

function Update-FederationStatus {
    param(
        [string]$HashValue,
        [string]$TargetPath
    )

    $statusPath = Join-Path (Get-RepoRoot) 'federation\federation_status.json'
    $status = @{}
    if (Test-Path -LiteralPath $statusPath) {
        $raw = Get-Content -LiteralPath $statusPath -Raw
        if ($raw.Trim()) {
            $status = $raw | ConvertFrom-Json
        }
    }
    if (-not $status.hash_results) {
        $status.hash_results = @()
    }
    $relative = (Resolve-Path -LiteralPath $TargetPath).Path.Substring((Get-RepoRoot).Length + 1).Replace('\\', '/')
    $status.hash_results += [pscustomobject]@{
        timestamp = Get-TimeStamp
        path = $relative
        algorithm = 'sha256'
        hash = $HashValue
    }
    $status.timestamp = Get-TimeStamp
    $json = $status | ConvertTo-Json -Depth 8
    Set-Content -LiteralPath $statusPath -Value ($json + [Environment]::NewLine) -Encoding UTF8
}

$resolvedTarget = Resolve-Path -LiteralPath $TargetFile -ErrorAction Stop
Set-SchemaHeadersIfMissing -FilePath $resolvedTarget.Path -TemplatePath $SchemaTemplate

$hashCode = @"
import hashlib
import pathlib
path = pathlib.Path(r"""$($resolvedTarget.Path)""")
digest = hashlib.sha256(path.read_bytes()).hexdigest()
print(digest)
"@

$hashValue = Invoke-InlineHash -Code $hashCode
Write-GuardrailLog -EventName 'hash_computed' -Message "Computed SHA256 for $($resolvedTarget.Path)" -Severity 'info' -Metadata @{ hash = $hashValue }
Update-FederationStatus -HashValue $hashValue -TargetPath $resolvedTarget.Path
Write-Host "SHA256($($resolvedTarget.Path)) = $hashValue"
