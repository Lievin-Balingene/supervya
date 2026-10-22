"""Tests de cloisonnement entre deux comptes clients."""
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import Client, Utilisateur
from licensing.models import Licence
from licensing.services import activer_licence
from supervision.models import Alerte
from django.utils import timezone


class IsolationClientsTests(TestCase):
    def setUp(self):
        self.org1 = Client.objects.create(
            nom="Alpha",
            email_contact="alpha@exemple.com",
            email_alertes="alpha@exemple.com",
        )
        self.org2 = Client.objects.create(
            nom="Beta",
            email_contact="beta@exemple.com",
            email_alertes="beta@exemple.com",
        )
        self.u1 = Utilisateur.objects.create_user(
            username="alpha", password="AlphaPass123!", client=self.org1
        )
        self.u2 = Utilisateur.objects.create_user(
            username="beta", password="BetaPass123!", client=self.org2
        )
        self.l1 = Licence.objects.create(client=self.org1)
        self.l2 = Licence.objects.create(client=self.org2)

        with patch("licensing.services.ZabbixClient") as mock_cls:
            mock_cls.return_value.provision_licence_host.side_effect = ["101", "102"]
            activer_licence(self.l1.cle, "192.0.2.1")
            activer_licence(self.l2.cle, "192.0.2.2")

        self.l1.refresh_from_db()
        self.l2.refresh_from_db()

        Alerte.objects.create(
            licence=self.l1,
            zabbix_eventid="e1",
            titre="Alerte Alpha",
            severite=Alerte.Severite.HAUTE,
            active=True,
            date_debut=timezone.now(),
        )
        Alerte.objects.create(
            licence=self.l2,
            zabbix_eventid="e2",
            titre="Alerte Beta",
            severite=Alerte.Severite.HAUTE,
            active=True,
            date_debut=timezone.now(),
        )

    def test_api_etat_filtre_par_client(self):
        self.client.login(username="alpha", password="AlphaPass123!")
        data = self.client.get(reverse("dashboard:api-etat")).json()
        ids = {m["id"] for m in data["machines"]}
        self.assertIn(self.l1.pk, ids)
        self.assertNotIn(self.l2.pk, ids)
        titres = {a["titre"] for a in data["alertes"]}
        self.assertIn("Alerte Alpha", titres)
        self.assertNotIn("Alerte Beta", titres)

    def test_page_alertes_filtre_par_client(self):
        self.client.login(username="beta", password="BetaPass123!")
        response = self.client.get(reverse("dashboard:alertes"))
        self.assertContains(response, "Alerte Beta")
        self.assertNotContains(response, "Alerte Alpha")
