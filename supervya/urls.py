"""URL racine — Supervya."""
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Supervya — Administration"
admin.site.site_title = "Supervya"
admin.site.index_title = "Gestion de la plateforme"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("api/", include("licensing.urls")),
    path("", include("dashboard.urls")),
]
