import importlib.util
from datetime import UTC
from pathlib import Path
from uuid import UUID

# Path-independent load (matches test_observation_runtime): avoids depending on a
# sibling test importing main.py first to side-effect the service dir onto sys.path.
MODULE = Path(__file__).resolve().parents[1] / "observation_timeline.py"
spec = importlib.util.spec_from_file_location("observation_timeline_tested", MODULE)
assert spec and spec.loader
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def test_timeline_projects_latest_and_supersession():
    items = runtime.canonicalize_timeseries(
        field_id="fld_demo",
        tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
        season_id="sea_demo",
        indicator_code="ndvi",
        points=[
            {"datetime": "2026-07-01", "mean": 0.4},
            {"datetime": "2026-07-10", "mean": 0.6},
        ],
    )
    assert len(items) == 2
    assert items[0].publication_status.value == "superseded"
    assert items[1].publication_status.value == "published"
    assert items[1].supersedes == items[0].observation_ref
    assert items[1].acquired_at.tzinfo == UTC
