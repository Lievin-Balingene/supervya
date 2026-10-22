"""Espace administrateur Supervya (interfaces personnalisées, hors Django Admin)."""
from __future__ import annotations

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.models import Client, Utilisateur
from licensing.models import Licence
from licensing.services import synchroniser_etat_hote_zabbix
from supervision.models import Alerte
from supervision.zabbix_client import ZabbixAPIError

from .decorators import administrateur_requis
from .forms import ClientForm, LicenceCreateForm, LicenceIpForm, UtilisateurClientForm


@administrateur_requis
def gestion_accueil(request):
    stats = {
        "clients": Client.objects.count(),
        "clients_actifs": Client.objects.filter(actif=True).count(),
        "licences": Licence.objects.count(),
        "licences_actives": Licence.objects.filter(etat=Licence.Etat.ACTIVE).count(),
        "licences_generees": Licence.objects.filter(etat=Licence.Etat.GENEREE).count(),
        "alertes_actives": Alerte.objects.filter(active=True).count(),
        "utilisateurs": Utilisateur.objects.filter(client__isnull=False).count(),
    }
    recentes = Licence.objects.select_related("client").order_by("-date_creation")[:8]
    return render(
        request,
        "gestion/accueil.html",
        {"stats": stats, "licences_recentes": recentes},
    )


@administrateur_requis
def clients_liste(request):
    clients = Client.objects.annotate(
        nb_licences=Count("licences"),
        nb_users=Count("utilisateurs"),
    ).order_by("nom")
    return render(request, "gestion/clients_liste.html", {"clients": clients})


@administrateur_requis
@require_http_methods(["GET", "POST"])
def client_creer(request):
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save()
        messages.success(request, f"Client « {client.nom} » créé.")
        return redirect("dashboard:gestion-clients")
    return render(request, "gestion/client_form.html", {"form": form, "titre": "Nouveau client"})


@administrateur_requis
@require_http_methods(["GET", "POST"])
def client_modifier(request, client_id: int):
    client = get_object_or_404(Client, pk=client_id)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Client mis à jour.")
        return redirect("dashboard:gestion-clients")
    return render(
        request,
        "gestion/client_form.html",
        {"form": form, "titre": f"Modifier — {client.nom}", "client": client},
    )


@administrateur_requis
def licences_liste(request):
    etat = request.GET.get("etat", "")
    qs = Licence.objects.select_related("client").order_by("-date_creation")
    if etat:
        qs = qs.filter(etat=etat)
    return render(
        request,
        "gestion/licences_liste.html",
        {
            "licences": qs[:200],
            "etat_filtre": etat,
            "etats": Licence.Etat.choices,
        },
    )


@administrateur_requis
@require_http_methods(["GET", "POST"])
def licence_creer(request):
    initial = {}
    client_id = request.GET.get("client")
    if client_id:
        initial["client"] = client_id
    form = LicenceCreateForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        licence = form.save()
        messages.success(
            request,
            f"Licence générée : {licence.cle}",
        )
        return redirect("dashboard:gestion-licence", licence_id=licence.pk)
    return render(request, "gestion/licence_form.html", {"form": form})


@administrateur_requis
@require_http_methods(["GET", "POST"])
def licence_detail(request, licence_id: int):
    licence = get_object_or_404(Licence.objects.select_related("client"), pk=licence_id)
    ip_form = LicenceIpForm(initial={"adresse_ip": licence.adresse_ip or ""})

    if request.method == "POST" and "changer_ip" in request.POST:
        ip_form = LicenceIpForm(request.POST)
        if ip_form.is_valid():
            licence.adresse_ip = ip_form.cleaned_data["adresse_ip"]
            licence.save(update_fields=["adresse_ip"])
            messages.success(request, "Adresse IP mise à jour.")
            return redirect("dashboard:gestion-licence", licence_id=licence.pk)

    return render(
        request,
        "gestion/licence_detail.html",
        {"licence": licence, "ip_form": ip_form},
    )


def _action_licence(request, licence: Licence, nouvel_etat: str, label: str):
    licence.etat = nouvel_etat
    if nouvel_etat == Licence.Etat.ACTIVE:
        if not licence.date_expiration or licence.date_expiration <= timezone.now():
            licence.date_expiration = timezone.now() + timezone.timedelta(days=365)
            licence.save(update_fields=["etat", "date_expiration"])
        else:
            licence.save(update_fields=["etat"])
    else:
        licence.save(update_fields=["etat"])
    try:
        synchroniser_etat_hote_zabbix(licence)
    except ZabbixAPIError:
        messages.warning(
            request,
            f"Licence {label}, mais la synchronisation Zabbix a échoué (normal hors Docker).",
        )
    else:
        messages.success(request, f"Licence {label}.")
    return redirect("dashboard:gestion-licence", licence_id=licence.pk)


@administrateur_requis
@require_POST
def licence_suspendre(request, licence_id: int):
    licence = get_object_or_404(Licence, pk=licence_id)
    if licence.etat in (Licence.Etat.GENEREE, Licence.Etat.REVOQUEE):
        messages.error(request, "Cette licence ne peut pas être suspendue.")
        return redirect("dashboard:gestion-licence", licence_id=licence.pk)
    return _action_licence(request, licence, Licence.Etat.SUSPENDUE, "suspendue")


@administrateur_requis
@require_POST
def licence_revoquer(request, licence_id: int):
    licence = get_object_or_404(Licence, pk=licence_id)
    if licence.etat == Licence.Etat.REVOQUEE:
        messages.info(request, "Licence déjà révoquée.")
        return redirect("dashboard:gestion-licence", licence_id=licence.pk)
    return _action_licence(request, licence, Licence.Etat.REVOQUEE, "révoquée")


@administrateur_requis
@require_POST
def licence_renouveler(request, licence_id: int):
    licence = get_object_or_404(Licence, pk=licence_id)
    if licence.etat not in (Licence.Etat.SUSPENDUE, Licence.Etat.EXPIREE):
        messages.error(request, "Seules les licences suspendues ou expirées peuvent être renouvelées.")
        return redirect("dashboard:gestion-licence", licence_id=licence.pk)
    if not licence.zabbix_hostid:
        messages.error(request, "Licence jamais activée : impossible de renouveler.")
        return redirect("dashboard:gestion-licence", licence_id=licence.pk)
    return _action_licence(request, licence, Licence.Etat.ACTIVE, "renouvelée")


@administrateur_requis
def utilisateurs_liste(request):
    users = (
        Utilisateur.objects.select_related("client")
        .filter(Q(client__isnull=False) | Q(is_staff=True))
        .order_by("username")
    )
    return render(request, "gestion/utilisateurs_liste.html", {"utilisateurs": users})


@administrateur_requis
@require_http_methods(["GET", "POST"])
def utilisateur_creer(request):
    form = UtilisateurClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"Compte « {user.username} » créé.")
        return redirect("dashboard:gestion-utilisateurs")
    return render(request, "gestion/utilisateur_form.html", {"form": form})
