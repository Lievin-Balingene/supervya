from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def administrateur_requis(view_func):
    """Réservé aux administrateurs internes Supervya (is_staff)."""

    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return _wrapped


def client_requis(view_func):
    """Réservé aux utilisateurs rattachés à un client."""

    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_staff and not request.user.client_id:
            return redirect("dashboard:gestion")
        if not request.user.client_id:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return _wrapped
