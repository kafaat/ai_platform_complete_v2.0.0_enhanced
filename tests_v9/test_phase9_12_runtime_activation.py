from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "services" / "sahool-platform" / "api" / "main.py"
REGISTRY = ROOT / "services" / "sahool-platform" / "api" / "router_registry.py"
MANIFEST = ROOT / "migrations" / "MANIFEST.txt"


def test_phase9_12_routers_are_mounted_in_main_app() -> None:
    # التسجيل مُستخرَج إلى router_registry.register_routers(app) ويُستدعى من main.py.
    main_src = MAIN.read_text(encoding="utf-8")
    assert "register_routers(app)" in main_src, "main.py must call register_routers(app)"
    src = main_src + "\n" + REGISTRY.read_text(encoding="utf-8")
    required_imports = [
        "from api.phase9_autonomous_farm_os import router as phase9_autonomous_router",
        "from api.phase10_continuous_learning import router as phase10_learning_router",
        "from api.phase11_federated_agents import router as phase11_federation_router",
        "from api.phase12_marketplace_ecosystem import router as phase12_ecosystem_router",
    ]
    required_mounts = [
        "app.include_router(phase9_autonomous_router)",
        "app.include_router(phase10_learning_router)",
        "app.include_router(phase11_federation_router)",
        "app.include_router(phase12_ecosystem_router)",
    ]
    for item in required_imports + required_mounts:
        assert item in src


def test_phase6_12_migrations_are_in_official_manifest() -> None:
    manifest = MANIFEST.read_text(encoding="utf-8")
    required = [
        "v114_cloud_native_gis_best_practices.sql",
        "v115_precision_agriculture_phase6.sql",
        "v116_enterprise_gis_phase7.sql",
        "v117_global_scale_phase8.sql",
        "v118_phase9_autonomous_farm_os.sql",
        "v119_phase10_continuous_learning.sql",
        "v120_phase11_federated_agents.sql",
        "v121_marketplace_ecosystem.sql",
    ]
    for filename in required:
        assert filename in manifest
        assert (ROOT / "migrations" / filename).exists(), filename
