from django.urls import path

from . import gestion_views, views

app_name = "dashboard"

urlpatterns = [
    # Espace client
    path("", views.accueil, name="accueil"),
    path("licences/", views.licences_client, name="licences"),
    path("alertes/", views.alertes, name="alertes"),
    path(
        "alertes/<int:alerte_id>/marquer/",
        views.marquer_alerte_lue,
        name="alerte-marquer",
    ),
    path("machines/<int:licence_id>/", views.machine_detail, name="machine"),
    path(
        "machines/<int:licence_id>/seuils/",
        views.mettre_a_jour_seuils,
        name="seuils",
    ),
    path("api/etat/", views.api_etat, name="api-etat"),
    path(
        "api/machines/<int:licence_id>/graphiques/",
        views.api_graphiques,
        name="api-graphiques",
    ),
    # Espace administrateur Supervya
    path("gestion/", gestion_views.gestion_accueil, name="gestion"),
    path("gestion/clients/", gestion_views.clients_liste, name="gestion-clients"),
    path("gestion/clients/nouveau/", gestion_views.client_creer, name="gestion-client-creer"),
    path(
        "gestion/clients/<int:client_id>/",
        gestion_views.client_modifier,
        name="gestion-client-modifier",
    ),
    path("gestion/licences/", gestion_views.licences_liste, name="gestion-licences"),
    path(
        "gestion/licences/nouvelle/",
        gestion_views.licence_creer,
        name="gestion-licence-creer",
    ),
    path(
        "gestion/licences/<int:licence_id>/",
        gestion_views.licence_detail,
        name="gestion-licence",
    ),
    path(
        "gestion/licences/<int:licence_id>/suspendre/",
        gestion_views.licence_suspendre,
        name="gestion-licence-suspendre",
    ),
    path(
        "gestion/licences/<int:licence_id>/revoquer/",
        gestion_views.licence_revoquer,
        name="gestion-licence-revoquer",
    ),
    path(
        "gestion/licences/<int:licence_id>/renouveler/",
        gestion_views.licence_renouveler,
        name="gestion-licence-renouveler",
    ),
    path(
        "gestion/utilisateurs/",
        gestion_views.utilisateurs_liste,
        name="gestion-utilisateurs",
    ),
    path(
        "gestion/utilisateurs/nouveau/",
        gestion_views.utilisateur_creer,
        name="gestion-utilisateur-creer",
    ),
]
