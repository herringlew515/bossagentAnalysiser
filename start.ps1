param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Error 'Create the environment first: python -m venv .venv; then .\.venv\Scripts\python.exe -m pip install -e ".[dev]"'
}
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.env'))) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot '.env.example') -Destination (Join-Path $PSScriptRoot '.env')
    Write-Host 'Created .env. Configure your MySQL password before using the service.'
}
Write-Host "Career assistant: http://127.0.0.1:$Port"
& $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port $Port
