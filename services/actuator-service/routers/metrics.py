"""routers/metrics.py — مقاييس إزالة التكرار (idempotency metrics)
======================================================================
شريحة من تفكيك ``actuator_runtime.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجة حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسار/المخرجات مطابقة.
قراءة فقط — لا أسرار. الرموز المشتركة تبقى في ``main`` وتُشار إليها عبر ``main.X``.
"""

from __future__ import annotations

import actuator_runtime as main
from fastapi import APIRouter

router = APIRouter()


@router.get("/idempotency/metrics")
async def idempotency_metrics():
    """مقاييس إزالة التكرار (المراقبة قبل الفرض): الوضع + عدّ القرارات حسب المفتاح.

    قراءة فقط — يُمكّن مرحلة Observe من نمط الإغلاق المرن: قبل ترقية الوضع إلى cluster،
    راقِب shadow_divergence (كم مرّة كان العنقوديّ سيمنع تكراراً فاتَ المحلّيّ) و
    cluster_unavailable_fallback (صحّة المخزن). لا أسرار — عدّادات مجرّدة فقط.
    """
    return {
        "mode": main.ACTUATOR_IDEMPOTENCY_MODE,
        "dedup_window_sec": main.ACTUATOR_DEDUP_WINDOW_SEC,
        "metrics": dict(main._IDEM_METRICS),
        "local_store_size": len(main._dedup_last_fired),
    }
