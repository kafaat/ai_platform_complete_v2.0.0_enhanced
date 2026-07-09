#!/usr/bin/env python3
"""Guard P2 main.py decomposition for actuator, SAM2, and weather services."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _path(rel: str) -> Path:
    return ROOT / rel


def _text(rel: str) -> str:
    return _path(rel).read_text(encoding="utf-8")


def _loc(rel: str) -> int:
    return len(_text(rel).splitlines())


def _function_names(rel: str) -> set[str]:
    tree = ast.parse(_text(rel), filename=rel)
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _assert_file(rel: str) -> None:
    if not _path(rel).exists():
        raise SystemExit(f"missing expected P2 file: {rel}")


def _assert_heavy_extracted(label: str, main_rel: str, runtime_rel: str, heavy: set[str]) -> None:
    main_funcs = _function_names(main_rel)
    runtime_funcs = _function_names(runtime_rel)
    leaked = heavy & main_funcs
    missing = heavy - runtime_funcs
    if leaked:
        raise SystemExit(f"{label} heavy functions returned to main.py: {sorted(leaked)}")
    if missing:
        raise SystemExit(f"{label} runtime missing heavy functions: {sorted(missing)}")


def main() -> int:
    actuator_main = "services/actuator-service/main.py"
    actuator_runtime = "services/actuator-service/actuator_runtime.py"
    _assert_file(actuator_runtime)
    if _loc(actuator_main) > 80:
        raise SystemExit(f"actuator main.py regression: LOC {_loc(actuator_main)} > 80")
    if "from actuator_runtime import *" not in _text(actuator_main):
        raise SystemExit("actuator main.py no longer delegates to actuator_runtime")
    _assert_heavy_extracted(
        "actuator",
        actuator_main,
        actuator_runtime,
        {
            "send_mqtt_command",
            "evaluate_rules",
            "mqtt_sensor_listener",
            "log_command",
            "_compensate",
            "_cluster_should_fire",
            "_authorize_device_control",
        },
    )

    sam2_main = "services/sam2-inference/main.py"
    sam2_runtime = "services/sam2-inference/sam2_runtime.py"
    _assert_file(sam2_runtime)
    if _loc(sam2_main) > 170:
        raise SystemExit(f"sam2 main.py regression: LOC {_loc(sam2_main)} > 170")
    if "import sam2_runtime as rt" not in _text(sam2_main):
        raise SystemExit("sam2 main.py no longer delegates to sam2_runtime")
    _assert_heavy_extracted(
        "sam2",
        sam2_main,
        sam2_runtime,
        {
            "_load_model",
            "_resolve_image_url",
            "_stac_latest_visual",
            "_read_rgb",
            "_mask_to_polygon",
            "_build_prompt",
        },
    )

    weather_main = "services/weather-service/main.py"
    weather_runtime = "services/weather-service/weather_runtime.py"
    _assert_file(weather_runtime)
    if _loc(weather_main) > 80:
        raise SystemExit(f"weather main.py regression: LOC {_loc(weather_main)} > 80")
    if "import weather_runtime as rt" not in _text(weather_main):
        raise SystemExit("weather main.py no longer delegates to weather_runtime")
    _assert_heavy_extracted(
        "weather",
        weather_main,
        weather_runtime,
        {
            "_cached_sample",
            "operation_window",
            "operation_plan",
            "tile_data",
            "operation_tile_data",
            "tile_series",
            "wind_grid",
        },
    )
    print("p2_main_decomposition_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
