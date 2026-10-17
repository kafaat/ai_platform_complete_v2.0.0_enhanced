"""PARALLEL-TAW-AND-KC-TABLES-DISAGREE-01 — مصدرٌ واحد لـTAW ولـKc (شاهد red→green).

**العطل المقيس على origin/main @ 0e5281614:** جداول متوازية متعارضة يقرؤها مستهلكون مختلفون
للحقل نفسه:

* TAW (مم/م): ``api/soil_water._TAW_MM_PER_M`` يعطي loam 175 وsilt_loam 200، بينما المحرّك
  ``core/engines/fao56._THETA_FC_WP_BY_TEXTURE`` يعطي 1000·(θFC − θWP) = 150 و170.
  (نصّ الفجوة ذكر «silt loam 175 مقابل 150» — المقيس 200 مقابل 170؛ 175 مقابل 150 هو loam.)
  وجدولٌ ثالث في ``api/soil_moisture_advisor._SOIL_PARAMS`` (NRCCA: loam θFC 0.40/θWP 0.125).
  وإملاء القوام نفسه غيّر الرقم: ``theta_fc_wp_for_texture("sandy_loam")`` سقط صامتاً إلى loam.
* Kc: ``api/water_balance.KC_BY_CROP_STAGE`` (maize initial 0.40) مقابل بطاقة المحصول (0.30)،
  ومنحنيات عامّة مكرّرة في water_balance/season_simulation/weather_advice/routers/crop_twin
  (الأخيرة تخالف الباقي: development 0.75، late 0.50).

**قرار المالك (2026-10-15):** بطاقة المحصول + FAO-56 هما المصدر الوحيد، وتُحذف النسخ.
هذا الملفّ يثبت: (أ) كلّ مستهلك TAW == FAO-56 لكلّ قوام بالإملاءين؛ (ب) كلّ مستهلك Kc ==
البطاقة لكلّ بطاقة؛ (ج) القيم المسمّاة في الفجوة؛ (د) غياب جدول حرفيّ لـKc/TAW خارج المصادر
القانونيّة في شيفرة الإنتاج تحت ``services/`` و``shared/`` (فحص AST بقائمة سماح مُعلَّلة).

التوقّعات تُشتقّ من ``crop_kc_profile`` و``_THETA_FC_WP_BY_TEXTURE`` (موجودان على main) لا من
المُوصِلات الجديدة، كي يحمرّ الشاهد على main بتأكيدٍ لا بخطأ استيراد.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_PLATFORM = _ROOT / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api.season_simulation import _seasonal_water_need  # noqa: E402
from api.soil_moisture_advisor import compute_rwc, irrigation_amount_mm  # noqa: E402
from api.soil_water import soil_water_params  # noqa: E402
from api.water_balance import WeatherInput, water_balance  # noqa: E402
from api.weather_advice import resolve_kc  # noqa: E402
from core.engines.fao56 import (  # noqa: E402
    _THETA_FC_WP_BY_TEXTURE,
    taw_from_root_depth,
    theta_fc_wp_for_texture,
)
from core.season_phenology import crop_kc_profile  # noqa: E402

_STAGES = ("initial", "development", "mid", "late")
_CARD_IDS = sorted(
    p.stem for p in (_PLATFORM / "core" / "crop_cards").glob("*.yaml") if not p.stem.startswith("_")
)
_TEXTURES = sorted(t for t in _THETA_FC_WP_BY_TEXTURE if t not in {"sandy", "mixed"})
_W = WeatherInput(t_min_c=15.0, t_max_c=30.0)


def _fao56_taw_per_m(texture: str) -> float:
    fc, wp = _THETA_FC_WP_BY_TEXTURE[texture]
    return round(1000.0 * (fc - wp), 1)


def _card_stage_kc(crop_id: str) -> dict[str, float]:
    """الإسقاط القانونيّ من البطاقة: initial=Kc_ini · development=(ini+mid)/2 · mid · late=Kc_end."""
    prof = crop_kc_profile(crop_id)
    assert prof is not None, f"{crop_id}: بطاقة بلا كتلة kc"
    ini, mid, end = prof.kc_initial, prof.kc_mid, prof.kc_end
    return {"initial": ini, "development": round((ini + mid) / 2.0, 3), "mid": mid, "late": end}


# ── (أ) TAW: كلّ مستهلك == FAO-56 لكلّ قوام، بالإملاءين ──────────────────────────────


def test_texture_universe_is_measured():
    # يحرس أنّ التوسيط أدناه ليس فارغاً (لا أخضر صامت).
    assert len(_TEXTURES) >= 9, _TEXTURES
    assert len(_CARD_IDS) >= 30, _CARD_IDS


@pytest.mark.parametrize("texture", _TEXTURES)
def test_soil_water_taw_equals_fao56_for_both_spellings(texture):
    expected = _fao56_taw_per_m(texture)
    for spelling in {texture, texture.replace(" ", "_")}:
        got = soil_water_params(spelling, root_depth_m=1.0)
        assert got["taw_mm_per_m"] == pytest.approx(expected), (spelling, got["taw_mm_per_m"])
        assert got["texture_known"] is True, spelling


@pytest.mark.parametrize("texture", _TEXTURES)
def test_fao56_theta_lookup_is_spelling_insensitive(texture):
    # كان "sandy_loam" يسقط صامتاً إلى loam لأنّ مفاتيح الجدول بمسافة.
    canonical = _THETA_FC_WP_BY_TEXTURE[texture]
    underscored = texture.replace(" ", "_")
    assert theta_fc_wp_for_texture(underscored) == canonical, underscored
    assert taw_from_root_depth(1.0, underscored) == pytest.approx(_fao56_taw_per_m(texture))


@pytest.mark.parametrize("soil_type", ["sand", "loam", "clay"])
def test_soil_moisture_advisor_theta_equals_fao56(soil_type):
    fc, wp = _THETA_FC_WP_BY_TEXTURE[soil_type]
    out = compute_rwc(0.2, soil_type)
    assert (out["theta_fc"], out["theta_wp"]) == (round(fc, 3), round(wp, 3)), out
    amount = irrigation_amount_mm(0.0, soil_type, root_depth_m=1.0)
    assert amount["irrigation_mm"] == pytest.approx(round(fc * 1000.0, 1))


def test_gap_named_textures_measured_values():
    # loam: 175 (جدول موازٍ) ⇒ 150؛ silt_loam: 200 ⇒ 170 (لا 175 كما ذكر نصّ الفجوة).
    assert soil_water_params("loam", 1.0)["taw_mm_per_m"] == 150.0
    assert soil_water_params("silt_loam", 1.0)["taw_mm_per_m"] == 170.0
    assert soil_water_params("طميي", 1.0)["taw_mm_per_m"] == 150.0  # المرادف العربيّ ⇒ loam


def test_texture_absent_from_fao56_is_flagged_not_invented():
    # silty_clay_loam لا يوجد في جدول FAO-56 القانونيّ؛ كان الجدول الموازي يخترع له 175.
    out = soil_water_params("silty_clay_loam", 1.0)
    assert out["texture_known"] is False, out
    assert out["taw_mm_per_m"] == _fao56_taw_per_m("loam")
    assert any("نسيج غير معروف" in w for w in out["warnings_ar"]), out["warnings_ar"]


# ── (ب) Kc: كلّ مستهلك == البطاقة لكلّ بطاقة ─────────────────────────────────────────


@pytest.mark.parametrize("crop_id", _CARD_IDS)
def test_water_balance_kc_equals_card(crop_id):
    expected = _card_stage_kc(crop_id)
    for stage in _STAGES:
        r = water_balance(_W, crop_id, stage, et0_mm=5.0)
        assert r.kc == pytest.approx(expected[stage]), (crop_id, stage, r.kc)
        assert r.kc_source_ar.startswith("محصول"), (crop_id, r.kc_source_ar)


@pytest.mark.parametrize("crop_id", _CARD_IDS)
def test_weather_advice_kc_equals_card(crop_id):
    expected = _card_stage_kc(crop_id)
    for stage in _STAGES:
        kc, known, _ = resolve_kc(crop_id, stage)
        assert known is True, crop_id
        assert kc == pytest.approx(expected[stage]), (crop_id, stage, kc)


@pytest.mark.parametrize("crop_id", _CARD_IDS)
def test_season_simulation_seasonal_need_uses_card(crop_id):
    # ١٠ أيّام × ET0=1 ⇒ التوزيع initial 2 · development 3 · mid 3 · late 2.
    k = _card_stage_kc(crop_id)
    expected = 2 * k["initial"] + 3 * k["development"] + 3 * k["mid"] + 2 * k["late"]
    assert _seasonal_water_need(crop_id, [1.0] * 10) == pytest.approx(expected), crop_id


def test_gap_named_crop_maize_initial_is_card_value():
    assert _card_stage_kc("maize")["initial"] == 0.30
    assert water_balance(_W, "maize", "initial", et0_mm=5.0).kc == pytest.approx(0.30)
    assert resolve_kc("maize", "initial")[0] == pytest.approx(0.30)


def test_legacy_dates_key_resolves_to_date_palm_card():
    expected = _card_stage_kc("date_palm")
    for stage in _STAGES:
        assert water_balance(_W, "dates", stage, et0_mm=5.0).kc == pytest.approx(expected[stage])
        assert resolve_kc("dates", stage)[0] == pytest.approx(expected[stage])


def test_unknown_crop_generic_curve_is_one_curve_everywhere():
    from core.season_phenology import GENERIC_STAGE_KC

    for stage in _STAGES:
        wb = water_balance(_W, "dragonfruit", stage, et0_mm=5.0)
        assert wb.kc == GENERIC_STAGE_KC[stage], stage
        assert wb.kc_source_ar.startswith("عامّ"), wb.kc_source_ar
        kc, known, _ = resolve_kc("dragonfruit", stage)
        assert (kc, known) == (GENERIC_STAGE_KC[stage], False), stage
    g = GENERIC_STAGE_KC
    expected = 2 * g["initial"] + 3 * g["development"] + 3 * g["mid"] + 2 * g["late"]
    assert _seasonal_water_need("dragonfruit", [1.0] * 10) == pytest.approx(expected)


# ── المستهلك الرابع: routers/crop_twin (compose) ──────────────────────────────────────


@pytest.fixture
def _crop_twin(monkeypatch):
    import api.main  # noqa: F401 — تهيئة api.main قبل الموجِّه (دورة استيراد)
    import api.routers.crop_twin as mod

    async def _fake_gdd(*, daily_t_min, daily_t_max, base_c, upper_cutoff_c, method, **_kw):
        daily = [
            max(0.0, (mx + mn) / 2.0 - base_c)
            for mn, mx in zip(daily_t_min, daily_t_max, strict=True)
        ]
        return {
            "product": "gdd",
            "calculation_version": "gdd/daily/1.0.0",
            "daily_gdd": daily,
            "accumulated_gdd": sum(daily),
            "thresholds_used": {
                "base_c": base_c,
                "upper_cutoff_c": upper_cutoff_c,
                "method": method,
            },
            "valid_period": {"days": len(daily)},
            "limitations": [],
            "derived_from": "canonical_daily_weather_series",
            "gdd_lineage_id": "gddseq/fake-taw-kc",
            "contributing_state_ids": [f"snap-{i}" for i in range(len(daily))],
            "series_quality_status": "validated",
        }

    monkeypatch.setattr(mod, "get_gdd_product", _fake_gdd)
    from core.canonical_schemas import UserRole, UserSchema

    user = UserSchema(
        user_id="u-taw-kc",
        tenant_id="00000000-0000-0000-0000-000000000002",
        role=UserRole.OWNER,
        name_ar="شاهد",
    )

    async def _compose(crop: str, stage: str, texture: str) -> dict:
        req = mod.CropTwinComposeRequest(
            crop=crop,
            stage=stage,
            forecast=[mod.ComposeForecastDay(t_min_c=10.0, t_max_c=30.0, et0_mm=6.0)] * 5,
            soil=mod.ComposeSoil(texture=texture, root_depth_m=1.0),
        )
        return await mod.compose_crop_twin(req=req, user=user)

    return _compose


@pytest.mark.parametrize("crop", ["maize", "wheat", "dates"])
async def test_crop_twin_compose_kc_equals_card(_crop_twin, crop):
    expected = _card_stage_kc("date_palm" if crop == "dates" else crop)
    for stage in _STAGES:
        out = await _crop_twin(crop, stage, "loam")
        assert out["dynamic_kc"] == pytest.approx(expected[stage]), (crop, stage)


async def test_crop_twin_compose_generic_curve_and_taw(_crop_twin):
    from core.season_phenology import GENERIC_STAGE_KC

    for stage in _STAGES:
        out = await _crop_twin("dragonfruit", stage, "silt_loam")
        assert out["dynamic_kc"] == pytest.approx(GENERIC_STAGE_KC[stage]), stage
        assert out["water_state"]["taw_mm"] == pytest.approx(_fao56_taw_per_m("silt loam"))


# ── (د) بنيويّ: لا جدول Kc/TAW حرفيّ خارج المصادر القانونيّة ─────────────────────────

_SCAN_ROOTS = ("services", "shared")
_TEXTURE_KEYS = {
    "sand",
    "loamy sand",
    "sandy loam",
    "loam",
    "silt loam",
    "silt",
    "silty clay loam",
    "sandy clay loam",
    "clay loam",
    "sandy clay",
    "silty clay",
    "clay",
}
_STAGE_KEYS = set(_STAGES)
_KC_FIELD_KEYS = {"kc_ini", "kc_initial", "kc_dev", "kc_mid", "kc_end", "kc_late"}
_WATER_FIELD_KEYS = {
    "fc",
    "wp",
    "taw",
    "awc",
    "theta_fc",
    "theta_wp",
    "field_capacity",
    "wilting_point",
    "taw_mm_per_m",
}

# (مسار، المالك) ⇒ السبب. المالك = اسم الإسناد المحيط بالقاموس، أو <inline:دالّة>.
_ALLOWLIST: dict[tuple[str, str], str] = {
    (
        "services/sahool-platform/core/engines/fao56.py",
        "_THETA_FC_WP_BY_TEXTURE",
    ): "المصدر القانونيّ لـθFC/θWP وTAW = 1000·(θFC − θWP) (FAO-56 Table 19)",
    (
        "services/sahool-platform/core/engines/fao56.py",
        "_TEW_REW_BY_TEXTURE",
    ): "TEW/REW لطبقة التبخّر السطحيّة Ze=0.10م (FAO-56 Ch.7) — كمّيّة غير TAW، في الملفّ القانونيّ",
    (
        "services/sahool-platform/core/season_phenology.py",
        "GENERIC_STAGE_KC",
    ): "المنحنى العامّ القانونيّ الوحيد للمحاصيل بلا بطاقة",
    (
        "services/sahool-platform/api/main.py",
        "_STAGE_EXPECTED_NDVI",
    ): "خطّ أساس NDVI حسب الطور — ليس Kc",
    (
        "services/sahool-platform/api/nutrient_4r.py",
        "_UPTAKE_FRACTIONS",
    ): "كسور امتصاص المغذّيات حسب الطور — ليست Kc",
    (
        "shared/wofost/engine.py",
        "CROP_PARAMS",
    ): "قرار المالك: نسخة WOFOST الموازية تبقى (نقلها يعكس اتّجاه shared→platform) — الفجوة PARTIAL",
    (
        "shared/wofost/engine.py",
        "SOIL_PARAMS",
    ): "قرار المالك: نسخة WOFOST الموازية تبقى (نقلها يعكس اتّجاه shared→platform) — الفجوة PARTIAL",
}


def _is_num(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        node = node.operand
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    )


def _str_keys(d: ast.Dict) -> list[tuple[str, ast.AST]]:
    return [
        (k.value, v)
        for k, v in zip(d.keys, d.values, strict=True)
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
    ]


def _table_kind(d: ast.Dict) -> str | None:
    """نوع الجدول الحرفيّ الذي يمثّله القاموس، أو None."""
    pairs = _str_keys(d)
    norm = [(" ".join(k.lower().replace("_", " ").replace("-", " ").split()), v) for k, v in pairs]
    tex = [(k, v) for k, v in norm if k in _TEXTURE_KEYS]
    if len(tex) >= 3:
        for _, v in tex:
            if _is_num(v) or (isinstance(v, ast.Tuple) and v.elts and all(map(_is_num, v.elts))):
                return "TAW/θ"
            if isinstance(v, ast.Dict) and any(
                k.lower() in _WATER_FIELD_KEYS and _is_num(iv) for k, iv in _str_keys(v)
            ):
                return "TAW/θ"
    stages = [v for k, v in pairs if k in _STAGE_KEYS]
    if len(stages) >= 3 and sum(map(_is_num, stages)) >= 3:
        return "Kc-stage"
    if any(k.lower() in _KC_FIELD_KEYS and _is_num(v) for k, v in pairs):
        return "Kc-field"
    return None


def _owner(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, ast.Assign) and cur.targets:
            t = cur.targets[0]
            return t.id if isinstance(t, ast.Name) else ast.unparse(t)
        if isinstance(cur, ast.AnnAssign):
            return ast.unparse(cur.target)
        if isinstance(cur, ast.FunctionDef | ast.AsyncFunctionDef):
            return f"<inline:{cur.name}>"
        cur = parents.get(cur)
    return "<module>"


def _detect(source: str) -> set[tuple[str, str]]:
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            kind = _table_kind(node)
            if kind:
                found.add((_owner(node, parents), kind))
    return found


_PREFILTER = re.compile(r"""["'](?:development|late|kc_|[a-z_ -]*(?:loam|sand|clay|silt))""", re.I)
_SKIP_DIRS = {"tests", "node_modules", ".venv", "venv", "__pycache__", "migrations", ".git"}


def _prod_files(root: Path):
    """ملفّات بايثون الإنتاجيّة (تُقلَّم مجلّدات الاختبار/التبعيّات أثناء المشي لا بعده)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(".py") and not name.startswith("test_") and name != "conftest.py":
                yield Path(dirpath) / name


def _scan() -> dict[tuple[str, str], str]:
    hits: dict[tuple[str, str], str] = {}
    for root in _SCAN_ROOTS:
        for path in _prod_files(_ROOT / root):
            rel = path.relative_to(_ROOT)
            try:
                source = path.read_text(encoding="utf-8")
                # ترشيح نصّيّ سليم قبل AST: كلّ جدول يكشفه ``_table_kind`` يحمل مفتاحاً نصّيّاً
                # يطابق هذا النمط (مرحلتان على الأقلّ من development/late، أو kc_*، أو قوام).
                if not _PREFILTER.search(source):
                    continue
                found = _detect(source)
            except (SyntaxError, UnicodeDecodeError):
                continue
            for owner, kind in found:
                hits[(rel.as_posix(), owner)] = kind
    return hits


@pytest.fixture(scope="module")
def _hits() -> dict[tuple[str, str], str]:
    return _scan()


def test_no_literal_kc_or_taw_table_outside_canonical_sources(_hits):
    offenders = {k: v for k, v in _hits.items() if k not in _ALLOWLIST}
    assert not offenders, (
        "جدول Kc/TAW حرفيّ خارج المصدر القانونيّ (بطاقة المحصول عبر season_phenology / "
        "core.engines.fao56) — اقرأ منهما بدل نسخة موازية: "
        + "; ".join(f"{p}::{o} [{k}]" for (p, o), k in sorted(offenders.items()))
    )


def test_allowlist_has_no_stale_entries(_hits):
    stale = sorted(k for k in _ALLOWLIST if k not in _hits)
    assert not stale, f"مدخلات سماح لم يعد الكاشف يجدها — احذفها: {stale}"


def test_allowlist_entries_carry_reasons():
    assert all(reason.strip() for reason in _ALLOWLIST.values())


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('T = {"sand": 65.0, "loam": 175.0, "clay": 135.0}', {("T", "TAW/θ")}),
        (
            'T = {"sandy_loam": (0.18, 0.07), "loam": (0.25, 0.1), "silt": (0.3, 0.12)}',
            {("T", "TAW/θ")},
        ),
        (
            'S = {"sand": {"theta_fc": 0.2}, "loam": {"theta_fc": 0.4}, "clay": {"theta_fc": 0.5}}',
            {("S", "TAW/θ")},
        ),
        (
            'K = {"wheat": {"initial": 0.4, "development": 0.75, "mid": 1.15, "late": 0.4}}',
            {("K", "Kc-stage")},
        ),
        (
            'def f(c):\n    return M.get(c, {"initial": 0.4, "development": 0.8, "mid": 1.1})',
            {("<inline:f>", "Kc-stage")},
        ),
        ('P = {"x": {"tbase": 5.0, "kc_mid": 1.15}}', {("P", "Kc-field")}),
        # سلبيّات: مرادفات نصّيّة، مرحلتان فقط، خصائص عرض بلا θFC/θWP، Kc غير حرفيّ.
        ('A = {"sand": "sand", "loam": "loam", "clay": "clay"}', set()),
        ('B = {"initial": 0.4, "mid": 1.1}', set()),
        (
            'D = {"sand": {"theta_s": 0.33}, "loam": {"theta_s": 0.47}, "clay": {"theta_s": 0.55}}',
            set(),
        ),
        ('R = {"kc_ini": s.kc_ini, "kc_mid": s.kc_mid}', set()),
    ],
)
def test_detector_self_test(source, expected):
    assert _detect(source) == expected
