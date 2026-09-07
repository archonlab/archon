[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [Parameter(Mandatory=$true)][string]$RuntimeLock,
    [Parameter(Mandatory=$true)][string]$Output,
    [Parameter(Mandatory=$true)][string]$ISCC
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$RuntimeRoot = (Resolve-Path $RuntimeRoot).Path
$RuntimeLock = (Resolve-Path $RuntimeLock).Path
$ISCC = (Resolve-Path $ISCC).Path
$Python = Join-Path $RuntimeRoot 'python.exe'
if (!(Test-Path $Python)) { throw 'Complete private Windows Python is missing (python.exe).' }
if (Test-Path $Output) { throw 'Output must be a new directory.' }
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:ARCHON_RUNTIME_PYTHON = $Python
function Invoke-Checked([string[]]$Arguments) {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python build step failed ($LASTEXITCODE)." }
}
$Builder = Join-Path $Root 'Tools/archon_windows_distribution.py'
$Probe = & $Python -B $Builder probe --runtime-root $RuntimeRoot
if ($LASTEXITCODE -ne 0) { throw 'Native runtime dependency probe failed.' }
New-Item -ItemType Directory -Path $Output | Out-Null
$Output = (Resolve-Path $Output).Path
$Stage = Join-Path $Output 'portable'
Invoke-Checked -Arguments @('-B', $Builder, 'stage', '--root', $Root, '--output', $Stage, '--runtime-root', $RuntimeRoot, '--runtime-lock', $RuntimeLock)
# Native smoke operates on a disposable sibling, preserving exact installer bytes.
$Smoke = Join-Path $Output 'acceptance copy with spaces'
Copy-Item -Recurse $Stage $Smoke
$SmokePython = Join-Path $Smoke 'Runtime/python/python.exe'
$env:ARCHON_RUNTIME_PYTHON = $SmokePython
& $SmokePython -B (Join-Path $Smoke 'Tools/archon_studio_desktop.py') --root $Smoke --headless-smoke
if ($LASTEXITCODE -ne 0) { throw 'Native desktop headless smoke failed.' }
$env:ARCHON_RUNTIME_PYTHON = $Python
Invoke-Checked -Arguments @('-B', $Builder, 'installer-files', '--root', $Stage, '--output', (Join-Path $Output 'payload.iss'))
& $ISCC "/DStageDir=$Stage" "/DFilesInclude=$(Join-Path $Output 'payload.iss')" "/O$Output" (Join-Path $PSScriptRoot 'installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
Invoke-Checked -Arguments @('-B', $Builder, 'verify', '--output', $Stage)
$Artifact = Join-Path $Output 'ARCHON-Studio-1.0.0.exe'
@{
    schema='archon_windows_native_build_v1'; runtime=($Probe | ConvertFrom-Json)
    artifact_sha256=(Get-FileHash $Artifact -Algorithm SHA256).Hash.ToLowerInvariant()
    compiler_sha256=(Get-FileHash $ISCC -Algorithm SHA256).Hash.ToLowerInvariant()
    compiler_version=(Get-Item $ISCC).VersionInfo.FileVersion
    stage_manifest_sha256=(Get-FileHash (Join-Path $Stage 'WINDOWS_DISTRIBUTION.json') -Algorithm SHA256).Hash.ToLowerInvariant()
    headless_smoke='PASS'; interactive_acceptance='PENDING'
} | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $Output 'BUILD_RECEIPT.json')
