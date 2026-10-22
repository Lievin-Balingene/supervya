from django.urls import path

from .views import ConnexionView, DeconnexionView, apres_connexion

urlpatterns = [
    path("login/", ConnexionView.as_view(), name="login"),
    path("logout/", DeconnexionView.as_view(), name="logout"),
    path("home/", apres_connexion, name="apres-connexion"),
]
