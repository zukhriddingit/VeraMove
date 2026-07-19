"""Application wiring for independently enabled, fail-closed providers."""

from datetime import UTC, datetime
from typing import Protocol

from fastapi import Request

from services.api.app.core.config import Settings
from services.api.app.core.errors import ProviderConfigurationError
from services.api.app.integrations.elevenlabs.base import JsonHttpTransport
from services.api.app.integrations.elevenlabs.live import (
    ElevenLabsVoiceProvider,
    HttpxJsonTransport,
)
from services.api.app.integrations.elevenlabs.mock import MockVoiceProvider
from services.api.app.integrations.elevenlabs.webhook import (
    ElevenLabsWebhookProcessor,
)
from services.api.app.integrations.openai.base import OpenAIJsonTransport
from services.api.app.integrations.openai.document import OpenAIDocumentParser
from services.api.app.integrations.openai.live import (
    OpenAIResponsesClient,
    OpenAIResponsesNarrativeClient,
)
from services.api.app.integrations.openai.mock import MockNegotiationGateway
from services.api.app.integrations.openai.recommendation import (
    OpenAIRecommendationNarrator,
)
from services.api.app.integrations.tavily.base import TavilyJsonTransport
from services.api.app.integrations.tavily.cached import CachedTavilyVendorDiscovery
from services.api.app.integrations.tavily.live import TavilyHttpClient
from services.api.app.integrations.tavily.mock import MockVendorDiscoveryGateway
from services.api.app.orchestration.fixtures import DemoFixtures
from services.api.app.orchestration.live_intelligence import LiveIntelligenceProvider
from services.api.app.orchestration.mock_intelligence import MockIntelligenceProvider
from services.api.app.orchestration.role_play import FixtureRolePlayVendorRoster
from services.api.app.orchestration.service import VeraMoveService, utc_now
from services.api.app.repositories.base import (
    CallRepository,
    JobRepository,
    QuoteRepository,
)
from services.api.app.repositories.memory import InMemoryRepository
from services.api.app.repositories.supabase import SupabaseRepository
from services.api.app.repositories.supabase_client import (
    SupabasePostgrestClient,
    SupabaseTableClient,
)

_repository = InMemoryRepository()


class ApplicationRepository(
    JobRepository,
    CallRepository,
    QuoteRepository,
    Protocol,
):
    """One repository implementation used across the aggregate transaction boundary."""


def get_repository() -> InMemoryRepository:
    return _repository


def get_settings(request: Request) -> Settings:
    """Return the settings snapshot used to create the current application."""

    return request.app.state.settings


def get_service(request: Request) -> VeraMoveService:
    """Return the service composed from the same application settings snapshot."""

    return request.app.state.service


def mock_now() -> datetime:
    """Keep synthetic provider timestamps ordered and demo responses deterministic."""

    return datetime(2026, 7, 18, 16, 0, tzinfo=UTC)


def build_repository(
    settings: Settings,
    supabase_client: SupabaseTableClient | None = None,
) -> InMemoryRepository | SupabaseRepository:
    """Select persistence independently; enabled misconfiguration fails startup."""

    if not settings.supabase.enabled:
        return _repository
    config = settings.require_supabase_config()
    assert config.url is not None
    assert config.secret_key is not None
    client = supabase_client or SupabasePostgrestClient(
        url=config.url,
        secret_key=config.secret_key,
    )
    return SupabaseRepository(client)


def build_service(
    settings: Settings,
    repository: ApplicationRepository,
    voice_transport: JsonHttpTransport | None = None,
    openai_transport: OpenAIJsonTransport | None = None,
    tavily_transport: TavilyJsonTransport | None = None,
) -> VeraMoveService:
    """Compose mock or live boundaries without initiating provider activity."""

    fixtures = DemoFixtures()
    if settings.app_mode == "mock":
        voice = MockVoiceProvider(fixtures)
    elif settings.app_mode == "live":
        voice = ElevenLabsVoiceProvider(
            settings,
            (voice_transport if voice_transport is not None else HttpxJsonTransport()),
        )
    else:
        raise ProviderConfigurationError("APP_MODE must be either mock or live")
    service_clock = mock_now if settings.app_mode == "mock" else utc_now
    webhooks = (
        ElevenLabsWebhookProcessor(
            secret="synthetic-webhook-secret",
            clock=mock_now,
        )
        if settings.app_mode == "mock"
        else ElevenLabsWebhookProcessor(
            secret=settings.live_voice.webhook_secret,
        )
    )
    negotiation_gateway = MockNegotiationGateway(fixtures)
    if settings.openai.enabled:
        openai_config = settings.require_openai_config()
        assert openai_config.api_key is not None
        responses_client = OpenAIResponsesClient(
            api_key=openai_config.api_key,
            api_base_url=openai_config.api_base_url,
            transport=openai_transport,
        )
        intelligence = LiveIntelligenceProvider(
            OpenAIDocumentParser(
                responses_client,
                model=openai_config.document_model,
            ),
            negotiation_gateway,
        )
        recommendation_narrator = OpenAIRecommendationNarrator(
            OpenAIResponsesNarrativeClient(
                api_key=openai_config.api_key,
                api_base_url=openai_config.api_base_url,
                transport=openai_transport,
            ),
            model=openai_config.recommendation_model,
        )
    else:
        intelligence = MockIntelligenceProvider(
            fixtures,
            negotiation_gateway,
        )
        recommendation_narrator = None

    if settings.tavily.enabled:
        tavily_config = settings.require_tavily_config()
        assert tavily_config.api_key is not None
        discovery = CachedTavilyVendorDiscovery(
            TavilyHttpClient(
                api_key=tavily_config.api_key,
                api_base_url=tavily_config.api_base_url,
                transport=tavily_transport,
            )
        )
    else:
        discovery = MockVendorDiscoveryGateway(fixtures)

    return VeraMoveService(
        jobs=repository,
        calls=repository,
        quotes=repository,
        voice=voice,
        intelligence=intelligence,
        discovery=discovery,
        webhooks=webhooks,
        fixtures=fixtures,
        vendor_roster=(
            FixtureRolePlayVendorRoster(fixtures)
            if settings.app_mode == "live"
            else None
        ),
        recommendation_narrator=recommendation_narrator,
        clock=service_clock,
    )
