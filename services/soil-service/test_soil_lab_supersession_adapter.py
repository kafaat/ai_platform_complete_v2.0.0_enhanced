from datetime import UTC, datetime

import evidence_adapters

from shared.contracts.soil import SoilObservationSource


def test_lab_correction_maps_prior_observation_by_canonical_property():
    rows = evidence_adapters.observations_from_properties(
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="fld-1",
        source_type=SoilObservationSource.LABORATORY,
        source_id="sample-2",
        properties={"ec_dsm": 5.2, "ph": 7.7},
        observed_at=datetime.now(UTC),
        approved=True,
        supersedes_observation_ids={"ec": "sob-old-ec"},
        supersession_reason="corrected laboratory result",
    )
    by_property = {row.property: row for row in rows}
    assert by_property["ec"].supersedes_observation_id == "sob-old-ec"
    assert by_property["ec"].supersession_reason == "corrected laboratory result"
    assert by_property["ph"].supersedes_observation_id is None
