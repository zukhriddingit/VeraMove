"""Fail-closed ElevenLabs browser token tests."""

from typing import Any

import pytest

from services.api.app.core.errors import ProviderRequestError
from services.api.app.integrations.elevenlabs.tokens import (
    ElevenLabsBrowserVoiceTokenClient,
)


class RecordingTransport:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.requests: list[tuple[str, dict[str, str], float]] = []

    def get_json(
        self,
        url: str,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        self.requests.append((url, headers, timeout_seconds))
        return self.response

    def get_bytes(self, url, headers, timeout_seconds):
        raise AssertionError("browser token issuance never fetches audio")


def test_issues_encoded_agent_token_without_exposing_key_in_url() -> None:
    transport = RecordingTransport({"token": "synthetic-ephemeral-token"})
    client = ElevenLabsBrowserVoiceTokenClient(
        api_key="synthetic-server-key",
        agent_id="agent_synthetic/intake",
        transport=transport,
    )

    assert client.issue_token() == "synthetic-ephemeral-token"
    assert transport.requests == [
        (
            "https://api.elevenlabs.io/v1/convai/conversation/token?agent_id=agent_synthetic%2Fintake",
            {"xi-api-key": "synthetic-server-key"},
            10.0,
        )
    ]
    assert "synthetic-server-key" not in transport.requests[0][0]


@pytest.mark.parametrize("payload", ({}, {"token": ""}, {"token": 7}))
def test_rejects_missing_or_malformed_provider_token(payload) -> None:
    client = ElevenLabsBrowserVoiceTokenClient(
        api_key="synthetic-server-key",
        agent_id="agent_synthetic_intake",
        transport=RecordingTransport(payload),
    )

    with pytest.raises(ProviderRequestError, match="invalid browser voice token"):
        client.issue_token()
