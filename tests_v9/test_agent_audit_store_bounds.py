"""The agent audit store stays bounded in record count and record size.

Every chat tool call appends an audit record. Both backends used to grow without limit
(in-memory list, Redis RPUSH) and kept the full tool ``result`` (field data, grids) and
``params`` (a caller-supplied grid) in every record.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import agent_stores as S  # noqa: E402


class _FakeRedisList:
    def __init__(self):
        self.items: list[str] = []

    def rpush(self, key, value):
        self.items.append(value)
        return len(self.items)

    def ltrim(self, key, start, end):
        n = len(self.items)
        start = start + n if start < 0 else start
        end = end + n if end < 0 else end
        self.items = self.items[max(0, start) : end + 1]

    def lrange(self, key, start, end):
        n = len(self.items)
        start = start + n if start < 0 else start
        end = end + n if end < 0 else end
        return [v.encode() for v in self.items[max(0, start) : end + 1]]


def _big_record(i: int) -> dict:
    grid = [[0.5] * 200 for _ in range(200)]
    return {
        "seq": i,
        "tool": "generate_productivity_zones",
        "outcome": "executed",
        "input_hash": f"h{i}",
        "result_summary": "ok",
        "params": {"field_id": "f1", "ndvi_grid": grid},
        "result": {"productivity_zones": [{"geometry": grid}]},
    }


def _stores(max_records: int):
    yield S.InMemoryAuditStore(max_records=max_records)
    fake = _FakeRedisList()
    yield S.RedisAuditStore(fake, max_records=max_records)


@pytest.mark.parametrize("which", [0, 1])
def test_audit_store_keeps_only_the_last_n_records(which):
    st = list(_stores(5))[which]
    for i in range(12):
        st.append({"seq": i, "result": {"reason": "x"}})
    recent = st.recent(100)
    assert [r["seq"] for r in recent] == [7, 8, 9, 10, 11]
    if which == 1:
        assert len(st._c.items) == 5


@pytest.mark.parametrize("which", [0, 1])
def test_audit_store_keeps_a_bounded_summary_not_the_raw_result(which):
    st = list(_stores(10))[which]
    st.append(_big_record(1))
    rec = st.recent(1)[0]
    assert len(json.dumps(rec)) < 4 * S.AUDIT_FIELD_MAX_BYTES + 1024
    # Fields existing consumers read are kept verbatim.
    for key in ("seq", "tool", "outcome", "input_hash", "result_summary"):
        assert rec[key] == _big_record(1)[key]
    assert rec["result"]["truncated"] is True
    assert rec["result"]["keys"] == ["productivity_zones"]
    assert len(rec["result"]["sha256"]) == 64
    assert rec["params"]["truncated"] is True
    assert rec["params"]["keys"] == ["field_id", "ndvi_grid"]


def test_small_results_are_kept_verbatim():
    st = S.InMemoryAuditStore()
    st.append({"seq": 1, "result": {"reason": "denied_by_user"}, "params": {"field_id": "f1"}})
    rec = st.recent(1)[0]
    assert rec["result"] == {"reason": "denied_by_user"}
    assert rec["params"] == {"field_id": "f1"}


def test_default_cap_and_env_override(monkeypatch):
    monkeypatch.delenv("SAHOOL_AGENT_AUDIT_MAX_RECORDS", raising=False)
    assert S.InMemoryAuditStore()._max == 10_000
    monkeypatch.setenv("SAHOOL_AGENT_AUDIT_MAX_RECORDS", "250")
    assert S.InMemoryAuditStore()._max == 250
    for bad in ("0", "-3", "nope"):
        monkeypatch.setenv("SAHOOL_AGENT_AUDIT_MAX_RECORDS", bad)
        assert S.InMemoryAuditStore()._max == 10_000
