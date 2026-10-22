from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("alertes/", views.alertes, name="alertes"),
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
]
