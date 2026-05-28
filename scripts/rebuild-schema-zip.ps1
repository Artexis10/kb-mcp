#requires -Version 5.1
<#
.SYNOPSIS
  Rebuild the Knowledge Base/_Schema.zip bundle from the canonical _Schema folder.

.DESCRIPTION
  Repacks _Schema/ into _Schema.zip so it can be re-uploaded as a skill to
  claude.ai whenever SKILL.md / references / project-keys.yaml change.

  Resolves the vault automatically: desktop first, then laptop. Honors
  $env:KB_MCP_VAULT_PATH when set.

.EXAMPLE
  pwsh -File scripts/rebuild-schema-zip.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Resolve-Vault {
  if ($env:KB_MCP_VAULT_PATH) {
    $p = $env:KB_MCP_VAULT_PATH
    if (Test-Path (Join-Path $p 'Knowledge Base/_Schema/SKILL.md')) { return $p }
    throw "KB_MCP_VAULT_PATH=$p does not contain Knowledge Base/_Schema/SKILL.md"
  }
  foreach ($candidate in @(
    'D:\Archive\Personal Archive\50 Notes\Obsidian',
    'C:\Users\win-laptop\Documents\Obsidian'
  )) {
    if (Test-Path (Join-Path $candidate 'Knowledge Base/_Schema/SKILL.md')) { return $candidate }
  }
  throw 'Could not locate Obsidian vault on this machine. Set $env:KB_MCP_VAULT_PATH.'
}

$vault     = Resolve-Vault
$kb        = Join-Path $vault 'Knowledge Base'
$schemaDir = Join-Path $kb '_Schema'
$zipPath   = Join-Path $kb '_Schema.zip'

Write-Host "vault:      $vault"
Write-Host "schema dir: $schemaDir"
Write-Host "zip target: $zipPath"

# Read the canonical version straight out of SKILL.md frontmatter so the
# operator sees what's about to ship.
$skillHead = (Get-Content (Join-Path $schemaDir 'SKILL.md') -TotalCount 8) -join "`n"
if ($skillHead -match '(?m)^\s*version:\s*([0-9]+\.[0-9]+\.[0-9]+)') {
  Write-Host "version:    $($matches[1])"
} else {
  Write-Warning 'Could not parse version from SKILL.md frontmatter.'
}

if (Test-Path $zipPath) { Remove-Item -LiteralPath $zipPath -Force }

# Compress-Archive on a folder packages the FOLDER as the top-level entry.
# To match claude.ai's expectation (SKILL.md at zip root, not under _Schema/),
# pass the folder's children instead.
$items = Get-ChildItem -LiteralPath $schemaDir -Force
Compress-Archive -LiteralPath $items.FullName -DestinationPath $zipPath -CompressionLevel Optimal

$size = (Get-Item -LiteralPath $zipPath).Length
Write-Host "wrote $zipPath ($([math]::Round($size/1KB,1)) KB)"
