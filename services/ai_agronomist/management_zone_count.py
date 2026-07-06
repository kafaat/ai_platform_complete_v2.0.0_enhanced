"""management_zone_count.py — اختيار عدد مناطق الإدارة الأمثل (V60.2).

**المشكلة:** عنقدة v60.1 (``productivity_zones_clustering.kmeans_1d``) تحتاج ``k`` مُمرَّراً
من المستخدم (افتراضيّ 3) — لا جواب مبدئيّ لسؤال الزراعة الدقيقة المركزيّ: «كم منطقة إدارة
يحتاج هذا الحقل؟». تقسيمٌ زائد يُبدّد الكلفة؛ ناقصٌ يُخفي تبايناً حقيقيّاً.

**الحلّ (منهجيّة Management Zone Analyst — Fridgen et al. 2004):** عنقدة ضبابيّة
(fuzzy c-means) عبر مدى من ``k``، ثمّ مؤشّران معياريّان لاختيار الأمثل:

- **FPI** (Fuzziness Performance Index): درجة تداخل العضويّة — الأدنى = مجموعات أوضح.
- **NCE** (Normalized Classification Entropy): درجة الفوضى — الأدنى = تنظيم أفضل.

عدد المناطق الأمثل = ``k`` الذي يُصغّر FPI (وعادةً NCE معه). **صدق:** هذا اقتراح إحصائيّ
لا قرار — يبقى بحاجة حكم أغرونوميّ وتحقّق ميدانيّ؛ ويُعاد ``None`` عند بيانات متدهورة بدل
اختراع عدد. نقيّ (stdlib فقط، لا numpy/sklearn) وحتميّ (بذر كوانتايل ثابت) فيتكرّر في CI.
"""

from __future__ import annotations

import math
from typing import Any

# مدى افتراضيّ لعدد المناطق (FPI/NCE غير مُعرَّفَين عند k=1؛ >6 نادراً عمليّ لحقل واحد).
_DEFAULT_K_MIN = 2
_DEFAULT_K_MAX = 6
_FUZZIFIER = 2.0  # m الاصطلاحيّ في fuzzy c-means (Bezdek).


def _valid_values(values: list[float]) -> list[float]:
    return [
        float(v) for v in values if isinstance(v, (int, float)) and v == v and abs(v) != math.inf
    ]


def fuzzy_cmeans_1d(
    values: list[float],
    k: int,
    *,
    m: float = _FUZZIFIER,
    iters: int = 60,
    tol: float = 1e-6,
) -> tuple[list[float], list[list[float]]] | None:
    """fuzzy c-means حتميّ أحاديّ البُعد.

    يُرجِع ``(centroids, memberships)`` حيث ``memberships[i][j]`` عضويّة القيمة i في
    المركز j (الصفوف تجمع لـ1)، أو ``None`` عند تعذّر تكوين k مجموعات. البذر كوانتايل
    ثابت (لا عشوائيّة) فالنتيجة تتكرّر. صدق: بيانات متجانسة/غير كافية ⇒ ``None``.
    """
    vals = _valid_values(values)
    distinct = sorted(set(vals))
    if k < 2 or len(distinct) < k:
        return None

    # بذر المراكز عند كوانتايلات متساوية التباعد من القيم المميَّزة المرتّبة (حتميّ).
    centroids = [
        distinct[min(len(distinct) - 1, (2 * j + 1) * len(distinct) // (2 * k))] for j in range(k)
    ]
    exp = 2.0 / (m - 1.0)

    for _ in range(iters):
        # تحديث العضويّة.
        memberships: list[list[float]] = []
        for x in vals:
            dists = [abs(x - c) for c in centroids]
            if min(dists) <= 1e-12:
                # القيمة تنطبق على مركز — عضويّة كاملة له (تجنّب القسمة على صفر).
                row = [1.0 if d <= 1e-12 else 0.0 for d in dists]
                s = sum(row)
                memberships.append([r / s for r in row])
                continue
            inv = [1.0 / (d**exp) for d in dists]
            s = sum(inv)
            memberships.append([r / s for r in inv])

        # تحديث المراكز (مرجّحة بـu^m).
        new_centroids: list[float] = []
        for j in range(k):
            num = sum((memberships[i][j] ** m) * vals[i] for i in range(len(vals)))
            den = sum(memberships[i][j] ** m for i in range(len(vals)))
            new_centroids.append(num / den if den > 0 else centroids[j])

        shift = max(abs(a - b) for a, b in zip(new_centroids, centroids, strict=True))
        centroids = new_centroids
        if shift < tol:
            break

    # ترتيب المراكز تصاعديّاً مع أعمدة العضويّة المقابِلة (اتّساقاً مع kmeans_1d).
    order = sorted(range(k), key=lambda j: centroids[j])
    centroids_sorted = [centroids[j] for j in order]
    memberships_sorted = [[row[j] for j in order] for row in memberships]
    return centroids_sorted, memberships_sorted


def fpi(memberships: list[list[float]], k: int) -> float:
    """Fuzziness Performance Index ∈ [0,1] — الأدنى = مجموعات أوضح (أقلّ تداخل)."""
    n = len(memberships)
    if n == 0 or k < 2:
        return 1.0
    fc = sum(u * u for row in memberships for u in row) / n  # partition coefficient F∈[1/k,1]
    # FPI = (k/(k-1))·(1-F): تقسيم صريح (F→1) ⇒ 0؛ ضبابيّ تامّ (F→1/k) ⇒ 1. الأدنى = الأمثل.
    return round((k / (k - 1.0)) * (1.0 - fc), 4)


def nce(memberships: list[list[float]], k: int) -> float:
    """Normalized Classification Entropy — الأدنى = تنظيم أفضل (فوضى أقلّ)."""
    n = len(memberships)
    if n == 0 or k < 2 or n <= k:
        return 1.0
    h = -sum(u * math.log(u) for row in memberships for u in row if u > 0) / n
    denom = 1.0 - (k / n)
    return round(h / denom, 4) if denom > 0 else 1.0


def recommend_zone_count(
    values: list[float],
    *,
    k_min: int = _DEFAULT_K_MIN,
    k_max: int = _DEFAULT_K_MAX,
) -> dict[str, Any] | None:
    """يقترح عدد مناطق الإدارة الأمثل عبر FPI/NCE على مدى ``k``.

    يُرجِع جدول المؤشّرات الكامل + ``recommended_k`` (يُصغّر FPI) + توافق FPI/NCE،
    أو ``None`` عند تعذّر أيّ عنقدة (بيانات متجانسة/قليلة). صدق: اقتراح إحصائيّ يبقى
    بحاجة حكم أغرونوميّ + تحقّق ميدانيّ (لا قرار نهائيّ، لا اختراع عند التدهور).
    """
    vals = _valid_values(values)
    distinct = len(set(vals))
    if distinct < 2:
        return None

    k_hi = min(k_max, distinct, len(vals) - 1)
    if k_hi < k_min:
        return None

    metrics: list[dict[str, Any]] = []
    for k in range(k_min, k_hi + 1):
        fcm = fuzzy_cmeans_1d(vals, k)
        if fcm is None:
            continue
        _, memberships = fcm
        metrics.append({"k": k, "fpi": fpi(memberships, k), "nce": nce(memberships, k)})
    if not metrics:
        return None

    fpi_k = min(metrics, key=lambda mrec: mrec["fpi"])["k"]
    nce_k = min(metrics, key=lambda mrec: mrec["nce"])["k"]
    return {
        "recommended_k": fpi_k,
        "criterion": "min_FPI (Management Zone Analyst; NCE reported alongside)",
        "fpi_optimal_k": fpi_k,
        "nce_optimal_k": nce_k,
        "agreement": fpi_k == nce_k,
        "k_range": [k_min, k_hi],
        "metrics": metrics,
        "note": (
            "اقتراح إحصائيّ (FPI/NCE على fuzzy c-means) لا قرار نهائيّ — "
            "يبقى بحاجة حكم أغرونوميّ وتحقّق ميدانيّ؛ عند اختلاف FPI/NCE يُرجّح FPI اصطلاحاً."
        ),
    }
