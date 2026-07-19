"""Vendor-roster boundaries for mock discovery and supervised role-play calls."""

from __future__ import annotations

from typing import Protocol

from services.api.app.contracts import DataClassification, JobSpecV1, Vendor
from services.api.app.core.errors import ProviderConfigurationError
from services.api.app.integrations.tavily.base import VendorDiscoveryGateway
from services.api.app.orchestration.fixtures import DemoFixtures


class VendorRoster(Protocol):
    """Choose exactly three vendor identities for the initial call workflow."""

    def initial_vendors(self, job_spec: JobSpecV1) -> list[Vendor]: ...


class DiscoveryVendorRoster:
    """Preserve discovery-driven behavior for the credential-free mock workflow."""

    def __init__(self, discovery: VendorDiscoveryGateway) -> None:
        self._discovery = discovery

    def initial_vendors(self, job_spec: JobSpecV1) -> list[Vendor]:
        candidates = self._discovery.discover(
            job_spec.origin.address_summary,
            job_spec.destination.address_summary,
        )
        distinct: dict[object, Vendor] = {}
        for vendor in candidates:
            distinct.setdefault(vendor.vendor_id, vendor)
        return [vendor.model_copy(deep=True) for vendor in list(distinct.values())[:3]]


class FixtureRolePlayVendorRoster:
    """Return three fictional vendors that never borrow Tavily company identities."""

    def __init__(self, fixtures: DemoFixtures) -> None:
        vendors = fixtures.load_live_role_play_vendors()
        vendor_ids = {vendor.vendor_id for vendor in vendors}
        if len(vendors) != 3 or len(vendor_ids) != 3:
            raise ProviderConfigurationError(
                "Live role-play roster requires exactly three distinct vendors"
            )
        if any(
            vendor.data_classification is not DataClassification.ROLE_PLAY
            for vendor in vendors
        ):
            raise ProviderConfigurationError(
                "Live role-play roster vendors must be classified as role_play"
            )
        self._vendors = tuple(vendor.model_copy(deep=True) for vendor in vendors)

    def initial_vendors(self, job_spec: JobSpecV1) -> list[Vendor]:
        del job_spec
        return [vendor.model_copy(deep=True) for vendor in self._vendors]
