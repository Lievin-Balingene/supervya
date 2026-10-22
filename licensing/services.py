"""Services métier liés aux licences et à l'activation."""
from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from supervision.zabbix_client import ZabbixAPIError, ZabbixClient

from .models import Licence


class ActivationError(Exception):
    """Erreur métier lors de l'activation d'une licence."""

    def __init__(self, message: str, *, code: str = "activation_error", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def activer_licence(cle: str, adresse_ip: str, *, client: ZabbixClient | None = None) -> dict:
    """
    Active une licence GENEREE (RG-03, RG-05) :
    provisionne l'hôte Zabbix et renvoie la configuration agent.
    """
    cle = (cle or "").strip().upper()
    if not cle:
        raise ActivationError("Clé de licence manquante.", code="cle_manquante")

    with transaction.atomic():
        try:
            licence = Licence.objects.select_for_update().select_related("client").get(cle=cle)
        except Licence.DoesNotExist as exc:
            raise ActivationError(
                "Licence introuvable.",
                code="licence_introuvable",
                status=404,
            ) from exc

        if licence.etat != Licence.Etat.GENEREE:
            raise ActivationError(
                "Cette licence a déjà été activée ou n'est plus disponible.",
                code="licence_non_activable",
                status=409,
            )

        if not licence.client.actif:
            raise ActivationError(
                "Le compte client est désactivé.",
                code="client_inactif",
                status=403,
            )

        zabbix = client or ZabbixClient()
        try:
            host_id = zabbix.provision_licence_host(
                client_id=licence.client_id,
                identifiant=licence.identifiant,
                systeme=licence.systeme,
                psk=licence.psk,
                seuil_cpu=licence.seuil_cpu,
                seuil_memoire=licence.seuil_memoire,
                seuil_disque=licence.seuil_disque,
                adresse_ip=adresse_ip,
            )
        except ZabbixAPIError as exc:
            raise ActivationError(
                f"Échec de provisionnement Zabbix: {exc}",
                code="zabbix_error",
                status=502,
            ) from exc

        licence.adresse_ip = adresse_ip
        licence.zabbix_hostid = host_id
        licence.etat = Licence.Etat.ACTIVE
        licence.date_activation = timezone.now()
        licence.save(
            update_fields=[
                "adresse_ip",
                "zabbix_hostid",
                "etat",
                "date_activation",
            ]
        )

    return {
        "Hostname": licence.identifiant,
        "ServerActive": settings.ZABBIX_SERVER_ACTIVE,
        "PSKIdentity": licence.identifiant,
        "PSK": licence.psk,
        "systeme": licence.systeme,
    }


def synchroniser_etat_hote_zabbix(licence: Licence, *, client: ZabbixClient | None = None) -> None:
    """Désactive ou réactive l'hôte Zabbix selon l'état de la licence (RG-06)."""
    if not licence.zabbix_hostid:
        return
    zabbix = client or ZabbixClient()
    desactiver = licence.etat in {
        Licence.Etat.SUSPENDUE,
        Licence.Etat.EXPIREE,
        Licence.Etat.REVOQUEE,
    }
    try:
        zabbix.set_host_status(licence.zabbix_hostid, disabled=desactiver)
    except ZabbixAPIError:
        raise


def appliquer_seuils_zabbix(licence: Licence, *, client: ZabbixClient | None = None) -> None:
    """Pousse les seuils Supervya vers les macros d'hôte Zabbix."""
    if not licence.zabbix_hostid:
        return
    zabbix = client or ZabbixClient()
    macros = zabbix.threshold_macros(
        cpu=licence.seuil_cpu,
        memoire=licence.seuil_memoire,
        disque=licence.seuil_disque,
    )
    zabbix.update_host_macros(licence.zabbix_hostid, macros)
