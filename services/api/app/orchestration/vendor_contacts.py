"""Deterministic public-business contact extraction from an official HTTPS host."""

from __future__ import annotations

import hashlib
import hmac
import html
import re
from datetime import datetime, time, timedelta
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import HttpUrl, TypeAdapter, ValidationError

from services.api.app.contracts import (
    ProvenanceType,
    Vendor,
    VendorCallAuthorizationV1,
    VendorContactCandidateV1,
)
from services.api.app.core.errors import DomainConflict
from services.api.app.integrations.tavily.base import ExtractedWebPage

_HTTP_URL = TypeAdapter(HttpUrl)
_TEL_PHONE = re.compile(
    r"tel:\s*(?P<number>\+?[0-9][0-9().\s-]{8,22}(?:\s*(?:;ext=|x|ext\.?\s*)\d{1,8})?)",
    re.IGNORECASE,
)
_VISIBLE_US_PHONE = re.compile(
    r"(?<!\d)(?P<number>(?:\+?1[\s.-]*)?(?:\([2-9]\d{2}\)|[2-9]\d{2})[\s.-]*\d{3}[\s.-]*\d{4})(?!\d)",
)
_EXTENSION = re.compile(r"(?:;ext=|\bext\.?|\bx)\s*\d{1,8}\s*$", re.IGNORECASE)
_NORMALIZED_US_PHONE = re.compile(r"^\+1[2-9]\d{9}$")


def official_website_url(vendor: Vendor) -> HttpUrl:
    """Resolve the reviewed official URL from trusted discovery provenance."""

    for reference in vendor.provenance:
        if (
            reference.source_type is not ProvenanceType.TAVILY
            or reference.location is None
        ):
            continue
        try:
            url = _HTTP_URL.validate_python(reference.location)
        except ValidationError:
            continue
        if url.scheme == "https" and url.host:
            return url
    raise DomainConflict("Selected vendor has no trusted official HTTPS source")


def extract_official_us_contacts(
    vendor: Vendor,
    page: ExtractedWebPage,
) -> list[VendorContactCandidateV1]:
    """Extract at most five US contacts only from the vendor's official host."""

    official = official_website_url(vendor)
    if _host(official) != _host(page.url):
        raise DomainConflict("Vendor contact source must use the official website host")

    content = html.unescape(page.content)
    matches = [
        *(match.group("number") for match in _TEL_PHONE.finditer(content)),
        *(match.group("number") for match in _VISIBLE_US_PHONE.finditer(content)),
    ]
    contacts: list[VendorContactCandidateV1] = []
    seen: set[str] = set()
    for raw in matches:
        normalized = _normalize_us_phone(raw)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        display = _display_phone(normalized)
        excerpt = _source_excerpt(raw, display)
        source_url = str(page.url)
        contacts.append(
            VendorContactCandidateV1(
                contact_id=uuid5(
                    NAMESPACE_URL,
                    f"veramove-contact:{vendor.vendor_id}:{normalized}:{source_url}",
                ),
                vendor_id=vendor.vendor_id,
                normalized_number=normalized,
                display_number=display,
                source_url=page.url,
                source_excerpt=excerpt,
                source_excerpt_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
            )
        )
        if len(contacts) == 5:
            break
    return contacts


def destination_hash(secret: str, normalized_number: str) -> str:
    """Create a stable server-only HMAC identifier for suppression checks."""

    if len(secret.encode()) < 32:
        raise DomainConflict("Vendor contact hash secret is not configured safely")
    if _NORMALIZED_US_PHONE.fullmatch(normalized_number) is None:
        raise DomainConflict("Vendor destination is not a normalized US number")
    return hmac.new(
        secret.encode(),
        normalized_number.encode(),
        hashlib.sha256,
    ).hexdigest()


def permitted_call_time(now: datetime, timezone_name: str) -> bool:
    """Permit outbound calls only from 08:00 inclusive to 21:00 local time."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise DomainConflict("Outbound call time must include a timezone")
    try:
        local = now.astimezone(ZoneInfo(timezone_name))
    except ZoneInfoNotFoundError as exc:
        raise DomainConflict("Recipient timezone is invalid") from exc
    return time(8, 0) <= local.time().replace(tzinfo=None) < time(21, 0)


def authorization_is_current(
    authorization: VendorCallAuthorizationV1,
    now: datetime,
    *,
    max_age_days: int,
) -> bool:
    """Check a bounded affirmative consent lifetime without mutating evidence."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise DomainConflict("Authorization check time must include a timezone")
    if not 1 <= max_age_days <= 365:
        raise DomainConflict("Consent maximum age must be between 1 and 365 days")
    age = now - authorization.consented_at
    return timedelta(0) <= age <= timedelta(days=max_age_days)


def _host(url: HttpUrl) -> str:
    host = (urlsplit(str(url)).hostname or "").lower().rstrip(".")
    return host.removeprefix("www.")


def _normalize_us_phone(value: str) -> str | None:
    base = _EXTENSION.sub("", value).strip()
    digits = "".join(character for character in base if character.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in {"0", "1"}:
        return None
    return f"+1{digits}"


def _display_phone(normalized: str) -> str:
    digits = normalized[2:]
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def _source_excerpt(raw: str, display: str) -> str:
    cleaned = " ".join(_EXTENSION.sub("", raw).split()).strip(" .,:;-")
    return (cleaned or display)[:160]


__all__ = [
    "authorization_is_current",
    "destination_hash",
    "extract_official_us_contacts",
    "official_website_url",
    "permitted_call_time",
]
