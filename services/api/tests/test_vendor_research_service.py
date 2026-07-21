"""Job-scoped real vendor discovery, shortlist, and research orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import HttpUrl

from services.api.app.contracts import (
    ConsentMethod,
    DataClassification,
    FeeCategory,
    JobRecord,
    JobState,
    ProvenanceReference,
    ProvenanceType,
    VendorCallAuthorizationRequest,
    VendorCallAuthorizationSelectionV1,
    VendorSearchQuery,
    WebsiteClaimKind,
    WebsiteResearchClaimV1,
)
from services.api.app.core.errors import DomainConflict, ProviderRequestError, ResourceNotFound
from services.api.app.integrations.tavily.base import ExtractedWebPage
from services.api.app.orchestration.vendor_research import VendorResearchService
from services.api.app.repositories.memory import InMemoryRepository

NOW = datetime(2026, 7, 21, 19, 0, tzinfo=UTC)
CONTACT_HASH_SECRET = "synthetic-contact-hash-secret-32-bytes-minimum"
REQUIRED_FEES = {
    FeeCategory.BASE_SERVICE,
    FeeCategory.HOURLY_MINIMUM,
    FeeCategory.TRAVEL,
    FeeCategory.FUEL,
    FeeCategory.STAIRS,
    FeeCategory.ELEVATOR,
    FeeCategory.LONG_CARRY,
    FeeCategory.PACKING,
    FeeCategory.MATERIALS,
    FeeCategory.DISASSEMBLY,
    FeeCategory.STORAGE,
    FeeCategory.INSURANCE,
    FeeCategory.TAX,
    FeeCategory.DEPOSIT,
}


class RecordingDiscovery:
    source = "tavily"

    def __init__(self, vendors) -> None:
        self.vendors = vendors
        self.queries: list[VendorSearchQuery] = []

    def source_call_list(self, query: VendorSearchQuery):
        self.queries.append(query)
        return [vendor.model_copy(deep=True) for vendor in self.vendors]

    def discover(self, origin, destination):
        raise AssertionError("job research must use the typed search query")


class RecordingExtract:
    def __init__(self, pages: dict[str, ExtractedWebPage | None]) -> None:
        self.pages = pages
        self.requests: list[tuple[HttpUrl, ...]] = []

    def extract(self, urls):
        self.requests.append(urls)
        return {str(url): self.pages.get(str(url)) for url in urls}


class RecordingClaimExtractor:
    def __init__(self) -> None:
        self.requests = []
        self.fail_hosts: set[str] = set()

    def extract(self, vendor, page, retrieved_at):
        self.requests.append((vendor, page, retrieved_at))
        if page.url.host in self.fail_hosts:
            raise ProviderRequestError("private provider detail")
        excerpt = page.content[:500]
        return [
            WebsiteResearchClaimV1(
                kind=WebsiteClaimKind.HOURLY_RATE,
                summary=f"{vendor.name} advertises moving service from $149/hour.",
                advertised_amount="149.00",
                currency="USD",
                unit="hour",
                qualifiers=["starting at"],
                source_url=page.url,
                source_excerpt=excerpt,
                retrieved_at=retrieved_at,
            )
        ]


def _confirmed_record(job_spec) -> JobRecord:
    confirmed = job_spec.model_copy(
        update={
            "origin": job_spec.origin.model_copy(
                update={"address_summary": "Newton, MA"}
            ),
            "destination": job_spec.destination.model_copy(
                update={"address_summary": "Boston, MA"}
            ),
            "data_classification": DataClassification.REAL_REDACTED,
            "confirmed": True,
            "confirmed_at": NOW,
            "locked_version": job_spec.version,
        },
        deep=True,
    )
    return JobRecord(
        job_spec=confirmed,
        state=JobState.CONFIRMED,
        created_at=NOW,
        updated_at=NOW,
    )


def _real_vendors(fixtures):
    vendors = []
    for index, vendor in enumerate(fixtures.load_vendors()):
        url = f"https://vendor-{index}.example/pricing"
        vendors.append(
            vendor.model_copy(
                update={
                    "data_classification": DataClassification.REAL_REDACTED,
                    "provenance": [
                        ProvenanceReference(
                            source_type=ProvenanceType.TAVILY,
                            source_id=f"vendor-{index}.example",
                            location=url,
                        )
                    ],
                },
                deep=True,
            )
        )
    return vendors


@pytest.fixture
def research_stack(fixtures, job_spec):
    repository = InMemoryRepository()
    job = _confirmed_record(job_spec)
    repository.create(job)
    vendors = _real_vendors(fixtures)
    pages = {
        vendor.provenance[0].location: ExtractedWebPage(
            url=HttpUrl(vendor.provenance[0].location),
            content="Moving services starting at $149/hour.",
            truncated=False,
        )
        for vendor in vendors
    }
    discovery = RecordingDiscovery(vendors)
    extract = RecordingExtract(pages)
    claim_extractor = RecordingClaimExtractor()
    service = VendorResearchService(
        jobs=repository,
        research=repository,
        authorizations=repository,
        calls=repository,
        discovery=discovery,
        extract=extract,
        claim_extractor=claim_extractor,
        required_fee_categories=REQUIRED_FEES,
        clock=lambda: NOW,
        contact_hash_secret=CONTACT_HASH_SECRET,
    )
    return service, repository, job, vendors, discovery, extract, claim_extractor


def test_discovery_uses_locked_city_state_and_persists_real_candidates(research_stack):
    service, repository, job, vendors, discovery, _, _ = research_stack

    result = service.discover(job.job_spec.job_id)
    replay = service.discover(job.job_spec.job_id)

    assert discovery.queries == [
        VendorSearchQuery(
            city="Newton",
            state="MA",
            service_type="moving from Newton, MA to Boston, MA",
            radius_miles=25,
        )
    ]
    assert replay == result
    assert result.source == "tavily"
    assert result.candidates == vendors
    assert all(
        vendor.data_classification is DataClassification.REAL_REDACTED
        for vendor in result.candidates
    )
    assert repository.get_vendor_research(job.job_spec.job_id, "1.0") == result


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Newton, Massachusetts", ("Newton", "MA")),
        ("Boston, ma", ("Boston", "MA")),
        ("Washington, District of Columbia", ("Washington", "DC")),
    ],
)
def test_city_state_normalizes_full_names_and_case(value, expected):
    assert VendorResearchService._city_state(value) == expected


def test_discovery_requires_confirmed_safe_city_state(fixtures, job_spec):
    repository = InMemoryRepository()
    draft = JobRecord(
        job_spec=job_spec,
        state=JobState.INTAKE_COMPLETE,
        created_at=NOW,
        updated_at=NOW,
    )
    repository.create(draft)
    service = VendorResearchService(
        jobs=repository,
        research=repository,
        authorizations=repository,
        calls=repository,
        discovery=RecordingDiscovery(_real_vendors(fixtures)),
        extract=RecordingExtract({}),
        claim_extractor=RecordingClaimExtractor(),
        required_fee_categories=REQUIRED_FEES,
        clock=lambda: NOW,
    )
    with pytest.raises(DomainConflict, match="confirmed"):
        service.discover(job_spec.job_id)

    confirmed = _confirmed_record(job_spec)
    confirmed.job_spec = confirmed.job_spec.model_copy(
        update={
            "origin": confirmed.job_spec.origin.model_copy(
                update={"address_summary": "123 Main Street, Newton, MA"}
            )
        },
        deep=True,
    )
    repository = InMemoryRepository()
    repository.create(confirmed)
    service = VendorResearchService(
        jobs=repository,
        research=repository,
        authorizations=repository,
        calls=repository,
        discovery=RecordingDiscovery(_real_vendors(fixtures)),
        extract=RecordingExtract({}),
        claim_extractor=RecordingClaimExtractor(),
        required_fee_categories=REQUIRED_FEES,
        clock=lambda: NOW,
    )
    with pytest.raises(DomainConflict, match="city and state"):
        service.discover(confirmed.job_spec.job_id)


def test_shortlist_accepts_only_three_persisted_candidates_and_clear_allows_refresh(
    research_stack,
):
    service, _, job, vendors, discovery, _, _ = research_stack
    service.discover(job.job_spec.job_id)

    with pytest.raises(DomainConflict, match="exactly three"):
        service.set_shortlist(
            job.job_spec.job_id,
            [vendors[0].vendor_id, vendors[1].vendor_id],
        )
    with pytest.raises(DomainConflict, match="persisted discovery candidates"):
        service.set_shortlist(
            job.job_spec.job_id,
            [vendors[0].vendor_id, vendors[1].vendor_id, uuid4()],
        )

    selected = service.set_shortlist(
        job.job_spec.job_id,
        [vendor.vendor_id for vendor in vendors],
    )
    assert [item.status for item in selected.dossiers] == ["pending"] * 3
    with pytest.raises(DomainConflict, match="clear the shortlist"):
        service.discover(job.job_spec.job_id, refresh=True)

    cleared = service.clear_shortlist(job.job_spec.job_id)
    assert cleared.selected_vendor_ids == []
    assert cleared.dossiers == []
    refreshed = service.discover(job.job_spec.job_id, refresh=True)
    assert len(discovery.queries) == 2
    assert refreshed.candidates == vendors


def test_analysis_persists_claims_questions_and_never_mutates_job_evidence(research_stack):
    service, repository, job, vendors, _, extract, claim_extractor = research_stack
    service.discover(job.job_spec.job_id)
    service.set_shortlist(
        job.job_spec.job_id,
        [vendor.vendor_id for vendor in vendors],
    )

    analyzed = service.analyze(job.job_spec.job_id)
    replay = service.analyze(job.job_spec.job_id)
    stored_job = repository.get(job.job_spec.job_id)

    assert [item.status for item in analyzed.dossiers] == ["complete"] * 3
    assert all(item.claims for item in analyzed.dossiers)
    assert all(item.verification_questions for item in analyzed.dossiers)
    assert all(
        claim.classification == "unverified_website_claim"
        for dossier in analyzed.dossiers
        for claim in dossier.claims
    )
    assert replay == analyzed
    assert len(extract.requests) == 1
    assert len(claim_extractor.requests) == 3
    assert stored_job is not None
    assert stored_job.calls == []
    assert stored_job.quotes == []
    assert stored_job.recommendation is None


def test_analysis_persists_reconstructable_official_contact_candidates(research_stack):
    service, repository, job, vendors, _, extract, _ = research_stack
    for index, vendor in enumerate(vendors):
        url = vendor.provenance[0].location
        extract.pages[url] = ExtractedWebPage(
            url=HttpUrl(url),
            content=f"Moving services start at $149/hour. Call (617) 555-010{index}.",
            truncated=False,
        )
    service.discover(job.job_spec.job_id)
    service.set_shortlist(
        job.job_spec.job_id,
        [vendor.vendor_id for vendor in vendors],
    )

    analyzed = service.analyze(job.job_spec.job_id)
    stored = repository.get_vendor_research(job.job_spec.job_id, "1.0")

    assert stored is not None
    assert [
        dossier.contact_candidates[0].normalized_number
        for dossier in analyzed.dossiers
    ] == ["+16175550100", "+16175550101", "+16175550102"]
    assert stored == analyzed
    safe_payload = analyzed.model_dump(mode="json")
    assert "normalized_number" not in repr(safe_payload)


def test_authorization_resolves_exactly_three_server_contacts_and_exposes_safe_view(
    research_stack,
):
    service, _, job, vendors, _, extract, _ = research_stack
    for index, vendor in enumerate(vendors):
        url = vendor.provenance[0].location
        extract.pages[url] = ExtractedWebPage(
            url=HttpUrl(url),
            content=f"Moving services start at $149/hour. Call (617) 555-010{index}.",
            truncated=False,
        )
    service.discover(job.job_spec.job_id)
    service.set_shortlist(
        job.job_spec.job_id,
        [vendor.vendor_id for vendor in vendors],
    )
    analyzed = service.analyze(job.job_spec.job_id)
    selections = [
        VendorCallAuthorizationSelectionV1(
            vendor_id=dossier.vendor.vendor_id,
            contact_id=dossier.contact_candidates[0].contact_id,
            recipient_timezone="America/New_York",
            consent_method=ConsentMethod.DIRECT_RECIPIENT_OPT_IN,
            consent_evidence_reference=f"synthetic-consent:{index}",
            consented_at=NOW,
            ai_call_consented=True,
            recording_consented=True,
        )
        for index, dossier in enumerate(analyzed.dossiers)
    ]

    view = service.authorize_calls(
        job.job_spec.job_id,
        VendorCallAuthorizationRequest(
            selections=selections,
            batch_acknowledged=True,
        ),
    )

    assert view.authorization_ready is True
    assert len(view.call_authorizations) == 3
    assert len(view.call_plans) == 3
    assert all(item.ready for item in view.call_authorizations)
    safe = view.model_dump_json()
    assert "+1617555" not in safe
    assert "number_hash" not in safe
    assert "normalized_number" not in safe

    cleared = service.clear_call_authorizations(job.job_spec.job_id)
    assert cleared.authorization_ready is False
    assert cleared.call_authorizations == []


def test_analysis_keeps_partial_success_and_retries_only_non_complete_dossiers(
    research_stack,
):
    service, _, job, vendors, _, extract, claim_extractor = research_stack
    failed_url = vendors[1].provenance[0].location
    extract.pages[failed_url] = None
    truncated_url = vendors[2].provenance[0].location
    extract.pages[truncated_url] = ExtractedWebPage(
        url=HttpUrl(truncated_url),
        content="Moving services starting at $149/hour.",
        truncated=True,
    )
    service.discover(job.job_spec.job_id)
    service.set_shortlist(
        job.job_spec.job_id,
        [vendor.vendor_id for vendor in vendors],
    )

    first = service.analyze(job.job_spec.job_id)
    assert [item.status for item in first.dossiers] == [
        "complete",
        "failed",
        "partial",
    ]
    assert "provider detail" not in repr(first)

    extract.pages[failed_url] = ExtractedWebPage(
        url=HttpUrl(failed_url),
        content="Moving services starting at $149/hour.",
        truncated=False,
    )
    extract.pages[truncated_url] = ExtractedWebPage(
        url=HttpUrl(truncated_url),
        content="Moving services starting at $149/hour.",
        truncated=False,
    )
    second = service.analyze(job.job_spec.job_id)

    assert [item.status for item in second.dossiers] == ["complete"] * 3
    assert len(extract.requests) == 2
    assert extract.requests[1] == (
        HttpUrl(failed_url),
        HttpUrl(truncated_url),
    )
    assert len(claim_extractor.requests) == 4


def test_get_before_discovery_is_not_found(research_stack):
    service, _, job, *_ = research_stack
    with pytest.raises(ResourceNotFound, match="Vendor research"):
        service.get(job.job_spec.job_id)
