from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = (ROOT / "services/sahool-platform/api/routers/fields.py").read_text(encoding="utf-8")
AUTH = (ROOT / "services/auth/main.py").read_text(encoding="utf-8")
RASTER = (ROOT / "services/raster-service/main.py").read_text(encoding="utf-8")
RASTER_AUTH_TEST = (ROOT / "tests_v9/test_raster_endpoint_auth_coverage.py").read_text(
    encoding="utf-8"
)


def test_fields_put_endpoint_exists_for_update_contract():
    assert '@router.put("/api/v1/fields/{field_id}", response_model=FieldDetail)' in FIELDS
    assert '@router.patch("/api/v1/fields/{field_id}", response_model=FieldDetail)' in FIELDS


def test_sensitive_mfa_enabled_by_default():
    assert 'os.getenv("ENFORCE_SENSITIVE_MFA", "true").lower() == "true"' in AUTH


def test_layer_tenant_fallback_fails_closed_without_tenant():
    body = RASTER[
        RASTER.index("async def _require_layer_tenant_authorized") : RASTER.index(
            "def _public_cog_url"
        )
    ]
    assert "db_owner = await db_persist.layer_owner_tenant(layer_id)" in body
    assert "if not req_tenant:" in body
    assert "مستأجر الطلب مطلوب لقراءة الطبقة" in body


def test_storage_and_offline_are_no_longer_public_catalog_in_guard():
    public = RASTER_AUTH_TEST[
        RASTER_AUTH_TEST.index("PUBLIC_CATALOG: set[str]") : RASTER_AUTH_TEST.index(
            "# ─────────────────────────────────────────────────────────────────────────────\n# كاشف ast"
        )
    ]
    service = RASTER_AUTH_TEST[
        RASTER_AUTH_TEST.index("SERVICE_ONLY: set[str]") : RASTER_AUTH_TEST.index(
            "# ─────────────────────────────────────────────────────────────────────────────\n# القائمة العامّة"
        )
    ]
    assert '"/storage/stats"' in service
    assert '"/offline/packs"' in service
    assert '"/offline/packs/{pack_name}"' in service
    assert '"/storage/stats"' not in public
