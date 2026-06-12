# publish.ps1
# Actualizeaza datele PPC si publica dashboard-ul pe GitHub Pages.
#
# Pasi:
#  1. Ruleaza scriptul de fetch (actualizeaza ppc-data.js cu date proaspete din Google Ads).
#  2. Copiaza dashboard-ul (ppc-dashboard-live.html -> docs/index.html) si ppc-data.js -> docs/ppc-data.js.
#  3. Face commit + push pe branch-ul GitHub Pages -> site-ul public se actualizeaza automat.
#
# Ruleaza acest script din radacina proiectului "Paralela 45"
# (sau seteaza $root mai jos la calea completa).

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> 1. Actualizez datele din Google Ads..."
python "scripts\fetch_google_ads_data.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Eroare la rularea fetch_google_ads_data.py. Public nu va fi actualizat." -ForegroundColor Red
    exit 1
}

Write-Host "==> 2. Copiez fisierele actualizate in docs/..."
New-Item -ItemType Directory -Force -Path "docs" | Out-Null
Copy-Item "ppc-dashboard-live.html" "docs\index.html" -Force
Copy-Item "ppc-data.js" "docs\ppc-data.js" -Force

Write-Host "==> 3. Trimit modificarile pe GitHub (GitHub Pages se actualizeaza automat)..."
git add docs/index.html docs/ppc-data.js
git commit -m "Actualizare automata date PPC - $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
git push

Write-Host "==> Terminat. Dashboard-ul public va fi actualizat in 1-2 minute." -ForegroundColor Green
