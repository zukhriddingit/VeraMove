"""Runtime composition tests for independently enabled live integrations."""

from typing import Any
from uuid import uuid4

import pytest

from services.api.app.api.dependencies import build_repository, build_service
from services.api.app.contracts import DocumentParseResult, IntakeSource
from services.api.app.core.config import (
    OpenAIConfig,
    Settings,
    SupabaseConfig,
    TavilyConfig,
)
from services.api.app.core.errors import DomainConflict
from services.api.app.integrations.openai.mock import MockNegotiationGateway
from services.api.app.integrations.tavily.cached import CachedTavilyVendorDiscovery
from services.api.app.integrations.tavily.mock import MockVendorDiscoveryGateway
from services.api.app.main import create_app
from services.api.app.orchestration.live_intelligence import LiveIntelligenceProvider
from services.api.app.orchestration.mock_intelligence import MockIntelligenceProvider
from services.api.app.repositories.memory import InMemoryRepository
from services.api.app.repositories.supabase import SupabaseRepository


class RecordingOpenAITransport:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def post(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.requests.append({"url": url, "headers": headers, "payload": payload})
        raise AssertionError("startup must not call OpenAI")


class RecordingTavilyTransport:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def post(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> Any:
        self.requests.append({"url": url, "headers": headers, "payload": payload})
        raise AssertionError("startup must not call Tavily")


class FakeSupabaseTableClient:
    def select_many(
        self,
        table: str,
        filters: dict[str, str],
    ) -> list[dict[str, Any]]:
        raise AssertionError("startup must not call Supabase")


class StaticDocumentGateway:
    def __init__(self, result: DocumentParseResult) -> None:
        self.result = result
        self.requests: list[tuple[bytes, str, str]] = []

    def parse_document(
        self,
        content: bytes,
        mime_type: str,
        source_id: str,
    ) -> DocumentParseResult:
        self.requests.append((content, mime_type, source_id))
        return self.result.model_copy(deep=True)


class StaticNarrator:
    def __init__(self, summary: str) -> None:
        self.summary = summary
        self.calls = 0

    def explain(self, job_spec, rankings, findings) -> str:
        del job_spec, rankings, findings
        self.calls += 1
        return self.summary

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("startup must not call Supabase")

    def upsert(
        self,
        table: str,
        row: dict[str, Any],
        on_conflict: str,
    ) -> dict[str, Any]:
        raise AssertionError("startup must not call Supabase")

    def update(
        self,
        table: str,
        filters: dict[str, str],
        values: dict[str, Any],
    ) -> dict[str, Any]:
        raise AssertionError("startup must not call Supabase")


def test_mock_defaults_keep_every_optional_provider_off() -> None:
    settings = Settings()
    repository = build_repository(settings)
    service = build_service(settings, repository)

    assert isinstance(repository, InMemoryRepository)
    assert isinstance(service._intelligence, MockIntelligenceProvider)
    assert isinstance(service._discovery, MockVendorDiscoveryGateway)
    assert service._recommendation_narrator is None


def test_openai_can_be_enabled_without_other_live_providers() -> None:
    transport = RecordingOpenAITransport()
    settings = Settings(openai=OpenAIConfig(enabled=True, api_key="synthetic-openai-key"))
    repository = build_repository(settings)
    service = build_service(
        settings,
        repository,
        openai_transport=transport,
    )

    assert isinstance(service._intelligence, LiveIntelligenceProvider)
    assert isinstance(service._intelligence._negotiation_gateway, MockNegotiationGateway)
    assert service._recommendation_narrator is not None
    assert isinstance(service._discovery, MockVendorDiscoveryGateway)
    assert transport.requests == []


def test_tavily_can_be_enabled_without_other_live_providers() -> None:
    transport = RecordingTavilyTransport()
    settings = Settings(tavily=TavilyConfig(enabled=True, api_key="synthetic-tavily-key"))
    repository = build_repository(settings)
    service = build_service(
        settings,
        repository,
        tavily_transport=transport,
    )

    assert isinstance(service._intelligence, MockIntelligenceProvider)
    assert isinstance(service._discovery, CachedTavilyVendorDiscovery)
    assert service.vendor_discovery_source == "tavily"
    assert transport.requests == []


def test_supabase_can_be_enabled_without_other_live_providers() -> None:
    client = FakeSupabaseTableClient()
    settings = Settings(
        supabase=SupabaseConfig(
            enabled=True,
            url="https://synthetic-project.supabase.co",
            secret_key="synthetic-supabase-secret",
        )
    )

    repository = build_repository(settings, supabase_client=client)
    service = build_service(settings, repository)

    assert isinstance(repository, SupabaseRepository)
    assert isinstance(service._intelligence, MockIntelligenceProvider)
    assert isinstance(service._discovery, MockVendorDiscoveryGateway)


def test_create_app_stores_one_composed_settings_repository_and_service() -> None:
    settings = Settings()
    application = create_app(settings=settings)

    assert application.state.settings is settings
    assert application.state.repository is build_repository(settings)
    assert application.state.service._jobs is application.state.repository


def test_live_intelligence_uses_the_same_document_contract_and_mock_negotiation(
    fixtures,
) -> None:
    job_spec = fixtures.load_job().model_copy(
        update={
            "job_id": uuid4(),
            "intake_source": IntakeSource.DOCUMENT,
            "confirmed": False,
            "confirmed_at": None,
            "locked_version": None,
        },
        deep=True,
    )
    gateway = StaticDocumentGateway(DocumentParseResult(job_spec=job_spec))
    provider = LiveIntelligenceProvider(
        gateway,
        MockNegotiationGateway(fixtures),
    )

    extracted = provider.extract_document("SYNTHETIC two-bedroom move")

    assert extracted == job_spec
    assert gateway.requests == [
        (
            b"SYNTHETIC two-bedroom move",
            "text/plain",
            "document-intake.txt",
        )
    ]
    with pytest.raises(DomainConflict, match="Document text is required"):
        provider.extract_document("   ")


def test_optional_narrator_can_only_replace_recommendation_summary(service) -> None:
    created = service.create_job_from_document("Synthetic inventory")
    service.confirm_job(created.job_spec.job_id)
    called = service.start_calls(created.job_spec.job_id)
    baseline = service._build_recommendation(called)
    narrator = StaticNarrator("Grounded synthetic recommendation.")
    service._recommendation_narrator = narrator

    narrated = service._build_recommendation(called)

    baseline_payload = baseline.model_dump(mode="json")
    narrated_payload = narrated.model_dump(mode="json")
    assert baseline_payload.pop("summary") != narrated_payload.pop("summary")
    assert narrated.summary == "Grounded synthetic recommendation."
    assert narrated_payload == baseline_payload
    assert narrator.calls == 1
