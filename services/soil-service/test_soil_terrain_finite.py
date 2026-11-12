import pytest
from pydantic import ValidationError

from shared.contracts.soil import TerrainRequest


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_terrain_requires_finite_cell_size_and_elevations(value):
    base = dict(
        tenant_id="t",
        field_id="f",
        geometry_hash="g",
        dem_version="dem",
        cell_size_m=30,
        elevation_m=[[0, 1, 2], [1, 2, 3], [2, 3, 4]],
    )
    with pytest.raises(ValidationError):
        TerrainRequest(**{**base, "cell_size_m": value})
    with pytest.raises(ValidationError):
        TerrainRequest(**{**base, "elevation_m": [[0, 1, 2], [1, value, 3], [2, 3, 4]]})
