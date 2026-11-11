import httpx
import pytest

from backend.config import Settings
from backend.paypal.client import PayPalAPIError, PayPalClient


def make_client(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return PayPalClient(Settings(paypal_client_id="id", paypal_client_secret="secret"), http=http)


def test_oauth_and_dispute_list():
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/v1/oauth2/token"):
            return httpx.Response(200, json={"access_token": "mock-token", "expires_in": 3600})
        return httpx.Response(200, json={"items": []})
    client = make_client(handler)
    assert client.list_disputes(page_size=1) == {"items": []}
    assert calls[0].headers["authorization"].startswith("Basic ")
    assert calls[1].headers["authorization"] == "Bearer mock-token"


def test_dispute_details_and_evidence_routes():
    paths = []
    def handler(request):
        paths.append((request.method, request.url.path))
        if request.url.path.endswith("/v1/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(200, json={"ok": True})
    client = make_client(handler)
    client.get_dispute("D-1")
    client.submit_evidence("D-1", {"evidence_type": "PROOF_OF_FULFILLMENT"})
    assert ("GET", "/v1/customer/disputes/D-1") in paths
    assert ("POST", "/v1/customer/disputes/D-1/provide-evidence") in paths


def test_api_error_does_not_expose_response_body():
    def handler(request):
        if request.url.path.endswith("/v1/oauth2/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(403, json={"secret": "do not leak"}, headers={"PayPal-Debug-Id": "debug-1"})
    client = make_client(handler)
    with pytest.raises(PayPalAPIError) as raised:
        client.list_disputes()
    assert raised.value.status_code == 403
    assert "do not leak" not in str(raised.value)
