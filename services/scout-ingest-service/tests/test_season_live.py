"""برهان HTTP حيّ لواجهة إدخال المواسم (SEASON-RECORD-ENTRY-01 شريحة 2) على PG16 أصليّ.

يقود الخدمة الفعليّة (TestClient) تحت الدور المقيَّد ``sahool_ingest`` بمنح v201/v202 (SELECT/INSERT/
UPDATE، لا DELETE) وRLS فعّال. يُثبِت البراهين التي تتطلّب قاعدة حقيقيّة (المدخل الحقيقيّ لا SQL مباشر):

  ①  توكن خدمة غائب ⇒ 401 · قبول بلا تصديق حافّة ⇒ 401 · قبول بلا دور season-reviewer ⇒ 403
  ③  رفع بامتداد .jpg وبايتات ليست JPEG ⇒ 415 · (سقف الحجم مُثبَت وحدةً)
  ④  PATCH على موسم مقبول ⇒ 409 **عبر مسار القبول الحقيقيّ** (لا دالّة التصديق فقط)
  ⑤  idempotency على draft_key: إعادة الإرسال لا تُنشئ نسخة
  ⑧  القبول يتطلّب كائناً موجوداً: مرجع دفتر مفقود ⇒ 422 logbook_missing
  ⑨  عزل RLS: المستأجِر B لا يرى مسودّات المستأجِر A (صفر صفوف)
  🔟 append-only: sahool_ingest بلا DELETE على season_records (permission denied)

``-m integration`` فقط، يتخطّى بلا قاعدة. مُصادَق حيّاً على PG16 (2026-07-19).
يتطلّب: ``TEST_ADMIN_URL`` (superuser، للإعداد) — إن غاب يتخطّى.
"""

from __future__ import annotations

import importlib
import os
import uuid

import pytest

asyncpg = pytest.importorskip("asyncpg")
pytestmark = pytest.mark.integration

ADMIN_URL = os.getenv("TEST_ADMIN_URL", "")
# درس fields.id: وظيفة تكامل مكسورة التهيئة تتخطّى وتظهر خضراء. في CI اقلب skip⇒fail صراحةً
# عبر CI_INTEGRATION_REQUIRED=1 — لا نرث خضرةً كاذبة من تهيئة ناقصة.
_REQUIRE_DB = os.getenv("CI_INTEGRATION_REQUIRED", "").strip().lower() in ("1", "true", "yes")
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SVC = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_A = "00000000-0000-0000-0000-0000000000aa"
_B = "00000000-0000-0000-0000-0000000000bb"
_TOKEN = "season-svc-token"  # noqa: S105 — قيمة اختبار
_HMAC = "edge-hmac-test-key"

# اجعل shared قابلاً للاستيراد (compute_edge_attestation) قبل أيّ import.
if _REPO not in os.sys.path:
    os.sys.path.insert(0, _REPO)


def _sign(uid: str, roles: str, ts: str) -> str:
    from shared.security.trusted_tenant import compute_edge_attestation

    return compute_edge_attestation(uid, roles, ts, _HMAC)


@pytest.fixture
async def live_app(tmp_path):
    if not ADMIN_URL:
        if _REQUIRE_DB:
            pytest.fail("TEST_ADMIN_URL unset but CI_INTEGRATION_REQUIRED=1 (integration must run)")
        pytest.skip("TEST_ADMIN_URL unset")
    try:
        admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    except Exception as exc:  # noqa: BLE001
        if _REQUIRE_DB:
            pytest.fail(f"admin PG unavailable but CI_INTEGRATION_REQUIRED=1: {type(exc).__name__}")
        pytest.skip(f"admin PG unavailable: {type(exc).__name__}")
    # مخطّط أدنى واقعيّ: fields ملك المنصّة (PK نصّيّ)، ثمّ v201 + v202.
    await admin.execute(
        "CREATE TABLE IF NOT EXISTS fields (field_id VARCHAR(50) PRIMARY KEY, tenant_id UUID NOT NULL)"
    )
    for f in ("migrations/v201_season_records.sql", "migrations/v202_season_draft_key.sql"):
        await admin.execute(open(os.path.join(_REPO, f), encoding="utf-8").read())
    # الدور المقيَّد + منح v201/v202 (نفس bootstrap): SELECT/INSERT/UPDATE، لا DELETE.
    await admin.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sahool_ingest') THEN
            CREATE ROLE sahool_ingest LOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS PASSWORD 'ingpw'; END IF;
        END $$;
        GRANT USAGE ON SCHEMA public TO sahool_ingest;
        GRANT SELECT, INSERT, UPDATE ON
          season_records, season_crop, season_events, season_harvest, season_cost_items
          TO sahool_ingest;
    """)
    # نظافة بين التشغيلات (append-only: لا DELETE بالدور المقيَّد؛ الإعداد بالمسؤول).
    await admin.execute("DELETE FROM season_crop; DELETE FROM season_records; DELETE FROM fields;")
    await admin.execute(
        "INSERT INTO fields VALUES ('field-a',$1),('field-b',$2)",
        uuid.UUID(_A),
        uuid.UUID(_B),
    )
    await admin.close()

    os.environ["DATABASE_URL"] = "postgresql://sahool_ingest:ingpw@" + ADMIN_URL.split("@", 1)[1]
    os.environ["SEASON_ENTRY_ENABLED"] = "1"
    os.environ["SEASON_ENTRY_SERVICE_TOKEN"] = _TOKEN
    os.environ["SEASON_EDGE_HMAC_KEY"] = _HMAC
    os.environ["LOGBOOK_LOCAL_DIR"] = str(tmp_path)  # dev file:// store
    os.environ.pop("S3_BUCKET", None)  # dev mode (S3 disabled ⇒ file://)
    for p in (_REPO, _SVC):
        if p not in os.sys.path:
            os.sys.path.append(p)
    import season_api

    importlib.reload(season_api)
    import main

    importlib.reload(main)
    from fastapi.testclient import TestClient

    return TestClient(main.app)


def _hdr(tenant: str, *, reviewer: bool = False, attest: bool = True, roles: str | None = None):
    h = {"X-Season-Entry-Token": _TOKEN, "X-Tenant-Id": tenant}
    if reviewer or roles is not None:
        ts = "1800000000"
        rolestr = roles if roles is not None else ("season-reviewer" if reviewer else "farmer")
        uid = "user-ali"
        h["X-User-Id"] = uid
        h["X-Roles"] = rolestr
        h["X-Edge-Timestamp"] = ts
        if attest:
            # نافذة ±120ث: زوّد now عبر ترويسة؟ الخدمة تستخدم الوقت الحقيقيّ؛ نستخدم ختم قريب.
            import time

            ts = str(int(time.time()))
            h["X-Edge-Timestamp"] = ts
            h["X-Edge-Attestation"] = _sign(uid, rolestr, ts)
    return h


async def test_season_entry_live_proofs(live_app):
    c = live_app

    draft = {
        "field_id": "field-a",
        "observed_at_from": "2022-11-01",
        "observed_at_to": "2023-05-01",
        "season_label": "شتاء 2022/2023",
        "draft_key": "dk-1",
    }

    # ① توكن خدمة غائب ⇒ 401 (جسم صالح كي يمرّ التحقّق ويصل لبوّابة التوكن)
    assert c.post("/internal/seasons", json=draft).status_code == 401
    r = c.post("/internal/seasons", json=draft, headers=_hdr(_A))
    assert r.status_code == 201, r.text
    sid = r.json()["season_id"]

    # ⑤ idempotency على draft_key: نفس المسودّة ⇒ نفس المعرّف، لا نسخة
    r2 = c.post("/internal/seasons", json=draft, headers=_hdr(_A))
    assert (
        r2.status_code == 201 and r2.json()["season_id"] == sid and r2.json()["idempotent"] is True
    )

    # ⑨ عزل RLS: المستأجِر B لا يرى مسودّة A
    lst_b = c.get("/internal/seasons?status=untrusted", headers=_hdr(_B))
    assert lst_b.status_code == 200
    assert all(s["id"] != sid for s in lst_b.json()["seasons"])
    lst_a = c.get("/internal/seasons?status=untrusted", headers=_hdr(_A))
    assert any(s["id"] == sid for s in lst_a.json()["seasons"])

    # PATCH ما دام untrusted ⇒ 200
    assert (
        c.patch(f"/internal/seasons/{sid}", json={"notes": "ملاحظة"}, headers=_hdr(_A)).status_code
        == 200
    )

    # ① قبول بلا تصديق حافّة ⇒ 401
    assert c.post(f"/internal/seasons/{sid}/accept", headers=_hdr(_A)).status_code == 401
    # ① توقيع HMAC باطل (X-User-Id ملفّقة بلا توقيع صحيح) ⇒ 401
    forged = _hdr(_A, reviewer=True)
    forged["X-Edge-Attestation"] = "deadbeef" * 8  # توقيع غير مطابق
    assert c.post(f"/internal/seasons/{sid}/accept", headers=forged).status_code == 401
    # ⑨-role قبول مُصدَّق لكن بلا دور season-reviewer ⇒ 403
    assert (
        c.post(f"/internal/seasons/{sid}/accept", headers=_hdr(_A, roles="farmer")).status_code
        == 403
    )
    # مالك/غير مالك: B يطلب presign لموسم A ⇒ 404 (لا 403 — لا تسريب وجود)
    assert c.get(f"/internal/seasons/{sid}/logbook", headers=_hdr(_B)).status_code == 404
    # ⑧ قبول بلا مرفق موجود ⇒ 422 logbook_missing
    r = c.post(f"/internal/seasons/{sid}/accept", headers=_hdr(_A, reviewer=True))
    assert r.status_code == 422 and r.json()["detail"] == "logbook_missing", r.text

    # ③ رفع بامتداد كاذب (بايتات ليست JPEG) ⇒ 415
    bad = c.post(
        f"/internal/seasons/{sid}/logbook",
        content=b"not really a jpeg",
        headers=_hdr(_A),
    )
    assert bad.status_code == 415, bad.text
    # ③ رفع >10MB (يُقاس بعد الاستلام، لا Content-Length) ⇒ 413
    big = b"\xff\xd8\xff" + b"\x00" * (10 * 1024 * 1024 + 1)
    assert (
        c.post(f"/internal/seasons/{sid}/logbook", content=big, headers=_hdr(_A)).status_code == 413
    )
    # رفع صحيح (JPEG magic) ⇒ 200
    ok = c.post(
        f"/internal/seasons/{sid}/logbook",
        content=b"\xff\xd8\xff\xe0\x00\x10JFIF real jpeg bytes",
        headers=_hdr(_A),
    )
    assert ok.status_code == 200, ok.text

    # القبول الآن ينجح (مُصدَّق + دور + مرفق موجود)
    acc = c.post(f"/internal/seasons/{sid}/accept", headers=_hdr(_A, reviewer=True))
    assert acc.status_code == 200 and acc.json()["trust_status"] == "accepted", acc.text
    assert acc.json()["accepted_by"] == "user-ali"

    # ④ PATCH على موسم مقبول ⇒ 409 (عبر مسار القبول الحقيقيّ)
    patch_after = c.patch(f"/internal/seasons/{sid}", json={"notes": "x"}, headers=_hdr(_A))
    assert patch_after.status_code == 409, patch_after.text
    # قبول مكرّر ⇒ 409 already_accepted
    assert (
        c.post(f"/internal/seasons/{sid}/accept", headers=_hdr(_A, reviewer=True)).status_code
        == 409
    )


async def test_sahool_ingest_has_no_delete_on_season(live_app):
    """🔟 append-only: الدور المقيَّد لا يملك DELETE على season_records (permission denied)."""
    conn = await asyncpg.connect(os.environ["DATABASE_URL"], statement_cache_size=0)
    try:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", _A)
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("DELETE FROM season_records")
    finally:
        await conn.close()
