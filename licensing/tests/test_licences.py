"""Tests des règles de licence (RG) et de l'activation."""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Client, Utilisateur
from licensing.models import Licence, generer_cle_licence
from licensing.services import ActivationError, activer_licence
from supervision.models import Alerte
from supervision.sync import controler_ip
from supervision.zabbix_client import ZabbixClient


class LicenceModelTests(TestCase):
    def setUp(self):
        self.client_org = Client.objects.create(
            nom="Acme",
            email_contact="acme@exemple.com",
            email_alertes="alertes@exemple.com",
        )

    def test_format_cle_rg01(self):
        cle = generer_cle_licence()
        self.assertRegex(cle, r"^SPV-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")

    def test_creation_genere_cle_et_psk_rg02(self):
        licence = Licence.objects.create(client=self.client_org)
        self.assertTrue(licence.cle.startswith("SPV-"))
        self.assertEqual(len(licence.psk), 64)
        self.assertTrue(licence.identifiant.startswith("spv-"))
        self.assertEqual(licence.etat, Licence.Etat.GENEREE)


@override_settings(
    ZABBIX_API_TOKEN="tok",
    ZABBIX_SERVER_ACTIVE="zabbix.exemple.com:10051",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class ActivationTests(TestCase):
    def setUp(self):
        self.org = Client.objects.create(
            nom="Client A",
            email_contact="a@exemple.com",
            email_alertes="a-alertes@exemple.com",
        )
        self.licence = Licence.objects.create(client=self.org, systeme="linux")

    @patch("licensing.services.ZabbixClient")
    def test_activation_ok_rg03(self, mock_cls):
        mock = mock_cls.return_value
        mock.provision_licence_host.return_value = "1001"

        config = activer_licence(self.licence.cle, "198.51.100.20", client=mock)

        self.licence.refresh_from_db()
        self.assertEqual(self.licence.etat, Licence.Etat.ACTIVE)
        self.assertEqual(self.licence.adresse_ip, "198.51.100.20")
        self.assertEqual(self.licence.zabbix_hostid, "1001")
        self.assertEqual(config["Hostname"], self.licence.identifiant)
        self.assertEqual(config["PSKIdentity"], self.licence.identifiant)
        self.assertEqual(config["ServerActive"], "zabbix.exemple.com:10051")
        mock.provision_licence_host.assert_called_once()

    @patch("licensing.services.ZabbixClient")
    def test_double_activation_refusee_rg05_cr01(self, mock_cls):
        mock = mock_cls.return_value
        mock.provision_licence_host.return_value = "1001"
        activer_licence(self.licence.cle, "198.51.100.20", client=mock)

        with self.assertRaises(ActivationError) as ctx:
            activer_licence(self.licence.cle, "198.51.100.21", client=mock)
        self.assertEqual(ctx.exception.code, "licence_non_activable")
        self.assertEqual(mock.provision_licence_host.call_count, 1)

    @patch("licensing.services.ZabbixClient")
    def test_api_activation_http(self, mock_cls):
        mock_cls.return_value.provision_licence_host.return_value = "2002"
        url = reverse("api-activation")
        response = self.client.post(
            url,
            data={"licence_key": self.licence.cle},
            content_type="application/json",
            REMOTE_ADDR="203.0.113.5",
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn("Hostname", body)
        self.assertIn("PSK", body)


@override_settings(
    ZABBIX_API_TOKEN="tok",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class RecetteTests(TestCase):
    """Critères de recette CR-01 à CR-08."""

    def setUp(self):
        self.org_a = Client.objects.create(
            nom="Org A",
            email_contact="a@exemple.com",
            email_alertes="a@exemple.com",
        )
        self.org_b = Client.objects.create(
            nom="Org B",
            email_contact="b@exemple.com",
            email_alertes="b@exemple.com",
        )
        self.user_a = Utilisateur.objects.create_user(
            username="usera",
            password="MotDePasseA123!",
            client=self.org_a,
        )
        self.user_b = Utilisateur.objects.create_user(
            username="userb",
            password="MotDePasseB123!",
            client=self.org_b,
        )
        self.licence_a = Licence.objects.create(client=self.org_a)
        self.licence_b = Licence.objects.create(client=self.org_b)

    @patch("licensing.services.ZabbixClient")
    def test_cr01_activation_unique(self, mock_cls):
        mock_cls.return_value.provision_licence_host.return_value = "1"
        activer_licence(self.licence_a.cle, "10.0.0.1")
        with self.assertRaises(ActivationError):
            activer_licence(self.licence_a.cle, "10.0.0.2")

    @patch("licensing.services.ZabbixClient")
    def test_cr02_provisionnement_zabbix(self, mock_cls):
        mock = mock_cls.return_value
        mock.provision_licence_host.return_value = "55"
        activer_licence(self.licence_a.cle, "10.0.0.1", client=mock)
        kwargs = mock.provision_licence_host.call_args.kwargs
        self.assertEqual(kwargs["identifiant"], self.licence_a.identifiant)
        self.assertEqual(kwargs["psk"], self.licence_a.psk)
        self.assertEqual(kwargs["systeme"], "linux")
        self.assertEqual(kwargs["adresse_ip"], "10.0.0.1")

    @patch("licensing.services.ZabbixClient")
    def test_cr03_cloisonnement_clients(self, mock_cls):
        mock_cls.return_value.provision_licence_host.return_value = "10"
        activer_licence(self.licence_a.cle, "10.0.0.1")
        mock_cls.return_value.provision_licence_host.return_value = "11"
        activer_licence(self.licence_b.cle, "10.0.0.2")

        self.client.login(username="usera", password="MotDePasseA123!")
        response = self.client.get(reverse("dashboard:accueil"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.licence_a.identifiant)
        self.assertNotContains(response, self.licence_b.identifiant)

        detail_b = reverse("dashboard:machine", args=[self.licence_b.pk])
        self.assertEqual(self.client.get(detail_b).status_code, 404)

        self.client.logout()
        self.client.login(username="userb", password="MotDePasseB123!")
        response = self.client.get(reverse("dashboard:accueil"))
        self.assertContains(response, self.licence_b.identifiant)
        self.assertNotContains(response, self.licence_a.identifiant)

    @patch("dashboard.views.appliquer_seuils_zabbix")
    @patch("licensing.services.ZabbixClient")
    def test_cr04_seuils_macros(self, mock_cls, mock_seuils):
        mock_cls.return_value.provision_licence_host.return_value = "10"
        activer_licence(self.licence_a.cle, "10.0.0.1")
        self.licence_a.refresh_from_db()

        self.client.login(username="usera", password="MotDePasseA123!")
        response = self.client.post(
            reverse("dashboard:seuils", args=[self.licence_a.pk]),
            {"seuil_cpu": "77", "seuil_memoire": "66", "seuil_disque": "55"},
        )
        self.assertEqual(response.status_code, 302)
        self.licence_a.refresh_from_db()
        self.assertEqual(self.licence_a.seuil_cpu, 77)
        self.assertEqual(self.licence_a.seuil_memoire, 66)
        self.assertEqual(self.licence_a.seuil_disque, 55)
        mock_seuils.assert_called()

    @patch("supervision.sync.send_mail")
    @patch("licensing.services.ZabbixClient")
    def test_cr05_alerte_et_email(self, mock_cls, mock_mail):
        mock_cls.return_value.provision_licence_host.return_value = "10"
        activer_licence(self.licence_a.cle, "10.0.0.1")
        self.licence_a.refresh_from_db()

        zabbix = MagicMock(spec=ZabbixClient)
        zabbix.get_problems.return_value = [
            {
                "eventid": "999",
                "name": "CPU critique",
                "severity": "4",
                "clock": str(int(timezone.now().timestamp())),
            }
        ]
        from supervision.sync import synchroniser_alertes

        crees, _ = synchroniser_alertes(self.licence_a, zabbix)
        self.assertEqual(crees, 1)
        self.assertTrue(
            Alerte.objects.filter(
                licence=self.licence_a, zabbix_eventid="999", active=True
            ).exists()
        )
        mock_mail.assert_called()
        self.assertIn("Supervya", mock_mail.call_args.args[0])

    @patch("licensing.services.ZabbixClient")
    def test_cr06_suspension_desactive_hote(self, mock_cls):
        mock = mock_cls.return_value
        mock.provision_licence_host.return_value = "10"
        activer_licence(self.licence_a.cle, "10.0.0.1", client=mock)
        self.licence_a.refresh_from_db()
        self.licence_a.etat = Licence.Etat.SUSPENDUE
        self.licence_a.save(update_fields=["etat"])

        from licensing.services import synchroniser_etat_hote_zabbix

        synchroniser_etat_hote_zabbix(self.licence_a, client=mock)
        mock.set_host_status.assert_called_with("10", disabled=True)

    @patch("licensing.services.ZabbixClient")
    def test_cr07_renouvellement_reactive_hote(self, mock_cls):
        mock = mock_cls.return_value
        mock.provision_licence_host.return_value = "10"
        activer_licence(self.licence_a.cle, "10.0.0.1", client=mock)
        self.licence_a.refresh_from_db()
        self.licence_a.etat = Licence.Etat.SUSPENDUE
        self.licence_a.save(update_fields=["etat"])
        self.licence_a.etat = Licence.Etat.ACTIVE
        self.licence_a.save(update_fields=["etat"])

        from licensing.services import synchroniser_etat_hote_zabbix

        synchroniser_etat_hote_zabbix(self.licence_a, client=mock)
        mock.set_host_status.assert_called_with("10", disabled=False)

    @patch("supervision.sync.send_mail")
    @patch("licensing.services.ZabbixClient")
    def test_cr08_ecart_ip(self, mock_cls, mock_mail):
        mock_cls.return_value.provision_licence_host.return_value = "10"
        activer_licence(self.licence_a.cle, "10.0.0.1")
        self.licence_a.refresh_from_db()

        zabbix = MagicMock(spec=ZabbixClient)
        zabbix.get_agent_connection_ip.return_value = "10.0.0.99"
        ecart = controler_ip(self.licence_a, zabbix)
        self.assertTrue(ecart)
        zabbix.set_host_status.assert_called_with("10", disabled=True)
        self.assertTrue(
            Alerte.objects.filter(
                licence=self.licence_a,
                severite=Alerte.Severite.IP_ECART,
                active=True,
            ).exists()
        )
