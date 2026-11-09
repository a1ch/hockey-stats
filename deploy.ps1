# Bettin Jimmy on Azure Container Apps (Ingot sponsorship sub). The container pulls
# main from GitHub when it starts, so: commit + push, then run this to restart it.
$ErrorActionPreference = "Stop"
$sub = "Microsoft Azure Sponsorship"; $rg = "rg-bettinjimmy"; $app = "bettinjimmy"
git push
$rev = az containerapp revision list --subscription $sub -g $rg -n $app --query "[?properties.active].name | [0]" -o tsv
az containerapp revision restart --subscription $sub -g $rg -n $app --revision $rev -o none
$fqdn = az containerapp show --subscription $sub -g $rg -n $app --query properties.configuration.ingress.fqdn -o tsv
Write-Host "Restarted. https://$fqdn (first load after it's been idle takes about a minute)"
