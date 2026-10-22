from __future__ import annotations

import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from licensing.models import Licence
from licensing.services import appliquer_seuils_zabbix
from supervision.models import Alerte, EtatMachine
from supervision.zabbix_client import ZabbixAPIError, ZabbixClient


def _client_ou_403(user):
    if user.is_staff and user.client_id is None:
        return None  # staff sans client : pas d'espace client
    if not user.client_id:
        raise Http404("Espace client indisponible.")
    return user.client


def _licences_client(client):
    return (
        Licence.objects.filter(client=client)
        .exclude(etat=Licence.Etat.GENEREE)
        .select_related("client", "etat_machine")
    )


@login_required
def accueil(request):
    client = _client_ou_403(request.user)
    if client is None:
        return redirect("admin:index")

    licences = list(_licences_client(client))
    machines = []
    for licence in licences:
        try:
            etat = licence.etat_machine
        except EtatMachine.DoesNotExist:
            etat = None
        alertes_actives = licence.alertes.filter(active=True).count()
        machines.append(
            {
                "licence": licence,
                "etat": etat,
                "couleur": etat.couleur if etat else "orange",
                "statut_label": etat.get_statut_display() if etat else "Inconnu",
                "alertes_actives": alertes_actives,
            }
        )

    alertes = (
        Alerte.objects.filter(licence__client=client, active=True)
        .select_related("licence")
        .order_by("-date_debut")[:50]
    )

    return render(
        request,
        "dashboard/accueil.html",
        {
            "client": client,
            "machines": machines,
            "alertes": alertes,
        },
    )


@login_required
@require_GET
def api_etat(request):
    """JSON pour le rafraîchissement automatique (30 s)."""
    client = _client_ou_403(request.user)
    if client is None:
        return JsonResponse({"detail": "Réservé aux clients."}, status=403)

    machines = []
    for licence in _licences_client(client):
        try:
            etat = licence.etat_machine
        except EtatMachine.DoesNotExist:
            etat = None
        machines.append(
            {
                "id": licence.pk,
                "identifiant": licence.identifiant,
                "cle": licence.cle,
                "systeme": licence.systeme,
                "couleur": etat.couleur if etat else "orange",
                "statut": etat.statut if etat else "inconnu",
                "statut_label": etat.get_statut_display() if etat else "Inconnu",
                "cpu_pct": etat.cpu_pct if etat else None,
                "memoire_pct": etat.memoire_pct if etat else None,
                "disque_pct": etat.disque_pct if etat else None,
                "agent_disponible": etat.agent_disponible if etat else False,
                "alertes_actives": licence.alertes.filter(active=True).count(),
            }
        )

    alertes = [
        {
            "id": a.pk,
            "titre": a.titre,
            "severite": a.severite,
            "severite_label": a.get_severite_display(),
            "machine": a.licence.identifiant,
            "date_debut": a.date_debut.isoformat(),
        }
        for a in Alerte.objects.filter(licence__client=client, active=True)
        .select_related("licence")
        .order_by("-date_debut")[:50]
    ]

    return JsonResponse({"machines": machines, "alertes": alertes})


@login_required
def machine_detail(request, licence_id: int):
    client = _client_ou_403(request.user)
    if client is None:
        return redirect("admin:index")

    licence = get_object_or_404(Licence, pk=licence_id, client=client)
    try:
        etat = licence.etat_machine
    except EtatMachine.DoesNotExist:
        etat = None

    alertes = licence.alertes.order_by("-date_debut")[:30]
    return render(
        request,
        "dashboard/machine.html",
        {
            "client": client,
            "licence": licence,
            "etat": etat,
            "alertes": alertes,
        },
    )


@login_required
@require_GET
def api_graphiques(request, licence_id: int):
    client = _client_ou_403(request.user)
    if client is None:
        return JsonResponse({"detail": "Réservé aux clients."}, status=403)

    licence = get_object_or_404(Licence, pk=licence_id, client=client)
    periode = request.GET.get("periode", "1h")
    now = int(time.time())
    durees = {"1h": 3600, "24h": 86400, "7j": 7 * 86400}
    duree = durees.get(periode, 3600)
    time_from = now - duree

    if not licence.zabbix_hostid:
        return JsonResponse({"series": {}, "periode": periode})

    zabbix = ZabbixClient()
    series: dict = {"cpu": [], "memoire": [], "disque": []}

    try:
        items = zabbix.call(
            "item.get",
            {
                "hostids": [licence.zabbix_hostid],
                "search": {"key_": "util"},
                "searchWildcards": True,
                "output": ["itemid", "key_", "value_type", "name"],
                "limit": 50,
            },
        )
        fs_items = zabbix.call(
            "item.get",
            {
                "hostids": [licence.zabbix_hostid],
                "search": {"key_": "pused"},
                "searchWildcards": True,
                "output": ["itemid", "key_", "value_type", "name"],
                "limit": 50,
            },
        )
        items = (items or []) + (fs_items or [])
    except ZabbixAPIError:
        return JsonResponse({"series": series, "periode": periode, "erreur": "zabbix"})

    mapping = {}
    for item in items:
        key = item.get("key_", "")
        if "cpu.util" in key and "cpu" not in mapping:
            mapping["cpu"] = item
        elif "memory.util" in key and "memoire" not in mapping:
            mapping["memoire"] = item
        elif "pused" in key and "disque" not in mapping:
            mapping["disque"] = item

    use_trends = periode == "7j"
    for nom, item in mapping.items():
        item_id = item["itemid"]
        value_type = int(item.get("value_type", 0))
        points = []
        try:
            if use_trends:
                rows = zabbix.get_trends(
                    item_id, time_from=time_from, time_till=now
                )
                for row in rows or []:
                    points.append(
                        {
                            "t": int(row["clock"]) * 1000,
                            "v": float(row.get("value_avg") or 0),
                        }
                    )
            else:
                rows = zabbix.get_history(
                    item_id,
                    value_type=value_type,
                    time_from=time_from,
                    time_till=now,
                )
                for row in rows or []:
                    points.append(
                        {
                            "t": int(row["clock"]) * 1000,
                            "v": float(row.get("value") or 0),
                        }
                    )
        except (ZabbixAPIError, TypeError, ValueError):
            points = []
        series[nom] = points

    return JsonResponse({"series": series, "periode": periode})


@login_required
@require_POST
def mettre_a_jour_seuils(request, licence_id: int):
    client = _client_ou_403(request.user)
    if client is None:
        return redirect("admin:index")

    licence = get_object_or_404(Licence, pk=licence_id, client=client)
    try:
        licence.seuil_cpu = int(request.POST.get("seuil_cpu", licence.seuil_cpu))
        licence.seuil_memoire = int(
            request.POST.get("seuil_memoire", licence.seuil_memoire)
        )
        licence.seuil_disque = int(
            request.POST.get("seuil_disque", licence.seuil_disque)
        )
        licence.full_clean()
        licence.save(update_fields=["seuil_cpu", "seuil_memoire", "seuil_disque"])
        appliquer_seuils_zabbix(licence)
        messages.success(request, "Seuils mis à jour.")
    except (ValueError, ValidationError, ZabbixAPIError) as exc:
        messages.error(request, f"Impossible de mettre à jour les seuils : {exc}")

    return redirect("dashboard:machine", licence_id=licence.pk)


@login_required
def alertes(request):
    client = _client_ou_403(request.user)
    if client is None:
        return redirect("admin:index")

    liste = (
        Alerte.objects.filter(licence__client=client)
        .select_related("licence")
        .order_by("-date_debut")[:200]
    )
    return render(
        request,
        "dashboard/alertes.html",
        {"client": client, "alertes": liste},
    )
