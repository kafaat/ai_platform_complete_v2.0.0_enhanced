"""`OWNERSHIP-CONTRACT-DECLARED-BUT-NEVER-MEASURED-01` — الحارسُ يقيس ما يُعلَن.

الحارسُ يعمل خطوةً حاجبة في `ci.yml`، فهذه الاختبارات لا تُعيد فحصَ ما يفحصه —
تحرس **دلالته**: أنّ الكشف بنيويّ لا نصّيّ، وأنّ الاستثناءَ الموثَّق ليس انحرافاً،
وأنّ الراتشِت يفشل في الاتّجاهين، وأنّ عقداً غيرَ مقروءٍ يفشل صراحةً لا صفراً كاذباً.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "ci" / "db_writer_ownership_guard.py"

_spec = importlib.util.spec_from_file_location("db_writer_ownership_guard", _SCRIPT)
assert _spec is not None and _spec.loader is not None
MOD = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = MOD
_spec.loader.exec_module(MOD)


def _baseline() -> dict:
    return json.loads(MOD.BASELINE.read_text(encoding="utf-8"))["violations"]


# ── الشجرة الحيّة ────────────────────────────────────────────────────────────


def test_the_tree_matches_the_baseline():
    assert MOD.findings() == []


def test_the_two_measured_ownership_defects_are_actually_caught():
    """M-03 بشقّيه — وهو العطلُ الذي وُجِد الحارسُ لأجله.

    `db_ownership.yml` يعلن الجدولين مملوكين لـ`actuator-service` وكاتبَهما هو
    وحده، و`sahool-platform` **قارئاً**. والمقيس أنّ `sahool-platform` يكتبهما.
    فإن غاب أحدُهما عن الأساس فالكشفُ يقيس شيئاً آخر — أو أنّ العطل عولج.
    """
    base = _baseline()
    for key in (
        "actuator_command_outbox::sahool-platform",
        "iot_command_dispatch::sahool-platform",
    ):
        assert key in base, f"العطلُ المُثبِت غائبٌ عن الأساس: {key}"
        assert base[key], f"مدخلٌ بلا ملفّ: {key}"


def test_the_inventory_says_what_it_does_not_claim():
    """أساسٌ يُقرأ «هذه أعطال» أسوأ من غيابه — المَعدود ليس محكوماً عليه.

    فبعضُ المداخل قد يكون **العقدُ** هو المخطئ فيها لا الكود. ولا يكفي أن أعرف
    ذلك: النصُّ نفسُه يجب أن يقوله، فمن يقرأه بعد سنةٍ لا يقرأ نيّتي.
    """
    comment = json.loads(MOD.BASELINE.read_text(encoding="utf-8"))["$comment"]
    assert "مَعدودةٌ لا محكومٌ عليها" in comment
    assert "العقدُ هو المخطئ" in comment
    assert "ينزل ولا يصعد" in comment


# ── مستودعٌ اصطناعيّ — لا يُكتَب شيء في الشجرة الحيّة (درس `probe_leak_guard`) ──


def _sandbox(tmp_path: Path, monkeypatch, *, contract: str, source: str) -> Path:
    (tmp_path / "docs" / "architecture").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "architecture" / "db_ownership.yml").write_text(contract, encoding="utf-8")
    target = tmp_path / "services" / "probe-service" / "store.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    monkeypatch.setattr(MOD, "ROOT", tmp_path)
    monkeypatch.setattr(MOD, "CONTRACT", tmp_path / "docs/architecture/db_ownership.yml")
    monkeypatch.setattr(MOD, "BASELINE", tmp_path / "baseline.json")
    return tmp_path


def _contract(**tables: str) -> str:
    """عقدٌ يتجاوز حدَّ المئة جدولٍ الذي يفرضه `load_contract`."""
    lines = ["tables:"]
    for name, body in tables.items():
        lines.append(f"  {name}:")
        lines.extend(f"    {ln}" for ln in body.strip().splitlines())
    for i in range(120):
        lines += [f"  filler_{i}:", "    owner: x", "    writers: [x]", "    readers: []"]
    return "\n".join(lines) + "\n"


_OWNED_ELSEWHERE = _contract(
    ledger="owner: other-service\nwriters: [other-service]\nreaders: [probe-service]"
)


def test_a_write_the_contract_does_not_permit_is_caught(tmp_path, monkeypatch):
    _sandbox(
        tmp_path,
        monkeypatch,
        contract=_OWNED_ELSEWHERE,
        source='SQL = "INSERT INTO ledger (a) VALUES ($1)"\n',
    )
    assert "ledger::probe-service" in MOD.survey()


def test_a_write_the_contract_permits_is_not_caught(tmp_path, monkeypatch):
    _sandbox(
        tmp_path,
        monkeypatch,
        contract=_contract(ledger="owner: probe-service\nwriters: [probe-service]\nreaders: []"),
        source='SQL = "INSERT INTO ledger (a) VALUES ($1)"\n',
    )
    assert MOD.survey() == {}


def test_a_documented_interim_bridge_is_not_a_violation(tmp_path, monkeypatch):
    """الحدُّ المُعلَن حقيقيّ: `mirror` إذنٌ صريحٌ في العقد لا انحراف.

    ولولا ذلك لأدان الحارسُ خمسةَ جسورٍ انتقاليّةٍ موثَّقة (`status: interim-bridge`)
    — وحارسٌ يُنذِر كذباً يُدرَّب الناسُ على تجاهله، فيموت وهو أخضر.
    """
    _sandbox(
        tmp_path,
        monkeypatch,
        contract=_contract(
            ledger=(
                "owner: other-service\nwriters: [other-service]\n"
                "mirror: probe-service\nstatus: interim-bridge\nreaders: []"
            )
        ),
        source='SQL = "INSERT INTO ledger (a) VALUES ($1)"\n',
    )
    assert MOD.survey() == {}


def test_a_table_outside_the_contract_is_out_of_scope(tmp_path, monkeypatch):
    """لا يُدان ما لم يُعلَن عنه — وإلّا طالب الحارسُ بإعلانِ كلّ جدولٍ مؤقّت."""
    _sandbox(
        tmp_path,
        monkeypatch,
        contract=_OWNED_ELSEWHERE,
        source='SQL = "INSERT INTO scratch_table (a) VALUES ($1)"\n',
    )
    assert MOD.survey() == {}


def test_the_detection_is_structural_so_a_comment_is_never_accused(tmp_path, monkeypatch):
    """درس درسٌ مقيسٌ في #951.

    تعليقٌ يشرح **لماذا** هُجِر مسارٌ يحوي نصَّ العبارة نفسِه. فبحثٌ نصّيٌّ يجعل
    **توثيقَ الإصلاح مُبطِلاً له**. الكشفُ من شجرة البناء لا يرى التعليقات.
    """
    _sandbox(
        tmp_path,
        monkeypatch,
        contract=_OWNED_ELSEWHERE,
        source="# تاريخيّاً كان هنا INSERT INTO ledger — نُقِل إلى مالكه\nX = 1\n",
    )
    assert MOD.survey() == {}


def test_update_and_delete_are_writes_too(tmp_path, monkeypatch):
    """حارسٌ يرى `INSERT` وحدَه يُلتَفّ عليه بإعادة صياغةٍ لا تُغيّر شيئاً."""
    for statement in ("UPDATE ledger SET a=1", "DELETE FROM ledger WHERE a=1"):
        _sandbox(
            tmp_path / statement[:6],
            monkeypatch,
            contract=_OWNED_ELSEWHERE,
            source=f'SQL = "{statement} AND b=2"\n',
        )
        assert "ledger::probe-service" in MOD.survey(), statement


# ── الراتشِت ────────────────────────────────────────────────────────────────


def test_the_ratchet_fails_in_both_directions(tmp_path, monkeypatch):
    """درس `AN-EXEMPTION-LIST-WITH-NO-DESCENDING-CEILING-01`.

    مخالفةٌ جديدة تُحمِّر — وكذلك **مدخلٌ بائتٌ لم يعد منحرفاً**. إعفاءٌ بلا سقفٍ
    نازل ليس ديناً مؤجَّلاً بل شطبٌ صامت.
    """
    root = _sandbox(
        tmp_path,
        monkeypatch,
        contract=_OWNED_ELSEWHERE,
        source='SQL = "INSERT INTO ledger (a) VALUES ($1)"\n',
    )
    base = root / "baseline.json"

    base.write_text(json.dumps({"violations": {}}), encoding="utf-8")
    assert any(f.startswith("مخالفةٌ جديدة") for f in MOD.findings())

    base.write_text(
        json.dumps({"violations": {"ledger::probe-service": ["x"], "ghost::gone": ["y"]}}),
        encoding="utf-8",
    )
    assert any(f.startswith("مدخلٌ بائت") for f in MOD.findings())


# ── الحارسُ يحرس نفسَه ──────────────────────────────────────────────────────


def test_an_unreadable_contract_fails_loudly_instead_of_passing_zero(tmp_path, monkeypatch):
    """**ثغرةٌ قِيست لا فُرِضت.** أوّلُ صياغةٍ لهذا الحارس قرأت جذرَ YAML بدل
    `tables`، فصار كلُّ جدولٍ «غيرَ مُصرَّحٍ عنه» وأبلغ **صفرَ مخالفات** على شجرةٍ
    تحمل خمساً وسبعين. حارسٌ يمرّ صفراً كاذباً أسوأُ من غيابه: يُقرَأ ضماناً
    ويُسجَّل تغطية.
    """
    empty = tmp_path / "empty.yml"
    empty.write_text("tables: {}\n", encoding="utf-8")
    monkeypatch.setattr(MOD, "CONTRACT", empty)
    with pytest.raises(SystemExit) as exc:
        MOD.load_contract()
    assert "OWNERSHIP_CONTRACT_UNREADABLE" in str(exc.value)


# ── هويّةُ الخدمة هي اسمُها في compose لا اسمُ مجلّدها ─────────────────────────


def test_a_directory_deployed_under_another_service_name_is_measured_under_that_name(
    tmp_path, monkeypatch
):
    """**المالكُ نفسُه كان يُدان بالكتابة إلى جداوله.**

    `services/odoo-bridge/` يُبنى خدمةً باسم `sahool-erp-bridge`، والعقدُ وخريطةُ الاستخراج
    يسمّيانها `erp-bridge`. فالماسحُ الذي يشتقّ الهويّةَ من المجلّد كان يقيس كاتباً اسمُه
    `odoo-bridge` لا يعرفه العقدُ، فسجّل مالكَ `odoo_sync_log` مخالفاً فيه (مدخلان في
    الأساس حتّى 2026-09-21). الربطُ يُعيد الكتابةَ إلى صاحبها لا يُعفيها.
    """
    _sandbox(
        tmp_path,
        monkeypatch,
        contract=_contract(odoo_sync_log="owner: erp-bridge\nwriters: [erp-bridge]\nreaders: []"),
        source="x = 1\n",
    )
    target = tmp_path / "services" / "odoo-bridge" / "erp_runtime.py"
    target.parent.mkdir(parents=True)
    target.write_text('SQL = "INSERT INTO odoo_sync_log (a) VALUES ($1)"\n', encoding="utf-8")
    assert "odoo_sync_log::erp-bridge" in MOD.write_sites()
    assert "odoo_sync_log::odoo-bridge" not in MOD.write_sites()
    assert MOD.survey() == {}


def test_the_directory_identity_map_is_backed_by_compose():
    """لا اسمٌ في الربط بلا كتلة compose تبنيه من ذلك المجلّد — وإلّا صار الربطُ إعفاءً بيد."""
    import yaml

    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    assert MOD._DIRECTORY_IDENTITY, "الربطُ فارغ — الاختبارُ لا يقيس شيئاً"
    for directory, identity in MOD._DIRECTORY_IDENTITY.items():
        service = compose["services"].get(f"sahool-{identity}")
        assert service, (
            f"لا خدمةَ `sahool-{identity}` في compose تُسند الربط {directory} ⇒ {identity}"
        )
        dockerfile = (service.get("build") or {}).get("dockerfile")
        assert dockerfile == f"services/{directory}/Dockerfile", (
            f"`sahool-{identity}` لا يُبنى من `services/{directory}/` بل من {dockerfile!r}"
        )
