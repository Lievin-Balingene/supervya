"""
Client unique d'accès à l'API JSON-RPC Zabbix pour Supervya.

Aucun autre module ne doit appeler Zabbix directement.
"""
from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TEMPLATE_LINUX_ACTIVE = "Linux by Zabbix agent active"
TEMPLATE_WINDOWS_ACTIVE = "Windows by Zabbix agent active"

MACRO_CPU = "{$CPU.UTIL.CRIT}"
MACRO_MEMORY = "{$MEMORY.UTIL.MAX}"
MACRO_DISK = "{$VFS.FS.PUSED.MAX.CRIT}"


class ZabbixAPIError(Exception):
    """Erreur renvoyée par l'API Zabbix ou le transport HTTP."""

    def __init__(self, message: str, *, code: int | None = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class ZabbixClient:
    """Client JSON-RPC authentifié par jeton d'API (Bearer)."""

    def __init__(
        self,
        api_url: str | None = None,
        api_token: str | None = None,
        timeout: int = 30,
        session: requests.Session | None = None,
    ):
        self.api_url = api_url or settings.ZABBIX_API_URL
        self.api_token = api_token if api_token is not None else settings.ZABBIX_API_TOKEN
        self.timeout = timeout
        self.session = session or requests.Session()
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def call(self, method: str, params: dict | list | None = None) -> Any:
        if not self.api_token:
            raise ZabbixAPIError("ZABBIX_API_TOKEN non configuré.")

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params if params is not None else {},
            "id": self._next_id(),
        }
        headers = {
            "Content-Type": "application/json-rpc",
            "Authorization": f"Bearer {self.api_token}",
        }
        try:
            response = self.session.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ZabbixAPIError(f"Échec HTTP vers Zabbix: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise ZabbixAPIError("Réponse Zabbix non JSON.") from exc

        if "error" in body:
            err = body["error"]
            raise ZabbixAPIError(
                err.get("message", "Erreur Zabbix"),
                code=err.get("code"),
                data=err.get("data"),
            )
        return body.get("result")

    # --- Groupes d'hôtes -------------------------------------------------

    def ensure_host_group(self, name: str) -> str:
        """Retourne le groupid, en créant le groupe s'il n'existe pas."""
        existing = self.call(
            "hostgroup.get",
            {"filter": {"name": [name]}, "output": ["groupid"]},
        )
        if existing:
            return str(existing[0]["groupid"])
        created = self.call("hostgroup.create", {"name": name})
        return str(created["groupids"][0])

    def client_group_name(self, client_id: int) -> str:
        return f"supervya-client-{client_id}"

    # --- Templates -------------------------------------------------------

    def get_template_id(self, template_name: str) -> str:
        result = self.call(
            "template.get",
            {"filter": {"host": [template_name]}, "output": ["templateid"]},
        )
        if not result:
            # Certains templates sont filtrables par name plutôt que host
            result = self.call(
                "template.get",
                {"filter": {"name": [template_name]}, "output": ["templateid"]},
            )
        if not result:
            raise ZabbixAPIError(f"Template introuvable: {template_name}")
        return str(result[0]["templateid"])

    def template_name_for_os(self, systeme: str) -> str:
        if systeme == "windows":
            return TEMPLATE_WINDOWS_ACTIVE
        return TEMPLATE_LINUX_ACTIVE

    # --- Hôtes -----------------------------------------------------------

    def create_host(
        self,
        *,
        hostname: str,
        group_id: str,
        template_id: str,
        psk_identity: str,
        psk: str,
        adresse_ip: str | None = None,
        macros: dict[str, str] | None = None,
    ) -> str:
        """
        Crée un hôte en mode agent actif avec chiffrement PSK.
        L'interface agent enregistre l'IP d'activation (référence RG-04).
        """
        host_macros = []
        for key, value in (macros or {}).items():
            host_macros.append({"macro": key, "value": str(value)})

        params: dict[str, Any] = {
            "host": hostname,
            "name": hostname,
            "groups": [{"groupid": group_id}],
            "templates": [{"templateid": template_id}],
            "tls_connect": 2,  # PSK
            "tls_accept": 2,  # PSK
            "tls_psk_identity": psk_identity,
            "tls_psk": psk,
            "status": 0,  # activé
            "interfaces": [
                {
                    "type": 1,  # agent
                    "main": 1,
                    "useip": 1,
                    "ip": adresse_ip or "0.0.0.0",
                    "dns": "",
                    "port": "10050",
                }
            ],
        }
        if host_macros:
            params["macros"] = host_macros

        result = self.call("host.create", params)
        return str(result["hostids"][0])

    def get_host(self, host_id: str) -> dict | None:
        result = self.call(
            "host.get",
            {
                "hostids": [host_id],
                "output": [
                    "hostid",
                    "host",
                    "name",
                    "status",
                    "available",
                    "active_available",
                ],
            },
        )
        return result[0] if result else None

    def get_hosts_by_group(self, group_id: str) -> list[dict]:
        return self.call(
            "host.get",
            {
                "groupids": [group_id],
                "output": [
                    "hostid",
                    "host",
                    "name",
                    "status",
                    "available",
                    "active_available",
                ],
            },
        )

    def get_host_by_name(self, hostname: str) -> dict | None:
        result = self.call(
            "host.get",
            {
                "filter": {"host": [hostname]},
                "output": [
                    "hostid",
                    "host",
                    "name",
                    "status",
                    "available",
                    "active_available",
                ],
            },
        )
        return result[0] if result else None

    def set_host_status(self, host_id: str, disabled: bool) -> None:
        """disabled=True → status=1 (désactivé), False → status=0."""
        self.call(
            "host.update",
            {"hostid": host_id, "status": 1 if disabled else 0},
        )

    def update_host_macros(self, host_id: str, macros: dict[str, str]) -> None:
        existing = self.call(
            "usermacro.get",
            {"hostids": [host_id], "output": ["hostmacroid", "macro", "value"]},
        )
        by_name = {m["macro"]: m for m in existing}
        for macro, value in macros.items():
            if macro in by_name:
                self.call(
                    "usermacro.update",
                    {
                        "hostmacroid": by_name[macro]["hostmacroid"],
                        "value": str(value),
                    },
                )
            else:
                self.call(
                    "usermacro.create",
                    {
                        "hostid": host_id,
                        "macro": macro,
                        "value": str(value),
                    },
                )

    def threshold_macros(
        self,
        *,
        cpu: int,
        memoire: int,
        disque: int,
    ) -> dict[str, str]:
        return {
            MACRO_CPU: str(cpu),
            MACRO_MEMORY: str(memoire),
            MACRO_DISK: str(disque),
        }

    # --- Disponibilité agent / IP ----------------------------------------

    def get_active_agent_availability(self, host_id: str) -> int | None:
        """
        Retourne active_available : 0 inconnu, 1 disponible, 2 indisponible.
        """
        host = self.get_host(host_id)
        if not host:
            return None
        value = host.get("active_available")
        return int(value) if value is not None else None

    def get_agent_connection_ip(self, host_id: str) -> str | None:
        """
        IP de connexion de l'agent pour le contrôle RG-04.

        Priorité :
        1. item actif ``supervya.agent.ip`` (exposé par le script d'installation) ;
        2. interface agent principale de l'hôte.
        """
        items = self.call(
            "item.get",
            {
                "hostids": [host_id],
                "filter": {"key_": ["supervya.agent.ip"]},
                "output": ["lastvalue", "status", "state"],
            },
        )
        if items:
            value = (items[0].get("lastvalue") or "").strip()
            if value:
                return value.split()[0]

        interfaces = self.call(
            "hostinterface.get",
            {
                "hostids": [host_id],
                "filter": {"main": "1", "type": "1"},
                "output": ["ip", "dns", "useip", "type", "main"],
            },
        )
        for iface in interfaces or []:
            ip = (iface.get("ip") or "").strip()
            if ip and ip not in ("0.0.0.0",):
                return ip
        return None

    def update_host_interface_ip(self, host_id: str, adresse_ip: str) -> None:
        """Met à jour l'IP de l'interface agent principale."""
        interfaces = self.call(
            "hostinterface.get",
            {
                "hostids": [host_id],
                "filter": {"main": "1", "type": "1"},
                "output": ["interfaceid"],
            },
        )
        if not interfaces:
            return
        self.call(
            "hostinterface.update",
            {
                "interfaceid": interfaces[0]["interfaceid"],
                "ip": adresse_ip,
                "useip": 1,
            },
        )

    # --- Problèmes / historiques ----------------------------------------

    def get_problems(self, host_ids: list[str]) -> list[dict]:
        if not host_ids:
            return []
        return self.call(
            "problem.get",
            {
                "hostids": host_ids,
                "output": "extend",
                "recent": True,
                "sortfield": ["eventid"],
                "sortorder": "DESC",
            },
        )

    def get_items(self, host_id: str, keys: list[str]) -> list[dict]:
        return self.call(
            "item.get",
            {
                "hostids": [host_id],
                "filter": {"key_": keys},
                "output": [
                    "itemid",
                    "name",
                    "key_",
                    "lastvalue",
                    "lastclock",
                    "units",
                    "value_type",
                ],
            },
        )

    def get_history(
        self,
        item_id: str,
        *,
        value_type: int,
        time_from: int,
        time_till: int,
        limit: int = 5000,
    ) -> list[dict]:
        return self.call(
            "history.get",
            {
                "itemids": [item_id],
                "history": value_type,
                "time_from": time_from,
                "time_till": time_till,
                "sortfield": "clock",
                "sortorder": "ASC",
                "limit": limit,
                "output": "extend",
            },
        )

    def get_trends(
        self,
        item_id: str,
        *,
        time_from: int,
        time_till: int,
        limit: int = 5000,
    ) -> list[dict]:
        return self.call(
            "trend.get",
            {
                "itemids": [item_id],
                "time_from": time_from,
                "time_till": time_till,
                "limit": limit,
                "output": "extend",
            },
        )

    # --- Orchestration métier --------------------------------------------

    def provision_licence_host(
        self,
        *,
        client_id: int,
        identifiant: str,
        systeme: str,
        psk: str,
        seuil_cpu: int,
        seuil_memoire: int,
        seuil_disque: int,
        adresse_ip: str | None = None,
    ) -> str:
        """
        Crée groupe + hôte + template + PSK + macros (RG-03, RG-07, RG-08, RG-09).
        Retourne le hostid Zabbix.
        """
        group_id = self.ensure_host_group(self.client_group_name(client_id))
        template_id = self.get_template_id(self.template_name_for_os(systeme))
        macros = self.threshold_macros(
            cpu=seuil_cpu,
            memoire=seuil_memoire,
            disque=seuil_disque,
        )
        return self.create_host(
            hostname=identifiant,
            group_id=group_id,
            template_id=template_id,
            psk_identity=identifiant,
            psk=psk,
            adresse_ip=adresse_ip,
            macros=macros,
        )
