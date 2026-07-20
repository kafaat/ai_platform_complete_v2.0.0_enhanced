"""حارس سلامة مرفق الدفتر (SEASON-RECORD-ENTRY-01 §4-③) — نواة نقيّة + براهين سلبيّة.

يفرض التعديل الملزم ③: الفحص بالمحتوى (magic bytes) لا بالامتداد، الحجم بعد الاستلام،
المفتاح مُشتقّ من الخادم (tenant+season_id+sha) فلا يختار العميل مساره ولا يهرّب موسماً تحت آخر.

وحدة صرفة — ``pytest -m unit`` (لا FastAPI/شبكة/boto3).
"""

from __future__ import annotations

import pytest

from shared.security.season_logbook import (
    ERROR_LOGBOOK_MISSING,
    ERROR_LOGBOOK_TOO_LARGE,
    ERROR_LOGBOOK_UNSUPPORTED_TYPE,
    MAX_LOGBOOK_BYTES,
    PRESIGN_TTL_S,
    content_sha256,
    derive_logbook_key,
    detect_content_type,
    key_belongs_to,
    logbook_size_ok,
)

pytestmark = pytest.mark.unit

_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF"
_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
_PDF = b"%PDF-1.7\n%\xe2\xe3"


def test_magic_bytes_accepts_the_three_allowed_types():
    assert detect_content_type(_JPEG) == ("image/jpeg", "jpg")
    assert detect_content_type(_PNG) == ("image/png", "png")
    assert detect_content_type(_PDF) == ("application/pdf", "pdf")


def test_extension_lie_rejected_by_content():
    """③ الفجوة: امتداد .jpg لكن البايتات ليست JPEG ⇒ رفض (لا نثق بالامتداد/الترويسة)."""
    # نصّ عاديّ / SVG / gzip — يُدّعى صورة لكنّ magic bytes تفضحه.
    assert detect_content_type(b"GIF89a...") is None  # GIF ليس ضمن المسموح
    assert detect_content_type(b"<svg xmlns=") is None
    assert detect_content_type(b"\x1f\x8b\x08") is None  # gzip
    assert detect_content_type(b"just plain text pretending to be .jpg") is None
    assert detect_content_type(b"") is None
    assert detect_content_type(None) is None


def test_size_measured_after_receipt_not_claimed():
    """③ الحجم بعد الاستلام: ≤10MB يمرّ، >10MB يُرفَض، 0 يُرفَض (fail-closed)."""
    assert logbook_size_ok(1) is True
    assert logbook_size_ok(MAX_LOGBOOK_BYTES) is True
    assert logbook_size_ok(MAX_LOGBOOK_BYTES + 1) is False
    assert logbook_size_ok(0) is False
    assert logbook_size_ok(-5) is False
    assert MAX_LOGBOOK_BYTES == 10 * 1024 * 1024


def test_key_is_server_derived_and_embeds_season():
    """المفتاح: season-logbooks/<tenant>/<season_id>/<sha>.<ext> — كلّه من الخادم."""
    sha = content_sha256(_JPEG)
    key = derive_logbook_key("tenant-a", "season-123", sha, "jpg")
    assert key == f"season-logbooks/tenant-a/season-123/{sha}.jpg"
    # sha مشتقّ فعلاً من البايتات (تغيّر البايت ⇒ تغيّر المفتاح)
    assert content_sha256(_JPEG) != content_sha256(_JPEG + b"x")


def test_key_derivation_fail_closed_on_missing_parts():
    sha = content_sha256(_PNG)
    for bad in (
        ("", "s", sha, "png"),
        ("t", "", sha, "png"),
        ("t", "s", "", "png"),
        ("t", "s", sha, ""),
    ):
        with pytest.raises(ValueError):
            derive_logbook_key(*bad)


def test_key_ownership_check_blocks_cross_tenant_and_cross_season():
    """presigned-GET: المفتاح يجب أن يقع تحت مستأجِر+موسم المُتّصِل (دفاع عمق خلف RLS)."""
    sha = content_sha256(_PDF)
    key = derive_logbook_key("tenant-a", "season-1", sha, "pdf")
    assert key_belongs_to(key, "tenant-a", "season-1") is True
    assert key_belongs_to(key, "tenant-b", "season-1") is False  # مستأجِر آخر
    assert key_belongs_to(key, "tenant-a", "season-2") is False  # موسم آخر
    assert key_belongs_to(key, "", "season-1") is False
    assert key_belongs_to("", "tenant-a", "season-1") is False


def test_presign_ttl_and_error_codes_stable():
    """أسقف/رموز مستقرّة يعتمدها الحارس السلوكيّ في الشريحة 2ب."""
    assert PRESIGN_TTL_S == 300
    assert ERROR_LOGBOOK_UNSUPPORTED_TYPE == "logbook_unsupported_type"
    assert ERROR_LOGBOOK_TOO_LARGE == "logbook_too_large"
    assert ERROR_LOGBOOK_MISSING == "logbook_missing"
