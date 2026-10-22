from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import ActivationError, activer_licence
from .throttling import ActivationRateThrottle


class ActivationAPIView(APIView):
    """POST /api/activation — activation d'une licence par clé."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ActivationRateThrottle]

    def post(self, request):
        cle = request.data.get("licence_key") or request.data.get("cle") or ""
        adresse_ip = self._client_ip(request)

        try:
            config = activer_licence(cle, adresse_ip)
        except ActivationError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=exc.status,
            )

        return Response(config, status=status.HTTP_201_CREATED)

    @staticmethod
    def _client_ip(request) -> str:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR") or "0.0.0.0"
