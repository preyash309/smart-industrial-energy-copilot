$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$dashboardPython=Join-Path $projectRoot '.venv-dashboard/Scripts/python.exe'
if(-not(Test-Path -LiteralPath $dashboardPython)){throw 'Create .venv-dashboard with python -m venv .venv-dashboard first.'}
& $dashboardPython -m pip install -r (Join-Path $projectRoot 'requirements-dashboard.txt')
if($LASTEXITCODE -ne 0){throw 'Dashboard dependency installation failed.'}
& $dashboardPython -c 'import sys,streamlit,plotly; print(sys.executable); print("Streamlit",streamlit.__version__); print("Plotly",plotly.__version__)'
if($LASTEXITCODE -ne 0){throw 'Dashboard imports failed.'}
Write-Output "Start the app from $projectRoot with .venv-dashboard/Scripts/python.exe -m streamlit run dashboard/app.py"
