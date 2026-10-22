from rest_framework.throttling import AnonRateThrottle


class ActivationRateThrottle(AnonRateThrottle):
    """Limitation de débit pour POST /api/activation (ENF-06)."""

    scope = "activation"
