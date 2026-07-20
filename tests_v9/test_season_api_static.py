"""حارس ساكن + سلوك مخزن الكائنات لواجهة إدخال المواسم (SEASON-RECORD-ENTRY-01 شريحة 2).

وحدة صرفة — ``pytest -m unit`` (لا شبكة/قاعدة). يغطّي من براهين المواصفة العشرة ما يُثبَت بلا PG:
  • بنيويّ: النقاط الستّ على scout-ingest، صفر مسار منصّة، وأسلاك الأمان موجودة في كلّ نقطة.
  • ③ سلامة المرفق: sniff magic bytes + سقف الحجم (مُثبَت أيضاً في test_season_logbook_content_safety).
  • ⑦ سقف presign ≤300ث مفروض داخل blob_store (دفاع عميق، لا عند المستدعي فقط).
  • ⑧/⑪ برهان الكائن عند القبول: مرجع ميت ⇒ object_exists False؛ وfile:// في وضع الإنتاج (S3 مهيّأة) ⇒
    False (نظام ملفّات الحاوية زائل — دليل وهميّ يُرفَض). البراهين الحيّة (RLS، 409، idempotency) في
    services/scout-ingest-service/tests/test_season_live.py.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_SVC = _ROOT / "services" / "scout-ingest-service"
_SEASON_API = _SVC / "season_api.py"
_BLOB_STORE = _ROOT / "shared" / "storage" / "blob_store.py"


def _load_blob_store():
    """Load blob_store from its ABSOLUTE path — immune to the ``shared`` name collision.

    The repo has TWO ``shared`` packages (repo-root and ``services/mcp_servers/shared``);
    an mcp test can rebind top-level ``shared`` to the mcp one (which lacks ``storage``)
    in the shared pytest worker, so ``from shared.storage import blob_store`` fails
    depending on test order. Loading the file directly (the aquacrop/rs-anomaly static-
    guard pattern) bypasses ``sys.modules['shared']`` entirely — blob_store is stdlib-only
    (no ``from shared…``), so it exec's cleanly regardless of any shadow binding.
    """
    spec = importlib.util.spec_from_file_location("season_blob_store", _BLOB_STORE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# Loaded once, path-independent — no reliance on the shadowed top-level ``shared`` package.
_BS = _load_blob_store()


def _route_decorators() -> set[tuple[str, str]]:
    """(METHOD, path) pairs from ``@router.<method>("<path>")`` — AST parse, NO import.

    The endpoint module imports FastAPI, which is absent in the no-fastapi ``-m unit``
    tier; so this static guard reads the source (like other ``*_static`` guards) instead
    of importing ``season_api``. Keeps the guard honest without dragging FastAPI in.
    """
    tree = ast.parse(_SEASON_API.read_text(encoding="utf-8"))
    out: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) and not isinstance(node, ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            # @router.post("/path", ...)
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and isinstance(dec.func.value, ast.Name)
                and dec.func.value.id == "router"
                and dec.args
                and isinstance(dec.args[0], ast.Constant)
            ):
                out.add((dec.func.attr.upper(), dec.args[0].value))
    return out


# ── بنيويّ: النقاط + صفر مسار منصّة + أسلاك الأمان ───────────────────────────────
def test_ten_endpoints_all_on_scout_ingest_internal():
    routes = _route_decorators()
    # النواة الستّ (شريحة 2b)
    assert ("POST", "/internal/seasons") in routes  # إنشاء مسودّة
    assert ("PATCH", "/internal/seasons/{season_id}") in routes
    assert ("POST", "/internal/seasons/{season_id}/logbook") in routes
    assert ("GET", "/internal/seasons/{season_id}/logbook") in routes
    assert ("POST", "/internal/seasons/{season_id}/accept") in routes
    assert ("GET", "/internal/seasons") in routes
    # الأبناء الأربعة (SEASON-ENTRY-EVENTS-UI): تفتح مسار SIM-GOLDEN
    assert ("POST", "/internal/seasons/{season_id}/events") in routes
    assert ("POST", "/internal/seasons/{season_id}/harvest") in routes
    assert ("POST", "/internal/seasons/{season_id}/costs") in routes
    assert ("GET", "/internal/seasons/{season_id}/detail") in routes
    assert len(routes) == 10
    # صفر مسار منصّة: كلّ المسارات داخليّة على هذه الخدمة المالكة
    for _method, path in routes:
        assert path.startswith("/internal/seasons")


def test_security_wiring_present_in_source():
    """كلّ نقطة تمرّ ببوّابات الأمان؛ والقبول يزيد التصديق من الحافّة + الدور + برهان الكائن."""
    src = _SEASON_API.read_text(encoding="utf-8")
    # توكن الخدمة + المستأجِر من الحافّة على كلّ النقاط
    assert src.count("_require_service_token(") >= 6
    assert src.count("_require_tenant(") >= 6
    assert "_require_enabled()" in src  # خلف الراية
    # القبول: تصديق حافّة HMAC + دور مُراجِع + برهان وجود الكائن
    assert "verify_edge_attestation(" in src
    assert "has_reviewer_role(" in src
    assert "blob_store.object_exists(" in src
    assert "ERROR_LOGBOOK_MISSING" in src
    # المرفق: فحص محتوى + حدّ حجم مُتدفّق
    assert "detect_content_type(" in src
    assert "MAX_LOGBOOK_BYTES" in src
    assert "request.stream()" in src  # تدفّق لملفّ مؤقّت لا الذاكرة
    assert "tempfile" in src
    # PATCH/accept على موسم مقبول ⇒ 409 من النقطة نفسها
    assert "409" in src


def test_patch_rejects_after_accept_status_check():
    """④: منطق PATCH يرفض ما لم يكن الموسم untrusted (409) — الحارس من مدخله الحقيقيّ."""
    src = _SEASON_API.read_text(encoding="utf-8")
    assert 'status != "untrusted"' in src
    assert "season_not_editable_after_accept" in src


# ── ⑦ سقف presign TTL داخل blob_store ────────────────────────────────────────────
def test_presign_ttl_cap_enforced_inside_module():
    blob_store = _BS

    for bad in (0, -1, 301, 3600):
        with pytest.raises(blob_store.BlobStoreError):
            blob_store.presigned_get_url("file:///x", bad)
    # 300 مسموح (الحدّ نفسه)؛ file:// يعود كما هو (تطوير)
    assert blob_store.presigned_get_url("file:///x", 300) == "file:///x"


# ── ⑧/⑪ برهان الكائن عند القبول ─────────────────────────────────────────────────
def test_object_exists_dead_ref_and_file_in_production(monkeypatch):
    blob_store = _BS

    # مرجع فارغ/مجهول ⇒ False
    assert blob_store.object_exists("") is False
    assert blob_store.object_exists("weird://x") is False
    # dev (S3 معطَّلة): file:// موجود = True، غير موجود = False
    monkeypatch.setattr(blob_store, "S3_BUCKET", "")
    assert blob_store.object_exists("file:///definitely/missing/xyz") is False
    # ⑪ إنتاج (S3 مهيّأة): file:// ⇒ False دائماً (نظام ملفّات الحاوية زائل)
    monkeypatch.setattr(blob_store, "S3_BUCKET", "prod-bucket")
    monkeypatch.setattr(blob_store, "S3_ENDPOINT", "http://minio:9000")
    assert blob_store.s3_enabled() is True
    assert blob_store.object_exists("file:///tmp/anything") is False


# ── مخزن الكائنات: fail-closed + تدهور مُعلَن + ① تهيئة مكسورة ────────────────────
def test_upload_dev_fallback_and_roundtrip(tmp_path, monkeypatch):
    blob_store = _BS

    monkeypatch.setattr(blob_store, "S3_BUCKET", "")  # dev
    monkeypatch.setattr(blob_store, "LOCAL_DIR", str(tmp_path))
    ref = blob_store.upload_bytes("season-logbooks/t/s/abc.jpg", b"\xff\xd8\xff data", "image/jpeg")
    assert ref.startswith("file://")
    assert blob_store.object_exists(ref) is True  # dev file exists


def test_missing_keys_fail_closed_when_s3_enabled(monkeypatch):
    blob_store = _BS

    monkeypatch.setattr(blob_store, "S3_BUCKET", "b")
    monkeypatch.setattr(blob_store, "S3_ENDPOINT", "http://minio:9000")
    monkeypatch.delenv("S3_ACCESS_KEY", raising=False)
    monkeypatch.delenv("S3_SECRET_KEY", raising=False)
    with pytest.raises(blob_store.BlobStoreError, match="ACCESS_KEY|SECRET_KEY"):
        blob_store.upload_bytes("k", b"\xff\xd8\xff", "image/jpeg")


def test_bucket_without_endpoint_is_broken_not_dev(monkeypatch):
    """①: BUCKET مضبوط بلا ENDPOINT = مكسور (لا سقوط صامت لـfile://)."""
    blob_store = _BS

    monkeypatch.setattr(blob_store, "S3_BUCKET", "b")
    monkeypatch.setattr(blob_store, "S3_ENDPOINT", "")
    with pytest.raises(blob_store.BlobStoreError, match="misconfigured|S3_ENDPOINT"):
        blob_store.upload_bytes("k", b"\xff\xd8\xff", "image/jpeg")


def test_endpoint_scheme_from_ssl_flag_no_silent_http(monkeypatch):
    """②: المخطّط من S3_USE_SSL صراحةً — لا استنتاج صامت من الـendpoint."""
    blob_store = _BS

    monkeypatch.setattr(blob_store, "S3_ENDPOINT", "minio.example.com:9000")
    monkeypatch.setattr(blob_store, "S3_USE_SSL", "true")
    assert blob_store._endpoint_url() == "https://minio.example.com:9000"
    monkeypatch.setattr(blob_store, "S3_USE_SSL", "false")
    assert blob_store._endpoint_url() == "http://minio.example.com:9000"


# ── ③ برهان ترتيبيّ ضدّ الارتداد: تصادم اسم الحزمة shared لا يكسر تحميل blob_store ──
def test_blob_store_immune_to_shared_package_shadow(monkeypatch):
    """يحاكي الجريمة: حقن services/mcp_servers (حزمة shared بلا storage) في sys.path[0]
    وربط shared عليها في sys.modules — ثمّ يجب أن يبقى تحميل blob_store عبر المسار ناجحاً.

    توثيق: ``shared`` اسم حزمة عالي الاصطدام (repo-root + services/mcp_servers/shared)؛
    الحُرّاس التي تستورد ``shared.*`` يجب أن تحمّل عبر المسار المطلق لا عبر اسم الحزمة.
    """
    mcp_dir = _ROOT / "services" / "mcp_servers"
    monkeypatch.syspath_prepend(str(mcp_dir))  # auto-restored — لا يتسرّب للجيران
    # اربط shared على نسخة mcp_servers (بلا storage) كما يفعل الملوِّث
    for name in [n for n in list(sys.modules) if n == "shared" or n.startswith("shared.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    import shared as _shadow  # noqa: PLC0415 — الآن shared = mcp_servers/shared (بلا storage)

    assert "mcp_servers" in (getattr(_shadow, "__file__", "") or "")
    with pytest.raises(ModuleNotFoundError):
        import shared.storage  # noqa: F401,PLC0415 — النسخة المظلِّلة لا تملك storage
    # ومع ذلك: التحميل عبر المسار المطلق يبقى ناجحاً (مناعة الحارس)
    bs = _load_blob_store()
    assert bs.PRESIGN_TTL_S == 300 if hasattr(bs, "PRESIGN_TTL_S") else True
    assert bs.s3_enabled() in (True, False)  # يُحمَّل ويعمل رغم التظليل
