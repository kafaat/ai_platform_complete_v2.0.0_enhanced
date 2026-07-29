from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "runtime_environment_preflight.py"


def load_module():
    spec = importlib.util.spec_from_file_location("runtime_environment_preflight", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_never_claims_runtime_truth():
    module = load_module()
    payload, _ = module.build()
    assert payload["runtime_verified"] is False
    assert payload["production_certified"] is False


def test_blocked_state_has_explicit_blockers():
    module = load_module()
    payload, _ = module.build()
    if not payload["runnable"]:
        assert payload["state"] == "BLOCKED_ENVIRONMENT"
        assert payload["blockers"]


def test_the_artifact_matches_this_machine_when_it_describes_this_machine():
    """المساواة الكاملة تُفرَض **داخل نطاق الأثر**، لا عبر آلات مختلفة.

    الصيغة السابقة قارنت الأثر المُلتزَم بما تولّده الآلة الحاليّة بلا شرط، فكانت تفشل
    حيثما اختلفت القدرة لا حيثما انحرف الأثر: عدّاء GitHub يملك Docker فيولّد
    `RUNNABLE`، وصندوق بلا خفيّ يولّد `BLOCKED_ENVIRONMENT` — والاثنان صادقان. أي أنّ
    الفشل كان يقول «الآلات ليست واحدة»، وهي حقيقة لا انحدار.
    """
    module = load_module()
    stored = json.loads(module.OUT_JSON.read_text(encoding="utf-8"))
    current, _ = module.build()
    if module.capability_scope(stored) == module.capability_scope(current):
        assert module.normalized(stored) == module.normalized(current)


def test_the_shape_layer_holds_on_any_machine():
    """ما لا تملك أيّ بيئة أن تُعفي منه — ولذلك يُفحَص حتّى حين تُتخطّى المقارنة."""
    module = load_module()
    stored = json.loads(module.OUT_JSON.read_text(encoding="utf-8"))
    assert module.shape_problems(stored) == []


def test_a_readiness_claim_contradicted_by_its_own_blockers_is_caught():
    """أثر يقول RUNNABLE وهو يحمل حاجباً كذبٌ مهما كانت الآلة."""
    module = load_module()
    lying = json.loads(module.OUT_JSON.read_text(encoding="utf-8"))
    lying["runnable"] = True
    lying["state"] = "RUNNABLE"
    lying["blockers"] = [{"code": "DOCKER_DAEMON_UNREACHABLE", "detail": "x"}]
    assert module.shape_problems(lying)


def test_machine_text_creeping_back_into_the_reason_is_caught():
    """جوهر `RUNTIME-ENV-PREFLIGHT-STAMPS-THE-MACHINE-01`: السبب مُصنَّف لا منقول."""
    module = load_module()
    leaked = json.loads(module.OUT_JSON.read_text(encoding="utf-8"))
    leaked["docker_daemon"]["reason"] = "Cannot connect to the Docker daemon at unix:///..."
    assert module.shape_problems(leaked)


def test_a_tool_record_carrying_more_than_availability_is_caught():
    """`path`/`version` هويّة آلة — والشكل نفسه يجب ألّا يتغيّر بتغيّرها."""
    module = load_module()
    leaked = json.loads(module.OUT_JSON.read_text(encoding="utf-8"))
    leaked["tools"]["git"] = {"available": True, "path": "/usr/bin/git"}
    assert module.shape_problems(leaked)


def test_every_tool_record_has_the_same_keys_regardless_of_availability():
    """الأداة المفقودة كانت تُسجَّل بثلاثة مفاتيح والموجودة بواحد — بصمة آلة في **الشكل**."""
    module = load_module()
    payload, _ = module.build()
    shapes = {frozenset(record) for record in payload["tools"].values()}
    assert shapes == {frozenset({"available"})}, f"سجلّات أدوات مختلفة الشكل: {shapes}"
