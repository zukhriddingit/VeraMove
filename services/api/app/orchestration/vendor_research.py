"""Job-scoped real vendor discovery and source-backed website research."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import HttpUrl, TypeAdapter, ValidationError

from services.api.app.contracts import (
    DataClassification,
    FeeCategory,
    JobRecord,
    JobVendorResearchV1,
    ProvenanceType,
    Vendor,
    VendorResearchDossierV1,
    VendorSearchQuery,
)
from services.api.app.core.errors import (
    DomainConflict,
    ProviderRequestError,
    ResourceNotFound,
)
from services.api.app.integrations.openai.base import WebsiteClaimExtractor
from services.api.app.integrations.tavily.base import (
    TavilyExtractClient,
    VendorDiscoveryGateway,
)
from services.api.app.orchestration.vendor_contacts import (
    extract_official_us_contacts,
)
from services.api.app.orchestration.vendor_research_questions import (
    build_verification_plan,
)
from services.api.app.repositories.base import (
    JobRepository,
    VendorResearchRepository,
)

_CITY_STATE = re.compile(r"^(?P<city>[A-Za-z][A-Za-z .'-]{0,98}), (?P<state>[A-Z]{2})$")
_HTTP_URL = TypeAdapter(HttpUrl)


def utc_now() -> datetime:
    return datetime.now(UTC)


class VendorResearchService:
    """Coordinate bounded vendor research without creating call evidence."""

    def __init__(
        self,
        *,
        jobs: JobRepository,
        research: VendorResearchRepository,
        discovery: VendorDiscoveryGateway,
        extract: TavilyExtractClient,
        claim_extractor: WebsiteClaimExtractor | None,
        required_fee_categories: set[FeeCategory],
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._jobs = jobs
        self._research = research
        self._discovery = discovery
        self._extract = extract
        self._claim_extractor = claim_extractor
        self._required_fee_categories = set(required_fee_categories)
        self._clock = clock

    def get(self, job_id: UUID) -> JobVendorResearchV1:
        job = self._get_job(job_id)
        research = self._research.get_vendor_research(job_id, job.job_spec.version)
        if research is None:
            raise ResourceNotFound(f"Vendor research for job {job_id} was not found")
        return research

    def discover(
        self,
        job_id: UUID,
        *,
        refresh: bool = False,
    ) -> JobVendorResearchV1:
        job = self._require_confirmed_job(job_id)
        existing = self._research.get_vendor_research(job_id, job.job_spec.version)
        if existing is not None and not refresh:
            return existing
        if existing is not None and existing.selected_vendor_ids:
            raise DomainConflict(
                "Please clear the shortlist before refreshing vendor discovery"
            )

        query = self._build_query(job)
        vendors = self._normalize_candidates(
            self._discovery.source_call_list(query),
            source=self._discovery.source,
        )
        if not vendors:
            raise ProviderRequestError("Vendor discovery returned no safe candidates")

        now = self._clock()
        created_at = existing.created_at if existing is not None else now
        result = JobVendorResearchV1(
            job_id=job_id,
            job_spec_version=job.job_spec.version,
            query=query,
            candidates=vendors,
            source=self._discovery.source,
            created_at=created_at,
            updated_at=now,
        )
        return self._research.save_vendor_research(result)

    def set_shortlist(
        self,
        job_id: UUID,
        vendor_ids: list[UUID],
    ) -> JobVendorResearchV1:
        self._require_confirmed_job(job_id)
        current = self.get(job_id)
        if len(vendor_ids) != 3 or len(set(vendor_ids)) != 3:
            raise DomainConflict("The shortlist must contain exactly three vendors")

        candidates = {vendor.vendor_id: vendor for vendor in current.candidates}
        if not set(vendor_ids).issubset(candidates):
            raise DomainConflict(
                "The shortlist must use exactly three persisted discovery candidates"
            )
        dossiers = [
            VendorResearchDossierV1(vendor=candidates[vendor_id], status="pending")
            for vendor_id in vendor_ids
        ]
        updated = current.model_copy(
            update={
                "selected_vendor_ids": list(vendor_ids),
                "dossiers": dossiers,
                "updated_at": self._clock(),
            },
            deep=True,
        )
        return self._research.save_vendor_research(updated)

    def clear_shortlist(self, job_id: UUID) -> JobVendorResearchV1:
        self._require_confirmed_job(job_id)
        current = self.get(job_id)
        updated = current.model_copy(
            update={
                "selected_vendor_ids": [],
                "dossiers": [],
                "updated_at": self._clock(),
            },
            deep=True,
        )
        return self._research.save_vendor_research(updated)

    def analyze(
        self,
        job_id: UUID,
        *,
        refresh: bool = False,
    ) -> JobVendorResearchV1:
        job = self._require_confirmed_job(job_id)
        current = self.get(job_id)
        if len(current.selected_vendor_ids) != 3 or len(current.dossiers) != 3:
            raise DomainConflict("Save exactly three vendors before researching websites")

        target_ids = {
            dossier.vendor.vendor_id
            for dossier in current.dossiers
            if refresh or dossier.status != "complete"
        }
        if not target_ids:
            return current

        target_dossiers = [
            dossier
            for dossier in current.dossiers
            if dossier.vendor.vendor_id in target_ids
        ]
        url_by_vendor = {
            dossier.vendor.vendor_id: self._research_url(
                dossier.vendor,
                current.source,
            )
            for dossier in target_dossiers
        }
        urls = tuple(url_by_vendor[dossier.vendor.vendor_id] for dossier in target_dossiers)
        try:
            pages = self._extract.extract(urls)
        except ProviderRequestError:
            pages = {str(url): None for url in urls}

        dossier_by_id = {
            dossier.vendor.vendor_id: dossier.model_copy(deep=True)
            for dossier in current.dossiers
        }
        for dossier in target_dossiers:
            vendor_id = dossier.vendor.vendor_id
            url = url_by_vendor[vendor_id]
            page = pages.get(str(url))
            researched_at = self._clock()
            if page is None:
                replacement = self._failed_dossier(
                    dossier.vendor,
                    researched_at,
                    "Vendor website content was unavailable. Retry research later.",
                )
            else:
                contacts = (
                    extract_official_us_contacts(dossier.vendor, page)
                    if current.source == "tavily"
                    else []
                )
                if self._claim_extractor is None:
                    replacement = self._failed_or_partial_dossier(
                        dossier.vendor,
                        researched_at,
                        "Website claim analysis is not configured. Retry research later.",
                        contacts,
                    )
                    dossier_by_id[vendor_id] = replacement
                    current = current.model_copy(
                        update={
                            "dossiers": [
                                dossier_by_id[vendor_id]
                                for vendor_id in current.selected_vendor_ids
                            ],
                            "updated_at": researched_at,
                        },
                        deep=True,
                    )
                    current = self._research.save_vendor_research(current)
                    continue
                try:
                    claims = self._claim_extractor.extract(
                        dossier.vendor,
                        page,
                        researched_at,
                    )
                except ProviderRequestError:
                    replacement = self._failed_or_partial_dossier(
                        dossier.vendor,
                        researched_at,
                        "Website claim analysis was unavailable. Retry research later.",
                        contacts,
                    )
                else:
                    questions, missing = build_verification_plan(
                        job.job_spec,
                        claims,
                        self._required_fee_categories,
                    )
                    if page.truncated and not claims and not contacts:
                        replacement = self._failed_dossier(
                            dossier.vendor,
                            researched_at,
                            "Website content was truncated before any supported claim was found.",
                        )
                    else:
                        replacement = VendorResearchDossierV1(
                            vendor=dossier.vendor,
                            status="partial" if page.truncated else "complete",
                            claims=claims,
                            contact_candidates=contacts,
                            missing_fee_categories=missing,
                            verification_questions=questions,
                            researched_at=researched_at,
                            safe_failure_reason=(
                                "Website content was truncated; verify all terms during the call."
                                if page.truncated
                                else None
                            ),
                        )

            dossier_by_id[vendor_id] = replacement
            current = current.model_copy(
                update={
                    "dossiers": [
                        dossier_by_id[vendor_id]
                        for vendor_id in current.selected_vendor_ids
                    ],
                    "updated_at": researched_at,
                },
                deep=True,
            )
            current = self._research.save_vendor_research(current)
        return current

    def _get_job(self, job_id: UUID) -> JobRecord:
        job = self._jobs.get(job_id)
        if job is None:
            raise ResourceNotFound(f"Job {job_id} was not found")
        return job

    def _require_confirmed_job(self, job_id: UUID) -> JobRecord:
        job = self._get_job(job_id)
        if not job.job_spec.confirmed or job.job_spec.locked_version != job.job_spec.version:
            raise DomainConflict("Vendor research requires a confirmed, locked JobSpec")
        return job

    @staticmethod
    def _city_state(value: str | None) -> tuple[str, str]:
        match = _CITY_STATE.fullmatch(value or "")
        if match is None:
            raise DomainConflict(
                "Vendor discovery requires origin and destination as city and state only"
            )
        return match.group("city"), match.group("state")

    def _build_query(self, job: JobRecord) -> VendorSearchQuery:
        origin_city, origin_state = self._city_state(
            job.job_spec.origin.address_summary
        )
        destination_city, destination_state = self._city_state(
            job.job_spec.destination.address_summary
        )
        service_type = (
            f"moving from {origin_city}, {origin_state} "
            f"to {destination_city}, {destination_state}"
        )
        if len(service_type) > 100:
            raise DomainConflict("Vendor discovery city and state values are too long")
        return VendorSearchQuery(
            city=origin_city,
            state=origin_state,
            service_type=service_type,
            radius_miles=25,
        )

    @staticmethod
    def _normalize_candidates(
        candidates: Iterable[Vendor],
        *,
        source: str,
    ) -> list[Vendor]:
        normalized: list[Vendor] = []
        seen_ids: set[UUID] = set()
        for candidate in candidates:
            if candidate.vendor_id in seen_ids:
                continue
            if source == "tavily":
                try:
                    VendorResearchService._tavily_url(candidate)
                except DomainConflict:
                    continue
                candidate = candidate.model_copy(
                    update={"data_classification": DataClassification.REAL_REDACTED},
                    deep=True,
                )
            normalized.append(candidate)
            seen_ids.add(candidate.vendor_id)
            if len(normalized) == 10:
                break
        return normalized

    @staticmethod
    def _tavily_url(vendor: Vendor) -> HttpUrl:
        for reference in vendor.provenance:
            if (
                reference.source_type is ProvenanceType.TAVILY
                and reference.location is not None
            ):
                try:
                    url = _HTTP_URL.validate_python(reference.location)
                except ValidationError:
                    continue
                if url.scheme == "https":
                    return url
        raise DomainConflict("Selected vendor has no trusted HTTPS Tavily source")

    @staticmethod
    def _research_url(vendor: Vendor, source: str) -> HttpUrl:
        if source == "tavily":
            return VendorResearchService._tavily_url(vendor)
        return _HTTP_URL.validate_python(
            f"https://research.example.com/{vendor.slug}"
        )

    @staticmethod
    def _failed_dossier(
        vendor: Vendor,
        researched_at: datetime,
        reason: str,
    ) -> VendorResearchDossierV1:
        return VendorResearchDossierV1(
            vendor=vendor,
            status="failed",
            researched_at=researched_at,
            safe_failure_reason=reason,
        )

    @staticmethod
    def _failed_or_partial_dossier(
        vendor: Vendor,
        researched_at: datetime,
        reason: str,
        contacts: list,
    ) -> VendorResearchDossierV1:
        if not contacts:
            return VendorResearchService._failed_dossier(
                vendor,
                researched_at,
                reason,
            )
        return VendorResearchDossierV1(
            vendor=vendor,
            status="partial",
            contact_candidates=contacts,
            researched_at=researched_at,
            safe_failure_reason=reason,
        )


__all__ = ["VendorResearchService"]
