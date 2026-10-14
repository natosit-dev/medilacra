from __future__ import annotations

import json

import pytest

from connectathon.shn_provider.client import SHNProviderClient


PROXY = "https://touchstone.aegis.net:59747/cds-services/shn-order-sign"
SHN = "https://pa-test.shn-preview.org"


def _test_client(tmp_path, **kwargs):
    credential_file = tmp_path / "client.json"
    credential_file.write_text(
        json.dumps({"client_id": "test-client", "client_secret": "SECRET-NOT-LOGGED"})
    )
    client = SHNProviderClient(client_file=credential_file, base_url=SHN, **kwargs)
    sent = []

    def fake_open(request):
        sent.append(request)
        if request.full_url == f"{SHN}/oauth/token":
            return 200, {"access_token": "SYNTHETIC-TOKEN", "expires_in": 300}, {}
        return 200, {"cards": []}, {"X-Correlation-Id": "test-correlation"}

    client._open = fake_open
    return client, sent


def _headers(request):
    return {name.lower(): value for name, value in request.header_items()}


def test_touchstone_crd_uses_proxy_but_oauth_remains_at_shn(tmp_path):
    client, sent = _test_client(
        tmp_path, touchstone_crd_url=PROXY, touchstone_user_key="USER-KEY-TEST"
    )
    result = client.crd({"hook": "order-sign"}, correlation_prefix="test")

    assert [request.full_url for request in sent] == [
        f"{SHN}/oauth/token",
        PROXY,
    ]
    assert _headers(sent[1])["user_key"] == "USER-KEY-TEST"
    assert _headers(sent[1])["authorization"] == "Bearer SYNTHETIC-TOKEN"
    assert result.ok
    assert "USER-KEY-TEST" not in json.dumps(result.transport_dict())
    assert "SYNTHETIC-TOKEN" not in json.dumps(result.transport_dict())


def test_touchstone_does_not_proxy_dtr_pas_or_inquiry(tmp_path):
    client, sent = _test_client(
        tmp_path, touchstone_crd_url=PROXY, touchstone_user_key="USER-KEY-TEST"
    )
    client.dtr({"resourceType": "Parameters"}, correlation_prefix="test")
    client.pas_submit({"resourceType": "Bundle"}, correlation_prefix="test")
    client.pas_inquire({"resourceType": "Parameters"}, correlation_prefix="test")

    assert [request.full_url for request in sent[1:]] == [
        f"{SHN}/Questionnaire/$questionnaire-package",
        f"{SHN}/Claim/$submit",
        f"{SHN}/Claim/$inquire",
    ]
    assert all("user_key" not in _headers(request) for request in sent[1:])


def test_direct_shn_remains_default(tmp_path):
    client, sent = _test_client(tmp_path)
    client.crd({"hook": "order-sign"}, correlation_prefix="test")
    assert sent[1].full_url == f"{SHN}/cds-services/shn-order-sign"
    assert "user_key" not in _headers(sent[1])


@pytest.mark.parametrize(
    "url",
    [
        "https://www.google.com/cds-services/shn-order-sign",
        "http://touchstone.aegis.net:59747/cds-services/shn-order-sign",
        "https://touchstone.aegis.net:59747/",
        "https://touchstone.aegis.net:59747/cds-services/shn-order-sign?token=x",
    ],
)
def test_proxy_requires_https_aegis_endpoint(tmp_path, url):
    with pytest.raises(ValueError, match="Touchstone CRD URL"):
        _test_client(tmp_path, touchstone_crd_url=url, touchstone_user_key="secret")


def test_proxy_configuration_requires_both_values(tmp_path):
    with pytest.raises(ValueError, match="requires both"):
        _test_client(tmp_path, touchstone_crd_url=PROXY)
    with pytest.raises(ValueError, match="requires both"):
        _test_client(tmp_path, touchstone_user_key="secret")
