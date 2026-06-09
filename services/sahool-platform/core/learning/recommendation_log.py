"""
core.learning.recommendation_log
================================
سجلّ التوصيات والنتائج — أساس كل تعلّم.

كل توصية تُسجَّل، وعند توفّر النتيجة (الحصاد) تُربط بها. هذا السجلّ هو
ذاكرة المنصة: بدونه لا تعلّم ولا تحسّن. يُغذّي:
  - حلقة المعايرة (calibration_loop)
  - تقييم دقة النموذج (MAPE على held-out)
  - كشف الانحراف (drift) موسماً بعد موسم

كل سجلّ يحمل: التوصية + أساسها (provenance) + درجة الجودة وقتها +
ثم النتيجة الفعلية حين تتوفّر. لا أرقام تُكتب قبل توفّرها.
"""
from __future__ import annotations

import csv
import json
import os
try:
    import fcntl  # POSIX file locking
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path


@dataclass
class RecommendationProvenance:
    """تتبّع التوصية (forensic traceability) — أهمّ من الميزات.

    المراجعتان (2026-05-28) أكّدتا: 'لماذا خرجت هذه التوصية؟' يجب أن
    يُجاب بدقّة بعد 8 أشهر. لا يكفي حفظ القيمة، يجب حفظ النسب الكامل:
      • نسخة نموذج كل محرّك شارك (model_version)
      • مصادر البيانات (weather_source: open-meteo/copernicus/farmonaut)
      • snapshot للمدخلات الحرجة في لحظة التوصية
      • قائمة المحرّكات المشاركة (engines_used)
    """
    model_versions: dict      # {"fao56":"v1", "wofost":"7.2", ...}
    weather_source: str       # "open-meteo" / "copernicus" / "manual"
    weather_data_date: str    # ISO date للقراءة الطقسية المستخدمة
    input_snapshot: dict      # {"ndvi":0.55, "ec":1.2, ...} — قيم اللحظة
    engines_used: list        # ["fao56","fertility","fuzzy",...]
    calibration_set_id: str | None = None   # أيّ مجموعة معايرة استُخدمت
    knowledge_snippets_ids: list | None = None   # KB IDs المُستحضَرة


@dataclass
class RecommendationRecord:
    rec_id: str
    tenant_id: str
    district_id: str
    zone_id: str
    crop: str
    issued_date: str
    recommendation_ar: str
    quality_grade: str           # من validate_observations
    predicted_yield_t_ha: float | None   # null إن قيد المعايرة
    confidence: str
    # filled later when outcome arrives:
    actual_yield_t_ha: float | None = None
    outcome_date: str | None = None
    error_pct: float | None = None       # |actual-predicted|/actual
    # forensic provenance (اختياري للتوافق الخلفي، مُوصى به للتوصيات الجديدة):
    provenance: dict | None = None       # serialized RecommendationProvenance


def log_recommendation(log_path: Path, rec: RecommendationRecord) -> None:
    """Append a recommendation (outcome fields empty until harvest)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    records = load_log(log_path)
    records.append(rec)
    _write(log_path, records)


def record_outcome(
    log_path: Path, rec_id: str, actual_yield: float, outcome_date: str,
) -> bool:
    """Bind an actual harvest result to a prior recommendation.
    يستخدم قفل ملف (POSIX) ليلفّ القراءة+التعديل+الكتابة، فيمنع فقدان
    التحديثات عند الكتابة المتزامنة (التطبيق المتعدّد على نفس الملف)."""
    # قفل على ملف مرافق (.lock) يحمي العملية كاملة من السباق
    lock_path = Path(str(log_path) + ".lock")
    lock_f = open(lock_path, "w")
    try:
        if _HAS_FCNTL:
            fcntl.flock(lock_f, fcntl.LOCK_EX)  # حصري — ينتظر دوره
        records = load_log(log_path)
        found = False
        for r in records:
            if r.rec_id == rec_id:
                r.actual_yield_t_ha = actual_yield
                r.outcome_date = outcome_date
                if r.predicted_yield_t_ha and actual_yield > 0:
                    r.error_pct = round(
                        abs(actual_yield - r.predicted_yield_t_ha) / actual_yield * 100, 1
                    )
                found = True
        if found:
            _write(log_path, records)
        return found
    finally:
        if _HAS_FCNTL:
            fcntl.flock(lock_f, fcntl.LOCK_UN)
        lock_f.close()


def compute_mape(log_path: Path) -> dict:
    """MAPE over records that have BOTH prediction and outcome.

    Honest: reports n, and warns if too few / single-farm."""
    records = load_log(log_path)
    paired = [
        r for r in records
        if r.predicted_yield_t_ha and r.actual_yield_t_ha
    ]
    if not paired:
        return {"mape": None, "n": 0, "note_ar": "لا أزواج توقّع/نتيجة بعد"}
    errs = [
        abs(r.actual_yield_t_ha - r.predicted_yield_t_ha) / r.actual_yield_t_ha
        for r in paired
    ]
    mape = round(sum(errs) / len(errs) * 100, 1)
    farms = len({r.tenant_id for r in paired})
    note = f"MAPE={mape}% على {len(paired)} أزواج، {farms} مزارع"
    if farms < 2:
        note += " ⚠️ مزرعة واحدة — قد يكون متفائلاً (pseudoreplication)"
    return {"mape": mape, "n": len(paired), "n_farms": farms, "note_ar": note}


def load_log(log_path: Path) -> list[RecommendationRecord]:
    if not log_path.exists():
        return []
    out = []
    with open(log_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for k in ("predicted_yield_t_ha", "actual_yield_t_ha", "error_pct"):
                row[k] = float(row[k]) if row.get(k) not in (None, "", "None") else None
            out.append(RecommendationRecord(**row))
    return out


def _write(log_path: Path, records: list[RecommendationRecord]) -> None:
    fields = list(asdict(records[0]).keys()) if records else []
    with open(log_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in records:
            w.writerow(asdict(r))
