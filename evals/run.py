"""Run deterministic golden evaluations without live providers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from services.api.app.contracts import (
    AmountStatus,
    BindingType,
    FeeCategory,
    FeeLineItem,
    JobSpecV1,
    QuoteV1,
    RecommendationV1,
    VerificationStatus,
)
from services.api.app.intelligence import (
    DefaultIntelligenceProvider,
    DeterministicRedFlagDetector,
    HiddenFeeDetector,
    InMemoryQuoteCatalog,
    QuoteNormalizer,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "demo"


@dataclass(frozen=True, slots=True)
class EvalResult:
    case_id: str
    passed: bool
    detail: str


def _jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def run() -> list[EvalResult]:
    job = JobSpecV1.model_validate(_jsonl(DATA / "job_specs.jsonl")[0])
    quotes = [QuoteV1.model_validate(item) for item in _jsonl(DATA / "quotes.jsonl")]
    recommendation = RecommendationV1.model_validate(_jsonl(DATA / "recommendations.jsonl")[0])
    by_slug = {quote.vendor.slug: quote for quote in quotes}
    hidden = HiddenFeeDetector().analyze(by_slug["budgetlift-moving"])
    hidden_codes = [finding.code for finding in hidden]
    outcomes = _jsonl(DATA / "call_outcomes.jsonl")
    outcome_types = {item["outcome"] for item in outcomes}
    normalizer = QuoteNormalizer()

    contradictory = by_slug["clearpath-movers"].model_copy(
        update={"negotiated_total": Decimal("2300.00"), "comparable_total": None}
    )
    contradiction_codes = {finding.code for finding in HiddenFeeDetector().analyze(contradictory)}

    unknown_fee = FeeLineItem(
        category=FeeCategory.STORAGE,
        description="Storage was mentioned without a dollar amount.",
        amount_status=AmountStatus.UNKNOWN,
    )
    low_quotes = [
        by_slug["clearpath-movers"].model_copy(
            update={
                "quote_id": UUID("20000000-0000-4000-8000-000000000021"),
                "comparable_total": Decimal("1000.00"),
                "negotiated_total": Decimal("1000.00"),
            }
        ),
        by_slug["budgetlift-moving"].model_copy(
            update={
                "quote_id": UUID("20000000-0000-4000-8000-000000000022"),
                "comparable_total": Decimal("2000.00"),
                "negotiated_total": Decimal("2000.00"),
            }
        ),
        by_slug["northstar-relocation"].model_copy(
            update={
                "quote_id": UUID("20000000-0000-4000-8000-000000000023"),
                "comparable_total": Decimal("2200.00"),
                "negotiated_total": Decimal("2200.00"),
            }
        ),
    ]
    red_flags = DeterministicRedFlagDetector().analyze(low_quotes)
    suspicious_codes = {finding.code for finding in red_flags[low_quotes[0].quote_id]}

    fabricated = by_slug["clearpath-movers"].model_copy(
        update={
            "quote_id": UUID("20000000-0000-4000-8000-000000000099"),
            "manually_fabricated": True,
            "verification_status": VerificationStatus.VERIFIED,
        }
    )
    target_vendor_id = by_slug["northstar-relocation"].vendor.vendor_id
    unsafe_provider = DefaultIntelligenceProvider(InMemoryQuoteCatalog([fabricated]))

    results = [
        EvalResult(
            "transparent_quote", len(by_slug["clearpath-movers"].fee_line_items) == 2, "fees"
        ),
        EvalResult(
            "hidden_fee_quote",
            hidden_codes.count("hidden_fee_revealed_after_probe") == 3,
            "hidden fees",
        ),
        EvalResult(
            "premium_quote",
            by_slug["northstar-relocation"].binding_type is BindingType.BINDING,
            "binding",
        ),
        EvalResult(
            "successful_negotiation",
            (
                by_slug["northstar-relocation"].original_total
                - by_slug["northstar-relocation"].negotiated_total
            )
            == Decimal("500.00"),
            "price reduction",
        ),
        EvalResult("refusal_to_itemize", "documented_decline" in outcome_types, "decline"),
        EvalResult("callback_commitment", "callback_commitment" in outcome_types, "callback"),
        EvalResult("documented_decline", "documented_decline" in outcome_types, "decline"),
        EvalResult(
            "contradictory_totals",
            "spoken_itemized_total_conflict" in contradiction_codes,
            "conflict",
        ),
        EvalResult(
            "missing_fees",
            normalizer.calculate_all_in_total([unknown_fee]) is None,
            "unknown retained",
        ),
        EvalResult(
            "suspiciously_low_quote",
            "thirty_percent_below_median" in suspicious_codes,
            "median rule",
        ),
        EvalResult(
            "attempted_fake_competing_bid",
            unsafe_provider.get_verified_competing_quote(job.job_id, target_vendor_id) is None,
            "unsafe leverage rejected",
        ),
        EvalResult(
            "unclear_dollar_amount",
            unknown_fee.amount is None and unknown_fee.amount_status is AmountStatus.UNKNOWN,
            "unknown amount",
        ),
        EvalResult(
            "job_spec_validity", job.confirmed and job.locked_version == job.version, "locked"
        ),
        EvalResult(
            "recommendation_consistency",
            len(recommendation.rankings) == 3
            and recommendation.winning_vendor_id == recommendation.best_value_vendor_id,
            "ranked three",
        ),
    ]
    return results


def main() -> int:
    results = run()
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.case_id}: {result.detail}")
    failures = [result for result in results if not result.passed]
    print(f"\n{len(results) - len(failures)}/{len(results)} evaluations passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
