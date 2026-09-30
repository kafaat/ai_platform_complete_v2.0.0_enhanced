"""PCSE/WOFOST الحقيقيّ دون شبكة عبر ``/v1/simulate`` — يعمل حين تُركَّب pcse، ويُتخطّى دونها **صراحةً**.

كان المسار لا يعمل طرفاً لطرف (مقيس 2026-09-29، pcse 6.0.13): معاملات المحصول تُجلَب من GitHub وقت
التشغيل (``PCSEError`` دون شبكة)، ومع الشبكة يسقط ``AgroManager`` على dict خامّ. هنا يُشغَّل الموسم كاملاً
عبر تطبيق FastAPI الحقيقيّ و**أيّ محاولة اتّصال خارجيّة تُسجَّل وتُفشِل الاختبار**، ثمّ يُقارَن المُخرَج
بتشغيلٍ مرجعيّ لا يمرّ بشيفرة SAHOOL: قارئ CSV للطقس وقارئ CABO للتربة وقارئ YAML للإدارة — كلّها من
PCSE نفسها. التطابق يثبت الوحدات والبنى، لا مجرّد أنّ التشغيل لم ينهَر.

الطقس هنا **اصطناعيّ حتميّ** (دوالّ جيبيّة بموقعٍ يشبه المرتفعات اليمنيّة) لأنّ الغاية مطابقة الغراء
لقرّاء PCSE، لا ادّعاء غلّةٍ لحقلٍ حقيقيّ. CI الوحدة لا يُركّب pcse ⇒ يُتخطّى هذا الملفّ، والبُناة
مغطّاة هناك في ``test_wofost_pcse_input_builders.py``.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import textwrap
from datetime import date, timedelta

import pytest

_PCSE_INSTALLED = importlib.util.find_spec("pcse") is not None
pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        not _PCSE_INSTALLED,
        reason=(
            "pcse غير مُركَّبة (تبعيّة agriai اختياريّة؛ CI الوحدة لا يُركّبها) — التشغيل الحقيقيّ "
            "يُتخطّى هنا، والبُناة مغطّاة بلا pcse في test_wofost_pcse_input_builders.py"
        ),
    ),
]

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SVC = os.path.join(ROOT, "services", "agriai-engine")
if _SVC not in sys.path:
    sys.path.insert(0, _SVC)

import pcse_inputs as pi  # noqa: E402
import sim_crop_registry  # noqa: E402
import wofost_adapter as wa  # noqa: E402

TOKEN = "pcse-offline-token"
SITE = {"latitude": 15.35, "longitude": 44.21, "elevation_m": 2250.0}
SOW = date(2025, 7, 15)
LAST = date(2025, 12, 31)


def _synthetic_days(start: date, end: date, *, wind_key: str = "wind_2m_m_s") -> list[dict]:
    """سلسلة اصطناعيّة حتميّة (قيمٌ مُقرَّبة كي تعبر نصّ CSV كما هي)."""
    days = []
    for i in range((end - start).days + 1):
        phase = 2.0 * math.pi * i / 365.0
        tmin = round(9.0 + 3.0 * math.sin(phase), 1)
        days.append(
            {
                "date": (start + timedelta(days=i)).isoformat(),
                "tmin": tmin,
                "tmax": round(tmin + 13.0 + 2.0 * math.cos(3.0 * phase), 1),
                "rain_mm": 8.0 if i % 6 == 0 else 0.0,
                "solar_radiation_mj_m2": round(21.0 + 3.0 * math.sin(phase + 0.5), 2),
                "vapour_pressure_hpa": round(11.0 + 2.0 * math.cos(phase), 2),
                wind_key: round(2.5 + 0.5 * math.sin(2.0 * phase), 2),
            }
        )
    return days


@pytest.fixture(scope="module")
def pcse_home(tmp_path_factory):
    """``import pcse`` يكتب ``~/.pcse`` (قاعدة عرض 2.7 ميغابايت + إعدادات) — بيتٌ مؤقّت لا بيت المستخدم."""
    home = tmp_path_factory.mktemp("pcse_home")
    saved = {k: os.environ.get(k) for k in ("HOME", "USER")}
    os.environ.update(HOME=str(home), USER="pcse-test")
    yield home
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(scope="module")
def pcse_ns(pcse_home):
    # الاستيراد عبر المُحوِّل وحده (يُعيد سجلّات المُضيف)؛ استيرادات pcse اللاحقة هنا بلا أثر جانبيّ.
    return wa._load_pcse()


@pytest.fixture
def offline(monkeypatch):
    """كلّ ``connect`` إلى IPv4/IPv6 يُسجَّل ويُرفَض: التشغيل يجب ألّا يحاول الشبكة أصلاً."""
    attempts: list = []
    real_connect = socket.socket.connect

    def guarded(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            attempts.append(address)
            raise OSError(f"network disabled by test: {address!r}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    return attempts


@pytest.fixture
def client(monkeypatch, pcse_ns):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    monkeypatch.setenv("SIM_PCSE_ENABLED", "1")
    monkeypatch.setenv("AGRIAI_PRODUCTION_MODE", "0")
    spec = importlib.util.spec_from_file_location(
        "agriai_main_pcse_offline", os.path.join(_SVC, "main.py")
    )
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    return TestClient(main.app)


def _post(client, body):
    return client.post("/v1/simulate", json=body, headers={"x-agent-token": TOKEN})


def _csv_weather(tmp_path, days, *, angstrom=(0.29, 0.49)):
    """نفس السلسلة بصيغة ``CSVWeatherDataProvider`` ووحداته (IRRAD kJ · VAP kPa · RAIN mm)."""
    lines = [
        "## Site Characteristics",
        "Country     = 'Synthetic'",
        "Station     = 'SAHOOL equivalence test'",
        "Description = 'deterministic synthetic series'",
        "Source      = 'tests_v9'",
        "Contact     = 'none'",
        f"Longitude = {SITE['longitude']}; Latitude = {SITE['latitude']}; Elevation = {SITE['elevation_m']};"
        f" AngstromA = {angstrom[0]}; AngstromB = {angstrom[1]}; HasSunshine = False",
        "## Daily weather observations (missing values are NaN)",
        "DAY,IRRAD,TMIN,TMAX,VAP,WIND,RAIN,SNOWDEPTH",
    ]
    for d in days:
        lines.append(
            ",".join(
                [
                    d["date"].replace("-", ""),
                    repr(d["solar_radiation_mj_m2"] * 1000.0),
                    repr(d["tmin"]),
                    repr(d["tmax"]),
                    repr(d["vapour_pressure_hpa"] / 10.0),
                    repr(d["wind_2m_m_s"]),
                    repr(d["rain_mm"]),
                    "NaN",
                ]
            )
        )
    path = tmp_path / "synthetic_weather.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    from pcse.input import CSVWeatherDataProvider

    return CSVWeatherDataProvider(str(path), force_reload=True)


def _reference_run(tmp_path, crop_name, weather_provider, agro_yaml, *, wav_cm=None):
    """تشغيلٌ بقرّاء PCSE وحدها: YAMLCropDataProvider الأصليّ · CABOFileReader · YAMLAgroManagementReader."""
    from pcse.base import ParameterProvider
    from pcse.input import (
        CABOFileReader,
        WOFOST72SiteDataProvider,
        YAMLAgroManagementReader,
        YAMLCropDataProvider,
    )
    from pcse.models import Wofost72_WLP_CWB

    crop_copy = tmp_path / "crop_copy"  # المُنشئ الأصليّ يكتب pickle في دليله — نسخة لا الأصل
    shutil.copytree(pi.CROP_DIR, crop_copy, dirs_exist_ok=True)
    cabo = CABOFileReader(pi.DEFAULT_SOIL_FILE)
    soil = {k: cabo[k] for k, _ in pi.SOIL_FIELDS}
    wav = (soil["SMFCF"] - soil["SMW"]) * soil["RDMSOL"] if wav_cm is None else wav_cm
    site = WOFOST72SiteDataProvider(WAV=wav, SMLIM=soil["SMFCF"])
    agro_file = tmp_path / f"{crop_name}.agro.yaml"
    agro_file.write_text(textwrap.dedent(agro_yaml), encoding="utf-8")
    model = Wofost72_WLP_CWB(
        ParameterProvider(
            cropdata=YAMLCropDataProvider(model=Wofost72_WLP_CWB, fpath=str(crop_copy)),
            soildata=soil,
            sitedata=site,
        ),
        weather_provider,
        YAMLAgroManagementReader(str(agro_file)),
    )
    model.run_till_terminate()
    return model.get_summary_output()[0], model.get_terminal_output()


def _stage_date(body, name):
    return next(s["date"] for s in body["stages"] if s["stage"] == name)


def test_rainfed_season_offline_equals_pcse_native_readers(client, offline, tmp_path):
    days = _synthetic_days(SOW, LAST)
    resp = _post(
        client,
        {
            "crop": {"name": "barley"},
            "weather": {**SITE, "daily": days},
            "soil": {},
            "agromanagement": {"planting_date": SOW.isoformat()},
        },
    )
    assert resp.status_code == 200, resp.text
    assert offline == []  # ولا محاولة اتّصال واحدة
    body = resp.json()
    assert body["provenance"] == "pcse_wofost_uncalibrated"
    assert body["diagnostics"]["crop_cycle_end"] == "maturity"
    assert (
        body["diagnostics"]["parameter_version"]
        == pi.vendored_source_manifest()["crop_parameters"]["commit"]
    )
    assert "soil.SM0" in body["diagnostics"]["defaults_applied"]
    assert "default_soil_hydraulics" in body["yield_interval"]["drivers"]

    ref, terminal = _reference_run(
        tmp_path,
        "barley",
        _csv_weather(tmp_path, days),
        f"""
        AgroManagement:
        - {SOW.isoformat()}:
            CropCalendar:
                crop_name: barley
                variety_name: Spring_barley_301
                crop_start_date: {SOW.isoformat()}
                crop_start_type: sowing
                crop_end_date:
                crop_end_type: maturity
                max_duration: {(LAST - SOW).days}
            TimedEvents:
            StateEvents:
        """,
    )
    state = body["state"]
    for key, ours in (
        ("TWSO", "TWSO"),
        ("TAGP", "TAGP"),
        ("CTRAT", "CTRAT_cm"),
        ("CEVST", "CEVST_cm"),
    ):
        assert state[ours] == pytest.approx(ref[key], rel=1e-9), key
    # حقول المخطّط مُقرَّبة إلى 6 منازل (``_ROUND``)؛ ``state`` أعلاه يحمل القيم الكاملة.
    assert body["yield_kg_ha"] == pytest.approx(ref["TWSO"], abs=5e-7)
    assert body["water_use"] == pytest.approx(ref["CTRAT"] * 10.0, abs=5e-7)  # سم ⇒ ملّيمتر
    for stage, key in (("emergence", "DOE"), ("anthesis", "DOA"), ("maturity", "DOM")):
        assert _stage_date(body, stage) == ref[key].isoformat()
    assert body["diagnostics"]["water_balance_mm"]["rain"] == pytest.approx(
        terminal["RAINT"] * 10.0
    )
    # المُنشئ الأصليّ كان سيكتب pickle في الدليل المحزوم؛ لا أثر له بعد التشغيل.
    assert not [f for f in os.listdir(pi.CROP_DIR) if f.endswith(".pkl")]


def test_irrigated_season_with_harvest_date(client, offline, tmp_path):
    """أحداث الريّ تصل بمفتاحَي WaterbalanceFD ووحدتيهما (TOTIRR = Σ عمق×كفاءة)، والحصاد يُسجَّل DOH."""
    days = _synthetic_days(SOW, LAST)
    harvest = SOW + timedelta(days=60)
    events = [
        {"date": (SOW + timedelta(days=d)).isoformat(), "depth_mm": 30.0} for d in (10, 25, 40)
    ]
    resp = _post(
        client,
        {
            "crop": {"name": "barley"},
            "weather": {**SITE, "daily": days},
            "soil": {"available_water_mm": 60.0},
            "agromanagement": {
                "planting_date": SOW.isoformat(),
                "harvest_date": harvest.isoformat(),
                "irrigation_events": events,
                "application_efficiency": 0.8,
            },
        },
    )
    assert resp.status_code == 200, resp.text
    assert offline == []
    body = resp.json()
    diag = body["diagnostics"]
    assert diag["crop_cycle_end"] == "harvest_date" and diag["matured"] is False
    assert _stage_date(body, "harvest") == harvest.isoformat()
    assert diag["water_balance_mm"]["irrigation_effective"] == pytest.approx(3 * 30.0 * 0.8)
    assert diag["inputs"]["irrigation"]["net_mm"] == pytest.approx(72.0)
    assert "irrigation.none_declared" not in diag["defaults_applied"]
    assert "site.WAV" not in diag["defaults_applied"]  # 60 ملم من الطلب ⇒ 6 سم

    table = "\n".join(
        f"                - {e['date']}: {{amount: 3.0, efficiency: 0.8}}" for e in events
    )
    ref, _ = _reference_run(
        tmp_path,
        "barley",
        _csv_weather(tmp_path, days),
        f"""
        AgroManagement:
        - {SOW.isoformat()}:
            CropCalendar:
                crop_name: barley
                variety_name: Spring_barley_301
                crop_start_date: {SOW.isoformat()}
                crop_start_type: sowing
                crop_end_date: {harvest.isoformat()}
                crop_end_type: earliest
                max_duration: {(harvest - SOW).days + 1}
            TimedEvents:
            -   event_signal: irrigate
                name: reference irrigation
                comment: cm
                events_table:
{table}
            StateEvents:
        """,
        wav_cm=6.0,
    )
    assert ref["DOH"] == harvest
    assert body["state"]["TWSO"] == pytest.approx(ref["TWSO"], rel=1e-9)
    assert body["state"]["CTRAT_cm"] == pytest.approx(ref["CTRAT"], rel=1e-9)


def test_weather_provider_matches_pcse_csv_reader_day_by_day(pcse_ns, tmp_path):
    days = _synthetic_days(SOW, SOW + timedelta(days=40))
    ours = pcse_ns.WeatherDataProvider(pi.build_weather({**SITE, "daily": days}))
    ref = _csv_weather(tmp_path, days)
    assert (ours.angstA, ours.angstB) == (ref.angstA, ref.angstB)  # افتراضنا = ثابتا PCSE
    for d in days:
        day = date.fromisoformat(d["date"])
        a, b = ours(day), ref(day)
        for var in ("IRRAD", "TMIN", "TMAX", "VAP", "RAIN", "WIND", "E0", "ES0", "ET0"):
            assert getattr(a, var) == pytest.approx(getattr(b, var), rel=1e-12, abs=1e-12), (
                day,
                var,
            )


def test_wind_at_10m_is_converted_with_pcse_own_profile(pcse_ns):
    from pcse.util import wind10to2

    days = _synthetic_days(SOW, SOW + timedelta(days=3), wind_key="wind_10m_m_s")
    ours = pcse_ns.WeatherDataProvider(pi.build_weather({**SITE, "daily": days}))
    for d in days:
        assert ours(date.fromisoformat(d["date"])).WIND == pytest.approx(
            wind10to2(d["wind_10m_m_s"])
        )


def test_copied_pcse_bounds_and_default_soil_match_pcse(pcse_ns):
    from pcse.base import WeatherDataContainer
    from pcse.exceptions import PCSEError
    from pcse.input import CABOFileReader, WOFOST72SiteDataProvider
    from pcse.util import check_angstromAB

    for key, bounds in pi.PCSE_WEATHER_RANGES.items():
        assert tuple(float(x) for x in WeatherDataContainer.ranges[key]) == bounds, key
    assert (
        tuple(float(x) for x in WOFOST72SiteDataProvider._defaults["WAV"][1])
        == pi.PCSE_WAV_RANGE_CM
    )
    for a, b in (
        (0.29, 0.49),
        (0.1, 0.5),
        (0.09, 0.55),
        (0.41, 0.3),
        (0.2, 0.29),
        (0.25, 0.71),
        (0.35, 0.6),
    ):
        try:
            check_angstromAB(a, b)
            pcse_accepts = True
        except PCSEError:
            pcse_accepts = False
        try:
            pi.build_weather(
                {**SITE, "angstrom_a": a, "angstrom_b": b, "daily": _synthetic_days(SOW, SOW)}
            )
            ours_accepts = True
        except pi.SimulationInputError:
            ours_accepts = False
        assert ours_accepts is pcse_accepts, (a, b)
    cabo = CABOFileReader(pi.DEFAULT_SOIL_FILE)
    assert pi.load_default_soil()["values"] == {k: float(cabo[k]) for k, _ in pi.SOIL_FIELDS}


def test_every_registry_crop_runs_offline(client, offline):
    """المحاصيل الثلاثة في السجلّ تُحمَّل من الدليل المحزوم وتُشغَّل (لا صنف مفقود، لا شبكة)."""
    days = _synthetic_days(SOW, LAST)
    for name in sim_crop_registry.SUPPORTED_CROP_NAMES:
        start_type = "emergence" if name == "potato" else "sowing"
        resp = _post(
            client,
            {
                "crop": {"name": name},
                "weather": {**SITE, "daily": days},
                "agromanagement": {"planting_date": SOW.isoformat(), "crop_start_type": start_type},
            },
        )
        assert resp.status_code == 200, (name, resp.text)
        diag = resp.json()["diagnostics"]
        assert diag["pcse_variety"] == sim_crop_registry.get(name).pcse_variety
        assert diag["variety_calibration_region"]  # من Metadata.Coverage.Region في الملفّ
    assert offline == []


_LOGGING_PROBE = textwrap.dedent(
    """
    import json, logging, sys
    logging.basicConfig(level=logging.INFO, format="HOST %(message)s")
    pre = [logging.getLogger(n) for n in ("uvicorn.error", "uvicorn.access", "agriai-engine")]
    root = logging.getLogger()
    handlers_before, path_before = list(root.handlers), list(sys.path)
    import wofost_adapter as wa
    if sys.argv[1] == "without-restore":
        wa._restore_host_logging = lambda *args, **kwargs: None
    wa._load_pcse()
    print(json.dumps({
        "disabled": [lg.disabled for lg in pre],
        "root_handlers_unchanged": root.handlers == handlers_before,
        "sys_path_unchanged": sys.path == path_before,
        "pcse_level": logging.getLogger("pcse").level,
    }))
    """
)


def _logging_probe(tmp_path, mode):
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "USER": "pcse-test",
        "PYTHONPATH": os.pathsep.join([_SVC, ROOT]),
    }
    proc = subprocess.run(
        [sys.executable, "-c", _LOGGING_PROBE, mode],
        capture_output=True,
        encoding="utf-8",
        env={**env, "PYTHONIOENCODING": "utf-8"},
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_pcse_import_leaves_host_logging_intact(tmp_path):
    """عمليّة جديدة (الاستيراد مرّة واحدة لكلّ عمليّة): مُسجِّلات uvicorn تبقى فعّالة بعد pcse."""
    probe = _logging_probe(tmp_path, "with-restore")
    assert probe == {
        "disabled": [False, False, False],
        "root_handlers_unchanged": True,
        "sys_path_unchanged": True,
        "pcse_level": 30,
    }


def test_pcse_import_hazard_is_real_without_the_restore(tmp_path):
    """التكذيب: بلا الإعادة يُعطِّل dictConfig في pcse 6.0.13 مُسجِّلات المُضيف — الحارس ليس زخرفة.

    إن توقّفت نسخةٌ لاحقة من pcse عن ذلك فهذا الاختبار يحمرّ ليقول: الالتفاف لم يعد لازماً.
    """
    probe = _logging_probe(tmp_path, "without-restore")
    assert probe["disabled"] == [True, True, True]
    assert probe["root_handlers_unchanged"] is False
