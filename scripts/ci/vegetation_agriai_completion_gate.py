#!/usr/bin/env python3
"""Structural guard for the Vegetation → AgriAI production contract."""

import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا السكربت عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نتيجته (UnicodeEncodeError) ⇒ خروجٌ بغير صفر يُقرَأ حجباً وهو قد مرّ.
# **عند التحميل لا داخل `main()`** — بعضُ المخرَج يُطبَع من جسد الوحدة قبل أيّ نداء.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
checks = {
    ROOT / "services/vegetation-analysis-service/vegetation_contracts.py": [
        "quality_gate",
        "build_snapshot",
        "derive_lai_from_ndvi",
    ],
    ROOT / "services/vegetation-analysis-service/vegetation_runtime.py": [
        "VEGETATION_REAL_ONLY",
        "_real_timeseries_from_raster",
        "vegetation_snapshot",
    ],
    ROOT / "services/agriai-engine/agronomic_context.py": [
        "REQUIRED_CONTEXT",
        "validate_context",
        "temporal_integrity",
    ],
    ROOT / "services/agriai-engine/main.py": [
        "AGRIAI_STRICT_CONTEXT",
        "agronomic_context_validation",
        "vegetation_snapshot_hash",
    ],
}
errors = []
for path, tokens in checks.items():
    if not path.exists():
        errors.append(f"missing {path.relative_to(ROOT)}")
        continue
    text = path.read_text(encoding="utf-8")
    for token in tokens:
        if token not in text:
            errors.append(f"{path.relative_to(ROOT)} missing {token}")
if errors:
    print("FAIL")
    print("\n".join(errors))
    sys.exit(1)
print("PASS vegetation→agriai completion gate")
