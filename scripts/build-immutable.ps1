[CmdletBinding()]
param(
    [switch]$NoCache,
    [switch]$Gpu
)

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $repoRoot
try {
    $sha = (git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $sha -notmatch '^[0-9a-f]{40}$') {
        throw 'Unable to resolve a full 40-character Git SHA.'
    }

    if (git status --porcelain) {
        throw 'Working tree is dirty. Commit or stash changes before immutable build.'
    }

    $env:TESTED_SHA = $sha
    if ([string]::IsNullOrWhiteSpace($env:SAHOOL_BUILD_ID)) {
        $env:SAHOOL_BUILD_ID = "local-$($sha.Substring(0,12))"
    }

    $compose = @('-f', 'docker-compose.v9.yml')
    if ($Gpu) {
        $compose += @('-f', 'docker-compose.v9.gpu.yml', '--profile', 'gpu')
    }

    & docker compose @compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'docker compose config validation failed.' }

    $buildArgs = @('compose') + $compose + @('build')
    if ($NoCache) { $buildArgs += '--no-cache' }
    & docker @buildArgs
    if ($LASTEXITCODE -ne 0) { throw 'docker compose build failed.' }

    Write-Host "Immutable build completed for TESTED_SHA=$sha"
}
finally {
    Pop-Location
}
