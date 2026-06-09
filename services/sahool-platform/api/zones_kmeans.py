"""
api/zones_kmeans.py — تحديد مناطق الإدارة بـk-means على NDVI

خارطة الطريق: المرحلة ٣، البند ١٤.

يأخذ قيم NDVI (أو مؤشّرات أخرى) لخلايا الحقل ويجمّعها إلى ٣ مناطق
(LOW/MEDIUM/HIGH) عبر k-means، مع تصنيف PROBLEM للخلايا منخفضة الثقة أو
المتطرّفة. هذا البديل منخفض التكلفة لمناطق الإدارة عندما لا تتوفّر بيانات
EC أو yield-history (المزارع اليمني الصغير).

المبدأ: human-in-the-loop — يقترح المناطق، والمزارع/المهندس يؤكّد.
يربط النتيجة بـZoneClass في prescriptions.py (LOW/MEDIUM/HIGH/PROBLEM).

⚠ ملاحظة علميّة: NDVI يتشبّع عند الكتلة الحيويّة العالية وحسّاس للتاريخ.
لذا: (أ) نفضّل متوسّط سلسلة زمنيّة لا صورة واحدة، (ب) نَسِم الثقة. هذا ليس
بديلاً عن التحليل المختبري بل دليلاً للفحص.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np


@dataclass
class ZoneCell:
    """خليّة حقل واحدة بقيمتها."""
    cell_id: str
    value: float                  # NDVI متوسّط (أو مؤشّر آخر)
    confidence: float = 1.0       # 0-1 (من confidence_engine لو متاح)


@dataclass
class ZoneAssignment:
    cell_id: str
    zone_class: str               # low|medium|high|problem
    value: float
    cluster_center: float

    def to_dict(self) -> Dict:
        return {
            "cell_id": self.cell_id,
            "zone_class": self.zone_class,
            "value": round(self.value, 4),
            "cluster_center": round(self.cluster_center, 4),
        }


@dataclass
class ZoningResult:
    n_zones: int
    assignments: List[ZoneAssignment]
    zone_centers: Dict[str, float]      # متوسّط NDVI لكلّ منطقة
    zone_counts: Dict[str, int]
    notes_ar: str

    def to_dict(self) -> Dict:
        return {
            "n_zones": self.n_zones,
            "zone_centers": {k: round(v, 4) for k, v in self.zone_centers.items()},
            "zone_counts": self.zone_counts,
            "notes_ar": self.notes_ar,
            "assignments": [a.to_dict() for a in self.assignments],
        }


_MIN_CELLS = 6          # أقلّ من ذلك = لا معنى للتجميع
_LOW_CONFIDENCE = 0.4   # خليّة دون هذه الثقة → PROBLEM


def delineate_zones(
    cells: List[ZoneCell],
    *,
    n_zones: int = 3,
    random_state: int = 42,
) -> ZoningResult:
    """يقسّم خلايا الحقل إلى مناطق عبر k-means على NDVI.

    يرفع ValueError لو الخلايا < 6. يصنّف منخفضة الثقة كـPROBLEM.
    """
    if len(cells) < _MIN_CELLS:
        raise ValueError(f"يلزم ≥{_MIN_CELLS} خليّة للتجميع (وُجد {len(cells)})")
    if n_zones not in (2, 3, 4, 5):
        raise ValueError("n_zones يجب أن يكون بين 2 و5")

    from sklearn.cluster import KMeans

    # افصل منخفضة الثقة (PROBLEM) قبل التجميع
    valid = [c for c in cells if c.confidence >= _LOW_CONFIDENCE]
    problem = [c for c in cells if c.confidence < _LOW_CONFIDENCE]

    assignments: List[ZoneAssignment] = []
    zone_counts: Dict[str, int] = {"low": 0, "medium": 0, "high": 0, "problem": 0}

    # خلايا PROBLEM
    for c in problem:
        assignments.append(ZoneAssignment(c.cell_id, "problem", c.value, c.value))
        zone_counts["problem"] += 1

    zone_centers: Dict[str, float] = {}
    if len(valid) >= n_zones:
        X = np.array([[c.value] for c in valid])
        km = KMeans(n_clusters=n_zones, random_state=random_state, n_init=10)
        labels = km.fit_predict(X)
        centers = km.cluster_centers_.flatten()

        # رتّب الـclusters حسب المركز → low/medium/high
        order = np.argsort(centers)  # الأدنى أوّلاً
        if n_zones == 3:
            label_names = {order[0]: "low", order[1]: "medium", order[2]: "high"}
        elif n_zones == 2:
            label_names = {order[0]: "low", order[1]: "high"}
        else:
            # لأكثر من ٣: low, medium..., high
            names = ["low"] + ["medium"] * (n_zones - 2) + ["high"]
            label_names = {order[i]: names[i] for i in range(n_zones)}

        for c, lbl in zip(valid, labels):
            zname = label_names[lbl]
            assignments.append(ZoneAssignment(c.cell_id, zname, c.value, float(centers[lbl])))
            zone_counts[zname] = zone_counts.get(zname, 0) + 1

        for lbl, zname in label_names.items():
            zone_centers[zname] = float(centers[lbl])
    else:
        # خلايا صالحة قليلة جدّاً — كلّها medium بحذر
        for c in valid:
            assignments.append(ZoneAssignment(c.cell_id, "medium", c.value, c.value))
            zone_counts["medium"] += 1

    notes = (
        f"اقتُرحت {n_zones} مناطق من {len(cells)} خليّة "
        f"({zone_counts['problem']} منخفضة الثقة → problem). "
        "هذا اقتراح للفحص الميداني — يؤكّده المزارع/المهندس قبل أيّ قرار. "
        "ملاحظة: NDVI قد يتشبّع عند الكتلة العالية؛ يُفضّل متوسّط سلسلة زمنيّة."
    )

    return ZoningResult(
        n_zones=n_zones, assignments=assignments,
        zone_centers=zone_centers, zone_counts=zone_counts, notes_ar=notes,
    )
