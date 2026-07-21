"""Route-local models for provider-facing and runtime API surfaces."""

from typing import Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from services.api.app.contracts import ElevenLabsWebhookEvent, JobSpecV1
from services.api.app.orchestration.intake_sessions import (
    IntakeDataMode,
    IntakeRecoveryAction,
    IntakeSessionStatus,
)
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


class CreateIntakeSessionRequest(BaseModel):
    """Select the privacy boundary before creating a browser voice session."""

    model_config = ConfigDict(extra="forbid")

    data_mode: IntakeDataMode = IntakeDataMode.SUPERVISED_ROLE_PLAY


class IntakeSessionResponse(BaseModel):
    """Expose safe intake correlation and the result only after completion."""

    model_config = ConfigDict(extra="forbid")

    intake_session_id: UUID
    job_id: UUID
    data_mode: IntakeDataMode
    status: IntakeSessionStatus
    conversation_id: str | None = None
    job_spec: JobSpecV1 | None = None
    partial_job_spec: JobSpecV1 | None = None
    missing_fields: tuple[str, ...] = ()
    terminal_reason: str | None = None
    recovery_action: IntakeRecoveryAction | None = None
    recovery_target_id: UUID | None = None
    resumed_from_session_id: UUID | None = None
    recovery_available: bool = False


class ElevenLabsConversationInitiationRequest(BaseModel):
    """Provider pre-call fields; phone metadata is accepted then discarded."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    agent_id: str = Field(min_length=1, max_length=200)
    call_sid: str = Field(min_length=1, max_length=200)
    caller_id: str | None = Field(
        default=None,
        max_length=80,
        exclude=True,
        repr=False,
    )
    called_number: str | None = Field(
        default=None,
        max_length=80,
        exclude=True,
        repr=False,
    )


class IntakeDynamicVariables(BaseModel):
    """The complete custom-variable set defined by the Intake agent."""

    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    intake_session_id: UUID
    agent_config_version: str = Field(min_length=1, max_length=80)


class AttachIntakeConversationRequest(BaseModel):
    """Accept only a bounded provider conversation identifier from the SDK."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    conversation_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class BrowserVoiceTokenResponse(BaseModel):
    """Return one ephemeral token plus canonical correlation variables."""

    model_config = ConfigDict(extra="forbid")

    conversation_token: str = Field(min_length=1, max_length=8_192, repr=False)
    dynamic_variables: IntakeDynamicVariables


class ElevenLabsConversationInitiationResponse(BaseModel):
    """Exact ElevenLabs response envelope for inbound personalization."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["conversation_initiation_client_data"] = "conversation_initiation_client_data"
    dynamic_variables: IntakeDynamicVariables


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
