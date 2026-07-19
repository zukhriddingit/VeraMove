"""Tests for opaque, stable role-play recording capability URLs."""

from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from pydantic import HttpUrl

from services.api.app.core.errors import (
    ProviderConfigurationError,
    WebhookAuthenticationError,
)
from services.api.app.orchestration import recording_capability
from services.api.app.orchestration.recording_capability import (
    RecordingCapabilitySigner,
)

PUBLIC_ORIGIN = "https://api.veramove.example"
SIGNING_SECRET = "r" * 32


def test_recording_capability_url_is_stable_and_contains_no_provider_secret():
    call_id = uuid4()
    job_id = uuid4()
    signer = RecordingCapabilitySigner(PUBLIC_ORIGIN, SIGNING_SECRET)

    first = signer.build_url(call_id, job_id)
    second = signer.build_url(call_id, job_id)

    assert isinstance(first, HttpUrl)
    assert first == second
    parsed = urlsplit(str(first))
    parameters = parse_qs(parsed.query)
    assert f"/api/calls/{call_id}/recording" == parsed.path
    assert parameters["job_id"] == [str(job_id)]
    assert len(parameters["signature"][0]) == 64
    assert SIGNING_SECRET not in str(first)
    assert "elevenlabs" not in str(first).lower()
    signer.verify(call_id, job_id, parameters["signature"][0])


@pytest.mark.parametrize(
    "origin",
    (
        "http://api.veramove.example",
        "https://api.veramove.example/path",
        "https://user:password@api.veramove.example",
    ),
)
def test_recording_signer_requires_validated_https_public_origin(origin):
    with pytest.raises(ProviderConfigurationError, match="HTTPS origin"):
        RecordingCapabilitySigner(origin, SIGNING_SECRET)


def test_recording_signer_rejects_short_secret():
    with pytest.raises(ProviderConfigurationError, match="RECORDING_SIGNING_SECRET"):
        RecordingCapabilitySigner(PUBLIC_ORIGIN, "too-short")


def test_recording_capability_rejects_call_job_signature_and_rotation_tampering():
    call_id = uuid4()
    job_id = uuid4()
    signer = RecordingCapabilitySigner(PUBLIC_ORIGIN, SIGNING_SECRET)
    parsed = urlsplit(str(signer.build_url(call_id, job_id)))
    signature = parse_qs(parsed.query)["signature"][0]

    for verifier, candidate_call, candidate_job, candidate_signature in (
        (signer, uuid4(), job_id, signature),
        (signer, call_id, uuid4(), signature),
        (signer, call_id, job_id, "0" * 64),
        (
            RecordingCapabilitySigner(PUBLIC_ORIGIN, "n" * 32),
            call_id,
            job_id,
            signature,
        ),
    ):
        with pytest.raises(WebhookAuthenticationError, match="recording capability"):
            verifier.verify(candidate_call, candidate_job, candidate_signature)


def test_recording_capability_verification_uses_constant_time_comparison(monkeypatch):
    call_id = uuid4()
    job_id = uuid4()
    signer = RecordingCapabilitySigner(PUBLIC_ORIGIN, SIGNING_SECRET)
    signature = parse_qs(urlsplit(str(signer.build_url(call_id, job_id))).query)["signature"][0]
    comparisons: list[tuple[str, str]] = []

    def record_comparison(left: str, right: str) -> bool:
        comparisons.append((left, right))
        return True

    monkeypatch.setattr(recording_capability.hmac, "compare_digest", record_comparison)

    signer.verify(call_id, job_id, signature)

    assert comparisons == [(signature, signature)]
