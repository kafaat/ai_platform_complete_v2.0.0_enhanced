"""api/boundary_models.py — نماذج طلب حدود الحقل (Field Boundaries)
=================================================================
كتلة مكتفية ذاتيّاً مُستخرَجة من ``api/main.py`` (تفكيك B1، نمط P0).

تحتوي على نماذج طلب نقاط حدود الحقل الثلاث (review/score/clean) وثابت حالات
المراجعة المسموحة. مكتفية ذاتيّاً: تعتمد فقط على ``pydantic`` + stdlib، بلا أيّ
رمز آخر من ``api.main``. مستهلِكها الوحيد ``api/routers/boundaries.py``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# مجموعة حالات المراجعة المسموحة (تطابق قيد CHECK في v58:
# field_boundaries_review_status_chk). 'unreviewed' هي القيمة الافتراضيّة في
# القاعدة، فلا نقبلها كانتقال صريح من الواجهة — المراجِع يَنتقل إلى قرار نهائيّ.
_BOUNDARY_REVIEW_STATES = {"approved", "rejected", "needs_edit"}


class BoundaryReviewRequest(BaseModel):
    """طلب مراجعة بشريّة (HIL) لحدّ الحقل — قرار المراجِع النهائيّ.

    review_status: واحدة من approved|rejected|needs_edit (يُتحقّق منها مقابل
    _BOUNDARY_REVIEW_STATES فيردّ 422 على ما عداها قبل لمس القاعدة).
    """

    review_status: str = Field(..., max_length=20)


class BoundaryScoreRequest(BaseModel):
    """طلب تهديف ثقة حدّ الحقل من خصائصه البنيويّة.

    props: خصائص قابلة للحساب عن الحدّ (vertex_count, area_ha, is_valid,
    ring_count, self_intersections, temporal_agreement?) — تُمرَّر كما هي إلى
    score_boundary (دالّة نقيّة حتميّة). source_type اختياريّ يُسجَّل provenance.

    props أصبحت اختياريّة (#15): إن لم تُرسَل (None) يَشتقّ الخادم الخصائص
    البنيويّة من field_boundaries.geom المخزَّنة عبر استعلام PostGIS واحد ثمّ
    يهدّفها — مع بقاء التوافق الخلفيّ عند إرسالها صراحةً.
    """

    props: dict | None = Field(default=None)
    source_type: str | None = Field(default=None, max_length=30)


class BoundaryCleanRequest(BaseModel):
    """طلب تنظيف طوبولوجيّ حتميّ لحدّ الحقل المخزَّن (v59).

    tolerance_m: وحدة تحمّل التبسيط بالمتر (افتراضيّ 5.0) — تُمرَّر إلى
    sahool_clean_boundary_geom التي تحوّلها داخليّاً إلى درجات (تقريب صالح قرب
    خطوط عرض اليمن — انظر تعليق الـmigration).
    """

    tolerance_m: float = Field(default=5.0)
