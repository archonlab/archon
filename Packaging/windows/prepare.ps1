param(
  [string]$Output = "dist-stage/windows",
  [string]$RuntimeRoot = ""
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$Args = @("$Root/Tools/archon_distribution_stage.py", "--root", $Root, "--platform", "windows", "--output", $Output, "--replace")
if ($RuntimeRoot) { $Args += @("--runtime-root", $RuntimeRoot) }
if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 @Args; exit $LASTEXITCODE }
if (Get-Command python -ErrorAction SilentlyContinue) { & python @Args; exit $LASTEXITCODE }
throw "Python 3 is required to prepare the Windows distribution stage."
