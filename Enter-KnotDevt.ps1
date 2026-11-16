# Dot-source from PowerShell: . .\Enter-KnotDevt.ps1
$projectRoot = $PSScriptRoot
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'KnotDevt'
$python313 = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
$projectVenv = Join-Path $projectRoot 'backend\.venv'
if (-not (Test-Path -LiteralPath $python313)) { throw 'Python 3.13 is required.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectVenv 'Scripts\python.exe'))) {
    throw 'Create backend\.venv with Python 3.13 before entering the environment.'
}
$env:UV_PROJECT_ENVIRONMENT = $projectVenv
$env:UV_PYTHON = $python313
$env:UV_CACHE_DIR = Join-Path $runtimeRoot 'cache\uv'
$env:PIP_CACHE_DIR = Join-Path $runtimeRoot 'cache\pip'
$env:TEMP = Join-Path $runtimeRoot 'temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP,$env:UV_CACHE_DIR,$env:PIP_CACHE_DIR | Out-Null
. (Join-Path $projectVenv 'Scripts\Activate.ps1')
$env:PATH = (Join-Path $projectVenv 'Scripts') + ';' + (Join-Path $runtimeRoot 'tools\Scripts') + ';' + $env:PATH
Write-Output 'KnotDevt: backend\.venv activated; Python, caches and temporary files use C:.'
