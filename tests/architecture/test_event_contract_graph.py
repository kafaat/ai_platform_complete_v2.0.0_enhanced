from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "event_contract_graph.py"
OUT = ROOT / "event-audit" / "generated" / "event_contract_graph.json"


def load_module():
    spec = importlib.util.spec_from_file_location("event_contract_graph", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_generated_event_graph_matches_repository():
    module = load_module()
    generated = json.loads(OUT.read_text(encoding="utf-8"))
    assert generated == module.build()


def test_static_inventory_does_not_claim_runtime_truth():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    assert data["summary"]["runtime_verified"] is False
    assert data["summary"]["production_certified"] is False


def test_subjects_and_references_are_deterministically_sorted():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    subjects = [item["subject"] for item in data["subjects"]]
    assert subjects == sorted(subjects)
    for item in data["subjects"]:
        for key in ("producers", "consumers"):
            refs = item[key]
            assert refs == sorted(
                refs, key=lambda r: (r["subject"] or "~", r["kind"], r["file"], r["line"])
            )


def test_dynamic_subjects_are_not_reported_as_missing_contracts():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    assert all(row["subject"] is None for row in data["dynamic_contracts"])
    literal_subjects = {row["subject"] for row in data["subjects"]}
    assert None not in literal_subjects


# ── حلّ الاسم بشكلَين مُثبَتَين فقط (WEATHER-FORECAST-TOPIC-HAS-NO-PUBLISHER-01) ──
# الحافّتان الحرفيّتان الوحيدتان اللتان رآهما الماسحُ كانتا لـweather-polygon-worker (سقالةٌ
# تشترك في موضوعٍ لا ناشرَ له). بإزالته صار الرسمُ بلا EMITS/CONSUMES بينما التدفّقاتُ
# الحقيقيّة مختبئةٌ خلف متغيّر. هذه الحالات تُثبِت أنّ الحلّ ضيّقٌ: شكلان، وما سواهما ديناميكيّ.


def _contracts(tmp_path, monkeypatch, source: str):
    module = load_module()
    svc = tmp_path / "services" / "probe-svc"
    svc.mkdir(parents=True)
    (svc / "worker.py").write_text(source, encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module.parse_file(svc / "worker.py")


def test_a_loop_over_a_module_tuple_of_literals_resolves_each_subject(tmp_path, monkeypatch):
    rows = _contracts(
        tmp_path,
        monkeypatch,
        'SUBJECTS = ("sahool.a.done", "sahool.b.done")\n'
        "async def run(js):\n"
        "    for subject in SUBJECTS:\n"
        "        await js.subscribe(subject, durable='d')\n",
    )
    assert sorted((r.subject, r.kind, r.resolution) for r in rows) == [
        ("sahool.a.done", "consumer", "module_constant_loop"),
        ("sahool.b.done", "consumer", "module_constant_loop"),
    ]


def test_a_single_local_token_template_becomes_a_wildcard_subject(tmp_path, monkeypatch):
    rows = _contracts(
        tmp_path,
        monkeypatch,
        "async def emit(nc, t, f):\n"
        '    subject = f"sahool.tenant.{t}.satellite.{f}.computed"\n'
        "    await nc.publish(subject, b'')\n",
    )
    assert [(r.subject, r.kind, r.resolution) for r in rows] == [
        ("sahool.tenant.*.satellite.*.computed", "producer", "local_token_template")
    ]


def test_anything_else_stays_dynamic(tmp_path, monkeypatch):
    """parameter · placeholder sharing a token · reassigned name · non-sahool prefix."""
    rows = _contracts(
        tmp_path,
        monkeypatch,
        "async def a(nc, subject):\n"
        "    await nc.publish(subject, b'')\n"
        "async def b(nc, kind):\n"
        '    subject = f"sahool.video.{kind}_done"\n'
        "    await nc.publish(subject, b'')\n"
        "async def c(nc, x, y):\n"
        '    subject = f"sahool.x.{x}"\n'
        '    subject = f"sahool.y.{y}"\n'
        "    await nc.publish(subject, b'')\n"
        "async def d(nc, x):\n"
        '    subject = f"other.{x}"\n'
        "    await nc.publish(subject, b'')\n",
    )
    assert len(rows) == 4
    assert all(r.subject is None and r.resolution == "dynamic" for r in rows), rows


def test_the_tree_shows_real_flows_after_the_scaffold_left():
    """الرسمُ الحقيقيّ يرى ناشراً ومشترِكاً بعد إزالة العامل — لا صفرَ صامتاً."""
    data = json.loads(OUT.read_text(encoding="utf-8"))
    by_subject = {s["subject"]: s for s in data["subjects"]}
    assert "sahool.weather.forecast.updated" not in by_subject, (
        "موضوعُ العامل المُزال عاد إلى الرسم — اشتراكٌ بلا ناشر"
    )
    sat = by_subject["sahool.tenant.*.satellite.*.computed"]
    assert {p["component"] for p in sat["producers"]} == {"vegetation-analysis-service"}
    learning = by_subject["sahool.events.season.closed"]
    assert {c["component"] for c in learning["consumers"]} == {"sahool-platform"}
