"""Evidence required before safety tiers may interpret an amount as zero.

Money is in USD; quantities are numeric JSON values, never booleans or strings.
Zero is an explicit observation, not a substitute for absent financial evidence.
"""

import math

ECONOMIC_ACTIONS = frozenset(
    {"investment", "contract", "loan", "irrigation", "fertilization", "pesticide"}
)
SPENDING_ACTIONS = frozenset({"investment", "irrigation", "fertilization", "pesticide"})


def contract_violations(action_type: str, action_data: dict, farm_context: dict) -> list[str]:
    required = {"action_data": [], "farm_context": []}
    if action_type in ECONOMIC_ACTIONS:
        required["farm_context"].append("annual_revenue_usd")
    if action_type in SPENDING_ACTIONS:
        required["action_data"].extend(["cost_usd", "projected_revenue_increase_usd"])
        required["farm_context"].extend(["annual_costs_usd", "cash_reserve_usd"])
    if action_type == "loan":
        required["action_data"].append("loan_amount_usd")
        required["farm_context"].append("current_debt_usd")
    if action_type == "contract":
        required["action_data"].append("contract_value_usd")
    if action_type == "pesticide":
        required["action_data"].extend(["chemical", "dosage_kg_ha"])
    if action_type == "irrigation":
        required["action_data"].append("water_m3")
        required["farm_context"].extend(
            ["field_area_ha", "season_water_used_m3_ha", "water_source"]
        )

    invalid = []
    for source, values in (("action_data", action_data), ("farm_context", farm_context)):
        invalid.extend(_nonfinite_paths(values, source))
        for key in required[source]:
            if values.get(key) is None:
                invalid.append(f"{source}.{key}")
        for key, value in values.items():
            if key.endswith(("_usd", "_m3", "_m3_ha", "_kg_ha", "_ds_m")) or key in {
                "field_area_ha",
                "season_carbon_kg_co2e",
            }:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not _finite(value)
                    or value < 0
                    or (key == "field_area_ha" and value == 0)
                ):
                    invalid.append(f"{source}.{key}")
            if key in {
                "crop",
                "growth_stage",
                "soil_texture",
                "chemical",
                "water_source",
            } and not isinstance(value, str):
                invalid.append(f"{source}.{key}")
    if action_type == "pesticide" and not (
        isinstance(action_data.get("chemical"), str) and action_data["chemical"].strip()
    ):
        invalid.append("action_data.chemical")
    if action_type == "irrigation" and str(farm_context.get("water_source")) not in {
        "groundwater",
        "surface",
        "mixed",
    }:
        invalid.append("farm_context.water_source")
    return list(dict.fromkeys(invalid))


def _finite(value: int | float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _nonfinite_paths(value, path):
    if isinstance(value, float) and not math.isfinite(value):
        yield path
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _nonfinite_paths(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _nonfinite_paths(child, f"{path}.{index}")
