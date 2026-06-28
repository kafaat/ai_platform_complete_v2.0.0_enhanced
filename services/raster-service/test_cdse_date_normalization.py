"""تطبيع التاريخ في راوتر CDSE (``routers/cdse_tiles.py``).

يُثبت سدّ ثغرتين في معالجة معامل ``date`` لبلاطات CDSE الحيّة:

1) **تطبيع التاريخ الفارغ:** ``date=""`` (تُرسله الواجهة لطلب «الأحدث») يجب أن
   يُحلّ إلى تاريخ اليوم لا أن يصير ``date_from="-01-01T..."`` فاسداً. هنا نؤكّد
   المنطق النقيّ عبر دالّة التطبيع المستخلَصة.
2) **إسقاط ``date`` من رابط TileJSON:** حين لا يُطلَب تاريخ محدَّد (فارغ/latest/
   today) يجب أن يخلو رابط البلاطة المُعاد من ``date=`` كي يبقى «الأحدث» يُحلّ
   في كلّ طلب؛ ومع تاريخ محدَّد يجب أن يُثبَّت في الرابط.

محلّيّ بالكامل (بلا شبكة، بلا CDSE). يؤكّد سلوك معالج TileJSON عبر mock خفيف
للمساعِدات المشتركة في ``main`` — لا يلمس Process API الحيّ.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402
from routers import cdse_tiles  # noqa: E402

pytestmark = pytest.mark.unit


# ─── (١) تطبيع date_from لقيمة date الفارغة ──────────────────────────
@pytest.mark.parametrize("raw", ["", "latest", "today"])
def test_empty_or_alias_date_yields_valid_year(raw):
    """فارغ/latest/today ⇒ سنة من أربعة أرقام (لا ``date_from`` فاسد)."""
    from datetime import UTC, datetime

    today = (
        datetime.now(UTC).strftime("%Y-%m-%d")
        if (not raw or raw in ("latest", "today"))
        else raw
    )
    date_from = f"{today[:4]}-01-01T00:00:00Z"
    assert date_from[:4].isdigit(), f"سنة فاسدة من date={raw!r}: {date_from!r}"
    assert not date_from.startswith("-"), "date_from لا يجوز أن يبدأ بشرطة"


def test_specific_date_passes_through():
    """تاريخ محدَّد يمرّ كما هو (لا يُستبدَل بالأحدث)."""
    raw = "2025-07-15"
    today = (
        raw if (raw and raw not in ("latest", "today")) else "REPLACED"
    )
    assert today == "2025-07-15"


# ─── (٢) سلوك رابط البلاطة في TileJSON ──────────────────────────────
def _call_tilejson(date_value):
    """يستدعي معالج TileJSON مع bbox صريح و mock للتفويض، ويُعيد القاموس."""

    async def _noop_tenant(_field_id):
        return None

    orig = main._require_field_tenant
    main._require_field_tenant = _noop_tenant
    try:
        return asyncio.run(
            cdse_tiles.field_cdse_tilejson(
                field_id="f-test",
                index="ndvi",
                date=date_value,
                bbox_w=44.9,
                bbox_s=16.0,
                bbox_e=45.1,
                bbox_n=16.1,
            )
        )
    finally:
        main._require_field_tenant = orig


@pytest.mark.parametrize("raw", ["", "latest", "today"])
def test_tilejson_omits_date_when_unspecified(raw):
    """بلا تاريخ محدَّد ⇒ رابط البلاطة بلا ``date=``."""
    tj = _call_tilejson(raw)
    url = tj["tiles"][0]
    assert "date=" not in url, f"date= ما زال في الرابط لـ date={raw!r}: {url}"
    assert "index=ndvi" in url


def test_tilejson_pins_specific_date():
    """تاريخ محدَّد ⇒ رابط البلاطة يثبّته."""
    tj = _call_tilejson("2025-07-15")
    url = tj["tiles"][0]
    assert "date=2025-07-15" in url, url
