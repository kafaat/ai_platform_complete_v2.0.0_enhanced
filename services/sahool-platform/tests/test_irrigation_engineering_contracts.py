from __future__ import annotations

import pytest
from api.irrigation_engineering_contracts import (
    ControllerContract,
    EnergySystemContract,
    IrrigationMachineContract,
    IrrigationProjectContract,
    MachineType,
)
from pydantic import ValidationError


def test_project_defaults_are_yemen_safe_and_non_operational() -> None:
    project = IrrigationProjectContract(tenant_id="tenant", name="North farm")
    assert project.timezone == "Asia/Aden"
    assert project.lifecycle_state == "draft"


def test_machine_contract_is_vendor_neutral() -> None:
    machine = IrrigationMachineContract(
        tenant_id="tenant",
        project_id="project",
        name="Pivot 1",
        machine_type=MachineType.CENTER_PIVOT,
        design_flow_lps=50,
        capabilities={"read_position": True, "upload_vri": False},
    )
    assert machine.machine_type == "center_pivot"
    assert machine.capabilities["read_position"] is True


def test_energy_rejects_usable_above_nominal() -> None:
    with pytest.raises(ValidationError):
        EnergySystemContract(
            tenant_id="tenant",
            project_id="project",
            system_type="solar_battery",
            battery_nominal_kwh=100,
            battery_usable_kwh=120,
        )


def test_controller_rejects_inline_secret() -> None:
    with pytest.raises(ValidationError):
        ControllerContract(
            tenant_id="tenant",
            project_id="project",
            provider="generic",
            credential_reference="token=plaintext",
        )


def test_contracts_forbid_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        IrrigationProjectContract(tenant_id="tenant", name="Farm", unexpected=True)
