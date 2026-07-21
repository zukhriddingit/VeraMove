"""Strict contracts for reviewed vendor contact and call authorization workflows."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field, HttpUrl, model_validator

from services.api.app.contracts.models import ContractModel

_DISPLAY_PHONE = re.compile(r"^\([2-9]\d{2}\) \d{3}-\d{4}$")
_NORMALIZED_PHONE = re.compile(r"^\+1[2-9]\d{9}$")


class CallContext(StrEnum):
    """Separate supervised role-play from consented official-business calls."""

    SUPERVISED_ROLE_PLAY = "supervised_role_play"
    OFFICIAL_BUSINESS = "official_business"


class VendorContactCandidateV1(ContractModel):
    """One official-site public business contact with tamper-evident provenance."""

    contact_id: UUID = Field(default_factory=uuid4)
    vendor_id: UUID
    normalized_number: str = Field(
        pattern=r"^\+1[2-9]\d{9}$",
        exclude=True,
        repr=False,
    )
    display_number: str = Field(pattern=r"^\([2-9]\d{2}\) \d{3}-\d{4}$")
    source_url: HttpUrl
    source_excerpt: str = Field(min_length=1, max_length=160)
    source_excerpt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="before")
    @classmethod
    def restore_private_normalized_number(cls, value: Any) -> Any:
        """Reconstruct the private canonical form from the persisted display value."""

        if not isinstance(value, dict) or value.get("normalized_number") is not None:
            return value
        display = value.get("display_number")
        if not isinstance(display, str) or _DISPLAY_PHONE.fullmatch(display) is None:
            return value
        digits = "".join(character for character in display if character.isdigit())
        return {**value, "normalized_number": f"+1{digits}"}

    @model_validator(mode="after")
    def display_matches_normalized(self) -> VendorContactCandidateV1:
        digits = "".join(
            character for character in self.display_number if character.isdigit()
        )
        if (
            _DISPLAY_PHONE.fullmatch(self.display_number) is None
            or _NORMALIZED_PHONE.fullmatch(self.normalized_number) is None
            or self.normalized_number != f"+1{digits}"
        ):
            raise ValueError("display_number must match normalized_number")
        if self.source_url.scheme != "https":
            raise ValueError("vendor contact sources must use HTTPS")
        return self


__all__ = ["CallContext", "VendorContactCandidateV1"]
