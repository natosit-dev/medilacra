from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://pa-test.shn-preview.org"
DEFAULT_CONSOLE_URL = "https://admin.shn-preview.org"
DEFAULT_CLIENT_FILE = (
    Path(__file__).resolve().parents[1]
    / "shn_live_baseline_00301"
    / "client.json"
)


@dataclass(frozen=True)
class SHNResponse:
    status_code: int
    body: Any
    correlation_id: str | None
    sent_correlation_id: str
    leg_id: str | None
    trace_url: str
    elapsed_ms: float
    warning: str | None = None
    link: str | None = None
    attempts: int = 1

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def transport_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "sent_correlation_id": self.sent_correlation_id,
            "correlation_id": self.correlation_id,
            "leg_id": self.leg_id,
            "trace_url": self.trace_url,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "warning": self.warning,
            "link": self.link,
            "attempts": self.attempts,
        }


class SHNProviderClient:
    """Small provider-test transport client.

    Secrets and bearer tokens stay in memory. Returned transport metadata never
    contains Authorization, client_secret or access_token.
    """

    def __init__(
        self,
        client_file: str | Path = DEFAULT_CLIENT_FILE,
        base_url: str = DEFAULT_BASE_URL,
        console_url: str = DEFAULT_CONSOLE_URL,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        default_retry_after: int = 65,
    ) -> None:
        self.client_file = Path(client_file)
        self.base_url = base_url.rstrip("/")
        self.console_url = console_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.default_retry_after = int(default_retry_after)
        self._token: str | None = None
        self._token_expires_at = 0.0

    @classmethod
    def from_environment(cls) -> "SHNProviderClient":
        return cls(
            client_file=os.getenv("SHN_CLIENT_FILE", str(DEFAULT_CLIENT_FILE)),
            base_url=os.getenv("SHN_BASE", DEFAULT_BASE_URL),
            console_url=os.getenv("SHN_CONSOLE", DEFAULT_CONSOLE_URL),
        )

    @classmethod
    def credentials_available(
        cls,
        client_file: str | Path | None = None,
    ) -> bool:
        path = Path(client_file) if client_file else Path(
            os.getenv("SHN_CLIENT_FILE", str(DEFAULT_CLIENT_FILE))
        )
        if not path.is_file():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return bool(data.get("client_id") and data.get("client_secret"))

    def _credentials(self) -> tuple[str, str]:
        if not self.client_file.is_file():
            raise FileNotFoundError(
                f"SHN client credential file not found: {self.client_file}"
            )
        data = json.loads(self.client_file.read_text(encoding="utf-8"))
        client_id = data.get("client_id")
        client_secret = data.get("client_secret")
        if not client_id or not client_secret:
            raise ValueError("SHN client file has no client_id/client_secret")
        return str(client_id), str(client_secret)

    @staticmethod
    def _decode_body(raw: bytes, content_type: str | None) -> Any:
        text = raw.decode("utf-8", errors="replace")
        if "json" in (content_type or "").lower() or text.lstrip().startswith(("{", "[")):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return text

    def _open(self, request: urllib.request.Request) -> tuple[int, Any, Any]:
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read()
                return (
                    int(response.status),
                    self._decode_body(raw, response.headers.get("Content-Type")),
                    response.headers,
                )
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return (
                int(exc.code),
                self._decode_body(raw, exc.headers.get("Content-Type")),
                exc.headers,
            )

    def _ensure_token(self) -> str:
        now = time.monotonic()
        if self._token and now < self._token_expires_at:
            return self._token

        client_id, client_secret = self._credentials()
        credential = base64.b64encode(
            f"{client_id}:{client_secret}".encode("utf-8")
        ).decode("ascii")
        body = urllib.parse.urlencode(
            {"grant_type": "client_credentials"}
        ).encode("ascii")
        request = urllib.request.Request(
            f"{self.base_url}/oauth/token",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Basic {credential}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        status, payload, _headers = self._open(request)
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError(f"SHN token request failed with HTTP {status}: {payload}")
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("SHN token response contains no access_token")
        expires_in = int(payload.get("expires_in", 300))
        self._token = str(token)
        self._token_expires_at = time.monotonic() + max(1, expires_in - 60)
        return self._token

    @staticmethod
    def _correlation_id(prefix: str) -> str:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        suffix = f"-{stamp}"
        clean = "".join(ch if ch.isalnum() or ch in "-._" else "-" for ch in prefix)
        return f"{clean[:64-len(suffix)]}{suffix}"

    def post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        correlation_prefix: str,
        content_type: str = "application/json",
    ) -> SHNResponse:
        sent_correlation_id = self._correlation_id(correlation_prefix)
        attempts = 0
        started = time.monotonic()

        while True:
            attempts += 1
            token = self._ensure_token()
            request = urllib.request.Request(
                f"{self.base_url}{path}",
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": content_type,
                    "X-Correlation-Id": sent_correlation_id,
                },
            )
            status, body, headers = self._open(request)

            if status != 429 or attempts > self.max_retries:
                break

            retry_after = headers.get("Retry-After")
            try:
                delay = int(retry_after)
            except (TypeError, ValueError):
                delay = self.default_retry_after
            time.sleep(max(0, delay))
            self._token = None
            self._token_expires_at = 0.0

        elapsed_ms = (time.monotonic() - started) * 1000.0
        correlation_id = headers.get("X-Correlation-Id")
        leg_id = headers.get("X-SHN-Leg-Id")
        trace_id = correlation_id or sent_correlation_id
        return SHNResponse(
            status_code=status,
            body=body,
            correlation_id=correlation_id,
            sent_correlation_id=sent_correlation_id,
            leg_id=leg_id,
            trace_url=f"{self.console_url}/connectathon/trace/{trace_id}",
            elapsed_ms=elapsed_ms,
            warning=headers.get("Warning"),
            link=headers.get("Link"),
            attempts=attempts,
        )

    def crd(self, payload: dict[str, Any], *, correlation_prefix: str) -> SHNResponse:
        return self.post(
            "/cds-services/shn-order-sign",
            payload,
            correlation_prefix=correlation_prefix,
        )

    def dtr(self, payload: dict[str, Any], *, correlation_prefix: str) -> SHNResponse:
        return self.post(
            "/Questionnaire/$questionnaire-package",
            payload,
            correlation_prefix=correlation_prefix,
        )

    def pas_submit(
        self,
        payload: dict[str, Any],
        *,
        correlation_prefix: str,
    ) -> SHNResponse:
        return self.post(
            "/Claim/$submit",
            payload,
            correlation_prefix=correlation_prefix,
            content_type="application/fhir+json",
        )

    def pas_inquire(
        self,
        payload: dict[str, Any],
        *,
        correlation_prefix: str,
    ) -> SHNResponse:
        return self.post(
            "/Claim/$inquire",
            payload,
            correlation_prefix=correlation_prefix,
            content_type="application/fhir+json",
        )
