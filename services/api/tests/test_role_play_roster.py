"""Fictional live-call roster tests."""

from services.api.app.contracts import DataClassification, JobSpecV1, ProvenanceType
from services.api.app.orchestration.fixtures import DemoFixtures
from services.api.app.orchestration.role_play import FixtureRolePlayVendorRoster


class FailingDiscovery:
    source = "tavily"

    def discover(self, origin: str | None, destination: str | None):
        del origin, destination
        raise AssertionError("role-play calls must not invoke Tavily discovery")


def test_fixture_role_play_roster_is_exactly_three_fictional_vendors(
    job_spec: JobSpecV1,
) -> None:
    vendors = FixtureRolePlayVendorRoster(DemoFixtures()).initial_vendors(job_spec)

    assert len(vendors) == 3
    assert len({vendor.vendor_id for vendor in vendors}) == 3
    assert all(
        vendor.data_classification is DataClassification.ROLE_PLAY
        for vendor in vendors
    )
    assert all(
        source.source_type is ProvenanceType.DEMO_FIXTURE
        for vendor in vendors
        for source in vendor.provenance
    )
    assert all("role-play" in vendor.contact_label.casefold() for vendor in vendors)
    assert all("tavily" not in vendor.model_dump_json().casefold() for vendor in vendors)


def test_fixture_role_play_roster_returns_defensive_copies(
    job_spec: JobSpecV1,
) -> None:
    roster = FixtureRolePlayVendorRoster(DemoFixtures())
    first = roster.initial_vendors(job_spec)
    first[0].name = "Mutated in test"

    second = roster.initial_vendors(job_spec)

    assert second[0].name != "Mutated in test"


def test_call_workflow_uses_injected_roster_without_discovery(
    service,
    job_spec: JobSpecV1,
) -> None:
    roster = FixtureRolePlayVendorRoster(DemoFixtures())
    service._vendor_roster = roster
    service._discovery = FailingDiscovery()
    service.create_job(job_spec)
    service.confirm_job(job_spec.job_id)

    result = service.start_calls(job_spec.job_id)

    expected_ids = {
        vendor.vendor_id for vendor in roster.initial_vendors(job_spec)
    }
    assert {call.vendor.vendor_id for call in result.calls} == expected_ids
