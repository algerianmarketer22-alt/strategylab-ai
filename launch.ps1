$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path '.venv/Scripts/python.exe')) {
    Write-Error 'Environnement absent. Suivre README.md pour installer Python et les dépendances.'
}
& ./.venv/Scripts/python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
