"""اختبارات وحدة لبانـي شبكة حدود الحقل (#15 — Field Boundary Graph).

تختبر الأجزاء النقيّة دون قاعدة بيانات (مجموعة الوحدة لا تملك Postgres):
  - نصّ adjacency_sql() يحوي اللبنات الجوهريّة (ST_Touches / ST_Intersection /
    field_boundary_graph / ON CONFLICT) والتحويل ::geography لطول الحافّة بالمتر.
  - الوحدة تُستورَد بنظافة، وrebuild_graph_for_tenant دالّة async (coroutine).
  - مُحلّل وسم asyncpg (_parse_affected_rows) يحسب الصفوف المتأثّرة صحيحاً.

ملاحظة صدق: السلوك الحيّ (ملء الشبكة فعليّاً عبر ST_Touches على هندسات حقيقيّة)
يُختبَر فقط ضدّ PostGIS حقيقيّ (اختبارات تكامل CI / وقت التشغيل)، لا في مجموعة
الوحدة هذه — لأنّها بلا قاعدة بيانات. هنا نتحقّق من صحّة تصميم SQL والتعاقد فقط.
"""

import inspect

from api.field_boundary_graph import (
    _parse_affected_rows,
    adjacency_sql,
    rebuild_graph_for_tenant,
)


class TestAdjacencySQL:
    def test_contains_st_touches(self):
        assert "ST_Touches" in adjacency_sql()

    def test_contains_st_intersection(self):
        assert "ST_Intersection" in adjacency_sql()

    def test_contains_target_table(self):
        assert "field_boundary_graph" in adjacency_sql()

    def test_contains_on_conflict_upsert(self):
        sql = adjacency_sql()
        assert "ON CONFLICT" in sql
        assert "DO UPDATE" in sql

    def test_uses_geography_for_meters(self):
        # طول الحافّة بالمتر يتطلّب التحويل ::geography (لا درجات 4326)
        sql = adjacency_sql()
        assert "::geography" in sql
        assert "ST_Length" in sql

    def test_guards_null_geoms(self):
        # best-effort: تجاهل الهندسات الفارغة
        assert "geom IS NOT NULL" in adjacency_sql()

    def test_writes_adjacent_relation_type(self):
        assert "'adjacent'" in adjacency_sql()

    def test_conflict_target_matches_unique_constraint(self):
        # القيد الفريد في v58: (tenant_id, field_id, neighbor_field_id, relation_type)
        sql = adjacency_sql()
        for col in ("tenant_id", "field_id", "neighbor_field_id", "relation_type"):
            assert col in sql

    def test_pure_deterministic_output(self):
        # دالّة نقيّة: استدعاءان متتاليان يعطيان النصّ نفسه
        assert adjacency_sql() == adjacency_sql()


class TestRebuildContract:
    def test_rebuild_is_coroutine_function(self):
        assert inspect.iscoroutinefunction(rebuild_graph_for_tenant)

    def test_module_imports_cleanly(self):
        import api.field_boundary_graph as mod

        assert hasattr(mod, "rebuild_graph_for_tenant")
        assert hasattr(mod, "adjacency_sql")


class TestParseAffectedRows:
    def test_parses_insert_tag(self):
        assert _parse_affected_rows("INSERT 0 5") == 5

    def test_parses_zero(self):
        assert _parse_affected_rows("INSERT 0 0") == 0

    def test_none_is_zero(self):
        assert _parse_affected_rows(None) == 0

    def test_empty_is_zero(self):
        assert _parse_affected_rows("") == 0

    def test_garbage_is_zero(self):
        assert _parse_affected_rows("WEIRD") == 0
