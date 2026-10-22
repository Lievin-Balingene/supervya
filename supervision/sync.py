"""Synchronisation périodique Zabbix → Supervya (alertes, état, contrôle IP)."""
from __future__ import annotations

import logging
from datetime import datetime

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from licensing.models import Licence
from licensing.services import synchroniser_etat_hote_zabbix
from supervision.models import Alerte, EtatMachine
from supervision.zabbix_client import ZabbixAPIError, ZabbixClient

logger = logging.getLogger(__name__)

# Correspondance sévérité Zabbix (0–5) → Supervya
SEVERITE_ZABBIX = {
    "0": Alerte.Severite.INFORMATION,
    "1": Alerte.Severite.INFORMATION,
    "2": Alerte.Severite.AVERTISSEMENT,
    "3": Alerte.Severite.MOYENNE,
    "4": Alerte.Severite.HAUTE,
    "5": Alerte.Severite.DISASTER,
}

KEYS_METRIQUES = [
    "system.cpu.util",
    "vm.memory.util",
    "vfs.fs.dependent.pused[/,pused]",
    "vfs.fs.size[/,pused]",
]


def _clock_to_datetime(clock) -> datetime:
    try:
        return datetime.fromtimestamp(int(clock), tz=timezone.get_current_timezone())
    except (TypeError, ValueError, OSError):
        return timezone.now()


def synchroniser_tout(client: ZabbixClient | None = None) -> dict:
    """Exécute un cycle complet de synchronisation."""
    zabbix = client or ZabbixClient()
    stats = {
        "licences": 0,
        "alertes_creees": 0,
        "alertes_maj": 0,
        "ip_ecarts": 0,
        "erreurs": 0,
    }

    licences = (
        Licence.objects.filter(zabbix_hostid__gt="")
        .exclude(etat=Licence.Etat.GENEREE)
        .select_related("client")
    )

    for licence in licences:
        stats["licences"] += 1
        try:
            licence.marquer_expiree_si_necessaire()
            synchroniser_etat_hote_zabbix(licence, client=zabbix)
            synchroniser_etat_machine(licence, zabbix)
            crees, maj = synchroniser_alertes(licence, zabbix)
            stats["alertes_creees"] += crees
            stats["alertes_maj"] += maj
            if controler_ip(licence, zabbix):
                stats["ip_ecarts"] += 1
        except ZabbixAPIError:
            logger.exception("Sync Zabbix échouée pour licence %s", licence.cle)
            stats["erreurs"] += 1
        except Exception:
            logger.exception("Erreur inattendue pour licence %s", licence.cle)
            stats["erreurs"] += 1

    return stats


def synchroniser_etat_machine(licence: Licence, zabbix: ZabbixClient) -> EtatMachine:
    etat, _ = EtatMachine.objects.get_or_create(licence=licence)

    if licence.etat != Licence.Etat.ACTIVE:
        etat.statut = EtatMachine.Statut.HORS_LIGNE
        etat.agent_disponible = False
        etat.save()
        return etat

    host = zabbix.get_host(licence.zabbix_hostid)
    active_avail = None
    if host is not None:
        raw = host.get("active_available")
        active_avail = int(raw) if raw is not None else None

    # 1 = disponible, 2 = indisponible (Zabbix)
    etat.agent_disponible = active_avail == 1

    cpu = mem = disk = None
    items = zabbix.get_items(licence.zabbix_hostid, KEYS_METRIQUES)
    # Élargir la recherche si les clés exactes du template diffèrent
    if not items:
        items = zabbix.call(
            "item.get",
            {
                "hostids": [licence.zabbix_hostid],
                "search": {"key_": "cpu.util"},
                "searchWildcards": True,
                "output": ["itemid", "key_", "lastvalue", "lastclock"],
                "limit": 20,
            },
        ) + zabbix.call(
            "item.get",
            {
                "hostids": [licence.zabbix_hostid],
                "search": {"key_": "memory.util"},
                "searchWildcards": True,
                "output": ["itemid", "key_", "lastvalue", "lastclock"],
                "limit": 10,
            },
        ) + zabbix.call(
            "item.get",
            {
                "hostids": [licence.zabbix_hostid],
                "search": {"key_": "vfs.fs"},
                "searchWildcards": True,
                "output": ["itemid", "key_", "lastvalue", "lastclock"],
                "limit": 30,
            },
        )

    last_clock = None
    for item in items or []:
        key = item.get("key_", "")
        try:
            value = float(item.get("lastvalue") or 0)
        except (TypeError, ValueError):
            continue
        clock = item.get("lastclock")
        if clock and (last_clock is None or int(clock) > last_clock):
            last_clock = int(clock)

        if "cpu.util" in key and cpu is None:
            cpu = value
        elif "memory.util" in key and mem is None:
            mem = value
        elif ("pused" in key or "vfs.fs.size" in key) and ("/" in key or "C:" in key or "pused" in key):
            if disk is None or ("[/,pused]" in key or "[/]" in key):
                disk = value

    etat.cpu_pct = cpu
    etat.memoire_pct = mem
    etat.disque_pct = disk
    if last_clock:
        etat.derniere_donnees = _clock_to_datetime(last_clock)

    if not etat.agent_disponible:
        etat.statut = EtatMachine.Statut.HORS_LIGNE
    else:
        etat.statut = _calculer_statut(cpu, mem, disk, licence)

    etat.save()
    return etat


def _calculer_statut(cpu, mem, disk, licence: Licence) -> str:
    valeurs = [
        (cpu, licence.seuil_cpu),
        (mem, licence.seuil_memoire),
        (disk, licence.seuil_disque),
    ]
    critique = False
    attention = False
    for valeur, seuil in valeurs:
        if valeur is None:
            continue
        if valeur >= seuil:
            critique = True
        elif valeur >= max(seuil - 10, 1):
            attention = True
    if critique:
        return EtatMachine.Statut.CRITIQUE
    if attention:
        return EtatMachine.Statut.ATTENTION
    return EtatMachine.Statut.OK


def synchroniser_alertes(licence: Licence, zabbix: ZabbixClient) -> tuple[int, int]:
    problems = zabbix.get_problems([licence.zabbix_hostid])
    event_ids_actifs = set()
    crees = maj = 0

    for problem in problems or []:
        event_id = str(problem.get("eventid") or "")
        if not event_id:
            continue
        event_ids_actifs.add(event_id)
        titre = problem.get("name") or f"Problème Zabbix {event_id}"
        severite = SEVERITE_ZABBIX.get(
            str(problem.get("severity", "2")),
            Alerte.Severite.AVERTISSEMENT,
        )
        date_debut = _clock_to_datetime(problem.get("clock"))

        with transaction.atomic():
            alerte, created = Alerte.objects.select_for_update().get_or_create(
                licence=licence,
                zabbix_eventid=event_id,
                defaults={
                    "titre": titre,
                    "message": titre,
                    "severite": severite,
                    "active": True,
                    "date_debut": date_debut,
                },
            )
            if created:
                crees += 1
                _envoyer_email_alerte(licence, alerte)
            else:
                changed = False
                if not alerte.active:
                    alerte.active = True
                    alerte.date_fin = None
                    changed = True
                if alerte.titre != titre:
                    alerte.titre = titre
                    alerte.message = titre
                    changed = True
                if alerte.severite != severite:
                    alerte.severite = severite
                    changed = True
                if changed:
                    alerte.save()
                    maj += 1

    # Clôturer les alertes Zabbix disparues (hors écart IP local)
    a_cloturer = Alerte.objects.filter(
        licence=licence,
        active=True,
    ).exclude(severite=Alerte.Severite.IP_ECART).exclude(zabbix_eventid="")

    for alerte in a_cloturer:
        if alerte.zabbix_eventid not in event_ids_actifs:
            alerte.active = False
            alerte.date_fin = timezone.now()
            alerte.save(update_fields=["active", "date_fin", "date_mise_a_jour"])
            maj += 1

    return crees, maj


def _envoyer_email_alerte(licence: Licence, alerte: Alerte) -> None:
    destinataire = licence.client.email_alertes or licence.client.email_contact
    if not destinataire:
        return
    sujet = f"[Supervya] Alerte — {licence.identifiant} — {alerte.titre}"
    corps = (
        f"Bonjour,\n\n"
        f"Une alerte a été détectée sur la machine {licence.identifiant}.\n\n"
        f"Titre : {alerte.titre}\n"
        f"Sévérité : {alerte.get_severite_display()}\n"
        f"Début : {alerte.date_debut}\n\n"
        f"— Supervya\n"
    )
    try:
        send_mail(
            sujet,
            corps,
            settings.DEFAULT_FROM_EMAIL,
            [destinataire],
            fail_silently=True,
        )
        alerte.email_envoye = True
        alerte.save(update_fields=["email_envoye", "date_mise_a_jour"])
    except Exception:
        logger.exception("Envoi e-mail alerte échoué pour %s", licence.cle)


def controler_ip(licence: Licence, zabbix: ZabbixClient) -> bool:
    """
    RG-04 : si l'IP agent ≠ IP licence → désactive l'hôte et crée une alerte.
    Retourne True en cas d'écart détecté.
    """
    if licence.etat != Licence.Etat.ACTIVE or not licence.adresse_ip:
        return False

    ip_agent = zabbix.get_agent_connection_ip(licence.zabbix_hostid)
    if not ip_agent:
        return False

    if ip_agent.strip() == str(licence.adresse_ip).strip():
        # Résoudre une éventuelle alerte d'écart précédente
        Alerte.objects.filter(
            licence=licence,
            severite=Alerte.Severite.IP_ECART,
            active=True,
        ).update(active=False, date_fin=timezone.now())
        return False

    zabbix.set_host_status(licence.zabbix_hostid, disabled=True)

    alerte, created = Alerte.objects.get_or_create(
        licence=licence,
        zabbix_eventid=f"ip-mismatch-{licence.pk}",
        defaults={
            "titre": "Écart d'adresse IP détecté",
            "message": (
                f"IP licence : {licence.adresse_ip} — "
                f"IP agent : {ip_agent}. Hôte désactivé."
            ),
            "severite": Alerte.Severite.IP_ECART,
            "active": True,
            "date_debut": timezone.now(),
        },
    )
    if not created and not alerte.active:
        alerte.active = True
        alerte.date_fin = None
        alerte.message = (
            f"IP licence : {licence.adresse_ip} — "
            f"IP agent : {ip_agent}. Hôte désactivé."
        )
        alerte.save()
        created = True

    if created or not alerte.email_envoye:
        _envoyer_email_alerte(licence, alerte)

    etat, _ = EtatMachine.objects.get_or_create(licence=licence)
    etat.statut = EtatMachine.Statut.CRITIQUE
    etat.agent_disponible = False
    etat.save(update_fields=["statut", "agent_disponible", "date_mise_a_jour"])

    logger.warning(
        "RG-04 : écart IP pour %s (licence=%s, agent=%s)",
        licence.cle,
        licence.adresse_ip,
        ip_agent,
    )
    return True
