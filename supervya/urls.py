"""URL racine — Supervya."""
from django.urls import include, path

urlpatterns = [
    path("accounts/", include("accounts.urls")),
    path("api/", include("licensing.urls")),
    path("", include("dashboard.urls")),
]
