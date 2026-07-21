"""Official-host extraction, consent authorization, and suppression tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import HttpUrl, ValidationError

from services.api.app.contracts import (
    ConsentMethod,
    DataClassification,
    JobRecord,
    JobState,
    ProvenanceReference,
    ProvenanceType,
    SuppressionReason,
    VendorCallAuthorizationV1,
    VendorContactCandidateV1,
    VendorResearchDossierV1,
    VendorSuppressionV1,
)
from services.api.app.core.errors import DomainConflict
from services.api.app.integrations.tavily.base import ExtractedWebPage
from services.api.app.orchestration.models import job_spec_sha256
from services.api.app.orchestration.vendor_contacts import (
    authorization_is_current,
    destination_hash,
    extract_official_us_contacts,
    permitted_call_time,
)
from services.api.app.repositories.memory import InMemoryRepository

NOW = datetime(2026, 7, 21, 16, 0, tzinfo=UTC)
HASH_SECRET = "synthetic-contact-hash-secret-32-bytes-minimum"


@pytest.fixture
def official_vendor(fixtures):
    return fixtures.load_vendors()[0].model_copy(
        update={
            "data_classification": DataClassification.REAL_REDACTED,
            "provenance": [
                ProvenanceReference(
                    source_type=ProvenanceType.TAVILY,
                    source_id="official.example",
                    location="https://www.official.example/pricing",
                )
            ],
        },
        deep=True,
    )


def test_extracts_tel_and_visible_us_numbers_from_official_host(official_vendor):
    page = ExtractedWebPage(
        url=HttpUrl("https://official.example/contact"),
        content=(
            '<a href="tel:+16175550101">Call our office</a> '
            "or reach dispatch at (617) 555-0102. Duplicate: 617-555-0101."
        ),
        truncated=False,
    )

    contacts = extract_official_us_contacts(official_vendor, page)

    assert [item.normalized_number for item in contacts] == [
        "+16175550101",
        "+16175550102",
    ]
    assert [item.display_number for item in contacts] == [
        "(617) 555-0101",
        "(617) 555-0102",
    ]
    assert all(str(item.source_url).startswith("https://official.example") for item in contacts)
    assert len({item.contact_id for item in contacts}) == 2


def test_rejects_contact_page_from_third_party_host(official_vendor):
    page = ExtractedWebPage(
        url=HttpUrl("https://directory.example/vendor"),
        content="Call (617) 555-0101.",
        truncated=False,
    )

    with pytest.raises(DomainConflict, match="official website host"):
        extract_official_us_contacts(official_vendor, page)


def test_caps_contacts_and_ignores_non_us_or_extension_only_values(official_vendor):
    page = ExtractedWebPage(
        url=HttpUrl("https://official.example/contact"),
        content=" ".join(
            [
                "+44 20 7946 0958",
                "ext. 123",
                *[f"(617) 555-01{index:02d}" for index in range(6)],
            ]
        ),
        truncated=False,
    )

    contacts = extract_official_us_contacts(official_vendor, page)

    assert len(contacts) == 5
    assert all(item.normalized_number.startswith("+1617") for item in contacts)


def test_private_normalized_number_is_reconstructed_after_safe_dump(official_vendor):
    contact = extract_official_us_contacts(
        official_vendor,
        ExtractedWebPage(
            url=HttpUrl("https://official.example/contact"),
            content="(617) 555-0101",
            truncated=False,
        ),
    )[0]

    safe = contact.model_dump(mode="json")
    assert "normalized_number" not in safe
    assert VendorContactCandidateV1.model_validate(safe).normalized_number == "+16175550101"


def test_dossier_rejects_contact_for_a_different_vendor(official_vendor):
    contact = extract_official_us_contacts(
        official_vendor,
        ExtractedWebPage(
            url=HttpUrl("https://official.example/contact"),
            content="(617) 555-0101",
            truncated=False,
        ),
    )[0]

    with pytest.raises(ValidationError, match="dossier vendor"):
        VendorResearchDossierV1(
            vendor=official_vendor,
            status="complete",
            contact_candidates=[
                contact.model_copy(update={"vendor_id": uuid4()}, deep=True)
            ],
            researched_at="2026-07-21T12:00:00Z",
        )


def _authorization(job_spec, vendor, contact) -> VendorCallAuthorizationV1:
    return VendorCallAuthorizationV1(
        job_id=job_spec.job_id,
        job_spec_version=job_spec.version,
        job_spec_sha256=job_spec_sha256(job_spec),
        vendor_id=vendor.vendor_id,
        contact_id=contact.contact_id,
        normalized_number=contact.normalized_number,
        display_number=contact.display_number,
        number_hash=destination_hash(HASH_SECRET, contact.normalized_number),
        recipient_timezone="America/New_York",
        consent_method=ConsentMethod.DIRECT_RECIPIENT_OPT_IN,
        consent_evidence_reference="consent:synthetic:001",
        consented_at=NOW - timedelta(hours=1),
        ai_call_consented=True,
        recording_consented=True,
        source_url=contact.source_url,
        created_at=NOW,
    )


def test_authorization_requires_ai_and_recording_opt_in(
    official_vendor,
    job_spec,
):
    contact = extract_official_us_contacts(
        official_vendor,
        ExtractedWebPage(
            url=HttpUrl("https://official.example/contact"),
            content="(617) 555-0101",
            truncated=False,
        ),
    )[0]
    payload = _authorization(job_spec, official_vendor, contact).model_dump(
        mode="python"
    )

    with pytest.raises(ValidationError):
        VendorCallAuthorizationV1.model_validate(
            {**payload, "ai_call_consented": False}
        )
    with pytest.raises(ValidationError):
        VendorCallAuthorizationV1.model_validate(
            {**payload, "recording_consented": False}
        )


def test_authorization_window_age_and_hash_are_fail_closed(
    official_vendor,
    job_spec,
):
    contact = extract_official_us_contacts(
        official_vendor,
        ExtractedWebPage(
            url=HttpUrl("https://official.example/contact"),
            content="(617) 555-0101",
            truncated=False,
        ),
    )[0]
    authorization = _authorization(job_spec, official_vendor, contact)

    assert permitted_call_time(NOW, "America/New_York") is True
    assert permitted_call_time(
        datetime(2026, 7, 21, 1, 0, tzinfo=UTC),
        "America/New_York",
    ) is False
    assert authorization_is_current(authorization, NOW, max_age_days=30)
    assert not authorization_is_current(
        authorization,
        NOW + timedelta(days=31),
        max_age_days=30,
    )
    assert destination_hash(HASH_SECRET, contact.normalized_number) == (
        authorization.number_hash
    )
    with pytest.raises(DomainConflict, match="secret"):
        destination_hash("weak", contact.normalized_number)


def test_authorization_and_suppression_repository_round_trip(
    official_vendor,
    job_spec,
):
    repository = InMemoryRepository()
    locked_spec = job_spec.model_copy(
        update={
            "confirmed": True,
            "confirmed_at": NOW,
            "locked_version": job_spec.version,
        },
        deep=True,
    )
    repository.create(
        JobRecord(
            job_spec=locked_spec,
            state=JobState.CONFIRMED,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    contact = extract_official_us_contacts(
        official_vendor,
        ExtractedWebPage(
            url=HttpUrl("https://official.example/contact"),
            content="(617) 555-0101",
            truncated=False,
        ),
    )[0]
    authorization = _authorization(locked_spec, official_vendor, contact)

    saved = repository.save_vendor_call_authorization(authorization)
    replay = repository.save_vendor_call_authorization(authorization)
    suppression = VendorSuppressionV1(
        number_hash=authorization.number_hash,
        reason=SuppressionReason.RECIPIENT_OPT_OUT,
        created_at=NOW,
    )
    repository.save_vendor_suppression(suppression)

    assert saved == replay
    assert repository.list_vendor_call_authorizations(
        locked_spec.job_id,
        locked_spec.version,
    ) == [authorization]
    assert repository.get_vendor_suppression(authorization.number_hash) == suppression
    assert "normalized_number" not in saved.model_dump(mode="json")
