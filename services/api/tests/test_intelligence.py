"""Deterministic intelligence, document, leverage, ranking, and dataset tests."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.run import run as run_evals
from services.api.app.contracts import (
    AmountStatus,
    AvailabilityStatus,
    BindingType,
    DocumentParseResult,
    FeeCategory,
    FeeLineItem,
    IntakeSource,
    JobSpecV1,
    QuoteV1,
    RecommendationV1,
    TranscriptQuoteFacts,
    VendorSearchQuery,
    VerificationStatus,
)
from services.api.app.integrations.openai.document import OpenAIDocumentParser
from services.api.app.integrations.tavily.cached import CachedTavilyVendorDiscovery
from services.api.app.integrations.tavily.mock import MockVendorDiscoveryGateway
from services.api.app.intelligence import (
    DefaultIntelligenceProvider,
    DeterministicRecommendationEngine,
    DeterministicRedFlagDetector,
    HiddenFeeDetector,
    InMemoryQuoteCatalog,
    QuoteNormalizer,
    QuoteVerifier,
)
from services.api.app.intelligence.document import merge_document_with_voice

ROOT = Path(__file__).resolve().parents[3]


class FakeDocumentClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


class FakeTavilyClient:
    def __init__(self):
        self.calls = 0

    def search(self, *, query: str, max_results: int):
        self.calls += 1
        assert "Example City" in query
        assert max_results == 10
        return [
            {
                "title": "Example Moving Cooperative",
                "url": "https://vendor.example.com/moving",
            }
        ]


def _document_result(job_spec: JobSpecV1) -> DocumentParseResult:
    payload = job_spec.model_dump(mode="python")
    payload.update(
        {
            "intake_source": IntakeSource.DOCUMENT,
            "move_date": None,
            "confirmed": False,
            "confirmed_at": None,
            "locked_version": None,
        }
    )
    document_spec = JobSpecV1.model_validate(payload)
    missing = document_spec.missing_required_fields()
    return DocumentParseResult(
        job_spec=document_spec,
        missing_fields=missing,
        warnings=["The move date was not present in the synthetic document."],
        fields_requiring_confirmation=["move_date"],
    )


def test_document_parser_preserves_missing_fields_and_uses_configurable_model(
    job_spec,
    monkeypatch,
):
    result = _document_result(job_spec)
    client = FakeDocumentClient(result.model_dump(mode="json"))
    monkeypatch.setenv("OPENAI_DOCUMENT_MODEL", "synthetic-structured-model")
    parsed = OpenAIDocumentParser(client).parse_document(
        b"%PDF-synthetic",
        "application/pdf",
        "synthetic-quote.pdf",
    )
    assert parsed.job_spec.intake_source is IntakeSource.DOCUMENT
    assert parsed.missing_fields == ["move_date"]
    assert client.calls[0]["model"] == "synthetic-structured-model"
    assert client.calls[0]["source_id"] == "synthetic-quote.pdf"
    assert client.calls[0]["response_schema"] is DocumentParseResult


def test_document_parser_revalidates_strict_structured_output(job_spec):
    payload = _document_result(job_spec).model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        OpenAIDocumentParser(FakeDocumentClient(payload)).parse_document(
            b"synthetic",
            "image/png",
            "synthetic-room.png",
        )


def test_document_merge_fills_only_missing_voice_facts(job_spec):
    voice_payload = job_spec.model_dump(mode="python")
    voice_payload.update({"intake_source": IntakeSource.VOICE, "move_date": None})
    voice = JobSpecV1.model_validate(voice_payload)
    document_result = _document_result(job_spec)
    document_payload = document_result.job_spec.model_dump(mode="python")
    document_payload["move_date"] = job_spec.move_date
    document = JobSpecV1.model_validate(document_payload)
    document_result = DocumentParseResult(
        job_spec=document,
        missing_fields=document.missing_required_fields(),
    )
    merged = merge_document_with_voice(voice, document_result)
    assert merged.job_spec.intake_source is IntakeSource.MERGED
    assert merged.job_spec.move_date == job_spec.move_date
    assert merged.job_spec.origin == voice.origin


def test_document_merge_rejects_confirmed_spec(job_spec):
    confirmed = job_spec.model_copy(
        update={
            "confirmed": True,
            "confirmed_at": "2026-07-18T15:00:00Z",
            "locked_version": "1.0",
        }
    )
    with pytest.raises(ValueError, match="confirmed"):
        merge_document_with_voice(confirmed, _document_result(job_spec))


def test_quote_normalizer_handles_flat_hourly_minimum_and_unknown():
    normalizer = QuoteNormalizer()
    hourly = FeeLineItem(
        category=FeeCategory.HOURLY_MINIMUM,
        description="Three-hour minimum at 200 USD per hour.",
        unit_rate="200.00",
        units="2.00",
        minimum_units="3.00",
    )
    flat = FeeLineItem(
        category=FeeCategory.TRAVEL,
        description="Flat travel charge.",
        amount="100.00",
    )
    unknown = FeeLineItem(
        category=FeeCategory.FUEL,
        description="Fuel amount was not stated.",
        amount_status=AmountStatus.UNKNOWN,
    )
    assert normalizer.calculate_all_in_total([hourly, flat]) == Decimal("700.00")
    assert normalizer.calculate_all_in_total([hourly, unknown]) is None


def test_verifier_preserves_provisional_data_and_corrects_contradiction(fixtures):
    provisional = fixtures.load_initial_quotes()[0].model_copy(
        update={"verification_status": VerificationStatus.PROVISIONAL}
    )
    supported = [
        item.model_copy(
            update={"amount": Decimal("1500.00")}
            if item.category is FeeCategory.BASE_SERVICE
            else {}
        )
        for item in provisional.fee_line_items
    ]
    total = QuoteNormalizer().calculate_all_in_total(supported)
    facts = TranscriptQuoteFacts(
        fee_line_items=supported,
        spoken_total=total,
        binding_type=BindingType.BINDING,
        availability="Synthetic date confirmed.",
        availability_status=AvailabilityStatus.AVAILABLE,
        addressed_fee_categories=[item.category for item in supported],
        evidence=provisional.transcript_evidence,
    )
    result = QuoteVerifier().verify(provisional, facts, {FeeCategory.FUEL})
    assert result.verified_quote.verification_status is VerificationStatus.VERIFIED
    assert result.verified_quote.provisional_data == provisional.provisional_data
    assert result.verified_quote.verified_data["provisional_preserved"] is True
    assert "base_service" in result.verified_quote.verified_data["contradicted_fee_categories"]
    assert any(item.code == "provisional_transcript_contradiction" for item in result.findings)
    assert any("fuel" in question for question in result.follow_up_questions)


def test_hidden_fee_and_total_conflict_are_machine_readable(fixtures):
    quote = fixtures.load_initial_quotes()[1].model_copy(
        update={"negotiated_total": Decimal("2400.00"), "comparable_total": None}
    )
    codes = {finding.code for finding in HiddenFeeDetector().analyze(quote)}
    assert "hidden_fee_revealed_after_probe" in codes
    assert "spoken_itemized_total_conflict" in codes
    assert "mandatory_fees_omitted_from_headline" in codes


def test_thirty_percent_below_median_red_flag(fixtures):
    quotes = fixtures.load_initial_quotes()
    totals = (Decimal("1000"), Decimal("2000"), Decimal("2200"))
    candidates = [
        quote.model_copy(update={"comparable_total": total, "negotiated_total": total})
        for quote, total in zip(quotes, totals, strict=True)
    ]
    flags = DeterministicRedFlagDetector().analyze(candidates)
    assert "thirty_percent_below_median" in {
        finding.code for finding in flags[candidates[0].quote_id]
    }


def test_verified_leverage_rejects_fake_or_same_vendor(fixtures, job_spec):
    quote = fixtures.load_initial_quotes()[0].model_copy(update={"manually_fabricated": True})
    provider = DefaultIntelligenceProvider(InMemoryQuoteCatalog([quote]))
    excluded = fixtures.load_initial_quotes()[2].vendor.vendor_id
    assert provider.get_verified_competing_quote(job_spec.job_id, excluded) is None

    safe = fixtures.load_initial_quotes()[0]
    provider = DefaultIntelligenceProvider(InMemoryQuoteCatalog([safe]))
    assert provider.get_verified_competing_quote(job_spec.job_id, safe.vendor.vendor_id) is None


def test_verified_leverage_returns_supported_other_vendor(fixtures, job_spec):
    quotes = fixtures.load_initial_quotes()
    provider = DefaultIntelligenceProvider(InMemoryQuoteCatalog(quotes))
    selected = provider.get_verified_competing_quote(
        job_spec.job_id,
        quotes[2].vendor.vendor_id,
    )
    assert selected is not None
    assert selected.quote.vendor.vendor_id != quotes[2].vendor.vendor_id
    assert selected.evidence_ids


def test_deterministic_recommendation_distinguishes_cheapest_and_best_value(
    fixtures,
    job_spec,
):
    recommendation = DeterministicRecommendationEngine().recommend(
        job_spec,
        fixtures.load_initial_quotes(),
    )
    assert recommendation.rankings[0].vendor.slug == "clearpath-movers"
    assert recommendation.cheapest_vendor_id == recommendation.winning_vendor_id
    assert recommendation.evidence_ids
    assert all(ranking.evidence_ids for ranking in recommendation.rankings)


def test_tavily_mock_returns_three_cached_synthetic_vendors(fixtures):
    gateway = MockVendorDiscoveryGateway(fixtures)
    query = VendorSearchQuery(city="Example City", state="MA", radius_miles=30)
    first = gateway.source_call_list(query)
    second = gateway.source_call_list(query)
    assert len(first) == 3
    assert gateway.cache_size == 1
    assert first == second
    assert all(vendor.data_classification.value == "synthetic" for vendor in first)


def test_tavily_results_are_normalized_cached_and_contact_redacted():
    client = FakeTavilyClient()
    gateway = CachedTavilyVendorDiscovery(client)
    query = VendorSearchQuery(city="Example City", state="MA")
    first = gateway.source_call_list(query)
    second = gateway.source_call_list(query)
    assert client.calls == 1
    assert first == second
    assert len(first) == 1
    assert "contact details intentionally not stored" in first[0].contact_label
    assert first[0].provenance[0].source_type.value == "tavily"


def test_public_dataset_contracts_and_labels_are_valid():
    data = ROOT / "data" / "demo"
    loaders = {
        "job_specs.jsonl": JobSpecV1,
        "quotes.jsonl": QuoteV1,
        "recommendations.jsonl": RecommendationV1,
    }
    for filename, model in loaders.items():
        payloads = [
            json.loads(line)
            for line in (data / filename).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert payloads
        assert all(model.model_validate(payload) for payload in payloads)
    public_records = "\n".join(
        path.read_text(encoding="utf-8")
        for path in data.iterdir()
        if path.suffix in {".json", ".jsonl", ".csv"}
    )
    assert "sk-" not in public_records
    assert not re.search(r"\b\d{3}[-.) ]+\d{3}[-. ]+\d{4}\b", public_records)


def test_golden_evaluations_all_pass():
    results = run_evals()
    assert len(results) >= 12
    assert all(result.passed for result in results)
