"""Protocol for future ElevenLabs conversation and Twilio transport adapters."""

from typing import Protocol

from services.api.app.contracts import CallRecord, JobSpecV1, Vendor


class TwilioTransport(Protocol):
    """Future outbound transport boundary, represented by a mock in this starter."""

    def create_call_reference(self, vendor: Vendor, job_spec: JobSpecV1) -> str: ...


class VoiceVendorGateway(Protocol):
    def create_calls(self, job_spec: JobSpecV1) -> list[CallRecord]: ...
