"""Typed FastAPI routes for the mock-first VeraMove workflow."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, status

from services.api.app.api.dependencies import get_service, get_settings
from services.api.app.api.models import (
    DocumentIntakeRequest,
    JobEventsResponse,
    RuntimeHealthResponse,
    WebhookRequest,
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
from services.api.app.orchestration.service import VeraMoveService

router = APIRouter()
Service = Annotated[VeraMoveService, Depends(get_service)]
RuntimeSettings = Annotated[Settings, Depends(get_settings)]


@router.get(
    "/health",
    response_model=HealthResponse | RuntimeHealthResponse,
    tags=["system"],
)
def health(settings: RuntimeSettings) -> RuntimeHealthResponse:
    return RuntimeHealthResponse(mode=settings.app_mode)


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


@router.post(
    "/api/webhooks/elevenlabs",
    response_model=WebhookAck,
    tags=["webhooks"],
)
async def elevenlabs_webhook(
    request: Request,
    _event: Annotated[WebhookRequest, Body()],
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
    return VendorDiscoveryResponse(vendors=service.discover_vendors(origin, destination))
