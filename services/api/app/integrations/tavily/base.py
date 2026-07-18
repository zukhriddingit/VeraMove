"""Protocol for future search-backed vendor discovery."""

from typing import Protocol

from services.api.app.contracts import Vendor


class VendorDiscoveryGateway(Protocol):
    def discover(self, origin: str | None, destination: str | None) -> list[Vendor]: ...
