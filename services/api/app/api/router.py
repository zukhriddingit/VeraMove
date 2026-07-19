"""Typed FastAPI routes for the mock-first VeraMove workflow."""

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status
from pydantic import ValidationError

from services.api.app.api.dependencies import (
    get_intake_session_service,
    get_integration_status,
    get_live_voice_operator_service,
    get_service,
    get_settings,
)
from services.api.app.api.integration_status import IntegrationStatusSnapshot
from services.api.app.api.models import (
    DocumentIntakeRequest,
    ElevenLabsConversationInitiationRequest,
    ElevenLabsConversationInitiationResponse,
    IntakeDynamicVariables,
    IntakeSessionResponse,
    JobEventsResponse,
    RuntimeHealthResponse,
)
from services.api.app.contracts import (
    HealthResponse,
    JobRecord,
    JobSpecV1,
    RecommendationV1,
    VendorDiscoveryResponse,
    WebhookAck,
)
from services.api.app.core.config import Settings
from services.api.app.core.errors import WebhookPayloadError
from services.api.app.orchestration.intake_sessions import (
    IntakeSessionService,
    verify_pre_call_secret,
)
from services.api.app.orchestration.live_voice_operator import (
    LiveVoiceOperatorService,
)
from services.api.app.orchestration.service import VeraMoveService

router = APIRouter()
Service = Annotated[VeraMoveService, Depends(get_service)]
RuntimeSettings = Annotated[Settings, Depends(get_settings)]
IntakeSessions = Annotated[IntakeSessionService, Depends(get_intake_session_service)]
IntegrationStatus = Annotated[IntegrationStatusSnapshot, Depends(get_integration_status)]
LiveVoiceOperator = Annotated[
    LiveVoiceOperatorService,
    Depends(get_live_voice_operator_service),
]


@router.get(
    "/health",
    response_model=HealthResponse | RuntimeHealthResponse,
    tags=["system"],
)
def health(settings: RuntimeSettings) -> RuntimeHealthResponse:
    return RuntimeHealthResponse(mode=settings.app_mode)


@router.get(
    "/api/integrations/status",
    response_model=IntegrationStatusSnapshot,
    tags=["system"],
)
def integration_status(snapshot: IntegrationStatus) -> IntegrationStatusSnapshot:
    return snapshot


@router.post(
    "/api/intake/document",
    response_model=JobRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["intake"],
)
def create_job_from_document(
    request: DocumentIntakeRequest,
    service: Service,
) -> JobRecord:
    return service.create_job_from_document(request.document_text)


@router.post(
    "/api/intake/sessions",
    response_model=IntakeSessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["intake"],
)
def create_intake_session(sessions: IntakeSessions) -> IntakeSessionResponse:
    return IntakeSessionResponse.model_validate(sessions.create_web_session().model_dump())


@router.get(
    "/api/intake/sessions/{session_id}",
    response_model=IntakeSessionResponse,
    tags=["intake"],
)
def get_intake_session(
    session_id: UUID,
    sessions: IntakeSessions,
) -> IntakeSessionResponse:
    return IntakeSessionResponse.model_validate(sessions.get_session(session_id).model_dump())


@router.get(
    "/api/intake/conversations/{conversation_id}",
    response_model=IntakeSessionResponse,
    tags=["intake"],
)
def get_intake_session_by_conversation(
    conversation_id: Annotated[str, Path(min_length=1, max_length=200)],
    sessions: IntakeSessions,
) -> IntakeSessionResponse:
    return IntakeSessionResponse.model_validate(
        sessions.get_by_conversation(conversation_id).model_dump()
    )


@router.post(
    "/api/webhooks/elevenlabs/pre-call",
    response_model=ElevenLabsConversationInitiationResponse,
    tags=["webhooks"],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": ElevenLabsConversationInitiationRequest.model_json_schema()
                }
            },
        }
    },
)
async def elevenlabs_conversation_initiation(
    request: Request,
    sessions: IntakeSessions,
    settings: RuntimeSettings,
) -> ElevenLabsConversationInitiationResponse:
    verify_pre_call_secret(
        settings.live_voice.precall_secret,
        request.headers.get("x-veramove-precall-secret"),
    )
    body = await request.body()
    if len(body) > 32_768:
        raise WebhookPayloadError("ElevenLabs conversation-initiation body is too large")
    try:
        raw_payload = json.loads(body)
        parsed = ElevenLabsConversationInitiationRequest.model_validate(raw_payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError) as exc:
        raise WebhookPayloadError("ElevenLabs conversation-initiation payload is invalid") from exc
    session = sessions.create_pre_call_session(
        agent_id=parsed.agent_id,
        provider_call_key=parsed.call_sid,
    )
    return ElevenLabsConversationInitiationResponse(
        dynamic_variables=IntakeDynamicVariables(
            job_id=session.job_id,
            intake_session_id=session.intake_session_id,
            agent_config_version=session.agent_config_version,
        )
    )


@router.post(
    "/api/jobs",
    response_model=JobRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["jobs"],
)
def create_job(job_spec: JobSpecV1, service: Service) -> JobRecord:
    return service.create_job(job_spec)


@router.get("/api/jobs/{job_id}", response_model=JobRecord, tags=["jobs"])
def get_job(job_id: UUID, service: Service) -> JobRecord:
    return service.get_job(job_id)


@router.get(
    "/api/jobs/{job_id}/events",
    response_model=JobEventsResponse,
    tags=["jobs"],
)
def get_job_events(job_id: UUID, service: Service) -> JobEventsResponse:
    return JobEventsResponse(events=service.get_events(job_id))


@router.post("/api/jobs/{job_id}/confirm", response_model=JobRecord, tags=["jobs"])
def confirm_job(job_id: UUID, service: Service) -> JobRecord:
    return service.confirm_job(job_id)


@router.post("/api/jobs/{job_id}/calls", response_model=JobRecord, tags=["calls"])
def start_calls(job_id: UUID, service: Service) -> JobRecord:
    return service.start_calls(job_id)


@router.post("/api/jobs/{job_id}/negotiate", response_model=JobRecord, tags=["negotiation"])
def negotiate(job_id: UUID, service: Service) -> JobRecord:
    return service.negotiate(job_id)


@router.get("/api/jobs/{job_id}/report", response_model=RecommendationV1, tags=["reports"])
def get_report(job_id: UUID, service: Service) -> RecommendationV1:
    return service.get_report(job_id)


@router.get(
    "/api/calls/{call_id}/recording",
    response_class=Response,
    responses={
        200: {
            "content": {
                "audio/mpeg": {},
                "audio/mp4": {},
                "audio/wav": {},
            },
            "description": "Validated provider recording audio.",
        }
    },
    tags=["calls"],
)
def get_call_recording(
    call_id: UUID,
    job_id: Annotated[UUID, Query()],
    signature: Annotated[str, Query(pattern=r"^[a-f0-9]{64}$")],
    operator: LiveVoiceOperator,
) -> Response:
    payload = operator.fetch_recording(call_id, job_id, signature)
    return Response(
        content=payload.content,
        media_type=payload.media_type,
        headers={
            "Cache-Control": payload.cache_control,
            "Content-Length": str(payload.content_length),
        },
    )


@router.post(
    "/api/calls/{call_id}/repair",
    response_model=WebhookAck,
    tags=["calls"],
)
def repair_call(
    call_id: UUID,
    operator: LiveVoiceOperator,
    service: Service,
    operator_secret: Annotated[
        str | None,
        Header(alias="x-veramove-operator-secret", max_length=512),
    ] = None,
) -> WebhookAck:
    repair = operator.prepare_repair(call_id, operator_secret)
    return service.handle_elevenlabs_repair(repair)


@router.post(
    "/api/webhooks/elevenlabs",
    response_model=WebhookAck,
    tags=["webhooks"],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "anyOf": [
                            {"$ref": "#/components/schemas/ElevenLabsWebhookEvent"},
                            {"$ref": "#/components/schemas/ElevenLabsPostCallWebhook"},
                        ]
                    },
                }
            },
        }
    },
)
async def elevenlabs_webhook(
    request: Request,
    service: Service,
) -> WebhookAck:
    return service.handle_elevenlabs_webhook(
        await request.body(),
        request.headers.get("elevenlabs-signature"),
    )


@router.get("/api/vendors/discover", response_model=VendorDiscoveryResponse, tags=["vendors"])
def discover_vendors(
    service: Service,
    origin: Annotated[str | None, Query(max_length=200)] = None,
    destination: Annotated[str | None, Query(max_length=200)] = None,
) -> VendorDiscoveryResponse:
    return VendorDiscoveryResponse(
        vendors=service.discover_vendors(origin, destination),
        source=service.vendor_discovery_source,
    )
