from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect

from dashboard.forms import ConnexionForm


class ConnexionView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = ConnexionForm
    redirect_authenticated_user = True

    def get_success_url(self):
        user = self.request.user
        if user.is_staff and not user.client_id:
            return "/gestion/"
        return "/"


class DeconnexionView(LogoutView):
    next_page = "login"


def apres_connexion(request):
    """Point d'entrée après auth : oriente admin ou client."""
    if not request.user.is_authenticated:
        return redirect("login")
    if request.user.is_staff and not request.user.client_id:
        return redirect("dashboard:gestion")
    return redirect("dashboard:accueil")
