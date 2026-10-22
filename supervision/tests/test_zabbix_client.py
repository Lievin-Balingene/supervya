"""Tests unitaires du client Zabbix avec serveur fictif (mock)."""
from unittest.mock import MagicMock

from django.test import SimpleTestCase, override_settings

from supervision.zabbix_client import (
    MACRO_CPU,
    TEMPLATE_LINUX_ACTIVE,
    TEMPLATE_WINDOWS_ACTIVE,
    ZabbixAPIError,
    ZabbixClient,
)


@override_settings(ZABBIX_API_URL="http://zabbix.test/api_jsonrpc.php", ZABBIX_API_TOKEN="tok")
class ZabbixClientTests(SimpleTestCase):
    def setUp(self):
        self.session = MagicMock()
        self.client = ZabbixClient(
            api_url="http://zabbix.test/api_jsonrpc.php",
            api_token="tok-test",
            session=self.session,
        )

    def _mock_result(self, result):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"jsonrpc": "2.0", "result": result, "id": 1}
        self.session.post.return_value = response

    def _mock_error(self, message="fail", code=-32602):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "jsonrpc": "2.0",
            "error": {"code": code, "message": message, "data": "details"},
            "id": 1,
        }
        self.session.post.return_value = response

    def test_call_envoie_bearer_token(self):
        self._mock_result([])
        self.client.call("host.get", {"limit": 1})
        args, kwargs = self.session.post.call_args
        self.assertEqual(args[0], "http://zabbix.test/api_jsonrpc.php")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer tok-test")
        self.assertEqual(kwargs["json"]["method"], "host.get")

    def test_call_remonte_erreur_api(self):
        self._mock_error("Invalid params")
        with self.assertRaises(ZabbixAPIError) as ctx:
            self.client.call("host.get")
        self.assertIn("Invalid params", str(ctx.exception))
        self.assertEqual(ctx.exception.code, -32602)

    def test_ensure_host_group_existant(self):
        self._mock_result([{"groupid": "15"}])
        group_id = self.client.ensure_host_group("supervya-client-1")
        self.assertEqual(group_id, "15")

    def test_ensure_host_group_creation(self):
        response_get = MagicMock()
        response_get.raise_for_status = MagicMock()
        response_get.json.return_value = {"jsonrpc": "2.0", "result": [], "id": 1}

        response_create = MagicMock()
        response_create.raise_for_status = MagicMock()
        response_create.json.return_value = {
            "jsonrpc": "2.0",
            "result": {"groupids": ["42"]},
            "id": 2,
        }
        self.session.post.side_effect = [response_get, response_create]

        group_id = self.client.ensure_host_group("supervya-client-9")
        self.assertEqual(group_id, "42")
        self.assertEqual(self.session.post.call_args_list[1].kwargs["json"]["method"], "hostgroup.create")

    def test_template_name_for_os(self):
        self.assertEqual(self.client.template_name_for_os("linux"), TEMPLATE_LINUX_ACTIVE)
        self.assertEqual(self.client.template_name_for_os("windows"), TEMPLATE_WINDOWS_ACTIVE)

    def test_client_group_name(self):
        self.assertEqual(self.client.client_group_name(7), "supervya-client-7")

    def test_threshold_macros(self):
        macros = self.client.threshold_macros(cpu=85, memoire=80, disque=90)
        self.assertEqual(macros[MACRO_CPU], "85")

    def test_set_host_status_desactive(self):
        self._mock_result(True)
        self.client.set_host_status("100", disabled=True)
        payload = self.session.post.call_args.kwargs["json"]
        self.assertEqual(payload["method"], "host.update")
        self.assertEqual(payload["params"]["status"], 1)

    def test_provision_licence_host(self):
        responses = []

        def add(result):
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.json.return_value = {"jsonrpc": "2.0", "result": result, "id": len(responses) + 1}
            responses.append(r)

        add([])  # hostgroup.get
        add({"groupids": ["1"]})  # hostgroup.create
        add([{"templateid": "10001"}])  # template.get
        add({"hostids": ["500"]})  # host.create
        add([])  # item.get supervya.agent.ip
        add([{"interfaceid": "9"}])  # hostinterface.get
        add({"itemids": ["700"]})  # item.create
        self.session.post.side_effect = responses

        host_id = self.client.provision_licence_host(
            client_id=3,
            identifiant="spv-abc",
            systeme="linux",
            psk="aabbcc",
            seuil_cpu=90,
            seuil_memoire=90,
            seuil_disque=90,
            adresse_ip="203.0.113.10",
        )
        self.assertEqual(host_id, "500")
        create_payload = responses[3].json.return_value  # not the call
        host_create = self.session.post.call_args_list[3].kwargs["json"]
        self.assertEqual(host_create["method"], "host.create")
        self.assertEqual(host_create["params"]["tls_psk_identity"], "spv-abc")
        self.assertEqual(host_create["params"]["interfaces"][0]["ip"], "203.0.113.10")
        self.assertIsNotNone(create_payload)
