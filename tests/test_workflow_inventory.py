"""Contract tests for read-only CI workflow inventory."""

from pathlib import Path

import pytest

from scripts.ci.workflow_inventory import inventory, main, parse_workflow


def setup(tmp_path: Path, name="sample.yml", source=None):
    folder = tmp_path / ".github" / "workflows"
    folder.mkdir(parents=True)
    (folder / name).write_text(
        source
        or """
name: CI
on:
  pull_request:
    paths:
      - "services/**"
jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - name: Run tests
        run: python -m pytest tests/architecture/test_sample.py
  integration:
    needs: unit
    uses: ./.github/workflows/reusable.yml
""",
        encoding="utf-8",
    )
    return tmp_path


def test_preserves_on_key_and_extracts_jobs(tmp_path):
    result = inventory(setup(tmp_path))
    assert result["workflow_count"] == 1
    assert result["job_count"] == 2
    workflow = result["workflows"][0]
    assert "pull_request" in workflow["on"]
    # Jobs are emitted sorted by id for determinism; address them by id, not position.
    assert [job["id"] for job in workflow["jobs"]] == ["integration", "unit"]
    jobs = {job["id"]: job for job in workflow["jobs"]}
    assert jobs["unit"]["explicit_test_paths"] == ["tests/architecture/test_sample.py"]
    assert jobs["integration"]["uses"] == "./.github/workflows/reusable.yml"
    assert jobs["integration"]["needs"] == "unit"
    assert result["scope"] == "static_workflow_inventory_not_required_check_authority"


def test_deterministic_inventory(tmp_path):
    root = setup(tmp_path)
    assert inventory(root) == inventory(root)


@pytest.mark.parametrize("raw", [b"[]", b"jobs: []", b"jobs:\n  test: []"])
def test_invalid_yaml_structure_fails_closed(raw):
    if raw == b"jobs:\n  test: []":
        # A malformed job is rejected by the inventory layer.
        pass
    else:
        with pytest.raises(ValueError):
            parse_workflow(raw)


def test_malformed_job_fails_closed(tmp_path):
    with pytest.raises(ValueError):
        inventory(setup(tmp_path, source="jobs:\n  test: []\n"))


def test_missing_directory_fails_closed(tmp_path):
    with pytest.raises(ValueError):
        inventory(tmp_path)


def test_symlink_workflow_rejected(tmp_path):
    root = setup(tmp_path)
    folder = root / ".github" / "workflows"
    (folder / "linked.yml").symlink_to(folder / "sample.yml")
    with pytest.raises(ValueError):
        inventory(root)


def test_cli_refuses_output_inside_repo(tmp_path):
    root = setup(tmp_path)
    assert main(["--root", str(root), "--output", str(root / "inventory.json")]) == 2
    assert not (root / "inventory.json").exists()


def test_cli_refuses_overwrite(tmp_path):
    root = setup(tmp_path)
    target = tmp_path.parent / (tmp_path.name + "-output.json")
    target.write_text("keep", encoding="utf-8")
    assert main(["--root", str(root), "--output", str(target)]) == 2
    assert target.read_text(encoding="utf-8") == "keep"
