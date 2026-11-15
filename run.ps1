$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Create the project virtual environment first. See README.md.'
}
& $projectPython (Join-Path $PSScriptRoot 'run.py') @args
