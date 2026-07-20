"""حارس ساكن: لا متغيّر psql (:'var' / :"var") داخل كتلة dollar-quoted في مُشغّلات الهجرة.

عطب staging (2026-07-20): ``EXECUTE '… FROM ' || quote_ident(:'app_role')`` داخل ``DO $$ … $$``
فشل بـ«syntax error at or near ":"» — لأنّ psql **لا يستبدل** متغيّراته داخل السلاسل الدولارية
(تُرسَل حرفيّاً للقاعدة). الإصلاح: تمرير القيمة عبر GUC (set_config) وقراءتها بـcurrent_setting
داخل الكتلة مع format('%I'). هذا الحارس يمنع تكرار النمط في أيّ مُشغّل هجرة.

وحدة صرفة — ``pytest -m unit``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_MIG = _ROOT / "migrations"

# كتل dollar-quoted: $$ … $$ أو $tag$ … $tag$ (غير جشِع، عبر الأسطر).
_DOLLAR_BLOCK = re.compile(r"(\$[A-Za-z_]*\$).*?\1", re.DOTALL)
# متغيّر psql بصيغة colon-quote: :'x' أو :"x".
_PSQL_VAR = re.compile(r""":['"][A-Za-z_][A-Za-z0-9_]*['"]""")


def _runner_files() -> list[Path]:
    return sorted(p for p in _MIG.glob("*.sh") if p.is_file())


def test_migration_runners_present():
    files = _runner_files()
    assert files, "no migration runner *.sh found under migrations/"


def test_no_psql_var_inside_dollar_quoted_block():
    offenders: list[str] = []
    for path in _runner_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for block in _DOLLAR_BLOCK.finditer(text):
            body = block.group(0)
            if _PSQL_VAR.search(body):
                line = text[: block.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(_ROOT)}:~{line}")
    assert not offenders, (
        "psql colon-vars (:'x'/:\"x\") are NOT substituted inside dollar-quoted blocks — "
        f"pass via set_config + current_setting + format('%I') instead: {offenders}"
    )
