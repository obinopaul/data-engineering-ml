"""Offline vendor checks. Real dlt pagination tests skip until dlt is installed."""
import importlib.util
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import requests

from Ingestion.vendor_sources import (
    VendorSession, adp_rows, adp_worker, check_page, netsuite_rows,
    page_size, required_env, token_auth,
)


def response(payload=None, status=200, request=None):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode() if payload is not None else b""
    result._content_consumed = True
    result.headers["Content-Type"] = "application/json"
    result.request = request
    result.url = request.url if request is not None else "https://api.adp.com/"
    return result


class VendorHelpersTests(unittest.TestCase):
    def test_missing_credential_identifies_name_without_value(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "ADP_CLIENT_ID"):
                required_env("ADP_CLIENT_ID")

    def test_projection_keeps_key_and_excludes_unselected_worker_details(self):
        worker = {"associateOID": "test-1", "workerStatus": {"code": "A"},
                  "person": {"name": "Test Person"}}
        result = adp_worker(worker, ["workerStatus"])
        self.assertEqual(result, {"id": "test-1", "workerStatus": {"code": "A"}})
        with self.assertRaises(ValueError):
            adp_worker({"workerStatus": {}}, ["workerStatus"])

    def test_page_size_respects_vendor_limit(self):
        for value in [0, 51, True, "50"]:
            with self.assertRaises(ValueError):
                page_size({"page_size": value}, 50)
        self.assertEqual(page_size({"page_size": 25}, 50), 25)

    def test_errors_do_not_look_like_empty_success(self):
        for payload in [{"error": "fixture"}, {"workers": None}, {"workers": [7]}]:
            with self.assertRaises(ValueError):
                check_page(response(payload), "workers")
        with self.assertRaisesRegex(RuntimeError, "403"):
            check_page(response({"error": "do not print this"}, 403), "workers")
        self.assertEqual(check_page(response({"workers": []}), "workers"), {"workers": []})

    def test_session_rejects_wrong_host_before_transport(self):
        with VendorSession(["api.adp.com"]) as session:
            for url in ["http://api.adp.com/", "https://other.example/", "https://api.adp.com:444/"]:
                with patch.object(requests.Session, "send") as send:
                    with self.assertRaises(ValueError):
                        session.send(requests.Request("GET", url).prepare())
                    send.assert_not_called()

    def test_session_disables_redirects_and_enforces_tls_timeout(self):
        prepared = requests.Request("GET", "https://api.adp.com/hr/v2/workers").prepare()
        with VendorSession(["api.adp.com"]) as session:
            with patch.object(requests.Session, "send", return_value=response({})) as send:
                session.send(prepared, verify=False, allow_redirects=True)
                self.assertTrue(send.call_args.kwargs["verify"])
                self.assertFalse(send.call_args.kwargs["allow_redirects"])
                self.assertEqual(send.call_args.kwargs["timeout"], (10, 60))
            with patch.object(requests.Session, "send", return_value=response({}, 302)):
                with self.assertRaisesRegex(RuntimeError, "redirect"):
                    session.send(prepared)

    def test_token_validation_and_refresh_margin(self):
        # Test our overrides without pretending the real dlt token client is installed.
        class Base:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
        module = types.ModuleType("dlt.sources.helpers.rest_client.auth")
        module.OAuth2ClientCredentials = Base
        with patch.dict("sys.modules", {module.__name__: module}):
            auth = token_auth(None, "https://accounts.adp.com/", lambda: {"data": {}})
        self.assertEqual(auth.parse_access_token({"access_token": "fixture"}), "fixture")
        for payload in [{}, {"access_token": None}, {"access_token": ""}]:
            with self.assertRaises(ValueError):
                auth.parse_access_token(payload)
        self.assertEqual(auth.parse_expiration_in_seconds({"expires_in": 3600}), 3540)
        with self.assertRaises(ValueError):
            auth.parse_expiration_in_seconds({"expires_in": 0})


@unittest.skipUnless(importlib.util.find_spec("dlt"), "dlt not installed; real-client tests pending")
class DltVendorTests(unittest.TestCase):
    """Real RESTClient/OAuth/paginators, with HTTP transport replaced by fixtures."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        key = Path(self.directory.name) / "test.pem"
        key.write_text("test transport fixture; no real private key")
        env = {
            "ADP_CLIENT_ID": "fixture-client", "ADP_CLIENT_SECRET": "fixture-secret",
            "ADP_CERT_PATH": str(key), "ADP_PRIVATE_KEY_PATH": str(key),
            "NETSUITE_ACCOUNT_ID": "123-sb1", "NETSUITE_CLIENT_ID": "fixture-client",
            "NETSUITE_CERTIFICATE_ID": "fixture-cert", "NETSUITE_PRIVATE_KEY_PATH": str(key),
        }
        self.key = str(key)
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_adp_pages_mtls_and_token_reuse(self):
        offsets, tokens, certificates = [], [], []

        def transport(adapter, request, **kwargs):
            certificates.append(kwargs.get("cert"))
            if request.url.startswith("https://accounts.adp.com/"):
                tokens.append(request)
                self.assertTrue(request.headers["Authorization"].startswith("Basic "))
                return response({"access_token": "fixture-token", "expires_in": 3600}, request=request)
            self.assertEqual(request.headers["Authorization"], "Bearer fixture-token")
            params = parse_qs(urlsplit(request.url).query)
            self.assertEqual(params["$top"], ["2"])
            offset = int(params["$skip"][0])
            offsets.append(offset)
            if offset == 0:
                return response({"workers": [{"associateOID": "A"}, {"associateOID": "B"}]}, request=request)
            if offset == 2:
                return response({"workers": [{"associateOID": "C"}]}, request=request)
            return response(status=204, request=request)

        with patch.object(requests.adapters.HTTPAdapter, "send", transport):
            rows = list(adp_rows({"page_size": 2}))
        self.assertEqual([row["id"] for row in rows], ["A", "B", "C"])
        self.assertEqual(offsets, [0, 2, 4])
        self.assertEqual(len(tokens), 1)
        self.assertTrue(all(cert == (self.key, self.key) for cert in certificates))

    def test_netsuite_post_pagination_and_has_more_stop(self):
        offsets = []

        def transport(adapter, request, **kwargs):
            if "/auth/" in request.url:
                return response({"access_token": "fixture-token", "expires_in": 3600}, request=request)
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.headers["Prefer"], "transient")
            self.assertIn("ORDER BY id", json.loads(request.body)["q"])
            params = parse_qs(urlsplit(request.url).query)
            offset = int(params["offset"][0])
            offsets.append(offset)
            payload = {"items": [{"id": offset + 1}], "hasMore": offset == 0, "totalResults": 2}
            return response(payload, request=request)

        with patch.object(requests.adapters.HTTPAdapter, "send", transport), patch(
            "Ingestion.vendor_sources.netsuite_token_request",
            return_value={"data": {"client_assertion": "fixture"}},
        ):
            rows = list(netsuite_rows({"query": "SELECT id FROM customer ORDER BY id", "page_size": 1}))
        self.assertEqual(offsets, [0, 1])
        self.assertEqual(rows, [{"id": 1}, {"id": 2}])

    def test_adp_repeated_page_fails_instead_of_looping(self):
        def transport(adapter, request, **kwargs):
            payload = {"access_token": "fixture-token"} if "/auth/" in request.url else {"workers": [{"associateOID": "A"}]}
            return response(payload, request=request)
        with patch.object(requests.adapters.HTTPAdapter, "send", transport):
            with self.assertRaisesRegex(ValueError, "repeated a page"):
                list(adp_rows({"page_size": 1}))


if __name__ == "__main__":
    unittest.main()
