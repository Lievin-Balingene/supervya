#!/usr/bin/env bash
# Installation de Zabbix Agent 2 (checks actifs) pour Supervya — Linux
set -euo pipefail

SUPERVYA_API_URL="${SUPERVYA_API_URL:-}"
LICENCE_KEY="${1:-${LICENCE_KEY:-}}"
ZABBIX_AGENT_CONF_DIR="${ZABBIX_AGENT_CONF_DIR:-/etc/zabbix}"
PSK_FILE="${ZABBIX_AGENT_CONF_DIR}/supervya.psk"
CONF_FILE="${ZABBIX_AGENT_CONF_DIR}/zabbix_agent2.d/supervya.conf"

usage() {
  echo "Usage:"
  echo "  export SUPERVYA_API_URL=https://supervya.votredomaine.com"
  echo "  curl -fsSL https://raw.githubusercontent.com/Lievin-Balingene/supervya/main/scripts/supervya-install.sh -o /tmp/supervya-install.sh"
  echo "  sudo -E bash /tmp/supervya-install.sh SPV-XXXX-XXXX-XXXX-XXXX"
  exit 1
}

[[ -n "${SUPERVYA_API_URL}" ]] || usage
[[ -n "${LICENCE_KEY}" ]] || usage

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Ce script doit être exécuté en root (sudo)." >&2
  exit 1
fi

echo "==> Supervya : activation de la licence…"
RESPONSE="$(curl -fsS -X POST "${SUPERVYA_API_URL%/}/api/activation" \
  -H "Content-Type: application/json" \
  -d "{\"licence_key\": \"${LICENCE_KEY}\"}")"

HOSTNAME="$(printf '%s' "${RESPONSE}" | sed -n 's/.*"Hostname"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
SERVER_ACTIVE="$(printf '%s' "${RESPONSE}" | sed -n 's/.*"ServerActive"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
PSK_IDENTITY="$(printf '%s' "${RESPONSE}" | sed -n 's/.*"PSKIdentity"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
PSK="$(printf '%s' "${RESPONSE}" | sed -n 's/.*"PSK"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"

if [[ -z "${HOSTNAME}" || -z "${SERVER_ACTIVE}" || -z "${PSK}" ]]; then
  echo "Réponse d'activation invalide:" >&2
  echo "${RESPONSE}" >&2
  exit 1
fi

echo "==> Installation de Zabbix Agent 2 (si nécessaire)…"
if ! command -v zabbix_agent2 >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq zabbix-agent2 || {
      echo "Installez zabbix-agent2 manuellement puis relancez ce script." >&2
      exit 1
    }
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y zabbix-agent2
  elif command -v yum >/dev/null 2>&1; then
    yum install -y zabbix-agent2
  else
    echo "Gestionnaire de paquets non supporté. Installez zabbix-agent2 puis relancez." >&2
    exit 1
  fi
fi

mkdir -p "${ZABBIX_AGENT_CONF_DIR}/zabbix_agent2.d"

umask 077
printf '%s\n' "${PSK}" > "${PSK_FILE}"
chown zabbix:zabbix "${PSK_FILE}" 2>/dev/null || chown root:root "${PSK_FILE}"
chmod 600 "${PSK_FILE}"

cat > "${CONF_FILE}" <<EOF
# Configuration Supervya — générée automatiquement
Hostname=${HOSTNAME}
ServerActive=${SERVER_ACTIVE}
Server=127.0.0.1
StartAgents=0
TLSConnect=psk
TLSAccept=psk
TLSPSKIdentity=${PSK_IDENTITY}
TLSPSKFile=${PSK_FILE}
Timeout=30
UserParameter=supervya.agent.ip,hostname -I 2>/dev/null | awk '{print \$1}'
EOF

chmod 644 "${CONF_FILE}"

# Item personnalisé côté serveur : créé automatiquement si un template Supervya
# est lié ; sinon la clé reste disponible pour un item manuel.

echo "==> Démarrage de zabbix-agent2…"
if command -v systemctl >/dev/null 2>&1; then
  systemctl enable zabbix-agent2
  systemctl restart zabbix-agent2
  systemctl --no-pager --full status zabbix-agent2 || true
else
  service zabbix-agent2 restart || true
fi

echo "Installation Supervya terminée. Hostname=${HOSTNAME}"
