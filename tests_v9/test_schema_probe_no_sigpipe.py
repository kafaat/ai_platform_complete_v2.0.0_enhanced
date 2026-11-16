"""SCHEMA-PROBE-SIGPIPE-141-01: the schema probe must not pipe a long list into ``head``.

``migrations/probe_schema_state.sh`` runs under ``set -euo pipefail``. A pipeline like
``printf '%s\\n' "$missing" | head -1`` lets ``head`` exit before ``printf`` has written the
whole list; ``printf`` then takes SIGPIPE and pipefail turns that into exit 141, so the probe
aborts with SCHEMA_PROBE_FAILED intermittently (an empty schema lists ~576 objects). The
probe now takes the first line by parameter expansion and the first 20 lines with awk over a
here-string. These tests run the probe's own reporting lines on a large list.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "migrations" / "probe_schema_state.sh"
BASH = shutil.which("bash")


def _report_block() -> str:
    """The probe's lines from ``m_tables=`` to the 'remaining omitted' line, verbatim."""
    text = PROBE.read_text(encoding="utf-8")
    start = text.index("m_tables=$(")
    end = text.index("status=INCOMPLETE", start)
    return text[start:end]


def _run(block: str, rows: int) -> subprocess.CompletedProcess[str]:
    script = (
        "set -euo pipefail\n"
        f'missing="$(for i in $(seq 1 {rows}); do printf \'%s|t_%s|table|t_%s|\\n\' "$i" "$i" "$i"; done)"\n'
        'if [ -n "$missing" ]; then :; fi\n'
        + block
        + ("\nfi\n" if "then" in block else "\n")
        + '\necho "FIRST=${first_missing}"\n'
    )
    return subprocess.run([BASH, "-c", script], capture_output=True, text=True, timeout=120)


def test_no_pipeline_into_head_in_the_probe():
    text = PROBE.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text, "the probe is expected to run under pipefail"
    offenders = [ln for ln in text.splitlines() if re.search(r"\|\s*head\b", ln)]
    assert not offenders, f"a pipe into head can SIGPIPE under pipefail: {offenders}"


@pytest.mark.skipif(BASH is None, reason="bash is not installed")
def test_the_probe_reporting_survives_a_list_far_larger_than_a_pipe_buffer():
    proc = _run(_report_block(), rows=40000)
    assert proc.returncode == 0, (
        f"probe reporting died with {proc.returncode}: {proc.stderr[-400:]}"
    )
    assert "FIRST=t_1" in proc.stdout, proc.stdout[-400:]
    shown = [ln for ln in proc.stdout.splitlines() if ln.startswith("  ✗ ")]
    assert len(shown) == 20, f"expected the first 20 objects, got {len(shown)}"


@pytest.mark.skipif(BASH is None, reason="bash is not installed")
def test_negative_control_the_old_pipeline_does_take_sigpipe():
    old = "first_missing=\"$(printf '%s\\n' \"$missing\" | head -1 | cut -d'|' -f2)\"\n"
    proc = _run(old, rows=40000)
    assert proc.returncode == 141, (
        f"the old `printf | head` line should die with SIGPIPE (141), got {proc.returncode}"
    )
