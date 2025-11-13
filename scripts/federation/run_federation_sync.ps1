param(
    [string]$ScriptPath = (Join-Path $PSScriptRoot "run_federation_sync.py"),
    [string[]]$ScriptArguments = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-PythonCandidates {
    $candidates = @()
    if ($env:VIRTUAL_ENV) {
        $venvPython = Join-Path $env:VIRTUAL_ENV "Scripts/python.exe"
        if (Test-Path $venvPython) {
            $candidates += $venvPython
        }
    }
    foreach ($cmd in @('python', 'py')) {
        try {
            $resolved = (Get-Command $cmd -ErrorAction Stop).Source
            if ($resolved) {
                $candidates += $resolved
            }
        } catch {
            # Ignore resolution failures; fall back to literal names later
        }
    }
    $candidates += @('python', 'py')
    return $candidates | Where-Object { $_ } | Select-Object -Unique
}

function Invoke-PythonExecutable {
    param(
        [string]$Executable,
        [string[]]$Arguments
    )

    try {
        $output = & $Executable @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        return [pscustomobject]@{
            Executable = $Executable
            Arguments = $Arguments
            Output = $output
            ExitCode = $exitCode
        }
    } catch {
        return [pscustomobject]@{
            Executable = $Executable
            Arguments = $Arguments
            Output = $_.Exception.Message
            ExitCode = 9009
        }
    }
}

function Convert-InlineArguments {
    param(
        [string[]]$Arguments
    )

    if ($Arguments.Count -lt 2 -or ($Arguments[0] -ne '-c' -and $Arguments[0] -ne '-m')) {
        return $Arguments
    }

    $converted = @($Arguments[0])
    for ($i = 1; $i -lt $Arguments.Count; $i++) {
        $arg = $Arguments[$i]
        $converted += ($arg -replace '"', '\\"')
    }
    return $converted
}

function Invoke-FaultTolerantPython {
    param(
        [string[]]$Arguments
    )

    $inline = $Arguments.Count -gt 0 -and ($Arguments[0] -eq '-c' -or $Arguments[0] -eq '-m')
    $escapedAttemptUsed = $false
    $candidates = Get-PythonCandidates
    $lastResult = $null

    foreach ($candidate in $candidates) {
        $result = Invoke-PythonExecutable -Executable $candidate -Arguments $Arguments
        $lastResult = $result
        if ($result.ExitCode -eq 0) {
            return $result
        }

        $combinedOutput = ($result.Output | Out-String).Trim()
        if ($result.ExitCode -eq 9009 -or $combinedOutput -match 'not recognized') {
            continue
        }

        if ($inline -and -not $escapedAttemptUsed) {
            $escapedAttemptUsed = $true
            $escapedArgs = Convert-InlineArguments -Arguments $Arguments
            $escapedResult = Invoke-PythonExecutable -Executable $candidate -Arguments $escapedArgs
            if ($escapedResult.ExitCode -eq 0) {
                Write-Verbose "Recovered inline Python command by escaping quotes for $candidate."
                return $escapedResult
            }
            $lastResult = $escapedResult
        }
    }

    if ($null -ne $lastResult) {
        $message = "Python execution failed after retries. ExitCode=$($lastResult.ExitCode). Output=$($lastResult.Output | Out-String)"
    } else {
        $message = "Python execution failed: no Python interpreter found."
    }
    throw $message
}

$resolvedScript = Resolve-Path -LiteralPath $ScriptPath -ErrorAction Stop
$pythonArguments = @($resolvedScript.Path) + $ScriptArguments

try {
    $result = Invoke-FaultTolerantPython -Arguments $pythonArguments
    Write-Host "Federation sync completed via $($result.Executable)."
    exit 0
} catch {
    Write-Error $_
    exit 1
}
