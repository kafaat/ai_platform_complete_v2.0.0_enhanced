#!/usr/bin/env python3
"""محمِّل الحدود الإداريّة اليمنيّة (A7) — أداة مشغِّل موثَّقة يملكها gis-workflow-service.

يقرأ ملفّي HDX/OCHA (admin1 محافظات + admin2 مديريّات، GeoJSON محلّيّ) ويُدرِجهما في المرجع المشترك
``admin_boundaries`` مع صفّ provenance لكلّ مستوى. **قناة واحدة: كلّ البيانات تدخل بالمُحمِّل الموثَّق أو
لا تدخل** (لا seed في git — يُجمّد لقطة تنفصل عن المصدر وتتقادم صامتاً).

**مرجعيّة إلزاميّة:** يلتقط ``license_title``/``license_url``/``dataset_version``/``retrieved_at`` كما لحظة
الجلب من صفحة HDX (رخصة OCHA قد تتغيّر بين الإصدارات — تظهر كتغيّر في السجلّ لا مفاجأة قانونيّة).

**سلامة الهندسة (شرط المالك):** كلّ هندسة تُفحَص بـ``ST_IsValid``؛ غير الصالحة تُصلَّح بـ``ST_MakeValid``
ويُسجَّل عددها في ``invalid_geometry_fixed`` (شفافيّة). ما يتعذّر إصلاحه ⇒ يُرفَض (trigger v200 يعضّ أيضاً).

تشغيل (مشغِّل، صلاحية إداريّة — لا sahool_app المقيَّد):
    python load_admin_boundaries.py --db "$ADMIN_DATABASE_URL" \
        --admin1 yem_admbnda_adm1.geojson --admin2 yem_admbnda_adm2.geojson \
        --source "HDX/OCHA Yemen COD-AB" --dataset-version 2024.1 \
        --license-title "Creative Commons Attribution for Intergov. Organisations" \
        --license-url "https://data.humdata.org/faqs/licenses" \
        --url "https://data.humdata.org/dataset/cod-ab-yem"
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

# قيم افتراضيّة لمفاتيح خصائص HDX COD-AB القياسيّة (تُعدَّل عبر الوسائط إن اختلف الإصدار).
_PCODE_KEYS = ("ADM{lvl}_PCODE", "admin{lvl}Pcode", "pcode")
_NAME_AR_KEYS = ("ADM{lvl}_AR", "admin{lvl}Name_ar", "name_ar")
_NAME_EN_KEYS = ("ADM{lvl}_EN", "admin{lvl}Name_en", "name_en")
_PARENT_KEYS = ("ADM1_PCODE", "admin1Pcode")


def _first(props: dict, keys, lvl: int) -> str | None:
    for k in keys:
        v = props.get(k.format(lvl=lvl))
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _features(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    feats = doc.get("features", []) if isinstance(doc, dict) else []
    if not feats:
        raise SystemExit(f"no features in {path}")
    return feats


def _insert_source(cur, *, level, args, feature_count, fixed) -> int:
    cur.execute(
        "INSERT INTO admin_boundaries_source "
        "(admin_level, source, dataset_version, license_title, license_url, url, retrieved_at, "
        " feature_count, invalid_geometry_fixed) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING source_id",
        (
            level,
            args.source,
            args.dataset_version,
            args.license_title,
            args.license_url,
            args.url,
            args.retrieved_at,
            feature_count,
            fixed,
        ),
    )
    return cur.fetchone()[0]


def _load_level(cur, *, level: int, path: str, args) -> tuple[int, int]:
    """يُدرِج مستوى إداريّاً؛ يعيد (عدد الصفوف، عدد الهندسات المُصلَّحة)."""
    feats = _features(path)
    fixed = 0
    source_id = _insert_source(cur, level=level, args=args, feature_count=len(feats), fixed=0)
    for feat in feats:
        props = feat.get("properties", {}) or {}
        geom_json = json.dumps(feat.get("geometry"))
        pcode = _first(props, _PCODE_KEYS, level)
        if not pcode:
            raise SystemExit(f"feature missing pcode at admin{level}")
        parent = _first(props, _PARENT_KEYS, 1) if level == 2 else None
        # سلامة الهندسة: صالحة كما هي، وإلّا ST_MakeValid (+ عدّ). MultiPolygon مضمون بـST_Multi.
        cur.execute("SELECT ST_IsValid(ST_GeomFromGeoJSON(%s))", (geom_json,))
        valid = cur.fetchone()[0]
        if not valid:
            fixed += 1
        cur.execute(
            "INSERT INTO admin_boundaries "
            "(admin_level, admin_code, admin_name_ar, admin_name_en, parent_code, geom, source_id) "
            "VALUES (%s,%s,%s,%s,%s, "
            "  ST_Multi(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))), %s) "
            "ON CONFLICT (admin_level, admin_code) DO UPDATE SET "
            "  admin_name_ar=EXCLUDED.admin_name_ar, admin_name_en=EXCLUDED.admin_name_en, "
            "  parent_code=EXCLUDED.parent_code, geom=EXCLUDED.geom, source_id=EXCLUDED.source_id",
            (
                level,
                pcode,
                _first(props, _NAME_AR_KEYS, level),
                _first(props, _NAME_EN_KEYS, level),
                parent,
                geom_json,
                source_id,
            ),
        )
    cur.execute(
        "UPDATE admin_boundaries_source SET invalid_geometry_fixed=%s WHERE source_id=%s",
        (fixed, source_id),
    )
    return len(feats), fixed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="ADMIN database URL (not sahool_app)")
    ap.add_argument("--admin1", required=True)
    ap.add_argument("--admin2", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--dataset-version", required=True, dest="dataset_version")
    ap.add_argument("--license-title", required=True, dest="license_title")
    ap.add_argument("--license-url", required=True, dest="license_url")
    ap.add_argument("--url", required=True)
    args = ap.parse_args()
    args.retrieved_at = datetime.now(UTC)

    import psycopg2  # أداة مشغِّل — لا تبعيّة runtime للخدمة

    conn = psycopg2.connect(args.db)
    try:
        with conn, conn.cursor() as cur:
            n1, f1 = _load_level(cur, level=1, path=args.admin1, args=args)
            n2, f2 = _load_level(cur, level=2, path=args.admin2, args=args)
        print(f"loaded admin1={n1} (fixed {f1}) · admin2={n2} (fixed {f2})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
