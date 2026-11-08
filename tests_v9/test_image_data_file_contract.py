"""Unit: data files a module reads at runtime must actually be in the image (G3 · I2).

«موجودٌ في المستودع» ليس «موجودٌ في الصورة». مقيس 2026-11-01 على ``cc0d2e295``:

* **G3** — ``shared/knowledge/source_registry.py`` يقرأ
  ``docs/architecture/knowledge_source_registry.json``، وصورة المنصّة تنسخ ``shared/`` و
  ``services/sahool-platform/`` فقط، و``.dockerignore`` يستبعد ``docs/``. فكلّ توصية ريّ
  ساعيّة (MPC) حُجِبت بـ``knowledge_context_unsatisfied`` في كلّ بيئة منشورة.
* **I2** — ``services/raster-service/terrain_source_registry.py`` يقرأ
  ``config/terrain_sources.yml``، وصورة الراستر لا تنسخه؛ بل كان الافتراضيّ ``parents[2]``
  مستحيلاً في ``/app`` (عنصران فقط) فيرفع الاستيراد نفسه ``IndexError``.

**المسار المتوقَّع داخل الصورة يُشتقّ من المُحمِّل نفسه** (لا يُنسَخ هنا نصّاً): نُموضِع
الوحدة حيث يضعها ``COPY``، ونسأل المُحمِّل أين سيبحث، ثمّ نتحقّق أنّ ``COPY`` يضع الملفّ
هناك وأنّ ``.dockerignore`` لا يستبعده — بدلالات Docker (آخِرُ نمطٍ مطابق يحكم، و``!``
يُعيد الإدراج، ونمطُ الدليل يشمل أبناءه).

ويُفحَص كلّ Dockerfile تحمل صورتُه مستهلكاً لـ``shared.knowledge`` — لا المنصّة وحدها —
فصورةٌ جديدة تستوردها بلا السجلّ تحمرّ هنا قبل أن تُنشَر.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RASTER = ROOT / "services" / "raster-service"
if str(RASTER) not in sys.path:
    sys.path.insert(0, str(RASTER))

import terrain_source_registry as tsr  # noqa: E402

from shared.knowledge import source_registry as ksr  # noqa: E402

KNOWLEDGE_MODULE = "shared/knowledge/source_registry.py"
KNOWLEDGE_DATA = "docs/architecture/knowledge_source_registry.json"
TERRAIN_MODULE = "services/raster-service/terrain_source_registry.py"
TERRAIN_DATA = "config/terrain_sources.yml"

_COPY = re.compile(r"^\s*(?:COPY|ADD)\s+(.*)$", re.IGNORECASE)
_KNOWLEDGE_IMPORT = re.compile(r"^\s*(?:from|import)\s+shared\.knowledge\b", re.MULTILINE)


# ── دلالات Docker: .dockerignore ────────────────────────────────────────────


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            continue
        char = pattern[i]
        out += "[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char)
        i += 1
    return re.compile(out)


def dockerignore_rules(context: Path) -> list[tuple[bool, re.Pattern[str]]]:
    """(استثناء؟، نمط) بترتيب الملفّ — الاستثناء ``!`` يُعيد الإدراج."""
    path = context / ".dockerignore"
    if not path.is_file():
        return []
    rules = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        line = line[1:].strip() if negate else line
        line = line.strip("/")
        if line:
            rules.append((negate, _pattern_regex(line)))
    return rules


def is_ignored(rel: str, rules: list[tuple[bool, re.Pattern[str]]]) -> bool:
    """آخرُ قاعدةٍ تُطابق المسار **أو أحد آبائه** تحكم (منطق moby/patternmatcher)."""
    parts = rel.split("/")
    prefixes = ["/".join(parts[: i + 1]) for i in range(len(parts))]
    ignored = False
    for negate, rx in rules:
        if any(rx.fullmatch(prefix) for prefix in prefixes):
            ignored = not negate
    return ignored


# ── دلالات Docker: COPY ─────────────────────────────────────────────────────


def copy_instructions(dockerfile: Path) -> list[tuple[list[str], str]]:
    text = re.sub(r"\\\n", " ", dockerfile.read_text(encoding="utf-8"))
    out = []
    for line in text.splitlines():
        match = _COPY.match(line)
        if not match:
            continue
        tokens = match.group(1).split()
        if any(token.startswith("--from=") for token in tokens):
            continue
        parts = [token for token in tokens if not token.startswith("--")]
        if len(parts) >= 2:
            out.append((parts[:-1], parts[-1]))
    return out


def image_paths(dockerfile: Path, rel: str, *, context: Path = ROOT) -> set[str]:
    """كلّ مسارٍ في الصورة يضع فيه هذا الـDockerfile ملفّ المستودع ``rel`` (فارغ = غائب)."""
    if not (context / rel).is_file() or is_ignored(rel, dockerignore_rules(context)):
        return set()
    landed: set[str] = set()
    for sources, dest in copy_instructions(dockerfile):
        for source in sources:
            src = source.strip("/").removeprefix("./")
            if src in ("", "."):
                landed.add(dest.rstrip("/") + "/" + rel)
            elif (context / src).is_dir() and rel.startswith(src + "/"):
                landed.add(dest.rstrip("/") + "/" + rel[len(src) + 1 :])
            elif src == rel:
                directory = dest.endswith("/") or len(sources) > 1
                landed.add(dest.rstrip("/") + "/" + Path(rel).name if directory else dest)
    return landed


def _single_image_path(dockerfile: Path, rel: str) -> str:
    paths = image_paths(dockerfile, rel)
    assert len(paths) == 1, f"{dockerfile.relative_to(ROOT)} يضع {rel} في {sorted(paths)}"
    return paths.pop()


def _dockerfiles() -> list[Path]:
    found = list(ROOT.glob("services/*/Dockerfile*")) + list(ROOT.glob("agents/*/Dockerfile*"))
    found += list(ROOT.glob("bots/*/Dockerfile*"))
    return sorted(path for path in found if path.is_file())


def _imports_shared_knowledge(dockerfile: Path) -> bool:
    """هل تحمل الصورة وحدةً (خارج الحزمة نفسها) تستورد ``shared.knowledge``؟"""
    for sources, _dest in copy_instructions(dockerfile):
        for source in sources:
            rel = source.strip("/").removeprefix("./")
            # `shared/` ينسخه الأسطول كلّه؛ المستهلك هو ما **يستورد** الحزمة لا ما يحملها.
            # و`.` نسبيٌّ إلى سياقٍ قد لا يكون الجذر — لا يُخمَّن.
            if rel in ("", ".", "shared", "shared/knowledge") or not (ROOT / rel).exists():
                continue
            src = ROOT / rel
            files = [src] if src.is_file() else src.rglob("*.py")
            for path in files:
                if path.suffix != ".py" or "shared/knowledge" in path.as_posix():
                    continue
                if _KNOWLEDGE_IMPORT.search(path.read_text(encoding="utf-8", errors="ignore")):
                    return True
    return False


# ── الاختبارات ──────────────────────────────────────────────────────────────


def test_the_dockerignore_matcher_follows_docker_semantics():
    """مُطابِقٌ مكسور يجعل كلّ ما يليه أخضرَ زوراً — فيُقاس أوّلاً على حالاتٍ معروفة."""
    rules = [(False, _pattern_regex("docs")), (True, _pattern_regex("docs/a/keep.json"))]
    assert is_ignored("docs/a/other.json", rules)
    assert is_ignored("docs", rules)
    assert not is_ignored("docs/a/keep.json", rules)
    assert not is_ignored("services/x/docs/readme.md", rules), "الأنماط مُرسّاة على جذر السياق"
    assert is_ignored("a/b/c.pyc", [(False, _pattern_regex("**/*.pyc"))])


def test_the_knowledge_registry_is_shipped_where_the_platform_loader_looks():
    dockerfile = ROOT / "services" / "sahool-platform" / "Dockerfile"
    module_in_image = _single_image_path(dockerfile, KNOWLEDGE_MODULE)
    expected = ksr.default_registry_path(module_in_image).as_posix()
    assert expected in image_paths(dockerfile, KNOWLEDGE_DATA), (
        f"المنصّة تقرأ {expected} ولا COPY يضعه هناك (أو .dockerignore يستبعده) — "
        "كلّ توصية ريّ ساعيّة ستُحجَب بـknowledge_context_unsatisfied"
    )


def test_every_image_that_imports_shared_knowledge_ships_the_registry():
    consumers = [path for path in _dockerfiles() if _imports_shared_knowledge(path)]
    assert consumers, "لا صورة تستورد shared.knowledge — المسح أعمى، لا «لا مشكلة»"
    for dockerfile in consumers:
        module_in_image = _single_image_path(dockerfile, KNOWLEDGE_MODULE)
        expected = ksr.default_registry_path(module_in_image).as_posix()
        assert expected in image_paths(dockerfile, KNOWLEDGE_DATA), (
            f"{dockerfile.relative_to(ROOT)} يستورد shared.knowledge بلا {KNOWLEDGE_DATA}"
        )


def test_the_terrain_registry_is_shipped_where_the_raster_loader_looks():
    dockerfiles = [path for path in _dockerfiles() if image_paths(path, TERRAIN_MODULE)]
    assert dockerfiles, "لا صورة تحمل terrain_source_registry.py — المسح أعمى"
    for dockerfile in dockerfiles:
        module_in_image = _single_image_path(dockerfile, TERRAIN_MODULE)
        expected = {p.as_posix() for p in tsr.config_candidates(module_in_image)}
        assert expected & image_paths(dockerfile, TERRAIN_DATA), (
            f"{dockerfile.relative_to(ROOT)}: الراستر يبحث في {sorted(expected)} ولا COPY "
            f"يضع {TERRAIN_DATA} هناك"
        )


def test_the_docs_exception_is_one_file_not_the_tree():
    """الاستثناء ضيّق: بقيّة ``docs/`` (ومنها شقيقات السجلّ) تبقى خارج سياق البناء."""
    rules = dockerignore_rules(ROOT)
    assert not is_ignored(KNOWLEDGE_DATA, rules)
    siblings = [
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "docs" / "architecture").iterdir()
        if p.is_file() and p.name != Path(KNOWLEDGE_DATA).name
    ]
    assert siblings
    assert all(is_ignored(rel, rules) for rel in siblings)
    assert is_ignored("docs/README.md", rules)


# ── المُحمِّلان: مسارٌ صامد وفشلٌ صريح ──────────────────────────────────────


def test_the_terrain_loader_resolves_an_image_layout_without_index_error():
    """``/app/terrain_source_registry.py`` له أبوان فقط؛ ``parents[2]`` كان يرفع."""
    assert tsr.config_candidates("/app/terrain_source_registry.py")[0] == Path(
        "/app/config/terrain_sources.yml"
    )
    assert tsr.default_config_path().is_file(), "المرشّح المستودعيّ يجد السجلّ محلّيّاً"


def test_a_missing_terrain_registry_is_reported_not_swallowed(tmp_path, caplog, monkeypatch):
    absent = tmp_path / "terrain_sources.yml"
    monkeypatch.setenv("TERRAIN_SOURCES_CONFIG", str(absent))
    assert tsr.registry_readable() is False
    with caplog.at_level("ERROR", logger=tsr.logger.name):
        assert tsr.load_terrain_sources(field_dem_path="") == []
    assert str(absent) in caplog.text


def test_the_knowledge_registry_env_override_is_honoured(monkeypatch):
    monkeypatch.setenv(ksr.REGISTRY_ENV, str(ROOT / KNOWLEDGE_DATA))
    assert ksr.registry_path() == ROOT / KNOWLEDGE_DATA
    monkeypatch.delenv(ksr.REGISTRY_ENV)
    assert ksr.registry_path() == ksr.REGISTRY_PATH
    assert ksr.REGISTRY_PATH == ROOT / KNOWLEDGE_DATA


def test_a_missing_knowledge_registry_raises_a_message_that_names_the_fix(tmp_path, monkeypatch):
    absent = tmp_path / "absent.json"
    monkeypatch.setenv(ksr.REGISTRY_ENV, str(absent))
    with pytest.raises(ksr.RegistryError) as raised:
        ksr.load_registry()
    message = str(raised.value)
    assert str(absent) in message
    assert KNOWLEDGE_DATA in message and ksr.REGISTRY_ENV in message


def test_the_knowledge_readiness_check_reports_a_missing_registry(tmp_path, monkeypatch):
    """الغياب يُعلَن مرّةً في ``/readyz`` لا صمتاً عند كلّ توصية (المسار في اختبار المنصّة)."""
    ksr.registry.cache_clear()
    monkeypatch.setenv(ksr.REGISTRY_ENV, str(tmp_path / "absent.json"))
    try:
        missing = ksr.readiness_check()
    finally:
        ksr.registry.cache_clear()
    assert missing["ok"] is False and "absent.json" in missing["error"]

    monkeypatch.delenv(ksr.REGISTRY_ENV)
    present = ksr.readiness_check()
    assert present["ok"] is True and present["count"] > 0
