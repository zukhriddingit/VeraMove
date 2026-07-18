"""FastAPI entry point for VeraMove."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services.api.app.api.router import router
from services.api.app.contracts import ErrorDetail, ErrorResponse
from services.api.app.core.config import Settings
from services.api.app.core.errors import DomainConflict, DomainError, ResourceNotFound


def create_app() -> FastAPI:
    settings = Settings.from_env()
    application = FastAPI(
        title="VeraMove API",
        summary="Mock-first moving-services negotiation API",
        version="0.1.0",
    )
    application.state.settings = settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(DomainError)
    async def handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        status_code = 404 if isinstance(exc, ResourceNotFound) else 409
        if not isinstance(exc, DomainConflict | ResourceNotFound):
            status_code = 400
        body = ErrorResponse(error=ErrorDetail(code=exc.code, message=str(exc)))
        return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))

    application.include_router(router)
    return application


app = create_app()
