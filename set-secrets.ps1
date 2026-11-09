# Sets the Odds API key and the site password on the hosted app.
# Prompts for both; nothing is saved on disk or shown on screen.
$ErrorActionPreference = "Stop"
$sub = "Microsoft Azure Sponsorship"; $rg = "rg-bettinjimmy"; $app = "bettinjimmy"
function Ask($label) {
  $s = Read-Host $label -AsSecureString
  [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
}
$key = Ask "Odds API key (from the-odds-api.com)"
$pw  = Ask "Password for the site (you'll type this to get in)"
az containerapp secret set --subscription $sub -g $rg -n $app --secrets "odds-api-key=$key" "app-password=$pw" -o none
az containerapp update --subscription $sub -g $rg -n $app --set-env-vars "ODDS_API_KEY=secretref:odds-api-key" "APP_PASSWORD=secretref:app-password" -o none
Remove-Variable key, pw
Write-Host "Done. The app restarts with the new settings in about a minute."
