"""Route-local models for provider-facing and runtime API surfaces."""

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from services.api.app.contracts import ElevenLabsWebhookEvent
from services.api.app.orchestration.models import JobEvent


class DocumentIntakeRequest(BaseModel):
    """Bound the unstructured document text accepted by the intake route."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    document_text: str = Field(min_length=1, max_length=50_000)


class RuntimeHealthResponse(BaseModel):
    """Expose the selected runtime mode without revealing configuration values."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    mode: Literal["mock", "live"]
    service: Literal["veramove-api"] = "veramove-api"


class JobEventsResponse(BaseModel):
    """Envelope safe normalized events for a single job."""

    model_config = ConfigDict(extra="forbid")

    events: list[JobEvent]


class PostCallWebhookData(BaseModel):
    """Allowlisted fields used from ElevenLabs post-call data."""

    model_config = ConfigDict(extra="allow")

    agent_id: str
    conversation_id: str
    status: str


class ElevenLabsPostCallWebhook(BaseModel):
    """Typed public shape for the ElevenLabs post-call webhook."""

    model_config = ConfigDict(extra="allow")

    type: Literal["post_call_transcription"]
    event_timestamp: int
    data: PostCallWebhookData


WebhookRequest: TypeAlias = ElevenLabsWebhookEvent | ElevenLabsPostCallWebhook
