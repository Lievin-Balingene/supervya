from django.urls import path

from .views import ActivationAPIView

urlpatterns = [
    path("activation", ActivationAPIView.as_view(), name="api-activation"),
    path("activation/", ActivationAPIView.as_view(), name="api-activation-slash"),
]
