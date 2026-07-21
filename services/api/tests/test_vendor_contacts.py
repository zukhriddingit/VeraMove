"""Official-host business contact extraction and contract tests."""

from uuid import uuid4

import pytest
from pydantic import HttpUrl, ValidationError

from services.api.app.contracts import (
    DataClassification,
    ProvenanceReference,
    ProvenanceType,
    VendorContactCandidateV1,
    VendorResearchDossierV1,
)
from services.api.app.core.errors import DomainConflict
from services.api.app.integrations.tavily.base import ExtractedWebPage
from services.api.app.orchestration.vendor_contacts import (
    extract_official_us_contacts,
)


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
