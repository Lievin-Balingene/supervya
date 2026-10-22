# Installation de Zabbix Agent 2 (checks actifs) pour Supervya — Windows
# Usage :
#   $env:SUPERVYA_API_URL = "https://supervya.exemple.com"
#   .\supervya-install.ps1 -LicenceKey "SPV-XXXX-XXXX-XXXX-XXXX"
# Exécuter en administrateur.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$LicenceKey,

    [string]$ApiUrl = $env:SUPERVYA_API_URL,

    [string]$AgentConfDir = "C:\Program Files\Zabbix Agent 2",

    [string]$AgentMsiUrl = $env:ZABBIX_AGENT_MSI_URL
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Ce script doit être exécuté en tant qu'administrateur."
    }
}

function Get-JsonProperty {
    param([object]$Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $null }
    return $prop.Value
}

Assert-Administrator

if ([string]::IsNullOrWhiteSpace($ApiUrl)) {
    throw "Définissez SUPERVYA_API_URL ou passez -ApiUrl."
}

$activationUrl = $ApiUrl.TrimEnd("/") + "/api/activation"
Write-Host "==> Supervya : activation de la licence…"

$body = @{ licence_key = $LicenceKey.Trim().ToUpperInvariant() } | ConvertTo-Json
try {
    $response = Invoke-RestMethod -Method Post -Uri $activationUrl -ContentType "application/json" -Body $body
}
catch {
    throw "Échec de l'activation : $($_.Exception.Message)"
}

$hostname = Get-JsonProperty $response "Hostname"
$serverActive = Get-JsonProperty $response "ServerActive"
$pskIdentity = Get-JsonProperty $response "PSKIdentity"
$psk = Get-JsonProperty $response "PSK"

if ([string]::IsNullOrWhiteSpace($hostname) -or
    [string]::IsNullOrWhiteSpace($serverActive) -or
    [string]::IsNullOrWhiteSpace($psk)) {
    throw "Réponse d'activation invalide."
}

$agentExe = Join-Path $AgentConfDir "zabbix_agent2.exe"
if (-not (Test-Path $agentExe)) {
    Write-Host "==> Zabbix Agent 2 introuvable dans '$AgentConfDir'."
    if ([string]::IsNullOrWhiteSpace($AgentMsiUrl)) {
        Write-Host "Installez Zabbix Agent 2 (Windows), puis relancez ce script."
        Write-Host "Téléchargement : https://www.zabbix.com/download_agents"
        throw "Zabbix Agent 2 non installé."
    }
    $msiPath = Join-Path $env:TEMP "zabbix_agent2_supervya.msi"
    Invoke-WebRequest -Uri $AgentMsiUrl -OutFile $msiPath
    Start-Process msiexec.exe -ArgumentList "/i `"$msiPath`" /qn" -Wait
}

$pskFile = Join-Path $AgentConfDir "supervya.psk"
$confFile = Join-Path $AgentConfDir "zabbix_agent2.d\supervya.conf"
$confDir = Split-Path $confFile -Parent
New-Item -ItemType Directory -Force -Path $confDir | Out-Null

Set-Content -Path $pskFile -Value $psk -Encoding ascii -NoNewline
icacls $pskFile /inheritance:r | Out-Null
icacls $pskFile /grant:r "SYSTEM:R" "Administrators:R" "NT SERVICE\Zabbix Agent 2:R" 2>$null | Out-Null

@"
# Configuration Supervya — générée automatiquement
Hostname=$hostname
ServerActive=$serverActive
Server=127.0.0.1
StartAgents=0
TLSConnect=psk
TLSAccept=psk
TLSPSKIdentity=$pskIdentity
TLSPSKFile=$pskFile
Timeout=30
UserParameter=supervya.agent.ip,powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { `$_.IPAddress -notlike '127.*' -and `$_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1 -ExpandProperty IPAddress)"
"@ | Set-Content -Path $confFile -Encoding ascii

Write-Host "==> Redémarrage du service Zabbix Agent 2…"
$service = Get-Service -Name "Zabbix Agent 2" -ErrorAction SilentlyContinue
if ($null -eq $service) {
    $service = Get-Service | Where-Object { $_.Name -like "*Zabbix*Agent*2*" } | Select-Object -First 1
}
if ($null -eq $service) {
    throw "Service Zabbix Agent 2 introuvable. Vérifiez l'installation."
}

Restart-Service -Name $service.Name -Force
Write-Host "Installation Supervya terminée. Hostname=$hostname"
