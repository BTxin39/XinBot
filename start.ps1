$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/'
}
uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
uv run --frozen xinbot start web
if ($LASTEXITCODE -ne 0) { throw 'XinBot failed to start; inspect the error above' }
