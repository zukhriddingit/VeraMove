"""Deterministic intelligence, document, leverage, ranking, and dataset tests."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

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
from services.api.app.intelligence.quotes import is_measurable_quote_improvement
from services.api.app.intelligence.ranking import (
    is_quote_eligible_for_leverage,
)
from services.api.app.orchestration.evidence import (
    EvidenceClaim,
    build_transcript_evidence,
)

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


def test_quote_normalizer_preserves_explicit_zero_totals(fixtures):
    quote = fixtures.load_initial_quotes()[0]
    zero_items = [
        item.model_copy(update={"amount": Decimal("0.00")}, deep=True)
        for item in quote.fee_line_items
    ]
    normalized = QuoteNormalizer().normalize(
        quote.model_copy(
            update={
                "fee_line_items": zero_items,
                "original_total": Decimal("0.00"),
                "negotiated_total": Decimal("0.00"),
                "comparable_total": Decimal("0.00"),
            },
            deep=True,
        )
    )

    assert normalized.original_total == Decimal("0.00")
    assert normalized.negotiated_total == Decimal("0.00")
    assert normalized.comparable_total == Decimal("0.00")


def _supported_quote_and_facts(fixtures):
    source = fixtures.load_initial_quotes()[0]
    fee = FeeLineItem(
        category=FeeCategory.STAIRS,
        description="Synthetic stairs fee.",
        amount=Decimal("250.00"),
        mandatory=True,
    )
    provisional = source.model_copy(
        update={
            "fee_line_items": [fee],
            "headline_total": Decimal("250.00"),
            "original_total": Decimal("250.00"),
            "negotiated_total": Decimal("250.00"),
            "comparable_total": Decimal("250.00"),
            "verification_status": VerificationStatus.PROVISIONAL,
            "transcript_evidence": [],
        },
        deep=True,
    )
    turns = (
        SimpleNamespace(
            message="The all-in total is $250.00.",
            time_in_call_secs=Decimal("2.125"),
        ),
        SimpleNamespace(
            message="The stairs fee is $250.00.",
            time_in_call_secs=Decimal("7.500"),
        ),
        SimpleNamespace(
            message="This is a binding quote.",
            time_in_call_secs=Decimal("12.000"),
        ),
        SimpleNamespace(
            message="We are available on the requested date.",
            time_in_call_secs=Decimal("17.000"),
        ),
    )
    evidence = build_transcript_evidence(
        call_id=source.transcript_evidence[0].call_id,
        recording_url=source.recording_url,
        transcript_turns=turns,
        claims=(
            EvidenceClaim("quote_total", ("all-in total",), Decimal("250.00")),
            EvidenceClaim("fee:stairs", ("stairs fee",), Decimal("250.00")),
            EvidenceClaim("binding_status", ("binding quote",)),
            EvidenceClaim("availability_status", ("available",)),
        ),
    )
    by_claim = {item.claim: item for item in evidence}
    facts = TranscriptQuoteFacts(
        fee_line_items=[
            fee.model_copy(update={"evidence_ids": [by_claim["fee:stairs"].evidence_id]})
        ],
        spoken_total=Decimal("250.00"),
        binding_type=BindingType.BINDING,
        availability="Available on the requested date.",
        availability_status=AvailabilityStatus.AVAILABLE,
        addressed_fee_categories=[FeeCategory.STAIRS],
        evidence=evidence,
    )
    return provisional, facts


def test_transcript_evidence_mapping_is_deterministic_bounded_and_claim_specific(
    fixtures,
):
    provisional, facts = _supported_quote_and_facts(fixtures)
    first = facts.evidence
    _, repeated = _supported_quote_and_facts(fixtures)

    assert first == repeated.evidence
    assert [item.claim for item in first] == [
        "quote_total",
        "fee:stairs",
        "binding_status",
        "availability_status",
    ]
    assert first[0].start_seconds == Decimal("2.13")
    assert first[0].end_seconds == Decimal("7.50")
    assert all(item.recording_url == provisional.recording_url for item in first)
    assert all(item.end_seconds - item.start_seconds <= Decimal("30") for item in first)

    unmatched = build_transcript_evidence(
        call_id=first[0].call_id,
        recording_url=provisional.recording_url,
        transcript_turns=(SimpleNamespace(message="No price was stated.", time_in_call_secs=0),),
        claims=(EvidenceClaim("quote_total", ("total",), Decimal("999.00")),),
    )
    assert unmatched == []


@pytest.mark.parametrize(
    ("missing_claim", "expected_missing"),
    [
        ("fee:stairs", "fee:stairs"),
        ("binding_status", "binding_status"),
        ("availability_status", "availability_status"),
    ],
)
def test_quote_verifier_requires_per_material_claim_evidence(
    fixtures,
    missing_claim,
    expected_missing,
):
    provisional, facts = _supported_quote_and_facts(fixtures)
    facts = facts.model_copy(
        update={"evidence": [item for item in facts.evidence if item.claim != missing_claim]},
        deep=True,
    )

    result = QuoteVerifier().verify(provisional, facts)

    assert result.verified_quote.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    assert expected_missing in result.verified_quote.verified_data["missing_evidence_claims"]


def test_quote_verifier_accepts_complete_per_claim_evidence(fixtures):
    provisional, facts = _supported_quote_and_facts(fixtures)

    result = QuoteVerifier().verify(provisional, facts)

    assert result.verified_quote.verification_status is VerificationStatus.VERIFIED
    assert result.verified_quote.comparable_total == Decimal("250.00")
    assert result.verified_quote.verified_data["missing_evidence_claims"] == []
    assert result.verified_quote.fee_line_items[0].evidence_ids


def test_quote_verifier_preserves_repeated_fee_categories(fixtures):
    provisional = fixtures.load_initial_quotes()[0].model_copy(
        update={"verification_status": VerificationStatus.PROVISIONAL},
        deep=True,
    )
    first = FeeLineItem(
        category=FeeCategory.MATERIALS,
        description="Synthetic carton materials.",
        amount=Decimal("40.00"),
    )
    second = FeeLineItem(
        category=FeeCategory.MATERIALS,
        description="Synthetic protective wrap.",
        amount=Decimal("60.00"),
    )
    evidence = build_transcript_evidence(
        call_id=provisional.transcript_evidence[0].call_id,
        recording_url=provisional.recording_url,
        transcript_turns=(
            SimpleNamespace(
                message="Carton materials are $40.00.",
                time_in_call_secs=1,
            ),
            SimpleNamespace(
                message="Protective wrap materials are $60.00.",
                time_in_call_secs=3,
            ),
            SimpleNamespace(message="The total is $100.00.", time_in_call_secs=5),
            SimpleNamespace(message="This quote is binding.", time_in_call_secs=7),
            SimpleNamespace(
                message="We are available on the synthetic date.",
                time_in_call_secs=9,
            ),
        ),
        claims=(
            EvidenceClaim("fee:materials:cartons", ("carton materials",), Decimal("40")),
            EvidenceClaim("fee:materials:wrap", ("wrap materials",), Decimal("60")),
            EvidenceClaim("quote_total", ("total",), Decimal("100")),
            EvidenceClaim("binding_status", ("binding",)),
            EvidenceClaim("availability_status", ("available",)),
        ),
    )
    by_claim = {item.claim: item.evidence_id for item in evidence}
    first = first.model_copy(update={"evidence_ids": [by_claim["fee:materials:cartons"]]})
    second = second.model_copy(update={"evidence_ids": [by_claim["fee:materials:wrap"]]})
    facts = TranscriptQuoteFacts(
        fee_line_items=[first, second],
        spoken_total=Decimal("100.00"),
        binding_type=BindingType.BINDING,
        availability="Synthetic date confirmed.",
        availability_status=AvailabilityStatus.AVAILABLE,
        addressed_fee_categories=[FeeCategory.MATERIALS],
        evidence=evidence,
    )

    result = QuoteVerifier().verify(
        provisional.model_copy(update={"fee_line_items": [first, second]}, deep=True),
        facts,
    )

    assert len(result.verified_quote.fee_line_items) == 2
    assert result.verified_quote.comparable_total == Decimal("100.00")


def test_verifier_preserves_provisional_data_and_corrects_contradiction(fixtures):
    provisional = fixtures.load_initial_quotes()[0].model_copy(
        update={"verification_status": VerificationStatus.PROVISIONAL}
    )
    unsupported_ids = [
        item.model_copy(
            update={"amount": Decimal("1500.00")}
            if item.category is FeeCategory.BASE_SERVICE
            else {}
        )
        for item in provisional.fee_line_items
    ]
    total = QuoteNormalizer().calculate_all_in_total(unsupported_ids)
    assert total is not None
    transcript_turns = []
    claims = []
    for index, item in enumerate(unsupported_ids):
        amount = QuoteNormalizer().calculate_line_item(item)
        assert amount is not None
        phrase = item.category.value.replace("_", " ")
        transcript_turns.append(
            SimpleNamespace(
                message=f"The {phrase} fee is ${amount}.",
                time_in_call_secs=index * 3,
            )
        )
        claims.append(EvidenceClaim(f"fee:{item.category.value}:{index}", (phrase,), amount))
    transcript_turns.extend(
        (
            SimpleNamespace(message=f"The total is ${total}.", time_in_call_secs=30),
            SimpleNamespace(message="This quote is binding.", time_in_call_secs=33),
            SimpleNamespace(
                message="We are available on the synthetic date.",
                time_in_call_secs=36,
            ),
        )
    )
    claims.extend(
        (
            EvidenceClaim("quote_total", ("total",), total),
            EvidenceClaim("binding_status", ("binding",)),
            EvidenceClaim("availability_status", ("available",)),
        )
    )
    evidence = build_transcript_evidence(
        call_id=provisional.transcript_evidence[0].call_id,
        recording_url=provisional.recording_url,
        transcript_turns=tuple(transcript_turns),
        claims=tuple(claims),
    )
    evidence_by_claim = {item.claim: item.evidence_id for item in evidence}
    supported = [
        item.model_copy(
            update={"evidence_ids": [evidence_by_claim[f"fee:{item.category.value}:{index}"]]}
        )
        for index, item in enumerate(unsupported_ids)
    ]
    total = QuoteNormalizer().calculate_all_in_total(supported)
    facts = TranscriptQuoteFacts(
        fee_line_items=supported,
        spoken_total=total,
        binding_type=BindingType.BINDING,
        availability="Synthetic date confirmed.",
        availability_status=AvailabilityStatus.AVAILABLE,
        addressed_fee_categories=[item.category for item in supported],
        evidence=evidence,
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


def test_ranking_filters_partial_fabricated_wrong_version_and_missing_recording(
    fixtures,
    job_spec,
):
    eligible, partial, other = fixtures.load_initial_quotes()
    fabricated = other.model_copy(
        update={"quote_id": uuid4(), "manually_fabricated": True},
        deep=True,
    )
    wrong_version = other.model_copy(
        update={"quote_id": uuid4(), "job_spec_version": "9.9"},
        deep=True,
    )
    missing_recording = other.model_copy(
        update={"quote_id": uuid4(), "recording_url": None},
        deep=True,
    )

    recommendation = DeterministicRecommendationEngine().recommend(
        job_spec,
        [eligible, partial, fabricated, wrong_version, missing_recording],
    )

    assert [item.quote_id for item in recommendation.rankings] == [eligible.quote_id]
    assert is_quote_eligible_for_leverage(
        eligible,
        job_id=job_spec.job_id,
        job_spec_version=job_spec.version,
    )
    for quote in (partial, fabricated, wrong_version, missing_recording):
        assert not is_quote_eligible_for_leverage(
            quote,
            job_id=job_spec.job_id,
            job_spec_version=job_spec.version,
        )


def test_ranking_rejects_a_set_with_no_eligible_quote(fixtures, job_spec):
    partial = fixtures.load_initial_quotes()[1]

    with pytest.raises(ValueError, match="eligible verified quote"):
        DeterministicRecommendationEngine().recommend(job_spec, [partial])


def test_measurable_improvement_is_limited_to_supported_changes(fixtures):
    initial = fixtures.load_initial_quotes()[0]
    unchanged = initial.model_copy(update={"concessions": ["Free snacks"]}, deep=True)
    lower_deposit = initial.model_copy(
        update={"deposit": initial.deposit - Decimal("10.00")},
        deep=True,
    )
    allowed_concession = initial.model_copy(
        update={"concessions": ["Fee waiver"]},
        deep=True,
    )

    assert not is_measurable_quote_improvement(initial, unchanged)
    assert is_measurable_quote_improvement(initial, lower_deposit)
    assert is_measurable_quote_improvement(
        initial,
        allowed_concession,
        allowed_new_concessions={"Fee waiver"},
    )


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
