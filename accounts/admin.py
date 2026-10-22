from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Client, Utilisateur


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("nom", "email_contact", "email_alertes", "actif", "date_creation")
    list_filter = ("actif",)
    search_fields = ("nom", "email_contact", "email_alertes")
    ordering = ("nom",)


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display = ("username", "email", "client", "is_staff", "is_active")
    list_filter = ("is_staff", "is_active", "client")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username",)
    fieldsets = UserAdmin.fieldsets + (
        ("Rattachement Supervya", {"fields": ("client",)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Rattachement Supervya", {"fields": ("client",)}),
    )
