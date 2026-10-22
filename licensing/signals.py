from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import Licence


@receiver(pre_save, sender=Licence)
def memoriser_etat_precedent(sender, instance: Licence, **kwargs):
    if not instance.pk:
        instance._etat_precedent = None
        instance._seuils_precedents = None
        return
    try:
        ancien = Licence.objects.get(pk=instance.pk)
    except Licence.DoesNotExist:
        instance._etat_precedent = None
        instance._seuils_precedents = None
        return
    instance._etat_precedent = ancien.etat
    instance._seuils_precedents = (
        ancien.seuil_cpu,
        ancien.seuil_memoire,
        ancien.seuil_disque,
    )
