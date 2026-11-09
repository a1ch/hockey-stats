# Deploys the committed code to Azure App Service (Ingot sponsorship sub, free F1 plan).
# Run from this folder:  .\deploy.ps1
$ErrorActionPreference = "Stop"
$sub = "Microsoft Azure Sponsorship"; $rg = "rg-bettinjimmy"; $app = "bettinjimmy-a1ch"
$zip = Join-Path $env:TEMP "bettinjimmy.zip"
git archive --format zip -o $zip HEAD
az webapp deploy --subscription $sub -g $rg -n $app --src-path $zip --type zip --async true -o none
Write-Host "Deployed. https://$app.azurewebsites.net (first load after it's been idle takes about a minute)"
