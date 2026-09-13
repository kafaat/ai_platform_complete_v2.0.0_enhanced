"""نطاقُ استثناءات Gitleaks المساريّة — كلُّ مدخلٍ يُعفي ملفّاً واحداً مُسمّى (C05).

المقيس بـgitleaks 8.24.3 محلّيّاً على شجرة #997: مدخلُ `docs/audits/patches/.*\\.patch$`
جعل الماسحَ **يتخطّى الملفَّ كلَّه** («Skipping file due to global allowlist»)، فملفُّ
patch جديدٌ يحمل توكناً اصطناعيّاً مرّ بلا إبلاغ؛ وبعد تضييقه إلى ملفّ SUP-08 وحده
أُبلِغ التوكن. فالاستثناءُ المساريّ إعفاءٌ كاملٌ لا تخفيفٌ، ويجب أن يُسمّي ملفّاً بعينه.

الحارسُ لا يحتاج الأداة: يقرأ `.gitleaks.toml` ويطابق تعبيراتِ `paths` على الملفّات
المتعقَّبة، فيفرض (١) أنّ كلَّ مدخلٍ يصيب ملفّاً متعقَّباً واحداً بالضبط، و(٢) أنّ
ملفّاً افتراضيّاً جديداً في المجلّد نفسه لا يصيبه أيُّ مدخل.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".gitleaks.toml"


def _allowlist_paths() -> list[str]:
    data = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    return list(data["allowlist"]["paths"])


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def test_every_path_allowlist_entry_names_exactly_one_tracked_file():
    tracked = _tracked()
    for pattern in _allowlist_paths():
        matches = [p for p in tracked if re.search(pattern, p)]
        assert len(matches) == 1, (
            f"مدخلُ الاستثناء {pattern!r} يصيب {len(matches)} ملفّاً متعقَّباً {matches[:5]} — "
            "الاستثناءُ المساريّ يُعفي الملفَّ كلَّه فيجب أن يُسمّي ملفّاً واحداً"
        )


@pytest.mark.parametrize(
    "hypothetical",
    [
        "docs/audits/patches/NEW-review.patch",
        "docs/audits/patches/SUP-09-anything.patch",
        "scripts/ci/some_other_guard.py",
        "scripts/release/scan_release_archive_v2.py",
    ],
)
def test_a_new_file_beside_an_allowlisted_one_is_still_scanned(hypothetical: str):
    for pattern in _allowlist_paths():
        assert not re.search(pattern, hypothetical), (
            f"{pattern!r} يُعفي {hypothetical} — مدخلٌ جامع يُخفي سرّاً في ملفٍّ لاحق"
        )
