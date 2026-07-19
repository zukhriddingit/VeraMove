"""FastAPI entry point for VeraMove."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services.api.app.api.dependencies import build_repository, build_service
from services.api.app.api.router import router
from services.api.app.contracts import ErrorDetail, ErrorResponse
from services.api.app.core.config import Settings
from services.api.app.core.errors import (
    DomainConflict,
    DomainError,
    ProviderConfigurationError,
    ProviderRequestError,
    ResourceNotFound,
    WebhookAuthenticationError,
    WebhookPayloadError,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    repository = build_repository(runtime_settings)
    service = build_service(runtime_settings, repository)
    application = FastAPI(
        title="VeraMove API",
        summary="Mock-first moving-services negotiation API",
        version="0.1.0",
    )
    application.state.settings = runtime_settings
    application.state.repository = repository
    application.state.service = service
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_settings.cors_allow_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(DomainError)
    async def handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        if isinstance(exc, ResourceNotFound):
            status_code = 404
        elif isinstance(exc, WebhookAuthenticationError):
            status_code = 401
        elif isinstance(exc, WebhookPayloadError):
            status_code = 400
        elif isinstance(exc, ProviderConfigurationError):
            status_code = 409
        elif isinstance(exc, ProviderRequestError):
            status_code = 502
        elif isinstance(exc, DomainConflict):
            status_code = 409
        else:
            status_code = 400
        body = ErrorResponse(error=ErrorDetail(code=exc.code, message=str(exc)))
        return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))

    application.include_router(router)
    return application


app = create_app()
