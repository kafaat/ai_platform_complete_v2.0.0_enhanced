"""H5 (PR3): bind ECw→water_source_id + enforce maximum_allowed_ec fail-closed.

Two layers:
  1. Pure `evaluate_water_salinity_gate` — the single source of the EC rule, reused
     by `build_canonical_well_capability` and by the served MPC recommendation.
  2. Static wiring guard — asserts the served daily MPC recommendation route resolves
     ECw from the bound water source (SoR, not client) and fails closed on the limit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from api.canonical_well_capability import (
    WATER_QUALITY_NOT_DECISION_GRADE,
    WATER_QUALITY_REQUIRED,
    WATER_QUALITY_STALE,
    WATER_SALINITY_LIMIT_EXCEEDED,
    build_canonical_well_capability,
    evaluate_water_salinity_gate,
)

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
_API = Path(__file__).resolve().parents[1] / "api"
ROUTE_SRC = (_API / "routers" / "irrigation_mpc.py").read_text(encoding="utf-8")
BIND_SRC = (_API / "irrigation_source_binding.py").read_text(encoding="utf-8")


# ─────────────────────────── pure gate: fail-closed rule ───────────────────────────


def test_gate_clear_when_ec_below_limit():
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality={"ec_ds_m": 2.4, "sampled_at": (NOW - timedelta(days=10)).isoformat()},
        now=NOW,
    )
    assert v["status"] == "clear"
    assert v["blocking_reasons"] == []
    assert v["water_ec_ds_m"] == 2.4
    assert v["maximum_allowed_ec_ds_m"] == 3.0


def test_gate_blocks_when_ec_exceeds_limit():
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality={"ec_ds_m": 4.1, "sampled_at": (NOW - timedelta(days=5)).isoformat()},
        now=NOW,
    )
    assert v["status"] == "blocked"
    assert WATER_SALINITY_LIMIT_EXCEEDED in v["blocking_reasons"]


def test_gate_blocks_when_limit_set_but_no_sample():
    # A configured limit with no measured sample fails closed — the limit is unverifiable.
    v = evaluate_water_salinity_gate(maximum_allowed_ec_ds_m=3.0, water_quality=None, now=NOW)
    assert v["status"] == "blocked"
    assert WATER_QUALITY_REQUIRED in v["blocking_reasons"]


def test_gate_blocks_on_stale_sample():
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality={"ec_ds_m": 1.0, "sampled_at": (NOW - timedelta(days=800)).isoformat()},
        now=NOW,
    )
    assert v["status"] == "blocked"
    assert WATER_QUALITY_STALE in v["blocking_reasons"]


def test_gate_clear_when_no_limit_configured():
    # No configured maximum ⇒ no limit to enforce ⇒ clear even without a sample.
    v = evaluate_water_salinity_gate(maximum_allowed_ec_ds_m=None, water_quality=None, now=NOW)
    assert v["status"] == "clear"
    assert v["blocking_reasons"] == []


def test_gate_boundary_equal_limit_is_clear():
    # ECw exactly at the limit is allowed (strict > blocks), matching the well-capability rule.
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality={"ec_ds_m": 3.0, "sampled_at": (NOW - timedelta(days=1)).isoformat()},
        now=NOW,
    )
    assert v["status"] == "clear"


# ───────────── dedup regression: build_canonical_well_capability still enforces ─────────────


def _well_inputs(ec: float) -> dict:
    return {
        "tenant_id": "t1",
        "project_id": "p1",
        "water_source": {
            "id": "source-1",
            "commissioned_max_flow_lps": 50.0,
            "maximum_allowed_ec_ds_m": 3.0,
        },
        "well": {"id": "well-1", "water_source_id": "source-1", "sustainable_flow_lps": 44.0},
        "pumping_test": {
            "id": "test-1",
            "status": "certified",
            "tested_at": (NOW - timedelta(days=30)).isoformat(),
            "tested_flow_lps": 48.0,
            "recommended_sustainable_flow_lps": 42.0,
            "recovery_rate_m_h": 5.0,
        },
        "latest_measurement": {
            "id": "m1",
            "static_level_m": 10.0,
            "dynamic_level_m": 18.0,
            "measured_at": (NOW - timedelta(hours=2)).isoformat(),
        },
        "allocation": {"daily_allocation_m3": 1000.0, "daily_used_m3": 100.0},
        "water_quality": {"ec_ds_m": ec, "sampled_at": (NOW - timedelta(days=10)).isoformat()},
        "now": NOW,
    }


def test_build_capability_still_blocks_on_salinity_after_dedup():
    cap = build_canonical_well_capability(**_well_inputs(ec=4.5))
    data = cap.to_dict()
    assert data["status"] == "blocked"
    assert WATER_SALINITY_LIMIT_EXCEEDED in data["blocking_reasons"]


def test_build_capability_verified_when_salinity_clear():
    cap = build_canonical_well_capability(**_well_inputs(ec=2.0))
    data = cap.to_dict()
    assert WATER_SALINITY_LIMIT_EXCEEDED not in data["blocking_reasons"]


# ───────────── H5.1 sensitive-gate tier policy (pure): estimated rejected ─────────────


def _dg(quality: str, ec: float = 2.0, age_days: int = 10) -> dict:
    return {
        "ec_ds_m": ec,
        "sampled_at": (NOW - timedelta(days=age_days)).isoformat(),
        "quality": quality,
    }


def test_gate_rejects_estimated_sample_when_decision_grade_required():
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality=_dg("estimated"),
        now=NOW,
        require_decision_grade=True,
    )
    assert v["status"] == "blocked"
    assert WATER_QUALITY_NOT_DECISION_GRADE in v["blocking_reasons"]


def test_gate_rejects_measured_sample_when_decision_grade_required():
    # `measured` (bare instrument reading) is NOT decision-grade for a sensitive gate.
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality=_dg("measured"),
        now=NOW,
        require_decision_grade=True,
    )
    assert v["status"] == "blocked"
    assert WATER_QUALITY_NOT_DECISION_GRADE in v["blocking_reasons"]


def test_gate_accepts_field_validated_sample():
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality=_dg("field_validated"),
        now=NOW,
        require_decision_grade=True,
    )
    assert v["status"] == "clear", v


def test_gate_accepts_certified_sample_as_laboratory_verified():
    # DB `certified` maps to the canonical laboratory_verified tier — decision-grade.
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality=_dg("certified"),
        now=NOW,
        require_decision_grade=True,
    )
    assert v["status"] == "clear", v


def test_gate_only_lower_grade_present_is_not_decision_grade():
    # Resolver filtered to decision-grade rows (none), but a lower-grade sample exists → distinct.
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality=None,
        now=NOW,
        require_decision_grade=True,
        non_decision_grade_sample_present=True,
    )
    assert v["status"] == "blocked"
    assert WATER_QUALITY_NOT_DECISION_GRADE in v["blocking_reasons"]
    assert WATER_QUALITY_REQUIRED not in v["blocking_reasons"]


def test_gate_no_sample_at_all_is_required_not_grade():
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality=None,
        now=NOW,
        require_decision_grade=True,
        non_decision_grade_sample_present=False,
    )
    assert v["status"] == "blocked"
    assert WATER_QUALITY_REQUIRED in v["blocking_reasons"]
    assert WATER_QUALITY_NOT_DECISION_GRADE not in v["blocking_reasons"]


def test_gate_legacy_path_does_not_require_decision_grade():
    # Backward compat: the well-capability path (require_decision_grade default False) accepts an
    # untagged sample below the limit — unchanged behaviour.
    v = evaluate_water_salinity_gate(
        maximum_allowed_ec_ds_m=3.0,
        water_quality={"ec_ds_m": 2.0, "sampled_at": (NOW - timedelta(days=10)).isoformat()},
        now=NOW,
    )
    assert v["status"] == "clear"


# ─────────────────── static wiring guard: served MPC recommendation ───────────────────


def test_binding_module_owns_server_authoritative_sql():
    # The source is resolved from the server-side binding table, joined to the source limit, with
    # the decision-grade sample filter — the SQL lives in the pure module (exercised by real-PG test).
    assert "field_irrigation_source_assignments" in BIND_SRC
    assert "irrigation_water_sources" in BIND_SRC
    assert "maximum_allowed_ec_ds_m" in BIND_SRC
    assert "irrigation_water_quality_samples" in BIND_SRC
    assert "DECISION_GRADE_SAMPLE_QUALITY_LIST" in BIND_SRC


def test_recommendation_route_derives_source_server_side_and_fails_closed():
    # water_source_id stays on the request but is advisory only (anti-steering), NOT the source.
    assert "water_source_id: str | None" in ROUTE_SRC
    # Server resolves the active binding(s) from SoR — never trusts the client for the source.
    assert "resolve_active_bindings(" in ROUTE_SRC
    assert "_active_field_source_bindings(" in ROUTE_SRC
    # Sensitive gate: decision-grade tier enforced; canonical fail-closed verdict + expert review.
    assert "require_decision_grade=True" in ROUTE_SRC
    assert "evaluate_water_salinity_gate(" in ROUTE_SRC
    assert "water_salinity_gate_blocked" in ROUTE_SRC
    assert "requires_expert_review" in ROUTE_SRC
    # Client bypass closed: a read failure fails closed; a mismatched client source is rejected.
    assert "water_source_binding_unresolved" in ROUTE_SRC
    assert "water_source_binding_mismatch" in ROUTE_SRC


def test_recommendation_route_does_not_trust_client_ecw():
    # No client-supplied ECw on the operational recommendation request — the binding is
    # server-authoritative, resolved from SoR (the old buggy client-source query is gone).
    assert "water_ec: float" not in ROUTE_SRC
    assert "WHERE water_source_id=$1" not in ROUTE_SRC  # the removed latent bug must not return


# ─────────── من «النصّ موجود في الملفّ» إلى «كلّ مُصدِرٍ مرّ بالبوّابة» ───────────
# الحارسُ أعلاه يفحص سلاسلَ نصٍّ في `ROUTE_SRC`، و`ROUTE_SRC` هو **الملفّ كلُّه** وفيه
# أكثرُ من نقطة. فما دام أيُّ مسارٍ يستدعي البوّابة يبقى أخضرَ ولو أصدرت النقاطُ الأخرى
# مرشّحاتٍ بلا فحص — وهو الصنفُ الذي يصفه كتالوج الحرّاس: يمرّ على شجرةٍ سليمة ولم
# يُقَس قطّ أنّه يحمرّ حين يوجد العطل. وهذه الكتلةُ تقلب جهةَ القياس: تُعدّد نقاطَ
# الإصدار من الشجرة النحويّة وتشترط على **كلٍّ** منها بوّابةً سابقة.


def _emitting_functions() -> dict[str, set[str]]:
    """الدوالُّ التي تستدعي `emit_mpc_candidate`، وما تستدعيه كلٌّ منها.

    مُشتَقٌّ من `ast` لا من نصّ: نقطةٌ جديدة تدخل الجردَ تلقائيّاً، فلا يبيت الحارس.
    """
    import ast

    found: dict[str, set[str]] = {}
    for node in ast.walk(ast.parse(ROUTE_SRC)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        called = {
            getattr(call.func, "id", None) or getattr(call.func, "attr", None)
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
        }
        if "emit_mpc_candidate" in called:
            found[node.name] = called
    return found


def test_every_candidate_emission_point_is_gated_on_the_salinity_verdict():
    emitters = _emitting_functions()
    assert emitters, (
        "لا نقطةَ إصدارٍ واحدة في هذا الملفّ. إن كان ذلك مقصوداً فالحارسُ فقد موضوعَه — "
        "احذفه عمداً أو انقله حيث انتقل الإصدار؛ ولا تدعه أخضرَ على الفراغ."
    )
    ungated = sorted(
        name for name, called in emitters.items() if "evaluate_water_salinity_gate" not in called
    )
    assert not ungated, (
        f"نقاطُ إصدارٍ تُصدِر مرشّحاً محكوماً بلا بوّابة ملوحة: {ungated}. "
        "الحدُّ الملحيّ fail-closed لا يُفرَض بوجود نصّه في الملفّ بل بمرور كلّ مُصدِرٍ به."
    )


def test_the_gate_verdict_is_read_not_merely_invoked():
    """استشارةٌ يُهمَل جوابُها تمرّ على أيّ حارسٍ يقيس **وقوعَ** النداء.

    فيُشترَط أن يكون سببُ الحجب المسمّى حاضراً في الدالّة المُصدِرة نفسِها، لا في
    مكانٍ ما من الملفّ.
    """
    import ast

    for node in ast.walk(ast.parse(ROUTE_SRC)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (
            _emitting_functions()
        ):
            body = ast.get_source_segment(ROUTE_SRC, node) or ""
            assert "water_salinity_gate_blocked" in body, (
                f"{node.name} تستدعي البوّابة ولا تحمل سببَ حجبها — "
                "أي أنّ النتيجة قد تُهمَل، وهو ما لا يراه حارسٌ نصّيّ."
            )
