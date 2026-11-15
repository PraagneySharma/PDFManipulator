"""Sign in with ChatGPT (SIWC) for the local open-source Windows desktop app.

Direct, documented OAuth 2.0 Authorization Code + PKCE. No ChatGPT cookies,
password scraping, private ChatGPT endpoints, API keys, or local web servers
beyond a transient 127.0.0.1 OAuth callback. Saved secrets are protected by
Windows DPAPI and never exposed to widgets or logs.

Docs: https://developers.openai.com/siwc/token-sharing-open-source
"""
from __future__ import annotations

import base64
import copy
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import threading
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
import uuid
import webbrowser

from .engine import WorkflowError

ISSUER = "https://auth.openai.com"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN_ENDPOINT = ISSUER + "/api/accounts/oauth/token"
DISCOVERY = ISSUER + "/.well-known/openid-configuration"
RESOURCE = "https://api.openai.com/v1"
MODELS = RESOURCE + "/models"
RESPONSES = RESOURCE + "/responses"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
USAGE_URL = "https://chatgpt.com/settings/usage"
CALLBACK_PATH = "/auth/callback"
SHARING_SCOPE = "chatgpt.tokens.use.direct"
APP_NAME = "PDFManipulator"


class ChatGPTError(WorkflowError):
    """A safe-to-display error that never contains raw tokens."""


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, *, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise ChatGPTError("Secure ChatGPT session storage requires Windows.")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_Blob), ctypes.c_wchar_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    result = _Blob()
    fn = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    # CRYPTPROTECT_UI_FORBIDDEN: no OS prompt in the desktop UI worker.
    ok = fn(ctypes.byref(source), None, None, None, None, 0x01, ctypes.byref(result))
    if not ok:
        raise ChatGPTError("Windows could not unlock the saved ChatGPT session.")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".chatgpt-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _timestamp(value) -> float:
    """Accept OAuth epoch seconds or ISO8601 response timestamps."""
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
    return 0.0


def _http_json(url: str, *, method: str = "GET", data: dict | None = None,
               token: str | None = None, form: bool = False, timeout: int = 25) -> dict:
    headers = {"Accept": "application/json"}
    payload = None
    if data is not None:
        if form:
            payload = urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            payload = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(url, data=payload, method=method, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ChatGPTError("ChatGPT returned too much data.")
        return json.loads(raw) if raw else {}
    except HTTPError as exc:
        try:
            data = json.loads(exc.read(4096))
            err = data.get("error")
            code = err.get("code", "") if isinstance(err, dict) else ""
            if not code and isinstance(data.get("detail"), str):
                code = "request_not_available"
            code = code if isinstance(code, str) and re.fullmatch(r"[\w.-]{1,80}", code) else ""
        except (ValueError, TypeError, OSError):
            code = ""
        extra = f" ({code})" if code else ""
        helptext = (" Review your app limits in ChatGPT Settings > Usage." if exc.code == 429 else "")
        raise ChatGPTError(f"ChatGPT request failed (HTTP {exc.code}){extra}.{helptext}") from None
    except (URLError, TimeoutError, OSError) as exc:
        raise ChatGPTError("Could not connect to OpenAI. Check internet access and try again.") from None
    except (TypeError, ValueError) as exc:
        raise ChatGPTError("OpenAI returned an invalid response.") from None


def _validate_id_token(encoded: str, *, client_id: str, nonce: str) -> dict:
    """Verify signature, issuer, audience, expiration, and the OAuth nonce."""
    if not isinstance(encoded, str) or len(encoded) > 20_000:
        raise ChatGPTError("OpenAI did not return a valid identity token.")
    try:
        header_b, body_b, signature_b = encoded.split(".")
        header = json.loads(_b64decode(header_b))
        claims = json.loads(_b64decode(body_b))
        signature = _b64decode(signature_b)
        if not isinstance(header, dict) or not isinstance(claims, dict):
            raise ValueError()
        alg = header.get("alg")
        if alg not in ("RS256", "ES256"):
            raise ValueError()
        kid = header.get("kid")
        if not isinstance(kid, str) or len(kid) > 256:
            raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeDecodeError) as exc:
        raise ChatGPTError("OpenAI identity-token format is invalid.") from None

    config = _http_json(DISCOVERY)
    jwks_url = config.get("jwks_uri")
    if config.get("issuer") != ISSUER or not isinstance(jwks_url, str):
        raise ChatGPTError("OpenAI identity issuer verification failed.")
    parts = urlsplit(jwks_url)
    if parts.scheme != "https" or parts.hostname != "auth.openai.com" or parts.port not in (None, 443):
        raise ChatGPTError("OpenAI key discovery returned an untrusted address.")
    keys = _http_json(jwks_url).get("keys", [])
    key = next((entry for entry in keys
                if isinstance(entry, dict) and entry.get("kid") == kid
                and entry.get("use", "sig") == "sig"), None)
    if key is None:
        raise ChatGPTError("OpenAI identity signing key is unavailable.")
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa, utils
        from cryptography.exceptions import InvalidSignature
        if alg == "RS256" and key.get("kty") == "RSA":
            public_key = rsa.RSAPublicNumbers(
                int.from_bytes(_b64decode(key["e"]), "big"),
                int.from_bytes(_b64decode(key["n"]), "big")).public_key()
            public_key.verify(signature, (header_b + "." + body_b).encode(),
                              padding.PKCS1v15(), hashes.SHA256())
        elif alg == "ES256" and key.get("kty") == "EC" and key.get("crv") == "P-256":
            if len(signature) != 64:
                raise ValueError()
            public_key = ec.EllipticCurvePublicNumbers(
                int.from_bytes(_b64decode(key["x"]), "big"),
                int.from_bytes(_b64decode(key["y"]), "big"), ec.SECP256R1()).public_key()
            r = int.from_bytes(signature[:32], "big")
            s = int.from_bytes(signature[32:], "big")
            public_key.verify(utils.encode_dss_signature(r, s),
                              (header_b + "." + body_b).encode(), ec.ECDSA(hashes.SHA256()))
        else:
            raise ValueError()
    except (InvalidSignature, KeyError, ValueError, TypeError) as exc:
        raise ChatGPTError("OpenAI identity-token signature could not be verified.") from None
    now = time.time()
    audience = claims.get("aud")
    aud_list = [audience] if isinstance(audience, str) else audience
    if (claims.get("iss") != ISSUER or not isinstance(aud_list, list)
        or client_id not in aud_list or (len(aud_list) > 1 and claims.get("azp") != client_id)
        or not isinstance(claims.get("exp"), (int, float)) or claims["exp"] <= now
        or not isinstance(claims.get("iat"), (int, float)) or claims["iat"] > now + 120
        or claims.get("nonce") != nonce
        or not isinstance(claims.get("sub"), str) or not claims["sub"]):
        raise ChatGPTError("OpenAI identity verification failed.")
    return claims


class _CredentialStore:
    """DPAPI-encrypted account registry and a persistent non-secret host ID."""

    def __init__(self, root: Path | None = None):
        if root is None:
            base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
            location = base / "PDFManipulator" / "chatgpt"
            legacy = base / "PDFWorkflowStudio" / "chatgpt"
            # Preserve the previous application's encrypted credentials and OAuth host ID.
            # Only migrate when the new account store is completely uninitialized.
            if (legacy.is_dir() and not (location / "accounts.dpapi").exists()
                    and not (location / "host.json").exists()):
                try:
                    location.mkdir(parents=True, exist_ok=True)
                    for name in ("host.json", "accounts.dpapi"):
                        old_file = legacy / name
                        if old_file.is_file():
                            shutil.copy2(old_file, location / name)
                except OSError as exc:
                    raise ChatGPTError("Could not migrate your saved ChatGPT connection.") from exc
        else:
            location = Path(root)
        self.root = location
        self.data_path = location / "accounts.dpapi"
        self.host_path = location / "host.json"
        self.lock = threading.RLock()
        self.state = {"active": None, "profiles": [], "pending_client": None}
        self.root.mkdir(parents=True, exist_ok=True)
        if self.host_path.exists():
            try:
                host = json.loads(self.host_path.read_text(encoding="utf-8"))["host_id"]
                if not isinstance(host, str) or not host.startswith("urn:uuid:"):
                    raise ValueError()
                uuid.UUID(host[9:])
            except (KeyError, ValueError, OSError, TypeError):
                raise ChatGPTError("Saved ChatGPT host identity is corrupted; restore your host file.")
            self.host_id = host
        else:
            self.host_id = "urn:uuid:" + str(uuid.uuid4())
            _atomic_write(self.host_path, json.dumps({"host_id": self.host_id}).encode())
        if self.data_path.exists():
            try:
                parsed = json.loads(_dpapi(self.data_path.read_bytes(), decrypt=True))
                if not isinstance(parsed, dict) or not isinstance(parsed.get("profiles"), list):
                    raise ValueError()
                self.state = parsed
            except (ValueError, TypeError, OSError):
                raise ChatGPTError("Saved ChatGPT sessions are unreadable. No credentials were changed.")

    def save(self):
        with self.lock:
            _atomic_write(self.data_path,
                          _dpapi(json.dumps(self.state, separators=(",", ":")).encode("utf-8")))

    def active(self) -> dict | None:
        with self.lock:
            ident = self.state.get("active")
            return copy.deepcopy(next((p for p in self.state["profiles"]
                                       if p.get("id") == ident), None))

    def selected(self, identity: str) -> dict | None:
        with self.lock:
            return copy.deepcopy(next((p for p in self.state["profiles"]
                                       if p.get("id") == identity), None))

    def upsert(self, profile: dict, active: bool = True):
        with self.lock:
            self.state["profiles"] = [p for p in self.state["profiles"] if p["id"] != profile["id"]]
            self.state["profiles"].append(copy.deepcopy(profile))
            if active:
                self.state["active"] = profile["id"]
            self.state["pending_client"] = None
            self.save()

    def select(self, identity: str):
        with self.lock:
            if self.selected(identity) is None:
                raise ChatGPTError("ChatGPT account is not saved.")
            self.state["active"] = identity
            self.save()


class ChatGPTConnection:
    """Account-aware sign-in and validated Responses API workflow planning."""

    def __init__(self, storage: Path | None = None):
        self.store = _CredentialStore(storage)
        self._lock = threading.RLock()
        self._models: list[dict] = []

    def session(self) -> dict:
        active = self.store.active()
        sharing = bool(active and SHARING_SCOPE in active.get("scopes", [])
                       and active.get("access_token"))
        with self.store.lock:
            profiles = [{
                "id": p["id"], "email": p.get("email") or "ChatGPT account",
                "connected": bool(p.get("refresh_token") and SHARING_SCOPE in p.get("scopes", []))
            } for p in self.store.state["profiles"]]
        return {"connected": bool(active and active.get("access_token")),
                "sharing": sharing, "email": (active or {}).get("email", ""),
                "id": (active or {}).get("id"), "model": (active or {}).get("model"),
                "profiles": profiles}

    def sign_in(self, *, new_account: bool = False, profile_id: str | None = None,
                timeout: float = 180, launch: Callable[[str], bool] = webbrowser.open) -> dict:
        with self._lock:
            original = None
            if not new_account:
                original = self.store.selected(profile_id) if profile_id else self.store.active()
                if profile_id and original is None:
                    raise ChatGPTError("The selected ChatGPT account is not saved.")
            saved = (original["client_id"] if original else
                     (None if new_account else self.store.state.get("pending_client")))
            client_id = saved or "dynamic_agent_client"
            nonce = secrets.token_urlsafe(24)
            state = secrets.token_urlsafe(32)
            verifier = secrets.token_urlsafe(64)
            challenge = _b64encode(hashlib.sha256(verifier.encode()).digest())

            # Bind the OAuth redirect port to the callback server before launching.
            received: dict[str, str] = {}
            finished = threading.Event()

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if urlsplit(self.path).path != CALLBACK_PATH:
                        self.send_error(404)
                        return
                    args = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                    reply = {k: v[0] for k, v in args.items() if len(v) == 1}
                    if not secrets.compare_digest(reply.get("state", ""), state) or finished.is_set():
                        self.send_error(400)
                        return
                    received.update(reply)
                    finished.set()
                    page = (b"<html><body><h2>Return to PDFManipulator</h2>"
                            b"<p>Finish connecting in the desktop application.</p></body></html>")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(page)))
                    self.end_headers()
                    self.wfile.write(page)

                def log_message(self, *_args):
                    pass

            server = HTTPServer(("127.0.0.1", 0), Handler)
            server.timeout = 0.5
            redirect = f"http://127.0.0.1:{server.server_address[1]}{CALLBACK_PATH}"
            query = {
                "client_id": client_id, "ext_agent_host_id": self.store.host_id,
                "response_type": "code", "redirect_uri": redirect,
                "scope": SCOPES, "resource": RESOURCE, "state": state,
                "nonce": nonce, "code_challenge_method": "S256",
                "code_challenge": challenge
            }
            if client_id == "dynamic_agent_client":
                query["agent_name_hint"] = APP_NAME
            elif original:
                if SHARING_SCOPE not in original.get("scopes", []):
                    # A prior consent decline needs an explicit fresh consent screen.
                    query["prompt"] = "consent"
                if original.get("id_token"):
                    query["id_token_hint"] = original["id_token"]
                if original.get("email"):
                    query["login_hint"] = original["email"]
            url = AUTHORIZE + "?" + urlencode(query)
            try:
                if not launch(url):
                    raise ChatGPTError("Could not open the browser for ChatGPT sign-in.")
                end = time.monotonic() + timeout
                while not finished.is_set() and time.monotonic() < end:
                    server.handle_request()
                if not finished.is_set():
                    raise ChatGPTError("ChatGPT sign-in timed out. Try again.")
            finally:
                server.server_close()
            if received.get("error"):
                raise ChatGPTError("ChatGPT sign-in was declined or cancelled.")
            code = received.get("code")
            issued = received.get("client_id", client_id)
            if not code or not isinstance(issued, str) or not issued.startswith("oaiapp_"):
                raise ChatGPTError("ChatGPT authorization did not complete.")
            if client_id != "dynamic_agent_client" and issued != client_id:
                raise ChatGPTError("ChatGPT returned a different client registration.")
            if client_id == "dynamic_agent_client":
                # Persist issued client ID before code exchange, even on an expiring code.
                with self.store.lock:
                    self.store.state["pending_client"] = issued
                    self.store.save()
            credentials = _http_json(TOKEN_ENDPOINT, method="POST", form=True, data={
                "grant_type": "authorization_code", "client_id": issued,
                "code": code, "code_verifier": verifier,
                "redirect_uri": redirect, "resource": RESOURCE
            })
            claims = _validate_id_token(credentials.get("id_token"), client_id=issued, nonce=nonce)
            if original and (claims["sub"] != original["subject"] or
                             claims["iss"] != original["issuer"]):
                raise ChatGPTError("This ChatGPT sign-in belongs to a different saved account.")
            granted = credentials.get("scope", "")
            scopes = granted.split() if isinstance(granted, str) else []
            access = credentials.get("access_token")
            refresh = credentials.get("refresh_token")
            if not (isinstance(access, str) and access and
                    isinstance(refresh, str) and refresh):
                raise ChatGPTError("ChatGPT did not grant a renewable session.")
            record = {
                "id": original["id"] if original else str(uuid.uuid4()),
                "subject": claims["sub"], "issuer": claims["iss"],
                "client_id": issued, "host_id": self.store.host_id,
                "email": claims.get("email", "") if isinstance(claims.get("email", ""), str) else "",
                "id_token": credentials["id_token"], "access_token": access,
                "refresh_token": refresh, "scopes": scopes,
                "expires_at": time.time() + float(credentials.get("expires_in", 3600)),
                "earliest_refresh_at": _timestamp(credentials.get("earliest_refresh_at")),
                "model": (original or {}).get("model"),
                "welcome_seen": bool((original or {}).get("welcome_seen")),
            }
            self.store.upsert(record)
            self._models = []
            return self.session()

    def mark_welcome_seen(self) -> bool:
        """Show the ChatGPT-plan usage notice only once per account registration."""
        with self._lock:
            profile = self.store.active()
            if (not profile or SHARING_SCOPE not in profile.get("scopes", [])
                    or profile.get("welcome_seen")):
                return False
            profile["welcome_seen"] = True
            self.store.upsert(profile)
            return True

    def select(self, identity: str) -> dict:
        with self._lock:
            self.store.select(identity)
            self._models = []
            return self.session()

    def _access_token(self) -> str:
        with self._lock:
            record = self.store.active()
            if record is None:
                raise ChatGPTError("Connect a ChatGPT account first.")
            if SHARING_SCOPE not in record.get("scopes", []):
                raise ChatGPTError("ChatGPT plan usage was not authorized. Reconnect and enable plan usage.")
            if time.time() + 90 < float(record.get("expires_at", 0)):
                return record["access_token"]
            if not record.get("refresh_token"):
                raise ChatGPTError("ChatGPT session expired. Sign in again.")
            earliest = _timestamp(record.get("earliest_refresh_at"))
            if earliest and time.time() < earliest:
                raise ChatGPTError("ChatGPT session is not ready for renewal. Try again shortly.")
            fresh = _http_json(TOKEN_ENDPOINT, method="POST", form=True, data={
                "grant_type": "refresh_token", "client_id": record["client_id"],
                "refresh_token": record["refresh_token"], "resource": RESOURCE
            })
            new_access = fresh.get("access_token")
            new_refresh = fresh.get("refresh_token")
            if not isinstance(new_access, str) or not isinstance(new_refresh, str):
                raise ChatGPTError("ChatGPT could not renew the session. Please sign in again.")
            record["access_token"] = new_access
            record["refresh_token"] = new_refresh
            if isinstance(fresh.get("scope"), str):
                record["scopes"] = fresh["scope"].split()
            record["expires_at"] = time.time() + float(fresh.get("expires_in", 3600))
            record["earliest_refresh_at"] = _timestamp(fresh.get("earliest_refresh_at"))
            self.store.upsert(record)
            return new_access

    def models(self) -> list[dict[str, str]]:
        token = self._access_token()
        data = _http_json(MODELS, token=token)
        options = data.get("models", [])
        if not isinstance(options, list):
            raise ChatGPTError("ChatGPT did not return a model catalog.")
        result = []
        for model in options:
            if not isinstance(model, dict) or model.get("visibility") != "list":
                continue
            slug, name = model.get("slug"), model.get("display_name")
            if isinstance(slug, str) and slug and isinstance(name, str) and name:
                result.append({"slug": slug, "name": name})
        if not result:
            raise ChatGPTError("No eligible models were offered by this ChatGPT connection.")
        self._models = result
        record = self.store.active()
        if record and record.get("model") not in {m["slug"] for m in result}:
            record["model"] = result[0]["slug"]
            self.store.upsert(record)
        return result

    def choose_model(self, slug: str):
        with self._lock:
            if slug not in {m["slug"] for m in self._models}:
                raise ChatGPTError("Choose a model listed for this ChatGPT account.")
            record = self.store.active()
            if not record:
                raise ChatGPTError("Sign in with ChatGPT first.")
            record["model"] = slug
            self.store.upsert(record)

    def interpret(self, prompt: str, aliases: list[str], *, consent: bool) -> list[dict]:
        from .ai import SYSTEM_PROMPT, parse_model_steps
        if not consent:
            raise ChatGPTError("Allow sending the instruction to ChatGPT first.")
        if not prompt.strip() or len(prompt) > 2000:
            raise ChatGPTError("Enter an instruction up to 2,000 characters.")
        if not aliases or len(aliases) > 30 or any(
                not a.startswith("input") or not a[5:].isdigit() for a in aliases):
            raise ChatGPTError("Add valid PDF inputs first.")
        record = self.store.active()
        if record is None or not record.get("model"):
            raise ChatGPTError("Connect ChatGPT and select a model before interpreting.")
        token = self._access_token()
        data = {
            "model": record["model"], "instructions": SYSTEM_PROMPT,
            "input": [{"role": "user", "content": json.dumps(
                {"request": prompt, "available_inputs": aliases})}],
            "store": False, "stream": True
        }
        req = Request(RESPONSES, data=json.dumps(data).encode(),
                      headers={"Authorization": "Bearer " + token,
                               "Content-Type": "application/json",
                               "Accept": "text/event-stream"}, method="POST")
        chunks: list[str] = []
        ended = False
        size = 0
        try:
            with urlopen(req, timeout=100) as stream:
                for raw in stream:
                    size += len(raw)
                    if size > 1_000_000:
                        raise ChatGPTError("ChatGPT response exceeded the safety limit.")
                    if not raw.startswith(b"data:"):
                        continue
                    content = raw[5:].strip()
                    if content == b"[DONE]":
                        continue
                    try:
                        event = json.loads(content)
                    except (ValueError, UnicodeDecodeError):
                        raise ChatGPTError("ChatGPT sent a malformed response stream.") from None
                    kind = event.get("type")
                    if kind == "response.output_text.delta":
                        delta = event.get("delta")
                        if isinstance(delta, str):
                            chunks.append(delta)
                            if sum(map(len, chunks)) > 64_000:
                                raise ChatGPTError("ChatGPT workflow response was too long.")
                    elif kind == "response.failed":
                        error = event.get("response", {}).get("error") or {}
                        name = error.get("code", "response_failed")
                        safe = name if isinstance(name, str) and re.fullmatch(r"[\w.-]{1,80}", name) else "response_failed"
                        extra = " Review ChatGPT Settings > Usage." if "usage" in safe else ""
                        raise ChatGPTError(f"ChatGPT could not complete the request ({safe}).{extra}")
                    elif kind == "response.incomplete":
                        raise ChatGPTError("ChatGPT could not finish the instruction.")
                    elif kind == "response.completed":
                        ended = True
            if not ended:
                raise ChatGPTError("ChatGPT stream ended without a completed response.")
        except HTTPError as exc:
            extra = " Review ChatGPT Settings > Usage." if exc.code == 429 else ""
            raise ChatGPTError(f"ChatGPT request failed (HTTP {exc.code}).{extra}") from None
        except (URLError, TimeoutError, OSError):
            raise ChatGPTError("ChatGPT connection was interrupted. Try again.") from None
        return parse_model_steps("".join(chunks), aliases)

    def sign_out(self) -> bool:
        """Clear local tokens even if remote revocation is unavailable."""
        with self._lock:
            profile = self.store.active()
            if not profile:
                return True
            confirmed = True
            token = profile.get("refresh_token")
            if token:
                try:
                    config = _http_json(DISCOVERY)
                    revoke = config.get("revocation_endpoint")
                    parts = urlsplit(revoke or "")
                    if parts.scheme != "https" or parts.hostname != "auth.openai.com":
                        raise ChatGPTError("Untrusted ChatGPT revocation endpoint.")
                    _http_json(revoke, method="POST", form=True, data={
                        "token": token, "token_type_hint": "refresh_token",
                        "client_id": profile["client_id"]
                    })
                except ChatGPTError:
                    confirmed = False
            for field in ("access_token", "refresh_token", "id_token", "expires_at"):
                profile.pop(field, None)
            self.store.upsert(profile)
            self._models = []
            return confirmed
