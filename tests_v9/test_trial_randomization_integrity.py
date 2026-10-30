"""Assignment integrity regressions without importing the API application."""

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def randomization():
    path = (
        Path(__file__).resolve().parents[1] / "services/sahool-platform/api/trial_randomization.py"
    )
    spec = importlib.util.spec_from_file_location("trial_randomization_integrity_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _assignments(randomization):
    return randomization.generate_block_assignments(
        randomization.RandomizationConfig(
            trial_id="trial-a", num_blocks=4, seed_source="user_provided", seed_value=0
        )
    )


def test_generated_assignments_are_complementary_and_reproducible(randomization):
    first = _assignments(randomization)
    assert first == _assignments(randomization)
    assert all(randomization.verify_assignment(block) for block in first.blocks)
    assert all(
        {block.treatment_position, block.control_position} == {"north", "south"}
        for block in first.blocks
    )


def test_control_cannot_be_moved_onto_treatment_position(randomization):
    block = _assignments(randomization).blocks[0]
    assert not randomization.verify_assignment(
        replace(block, control_position=block.treatment_position)
    )


@pytest.mark.parametrize("field", ["treatment_position", "control_position"])
@pytest.mark.parametrize("position", ["", "west", "NORTH", None, []])
def test_invalid_position_is_rejected(randomization, field, position):
    # Exercise both valid treatment orientations: every non-north string used
    # to be interpreted as south when the checksum was recomputed.
    for block in _assignments(randomization).blocks:
        assert not randomization.verify_assignment(replace(block, **{field: position}))


def test_swapping_both_positions_still_fails_the_original_checksum(randomization):
    block = _assignments(randomization).blocks[0]
    changed = replace(
        block,
        treatment_position=block.control_position,
        control_position=block.treatment_position,
    )
    assert not randomization.verify_assignment(changed)


def test_existing_assignment_checksum_remains_compatible(randomization):
    # Pre-fix trial-a/seed=42 fixture: checksum format must not change.
    block = randomization.BlockAssignment(
        block_number=1,
        treatment_position="north",
        control_position="south",
        block_seed=1782204709,
        seed_hash="f60ca46815ad57b1994ae3f1d29174cfbb4ea1b9308925cbe6412d3c47dd8df8",
    )
    assert randomization.verify_assignment(block)
