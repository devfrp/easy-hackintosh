# get.ps1 — Windows : installe Python/Git si besoin, récupère easy-hackintosh, lance l'assistant.
# Usage (PowerShell) :  irm <URL>/get.ps1 | iex
#   Variables : $env:REPO, $env:DIR, $env:EH_VERSION
#   ⚠ L'écriture sur clé USB (diskpart) exige une console PowerShell "Administrateur".
$ErrorActionPreference = 'Stop'

$Repo = if ($env:REPO) { $env:REPO } else { 'https://github.com/USER/easy-hackintosh' }
$Dir  = if ($env:DIR)  { $env:DIR }  else { Join-Path $HOME 'easy-hackintosh' }
function Say($m) { Write-Host ":: $m" -ForegroundColor Cyan }

function Ensure($cmd, $wingetId) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
      Say "Installation de $wingetId via winget"
      winget install --id $wingetId -e --accept-source-agreements --accept-package-agreements
    } else {
      throw "$cmd absent et winget indisponible. Installe $wingetId manuellement."
    }
  }
}

Ensure 'python' 'Python.Python.3.12'
Ensure 'git' 'Git.Git'

# Rafraîchir le PATH de la session (après une éventuelle install)
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
            [Environment]::GetEnvironmentVariable('Path','User')

if (Test-Path (Join-Path $Dir '.git')) {
  Say "Mise à jour de $Dir"; git -C $Dir pull --ff-only
} else {
  Say "Clonage dans $Dir"; git clone --depth 1 $Repo $Dir
}

Say "Lancement de l'assistant"
Set-Location $Dir
python easy_hackintosh.py
