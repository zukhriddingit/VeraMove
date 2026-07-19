"""Pure HMAC capabilities for canonical role-play recording URLs."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from urllib.parse import urlencode
from uuid import UUID

from pydantic import HttpUrl

from services.api.app.core.config import (
    MIN_LIVE_SECRET_BYTES,
    _https_origin,
    _secret_is_strong,
)
from services.api.app.core.errors import (
    ProviderConfigurationError,
    WebhookAuthenticationError,
)

CAPABILITY_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class RecordingCapabilitySigner:
    """Build and verify stable URLs without provider or repository access."""

    public_api_base_url: str
    signing_secret: str

    def __post_init__(self) -> None:
        origin = _https_origin("PUBLIC_API_BASE_URL", self.public_api_base_url)
        if not _secret_is_strong(self.signing_secret):
            raise ProviderConfigurationError(
                f"RECORDING_SIGNING_SECRET must be at least {MIN_LIVE_SECRET_BYTES} bytes"
            )
        object.__setattr__(self, "public_api_base_url", origin)

    def build_url(self, call_id: UUID, job_id: UUID) -> HttpUrl:
        """Return one deterministic capability URL for a canonical call/job pair."""

        canonical_call_id = _canonical_uuid(call_id)
        canonical_job_id = _canonical_uuid(job_id)
        signature = self._signature(canonical_call_id, canonical_job_id)
        query = urlencode({"job_id": str(canonical_job_id), "signature": signature})
        return HttpUrl(
            f"{self.public_api_base_url}/api/calls/{canonical_call_id}/recording?{query}"
        )

    def verify(
        self,
        call_id: UUID,
        job_id: UUID,
        signature: str,
    ) -> None:
        """Reject a capability unless every signed identity component matches."""

        try:
            canonical_call_id = _canonical_uuid(call_id)
            canonical_job_id = _canonical_uuid(job_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise WebhookAuthenticationError("Invalid recording capability") from exc
        expected = self._signature(canonical_call_id, canonical_job_id)
        if not isinstance(signature, str) or not hmac.compare_digest(
            expected,
            signature,
        ):
            raise WebhookAuthenticationError("Invalid recording capability")

    def _signature(self, call_id: UUID, job_id: UUID) -> str:
        message = (f"veramove-recording:{CAPABILITY_VERSION}:job={job_id}:call={call_id}").encode(
            "ascii"
        )
        return hmac.new(
            self.signing_secret.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()


def _canonical_uuid(value: UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))
