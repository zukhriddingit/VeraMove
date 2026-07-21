"""Deterministic public-business contact extraction from an official HTTPS host."""

from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from pydantic import HttpUrl, TypeAdapter, ValidationError

from services.api.app.contracts import (
    ProvenanceType,
    Vendor,
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


__all__ = ["extract_official_us_contacts", "official_website_url"]
