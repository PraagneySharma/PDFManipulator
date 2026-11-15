"""Offline OAuth protocol and model-stream tests; never contact a real account."""
import base64
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from studio.chatgpt import (
    APP_NAME, ChatGPTConnection, ChatGPTError, DISCOVERY, ISSUER,
    MODELS, RESPONSES, TOKEN_ENDPOINT, _b64encode, _validate_id_token
)


class ChatGPTProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = ChatGPTConnection(Path(self.temp.name))
        self.assertFalse(self.client.session()["connected"])
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        numbers = self.key.public_key().public_numbers()
        self.jwks = {"keys": [{"kid": "test-key", "use": "sig", "kty": "RSA",
                              "e": _b64encode(numbers.e.to_bytes(3, "big")),
                              "n": _b64encode(numbers.n.to_bytes(256, "big"))}]}
        self.nonce = None
        self.auth_url = None
        self.calls = []

    def jwt(self, nonce: str, sub: str = "sub-123", aud: str = "oaiapp_mock") -> str:
        header = _b64encode(json.dumps({"alg": "RS256", "kid": "test-key"}).encode())
        claims = _b64encode(json.dumps({
            "iss": ISSUER, "aud": aud, "sub": sub,
            "email": "person@example.com", "nonce": nonce,
            "exp": time.time() + 3600, "iat": time.time() - 10
        }).encode())
        signature = self.key.sign((header + "." + claims).encode(),
                                  padding.PKCS1v15(), hashes.SHA256())
        return header + "." + claims + "." + _b64encode(signature)

    def fake_request(self, url, *, method="GET", data=None, token=None, **kwargs):
        self.calls.append((url, method, data, token))
        if url == DISCOVERY:
            return {"issuer": ISSUER, "jwks_uri": ISSUER + "/test-jwks"}
        if url == ISSUER + "/test-jwks":
            return self.jwks
        if url == TOKEN_ENDPOINT:
            if data["grant_type"] == "refresh_token":
                return {"access_token": "rotated-access", "refresh_token": "rotated-refresh",
                        "expires_in": 3600, "scope": "openid chatgpt.tokens.use.direct"}
            return {"id_token": self.jwt(self.nonce), "access_token": "initial-access",
                    "refresh_token": "initial-refresh", "expires_in": 3600,
                    "scope": "openid email profile offline_access resource.invoke chatgpt.tokens.use.direct"}
        if url == MODELS:
            self.assertIn(token, {"initial-access", "rotated-access"})
            return {"models": [
                {"slug": "gpt-test", "display_name": "GPT test", "visibility": "list"},
                {"slug": "hidden", "display_name": "Private", "visibility": "hidden"}]}
        raise AssertionError("Unexpected test request: " + str(url))

    def simulated_browser(self, url: str) -> bool:
        self.auth_url = url
        p = parse_qs(urlsplit(url).query)
        self.nonce = p["nonce"][0]
        callback = (p["redirect_uri"][0] + "?" +
                    urlencode({"code": "mock-code", "state": p["state"][0],
                               "client_id": "oaiapp_mock"}))
        def visit():
            with urlopen(callback, timeout=5) as response:
                self.assertEqual(response.status, 200)
        thread = threading.Thread(target=visit, daemon=True)
        thread.start()
        return True

    def connect(self):
        with patch("studio.chatgpt._http_json", side_effect=self.fake_request):
            info = self.client.sign_in(launch=self.simulated_browser, timeout=5)
            models = self.client.models()
        return info, models

    def test_oauth_pkce_host_id_signin_permissions_and_models(self):
        info, models = self.connect()
        self.assertTrue(info["connected"])
        self.assertTrue(info["sharing"])
        self.assertEqual(info["email"], "person@example.com")
        self.assertEqual([m["slug"] for m in models], ["gpt-test"])
        p = parse_qs(urlsplit(self.auth_url).query)
        self.assertEqual(p["client_id"], ["dynamic_agent_client"])
        self.assertEqual(p["agent_name_hint"], [APP_NAME])
        self.assertEqual(p["code_challenge_method"], ["S256"])
        self.assertEqual(p["ext_agent_host_id"], [self.client.store.host_id])
        self.assertIn("chatgpt.tokens.use.direct", p["scope"][0])
        self.assertTrue(self.client.store.data_path.exists())
        self.assertNotIn(b"initial-access", self.client.store.data_path.read_bytes())
        self.assertTrue(self.client.mark_welcome_seen())
        self.assertFalse(self.client.mark_welcome_seen())
        # Credentials persist, but must never appear in the session dict.
        fresh = ChatGPTConnection(self.client.store.root)
        self.assertEqual(fresh.session()["model"], "gpt-test")
        self.assertTrue(fresh.session()["sharing"])
        self.assertNotIn("access_token", str(fresh.session()))

    def test_signin_identity_nonce_mismatch_rejected(self):
        self.nonce = "correct"
        with patch("studio.chatgpt._http_json", side_effect=self.fake_request):
            with self.assertRaisesRegex(ChatGPTError, "verification failed"):
                _validate_id_token(self.jwt("wrong"),
                                   client_id="oaiapp_mock", nonce="correct")

    def test_pkce_reconnect_reuses_client_id_and_host(self):
        self.connect()
        with patch("studio.chatgpt._http_json", side_effect=self.fake_request):
            self.client.sign_in(launch=self.simulated_browser, timeout=5)
        p = parse_qs(urlsplit(self.auth_url).query)
        self.assertEqual(p["client_id"], ["oaiapp_mock"])
        self.assertNotIn("agent_name_hint", p)
        self.assertEqual(p["ext_agent_host_id"], [self.client.store.host_id])

    def test_access_token_rotation_and_model_selection(self):
        self.connect()
        with self.assertRaisesRegex(ChatGPTError, "model listed"):
            self.client.choose_model("invented-model")
        active = self.client.store.active()
        active["expires_at"] = time.time() - 1
        self.client.store.upsert(active)
        with patch("studio.chatgpt._http_json", side_effect=self.fake_request):
            self.assertEqual(self.client._access_token(), "rotated-access")
        self.assertEqual(self.client.store.active()["refresh_token"], "rotated-refresh")

    def test_inference_sse_and_deterministic_validation(self):
        self.connect()
        delta = json.dumps({"steps": [{"op": "load", "source": "input1"},
                                      {"op": "split_every", "n": 3}]})
        events = (b'data: ' + json.dumps({"type": "response.output_text.delta",
                                        "delta": delta}).encode() + b'\n\n' +
                  b'data: {"type":"response.completed"}\n\n')
        args = {}
        def fake_stream(req, timeout=0):
            self.assertEqual(req.full_url, RESPONSES)
            args.update(json.loads(req.data))
            self.assertEqual(req.get_header("Authorization"), "Bearer initial-access")
            return io.BytesIO(events)
        with patch("studio.chatgpt.urlopen", side_effect=fake_stream):
            steps = self.client.interpret("Split in groups of three", ["input1"], consent=True)
        self.assertEqual(steps[-1]["n"], 3)
        self.assertIs(args["stream"], True)
        self.assertIs(args["store"], False)
        self.assertNotIn("temperature", args)
        self.assertIn("available_inputs", args["input"][0]["content"])
        self.assertNotIn("C:\\", json.dumps(args))

    def test_inference_fails_closed_when_stream_does_not_complete(self):
        self.connect()
        events = b'data: {"type":"response.output_text.delta","delta":"{}"}\n\n'
        with patch("studio.chatgpt.urlopen", return_value=io.BytesIO(events)):
            with self.assertRaisesRegex(ChatGPTError, "completed response"):
                self.client.interpret("Split every 2", ["input1"], consent=True)
        with self.assertRaisesRegex(ChatGPTError, "Allow sending"):
            self.client.interpret("Split every 2", ["input1"], consent=False)

    def test_identity_missing_plan_permission_does_not_enable_inference(self):
        self.connect()
        active = self.client.store.active()
        active["scopes"] = ["openid", "email"]
        self.client.store.upsert(active)
        self.assertFalse(self.client.session()["sharing"])
        with self.assertRaisesRegex(ChatGPTError, "not authorized"):
            self.client._access_token()

    def test_signout_clears_local_tokens_and_keeps_registration(self):
        self.connect()
        with patch("studio.chatgpt._http_json", side_effect=self.fake_request):
            self.assertFalse(self.client.sign_out())  # Mock has no revocation route.
        session = self.client.session()
        self.assertFalse(session["connected"])
        self.assertEqual(len(session["profiles"]), 1)
        self.assertFalse(self.client.store.active().get("refresh_token"))

    def test_corrupted_store_not_overwritten(self):
        self.connect()
        stored = self.client.store.data_path
        stored.write_bytes(b"not a DPAPI blob")
        with self.assertRaises(ChatGPTError):
            ChatGPTConnection(self.client.store.root)
        self.assertEqual(stored.read_bytes(), b"not a DPAPI blob")


if __name__ == "__main__":
    unittest.main()
