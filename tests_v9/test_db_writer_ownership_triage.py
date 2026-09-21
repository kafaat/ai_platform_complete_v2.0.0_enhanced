"""فرزُ مخالفات ملكيّة الكتابة: مصنوعةٌ تقول ما قِيس عن كلّ مخالفةٍ — ولا تحكم عليها.

`db_writer_ownership_baseline.json` يعدّ المخالفاتِ ولا يحكم («مَعدودةٌ لا محكومٌ عليها»).
`db_writer_ownership_triage.json` يضيف لكلّ مدخلٍ **أبعاداً مقيسة** (هل مجلّدُ المالك في
الشجرة · هل يكتب المالكُ الجدولَ في أيّ موضعٍ مقيس · من يكتبه فعلاً · صنفُ الكاتب) ثمّ
يشتقّ منها **صنفاً** بقاعدةٍ صريحة — فالصنفُ قياسٌ لا رأي. الرأيُ (العلاجُ المقترَح وصاحبُ
القرار) حقلٌ منفصل لا يُقاس هنا.

هذا الشاهدُ يربط المصنوعةَ بمصادرها الحيّة: المفاتيحُ = مفاتيحُ الأساس بالضبط، والأبعادُ
المقيسة = ما يُعيده محرّكُ الحارس الحاجب نفسُه الآن، والصنفُ = ما تُنتِجه القاعدةُ من تلك
الأبعاد. مصنوعةٌ تُحرَّر بيدٍ لتُخفي مخالفةً أو لترقّي صنفاً تُحمِّر هنا. ولا يدّعي الشاهدُ
أنّ أيَّ مخالفةٍ حُلّت: `status` لكلّ صفٍّ `triaged` ولا غير.
"""

from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TRIAGE = ROOT / "docs/architecture/db_writer_ownership_triage.json"
BASELINE = ROOT / "docs/architecture/db_writer_ownership_baseline.json"

CATEGORIES = {
    "owner-name-not-in-tree",  # العقدُ يسمّي مالكاً لا مجلّدَ له تحت services/
    "tooling-writer",  # الكاتبُ سكربتٌ لا خدمة
    "dual-writer",  # المالكُ يكتب الجدولَ فعلاً، وكاتبٌ آخر يكتبه معه
    "owner-never-writes",  # المالكُ المُعلَن لا يكتب الجدولَ في أيّ موضعٍ مقيس — الكاتبُ المخالف هو الكاتبُ الوحيد
}


def _guard():
    spec = importlib.util.spec_from_file_location(
        "db_writer_ownership_guard", ROOT / "scripts/ci/db_writer_ownership_guard.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _triage() -> dict:
    return json.loads(TRIAGE.read_text(encoding="utf-8"))


def derive_category(row: dict) -> str:
    """القاعدةُ الوحيدة التي تُنتِج الصنف — مكتوبةٌ هنا كي تُقاس لا كي تُقرأ."""
    if not row["owner_dir_in_tree"]:
        return "owner-name-not-in-tree"
    if row["writer"] == "scripts":
        return "tooling-writer"
    if row["owner_writes_table"]:
        return "dual-writer"
    return "owner-never-writes"


def test_the_triage_covers_the_baseline_exactly() -> None:
    """لا مخالفةَ بلا فرز، ولا فرزَ لمخالفةٍ زالت — الراتشِتُ في الاتّجاهين."""
    base = json.loads(BASELINE.read_text(encoding="utf-8"))["violations"]
    rows = _triage()["rows"]
    assert set(rows) == set(base), (
        f"بلا فرز: {sorted(set(base) - set(rows))} · فرزٌ بائت: {sorted(set(rows) - set(base))}"
    )
    for key, row in rows.items():
        assert row["files"] == base[key], key


def _owner_dir_in_tree(mod, owner: str | None) -> bool:
    """مجلّدُ المالك — بهويّة compose التي يعرفها المحرّك (`_DIRECTORY_IDENTITY`) لا بالاسم الحرفيّ وحده."""
    directories = [d for d, identity in mod._DIRECTORY_IDENTITY.items() if identity == owner] or [
        str(owner)
    ]
    return any((ROOT / "services" / d).is_dir() for d in directories)


def test_the_measured_dimensions_match_the_blocking_engine_now() -> None:
    """الأبعادُ المقيسة تُعاد من `write_sites()` والعقد الآن — لا من يوم كُتبت المصنوعة."""
    mod = _guard()
    contract = mod.load_contract()
    sites = mod.write_sites()
    writers_of: dict[str, set[str]] = {}
    for key in sites:
        table, service = key.split("::", 1)
        writers_of.setdefault(table, set()).add(service)
    for key, row in _triage()["rows"].items():
        table, writer = key.split("::", 1)
        assert row["table"] == table and row["writer"] == writer, key
        owner = contract.get(table, {}).get("owner")
        assert row["declared_owner"] == owner, key
        assert row["owner_dir_in_tree"] is _owner_dir_in_tree(mod, owner), key
        assert row["measured_writers_of_table"] == sorted(writers_of.get(table, set())), key
        assert row["owner_writes_table"] is (owner in writers_of.get(table, set())), key
        assert row["measured_writer_count"] == len(row["measured_writers_of_table"]), key
        assert row["multiple_non_owner_writers"] is (
            not row["owner_writes_table"] and len(row["measured_writers_of_table"]) > 1
        ), key


def test_the_category_is_derived_not_chosen() -> None:
    rows = _triage()["rows"]
    for key, row in rows.items():
        assert row["category"] in CATEGORIES, key
        assert row["category"] == derive_category(row), (
            f"{key}: الصنفُ المكتوب {row['category']} ≠ المشتقّ {derive_category(row)}"
        )


def test_the_counts_are_the_rows_not_a_hand_written_summary() -> None:
    triage = _triage()
    counted = Counter(r["category"] for r in triage["rows"].values())
    assert triage["counts"]["by_category"] == dict(counted)
    assert triage["counts"]["total"] == len(triage["rows"])


def test_the_triage_claims_no_resolution() -> None:
    """الفرزُ تصنيفٌ لا علاج: كلُّ صفٍّ `triaged`، وكلُّ صفٍّ يسمّي صاحبَ قراره."""
    for key, row in _triage()["rows"].items():
        assert row["status"] == "triaged", key
        assert row["decision_owner"] in {"owner", "engineering"}, key
        assert row["remedy"].strip(), key


def test_weather_signals_exposes_multiple_non_owner_writers() -> None:
    rows = _triage()["rows"]
    keys = [
        "weather_signals::weather-polygon-worker",
        "weather_signals::weather-signal-engine",
    ]
    for key in keys:
        row = rows[key]
        assert row["declared_owner"] == "weather-service"
        assert row["owner_writes_table"] is False
        assert row["measured_writer_count"] == 2
        assert row["multiple_non_owner_writers"] is True
        assert "الكاتبُ الوحيد" not in row["remedy"]


def test_sqlite_only_exclusions_are_visible_not_silent() -> None:
    excluded = _triage()["excluded_write_sites"]
    for key in (
        "knowledge_snippets::sahool-platform",
        "users::sahool-platform",
        "field_state::sahool-platform",
    ):
        assert excluded[key]["reason"] == "sqlite_only_backend"
        assert excluded[key]["evidence"]["driver_imports"] == ["sqlite3"]


def test_deployment_evidence_is_historical_and_never_cutover_ready() -> None:
    for key, row in _triage()["rows"].items():
        evidence = row["deployment_evidence"]
        assert evidence["observed_on"] == "2026-09-20", key
        assert evidence["source"] == "docs/evidence/railway_audit_review_20260920.md", key
        assert evidence["cutover_ready"] is False, key
        assert evidence["freshness"] == "historical_snapshot", key


# ── المولِّد في الحارس نفسِه: المصنوعةُ تساوي اشتقاقَها من الشجرة الآن ─────────────
#
# الفرزُ كان مصنوعةً بلا مولِّد في الشجرة (#1054 · #1055): الشواهدُ أعلاه تربطها بالمحرّك
# فتمنع تحريرَها كذباً، لكنّ إعادةَ توليدها بعد أيّ تغييرٍ كانت تحتاج أداةً خارجيّة.
# `triage_rows` / `excluded_write_sites` / `triage_document` في الحارس تُنتِجها من الشجرة
# حتميّاً، و`triage_drift` يحجب بياتَها صفّاً صفّاً. والشواهدُ هنا حالاتٌ مضادّة على دوالّ
# الاشتقاق نفسِها — لا إعادةُ إنتاجٍ للتصنيف.


def test_the_stored_triage_equals_the_derivation_on_the_current_tree() -> None:
    mod = _guard()
    stored = _triage()
    assert stored["rows"] == mod.triage_rows()
    assert stored["excluded_write_sites"] == mod.excluded_write_sites()
    assert mod.triage_drift() == []


def test_the_excluded_sites_are_the_scanner_rule_itself(tmp_path: Path) -> None:
    """ما يُسقِطه `write_sites` يظهر في `excluded_write_sites` بالدليل نفسِه — والمختلطُ لا يُستبعَد."""
    mod = _guard()
    (tmp_path / "services" / "svc-a").mkdir(parents=True)
    (tmp_path / "services" / "svc-a" / "lite.py").write_text(
        'import sqlite3\nSQL = "INSERT INTO ledger (a) VALUES (?)"\n', encoding="utf-8"
    )
    (tmp_path / "services" / "svc-a" / "mixed.py").write_text(
        'import sqlite3\nimport asyncpg\nSQL = "INSERT INTO ledger (a) VALUES ($1)"\n',
        encoding="utf-8",
    )
    contract = {"ledger": {"owner": "owner-svc", "writers": ["owner-svc"]}}
    sites = mod.write_sites(tmp_path)
    excluded = mod.excluded_write_sites(tmp_path, contract)
    assert sites == {"ledger::svc-a": ["services/svc-a/mixed.py"]}
    assert excluded == {
        "ledger::svc-a": {
            "files": ["services/svc-a/lite.py"],
            "reason": "sqlite_only_backend",
            "evidence": {"driver_imports": ["sqlite3"], "postgres_driver_imports": []},
            "contract_state": "not_authorised",
        }
    }


def test_an_unknown_backend_is_never_listed_as_excluded(tmp_path: Path) -> None:
    mod = _guard()
    (tmp_path / "services" / "svc-a").mkdir(parents=True)
    (tmp_path / "services" / "svc-a" / "store.py").write_text(
        'SQL = "INSERT INTO ledger (a) VALUES ($1)"\n', encoding="utf-8"
    )
    assert mod.excluded_write_sites(tmp_path, {}) == {}
    assert "ledger::svc-a" in mod.write_sites(tmp_path)


def _rows(mod, contract: dict, sites: dict, violations: dict, tmp_path: Path) -> dict:
    # مجلّداتُ المالكين تُصنَع في شجرةٍ اصطناعيّة كي يُقاس `owner_dir_in_tree` لا يُفترَض.
    for meta in contract.values():
        (tmp_path / "services" / meta["owner"]).mkdir(parents=True, exist_ok=True)
    return mod.triage_rows(contract=contract, sites=sites, violations=violations, root=tmp_path)


def _contract(**tables: dict) -> dict:
    return {
        name: {"owner": meta["owner"], "writers": [meta["owner"]]} for name, meta in tables.items()
    }


def test_an_unobserved_owner_with_one_writer_is_never_writes_and_single(tmp_path: Path) -> None:
    mod = _guard()
    rows = _rows(
        mod,
        _contract(ledger={"owner": "owner-svc"}),
        {"ledger::probe-svc": ["services/probe-svc/store.py"]},
        {"ledger::probe-svc": ["services/probe-svc/store.py"]},
        tmp_path,
    )
    row = rows["ledger::probe-svc"]
    assert row["category"] == "owner-never-writes"
    assert row["measured_writer_count"] == 1 and row["multiple_non_owner_writers"] is False
    assert "الوحيد" in row["remedy"] and row["decision_owner"] == "owner"
    assert "لم يُرصد" in row["remedy"] and "لا يكتب" not in row["remedy"]
    assert row["deployment_evidence"]["cutover_ready"] is False


def test_an_observed_owner_with_another_writer_is_dual(tmp_path: Path) -> None:
    mod = _guard()
    rows = _rows(
        mod,
        _contract(ledger={"owner": "owner-svc"}),
        {
            "ledger::owner-svc": ["services/owner-svc/store.py"],
            "ledger::probe-svc": ["services/probe-svc/store.py"],
        },
        {"ledger::probe-svc": ["services/probe-svc/store.py"]},
        tmp_path,
    )
    row = rows["ledger::probe-svc"]
    assert row["category"] == "dual-writer" and row["owner_writes_table"] is True
    assert row["non_owner_writers"] == ["probe-svc"] and row["decision_owner"] == "engineering"


def test_an_unobserved_owner_with_two_writers_is_flagged_and_never_called_the_only_one(
    tmp_path: Path,
) -> None:
    """**حالةُ `weather_signals` مصطنعةً:** الصنفُ يبقى، والعددُ بُعدٌ مستقلّ، والوصفُ يتبعه."""
    mod = _guard()
    rows = _rows(
        mod,
        _contract(signals={"owner": "owner-svc"}),
        {
            "signals::worker-a": ["services/worker-a/main.py"],
            "signals::worker-b": ["services/worker-b/main.py"],
        },
        {
            "signals::worker-a": ["services/worker-a/main.py"],
            "signals::worker-b": ["services/worker-b/main.py"],
        },
        tmp_path,
    )
    for key in ("signals::worker-a", "signals::worker-b"):
        row = rows[key]
        assert row["category"] == "owner-never-writes"
        assert row["measured_writer_count"] == 2 and row["multiple_non_owner_writers"] is True
        assert "المرصودُ الوحيدُ" not in row["remedy"] and "الكاتبُ الوحيد" not in row["remedy"]
        assert "مراجعةً هندسيّةً" in row["remedy"] and row["decision_owner"] == "owner"


def test_a_script_writer_is_tooling_whatever_the_owner_does(tmp_path: Path) -> None:
    mod = _guard()
    rows = _rows(
        mod,
        _contract(ledger={"owner": "owner-svc"}),
        {
            "ledger::scripts": ["scripts/e2e/seed.py"],
            "ledger::owner-svc": ["services/owner-svc/a.py"],
        },
        {"ledger::scripts": ["scripts/e2e/seed.py"]},
        tmp_path,
    )
    row = rows["ledger::scripts"]
    assert row["category"] == "tooling-writer" and row["writer_kind"] == "e2e-script"
    assert row["decision_owner"] == "engineering"


def test_an_owner_without_a_directory_or_a_compose_identity_is_named_not_in_tree(
    tmp_path: Path,
) -> None:
    mod = _guard()
    (tmp_path / "services").mkdir()
    rows = mod.triage_rows(
        contract={"ledger": {"owner": "ghost-svc", "writers": ["ghost-svc"]}},
        sites={"ledger::probe-svc": ["services/probe-svc/store.py"]},
        violations={"ledger::probe-svc": ["services/probe-svc/store.py"]},
        root=tmp_path,
    )
    row = rows["ledger::probe-svc"]
    assert row["owner_dir_in_tree"] is False and row["category"] == "owner-name-not-in-tree"


def test_a_hand_edited_row_or_exclusion_is_reported_as_drift(monkeypatch) -> None:
    """المصنوعةُ المخزَّنة تُقاس لا تُصدَّق: صفٌّ مُرقّى بيدٍ أو استبعادٌ مُضاف يُحمِّر --check."""
    mod = _guard()
    tampered = json.loads(json.dumps(_triage()))
    first = next(iter(tampered["rows"]))
    tampered["rows"][first]["category"] = "dual-writer"
    tampered["excluded_write_sites"]["phantom::svc"] = {
        "files": ["services/svc/x.py"],
        "reason": "sqlite_only_backend",
        "evidence": {"driver_imports": ["sqlite3"], "postgres_driver_imports": []},
        "contract_state": "outside_contract",
    }
    monkeypatch.setattr(mod, "_stored_triage", lambda: tampered)
    drift = mod.triage_drift()
    assert any(first in item and "category" in item for item in drift)
    assert any("phantom::svc" in item for item in drift)
