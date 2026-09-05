param(
    [string]$SourceRoot = "D:\reference_projects\NeuroClaw-main"
)

$ErrorActionPreference = "Stop"
$localFlowRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedSource = (Resolve-Path $SourceRoot).Path

if (-not (Test-Path -LiteralPath (Join-Path $resolvedSource "skills"))) {
    throw "NeuroClaw skills directory not found: $resolvedSource"
}

$skillTarget = Join-Path $localFlowRoot "skills"
New-Item -ItemType Directory -Force -Path $skillTarget | Out-Null

robocopy (Join-Path $resolvedSource "skills") $skillTarget /E /XD __pycache__ .pytest_cache /XF *.pyc | Out-Host
if ($LASTEXITCODE -gt 7) {
    throw "Skill copy failed with robocopy exit code $LASTEXITCODE"
}

$compatTarget = Join-Path $localFlowRoot "bakend\app\neuroclaw_compat"
$resourceTarget = Join-Path $localFlowRoot "bakend\resources"
$licenseTarget = Join-Path $localFlowRoot "THIRD_PARTY_NOTICES"
New-Item -ItemType Directory -Force -Path $compatTarget, $resourceTarget, $licenseTarget | Out-Null

Copy-Item -LiteralPath (Join-Path $resolvedSource "core\skill_loader\loader.py") -Destination (Join-Path $compatTarget "loader.py") -Force
Copy-Item -LiteralPath (Join-Path $resolvedSource "core\skill_loader\validate_dag.py") -Destination (Join-Path $compatTarget "validate_dag.py") -Force
Copy-Item -LiteralPath (Join-Path $resolvedSource "core\web\static\skill_summaries.json") -Destination (Join-Path $resourceTarget "neuroclaw_skill_summaries.json") -Force
Copy-Item -LiteralPath (Join-Path $resolvedSource "LICENSE") -Destination (Join-Path $licenseTarget "NeuroClaw-LICENSE.txt") -Force

$upstreamCount = (
    Get-ChildItem -LiteralPath (Join-Path $resolvedSource "skills") -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "SKILL.md") }
).Count

Write-Host "Synchronized $upstreamCount NeuroClaw skills into $skillTarget"

