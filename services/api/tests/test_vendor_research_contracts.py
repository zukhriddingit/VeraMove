"""Strict invariants for persisted vendor research contracts."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import HttpUrl, ValidationError

from services.api.app.contracts import (
    DataClassification,
    JobVendorResearchV1,
    VendorResearchDossierV1,
    VendorSearchQuery,
    VendorShortlistRequest,
    WebsiteClaimKind,
    WebsiteResearchClaimV1,
)

NOW = datetime(2026, 7, 21, 19, 0, tzinfo=UTC)


def _real_candidates(fixtures):
    return [
        vendor.model_copy(
            update={"data_classification": DataClassification.REAL_REDACTED},
            deep=True,
        )
        for vendor in fixtures.load_vendors()
    ]


def _research_payload(fixtures) -> dict:
    candidates = _real_candidates(fixtures)
    return {
        "job_id": uuid4(),
        "job_spec_version": "1.0",
        "query": VendorSearchQuery(city="Newton", state="MA"),
        "candidates": candidates,
        "selected_vendor_ids": [],
        "dossiers": [],
        "source": "tavily",
        "created_at": NOW,
        "updated_at": NOW,
    }


def test_shortlist_is_empty_or_exactly_three_distinct_candidates(fixtures):
    payload = _research_payload(fixtures)
    candidate_id = payload["candidates"][0].vendor_id

    with pytest.raises(ValidationError, match="exactly three distinct"):
        JobVendorResearchV1.model_validate(
            {**payload, "selected_vendor_ids": [candidate_id]}
        )

    with pytest.raises(ValidationError, match="exactly three distinct"):
        VendorShortlistRequest(vendor_ids=[candidate_id, candidate_id, candidate_id])


def test_shortlist_and_dossiers_must_come_from_persisted_candidates(fixtures):
    payload = _research_payload(fixtures)
    selected = [vendor.vendor_id for vendor in payload["candidates"]]
    outsider = uuid4()

    with pytest.raises(ValidationError, match="persisted candidates"):
        JobVendorResearchV1.model_validate(
            {**payload, "selected_vendor_ids": [*selected[:2], outsider]}
        )

    pending = [
        VendorResearchDossierV1(vendor=vendor, status="pending")
        for vendor in payload["candidates"]
    ]
    valid = JobVendorResearchV1.model_validate(
        {
            **payload,
            "selected_vendor_ids": selected,
            "dossiers": pending,
        }
    )
    assert {item.vendor.vendor_id for item in valid.dossiers} == set(selected)


def test_tavily_candidates_must_be_real_redacted(fixtures):
    payload = _research_payload(fixtures)
    payload["candidates"][0] = payload["candidates"][0].model_copy(
        update={"data_classification": DataClassification.ROLE_PLAY},
        deep=True,
    )

    with pytest.raises(ValidationError, match="real_redacted"):
        JobVendorResearchV1.model_validate(payload)


def test_claim_requires_https_exact_excerpt_and_unverified_classification():
    common = {
        "kind": WebsiteClaimKind.HOURLY_RATE,
        "summary": "Advertised from 149 USD per hour.",
        "advertised_amount": Decimal("149"),
        "currency": "USD",
        "unit": "hour",
        "qualifiers": ["starting at"],
        "source_url": HttpUrl("https://mover.example/pricing"),
        "source_excerpt": "Moving services starting at $149/hour.",
        "retrieved_at": NOW,
    }

    claim = WebsiteResearchClaimV1(**common)
    assert claim.classification == "unverified_website_claim"

    with pytest.raises(ValidationError):
        WebsiteResearchClaimV1(**common, classification="verified")
    with pytest.raises(ValidationError, match="HTTPS"):
        WebsiteResearchClaimV1(**{**common, "source_url": "http://mover.example"})
    with pytest.raises(ValidationError):
        WebsiteResearchClaimV1(
            **{**common, "source_excerpt": "x" * 501}
        )


@pytest.mark.parametrize(
    ("status", "claims", "researched_at", "failure", "message"),
    [
        ("pending", ["claim"], None, None, "pending dossiers"),
        ("complete", [], None, None, "terminal dossiers"),
        ("partial", [], NOW, "some content failed", "partial dossiers"),
        ("failed", ["claim"], NOW, "normalization failed", "failed dossiers"),
    ],
)
def test_dossier_status_is_internally_consistent(
    fixtures,
    status,
    claims,
    researched_at,
    failure,
    message,
):
    claim = WebsiteResearchClaimV1(
        kind=WebsiteClaimKind.SERVICE,
        summary="Packing services are advertised.",
        source_url="https://mover.example/services",
        source_excerpt="We offer packing services.",
        retrieved_at=NOW,
    )
    normalized_claims = [claim] if claims else []

    with pytest.raises(ValidationError, match=message):
        VendorResearchDossierV1(
            vendor=_real_candidates(fixtures)[0],
            status=status,
            claims=normalized_claims,
            researched_at=researched_at,
            safe_failure_reason=failure,
        )

