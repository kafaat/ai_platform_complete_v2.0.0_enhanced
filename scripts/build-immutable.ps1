[CmdletBinding()]
param(
    [switch]$NoCache,
    [switch]$Gpu
)

$ErrorActionPreference = 'Stop'
# Handle native exit codes below, including when the caller enables this PS 7 preference.
$PSNativeCommandUseErrorActionPreference = $false

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$previousSha = $env:TESTED_SHA
$previousBuildId = $env:SAHOOL_BUILD_ID
Push-Location $repoRoot
try {
    $sha = git rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $sha -notmatch '^[0-9a-f]{40}$') {
        throw 'Unable to resolve a full 40-character Git SHA. Run from a Git checkout.'
    }

    $changes = git status --porcelain
    if ($LASTEXITCODE -ne 0) { throw 'Unable to verify the Git working tree.' }
    if ($changes) {
        throw 'Working tree is dirty. Commit or stash changes before immutable build.'
    }

    $engineOS = docker info --format '{{.OSType}}'
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Engine is unreachable. For a local Windows build, start Docker Desktop and wait for the Linux engine. Check docker context ls and any DOCKER_CONTEXT or DOCKER_HOST override.'
    }
    if ($engineOS -ne 'linux') {
        throw 'SAHOOL requires a Linux Docker Engine. On Windows, switch Docker Desktop to Linux containers. For GPU access, enable its WSL 2 backend.'
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
    $env:TESTED_SHA = $previousSha
    $env:SAHOOL_BUILD_ID = $previousBuildId
    Pop-Location
}
