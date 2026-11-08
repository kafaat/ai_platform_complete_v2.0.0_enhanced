"""حارس: تبعيّات الحاويات مكتملة — كلّ حزمة طرف-ثالث «ثقيلة» تستوردها خدمة
يجب أن تكون مُعلَنة في requirements الخاصّة بها، وإلّا تتعطّل الحاوية بـ
ModuleNotFoundError عند الإقلاع (ما لا يكشفه smoke المحلّي لأنّ بيئة المطوّر
تملك كلّ الحزم).

كشف هذا الاختبار سابقاً: prometheus_client/asyncpg مفقودة في mcp_servers،
وnumpy/scipy/PyYAML مفقودة في sahool-platform — فتعطّلت الحاويات فعليّاً.

**نقطة عمياء أُغلِقت (DEFERRED-IMPORT-UNDECLARED-01):** كان الكشف نصّيّاً
بتعبير مرتكز على العمود صفر (`^(?:from|import)`)، فالاستيراد **المؤجَّل** داخل
دالّة غير مرئيّ له بالتصميم — والتعليق كان يبرّر ذلك بأنّ ما يهمّ هو الإقلاع.
لكنّ استيراداً مؤجَّلاً لحزمة غير مُعلَنة لا يُلغي العطل، بل **يؤجّله إلى أوّل
استعمال** ويجعله أسوأ تشخيصاً: الحاوية تُقلِع خضراء ثمّ تفشل عند الطلب، وغالباً
برسالة عامّة تُخفي `ModuleNotFoundError` خلف «الخدمة غير متاحة».

فالفحص صار على AST يرصد النوعين ويميّزهما في الرسالة (عطل إقلاع مقابل عطل أوّل
استعمال). والاستيراد المؤجَّل غير المُعلَن يجب أن يُسمَّى في
`docs/architecture/deferred_import_declaration_contract.json`: إمّا
`optional_by_design` (له بديل صادق موثَّق) أو `undeclared_debt` (مُجمَّد، يحتاج
قرار تبعيّة + pip-audit). ويُفرَض عكسيّاً: إدخال بلا مطابقة حيّة يُسقِط الفحص.
"""

import ast
import json
import os
import re
import shlex
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# حزم طرف-ثالث «ثقيلة» إن استوردتها خدمة على المستوى الأعلى وجب إعلانها.
# (اسم الاستيراد → اسم الحزمة في requirements)
CHECK = {
    "numpy": "numpy",
    "scipy": "scipy",
    "pandas": "pandas",
    "prometheus_client": "prometheus-client",
    "asyncpg": "asyncpg",
    "httpx": "httpx",
    "rasterio": "rasterio",
    "pyproj": "pyproj",
    "shapely": "shapely",
    "yaml": "pyyaml",
    "jwt": "pyjwt",
    # python-jose أُزيل (DEP-PYTHON-JOSE-HMAC-PUBKEY-CONFUSION-01): استيرادُه يعود فيُحمَّر
    # هنا بلا إعلان، وفي test_python_jose_absent بإعلان.
    "jose": "python-jose",
    "bcrypt": "bcrypt",
    "qdrant_client": "qdrant-client",
    "edge_tts": "edge-tts",
    "aiomqtt": "aiomqtt",
    "PIL": "pillow",
    "cv2": "opencv",
    "sklearn": "scikit-learn",
    "fastapi": "fastapi",
    "pydantic": "pydantic",
    "aiofiles": "aiofiles",
    "pypdf": "pypdf",
    "aiosmtplib": "aiosmtplib",
    "websockets": "websockets",
    # redis كان غائباً عن هذه الخريطة رغم إعلانه في ثمان خدمات — فغاب عن الحارس
    # صنفٌ كامل: مخزن nonce/حالة يُستورَد كسولاً ولا يُعلَن (DEFERRED-IMPORT-UNDECLARED-01).
    "redis": "redis",
}

CONTRACT = os.path.join(ROOT, "docs/architecture/deferred_import_declaration_contract.json")


def _norm(s: str) -> str:
    return s.lower().replace("_", "-")


def _service_dirs():
    base = os.path.join(ROOT, "services")
    for s in sorted(os.listdir(base)):
        d = os.path.join(base, s)
        if os.path.isdir(d):
            yield s, d


def _read_requirements(path: Path, parents: tuple[Path, ...] = ()) -> str:
    path = path.resolve()
    if path in parents:
        raise ValueError(f"Cyclic requirements include: {path}")
    content = path.read_text(encoding="utf-8")
    parts = [content]
    for line in content.splitlines():
        include = re.match(r"^\s*(?:-r\s*|--requirement(?:\s+|=|$))(.*)$", line)
        if include is None:
            continue
        targets = shlex.split(include.group(1), comments=True)
        if len(targets) != 1 or "://" in targets[0]:
            raise ValueError(f"Expected one local requirements include in {path}: {line}")
        parts.append(_read_requirements(path.parent / targets[0], (*parents, path)))
    return "\n".join(parts)


def _req_text(service_dir: str) -> str | None:
    parts = []
    for pat in ("requirements.txt", "requirements_real.txt", "api/requirements.txt"):
        path = Path(service_dir) / pat
        if path.is_file():
            parts.append(_read_requirements(path))
    return _norm(" ".join(parts)) if parts else None


@pytest.mark.unit
@pytest.mark.parametrize("option", ["-r ", "-r", "--requirement ", "--requirement="])
def test_requirements_includes_resolve_relative_to_each_file(tmp_path, option):
    nested = tmp_path / "nested directory"
    nested.mkdir()
    (tmp_path / "requirements.txt").write_text(
        f"fastapi==0.136.3\n  {option}'nested directory/shared.txt' # included\n",
        encoding="utf-8",
    )
    (nested / "shared.txt").write_text("httpx>=0.27\n-r ../common.txt\n", encoding="utf-8")
    (tmp_path / "common.txt").write_text("NumPy>=1.26\nPillow>=10\n", encoding="utf-8")
    text = _req_text(str(tmp_path))
    assert all(package in text for package in ("fastapi==", "httpx>=", "numpy>=", "pillow>="))


@pytest.mark.unit
def test_requirements_direct_entries_and_shared_includes_are_preserved(tmp_path):
    assert _req_text(str(tmp_path)) is None
    (tmp_path / "api").mkdir()
    direct = {
        "requirements.txt": "NumPy>=1.26\n# existing comment\n",
        "requirements_real.txt": "Pillow>=10\n",
        "api/requirements.txt": "HTTPX>=0.27\n",
    }
    for name, content in direct.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    assert _req_text(str(tmp_path)) == _norm(" ".join(direct.values()))
    (tmp_path / "requirements.txt").write_text("-r common.txt\n-r common.txt\n", encoding="utf-8")
    (tmp_path / "api/requirements.txt").write_text("-r ../common.txt\n", encoding="utf-8")
    (tmp_path / "common.txt").write_text("prometheus_client>=0.19\n", encoding="utf-8")
    assert "prometheus-client>=" in _req_text(str(tmp_path))


@pytest.mark.unit
def test_missing_requirements_include_fails_closed(tmp_path):
    (tmp_path / "requirements.txt").write_text("-r missing.txt\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="missing.txt"):
        _req_text(str(tmp_path))


@pytest.mark.unit
def test_cyclic_requirements_include_fails_closed(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "requirements.txt").write_text("-r nested/shared.txt\n", encoding="utf-8")
    (tmp_path / "nested/shared.txt").write_text(
        "--requirement=../requirements.txt\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Cyclic requirements include"):
        _req_text(str(tmp_path))


@pytest.mark.unit
@pytest.mark.parametrize(
    "line", ["-r", "--requirement=", "-r https://example.com/dependencies.txt"]
)
def test_invalid_or_remote_requirements_include_fails_closed(tmp_path, line):
    (tmp_path / "requirements.txt").write_text(line, encoding="utf-8")
    with pytest.raises(ValueError, match="Expected one local requirements include"):
        _req_text(str(tmp_path))


def _toplevel_thirdparty_imports(service_dir: str) -> set[str]:
    imps = set()
    for root, _dirs, files in os.walk(service_dir):
        if "__pycache__" in root:
            continue
        for fn in files:
            if not fn.endswith(".py") or fn.startswith("test"):
                continue
            for ln in open(os.path.join(root, fn), encoding="utf-8", errors="ignore"):
                # استيراد على المستوى الأعلى فقط (بلا مسافة بادئة) — يُنفَّذ عند الإقلاع
                m = re.match(r"^(?:from|import)\s+([a-zA-Z0-9_]+)", ln)
                if m:
                    imps.add(m.group(1))
    return imps


def _module_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [a.name.split(".")[0] for a in node.names]
    if isinstance(node, ast.ImportFrom) and node.module:
        return [node.module.split(".")[0]]
    return []


def _deferred_thirdparty_imports(service_dir: str) -> dict[str, set[str]]:
    """الاستيراد المؤجَّل (داخل دالّة/شرط) ⇒ {الوحدة: مواضع ``path:line``}.

    يُستثنى ما يظهر أيضاً على المستوى الأعلى في الملفّ نفسه: عندئذٍ العطل يقع عند
    الإقلاع ويلتقطه الفحص الأوّل، فتسجيله مرّتين ضجيج.
    """
    found: dict[str, set[str]] = {}
    for root, _dirs, files in os.walk(service_dir):
        if "__pycache__" in root:
            continue
        for fn in files:
            if not fn.endswith(".py") or fn.startswith("test"):
                continue
            path = os.path.join(root, fn)
            try:
                tree = ast.parse(open(path, encoding="utf-8", errors="ignore").read())
            except SyntaxError:
                continue
            top: set[str] = set()
            for node in tree.body:
                top.update(_module_names(node))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                for mod in _module_names(node):
                    if mod in CHECK and mod not in top:
                        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
                        found.setdefault(mod, set()).add(f"{rel}:{node.lineno}")
    return found


def _contract() -> dict[str, dict]:
    """{"service:module": entry} من فئتَي العقد — الاسم واحد والدلالة مختلفة."""
    raw = json.loads(open(CONTRACT, encoding="utf-8").read())
    out: dict[str, dict] = {}
    for category in ("optional_by_design", "undeclared_debt"):
        for entry in raw.get(category, []):
            out[f"{entry['service']}:{entry['module']}"] = {**entry, "category": category}
    return out


@pytest.mark.unit
def test_heavy_imports_declared_in_requirements():
    problems = []
    for name, d in _service_dirs():
        reqs = _req_text(d)
        if reqs is None:
            continue  # لا ملفّ requirements (خدمة غير مبنيّة كحاوية بايثون مستقلّة)
        imports = _toplevel_thirdparty_imports(d)
        for mod in sorted(imports):
            if mod not in CHECK:
                continue
            pkg = CHECK[mod]
            if _norm(pkg) not in reqs and _norm(mod) not in reqs:
                problems.append(f"{name}: يستورد '{mod}' لكنّ '{pkg}' غير مُعلَن في requirements")
    assert not problems, "تبعيّات حاويات مفقودة (تتعطّل عند الإقلاع):\n  " + "\n  ".join(problems)


def _undeclared_deferred() -> dict[str, set[str]]:
    """{"service:module": مواضع} لكلّ استيراد مؤجَّل لحزمة ثقيلة غير مُعلَنة."""
    out: dict[str, set[str]] = {}
    for name, d in _service_dirs():
        reqs = _req_text(d)
        if reqs is None:
            continue
        for mod, sites in _deferred_thirdparty_imports(d).items():
            pkg = CHECK[mod]
            if _norm(pkg) not in reqs and _norm(mod) not in reqs:
                out[f"{name}:{mod}"] = sites
    return out


@pytest.mark.unit
def test_deferred_imports_are_declared_or_named_in_the_contract():
    """استيراد مؤجَّل لحزمة غير مُعلَنة: يفشل عند **أوّل استعمال** لا عند الإقلاع.

    الحاوية تُقلِع خضراء ثمّ تنهار عند الطلب — وهو أسوأ من الفشل المبكر لأنّه
    يُقرأ عطلاً في الخدمة الخارجيّة لا نقصاً في الصورة. فكلّ حالة يجب أن تُسمَّى
    في العقد بفئتها وسببها، أو تُعلَن الحزمة.
    """
    contract = _contract()
    problems = []
    for key, sites in sorted(_undeclared_deferred().items()):
        if key not in contract:
            problems.append(f"{key} غير مُدرَج في العقد — مواضع: {sorted(sites)}")
    assert not problems, (
        "استيراد مؤجَّل لحزمة غير مُعلَنة وغير مُسمّاة في العقد "
        f"({os.path.relpath(CONTRACT, ROOT)}):\n  " + "\n  ".join(problems)
    )


@pytest.mark.unit
def test_contract_has_no_stale_entry():
    """إنفاذ عكسيّ: إدخال بلا حالة حيّة مطابقة يُسقِط الفحص.

    وإلّا تراكمت إدخالات ميّتة تُغطّي سلفاً حالةً تعود لاحقاً بلا مراجعة — وهو
    الدرس نفسه المُطبَّق في عقد التوافق الدائم (#735).
    """
    live = set(_undeclared_deferred())
    stale = sorted(set(_contract()) - live)
    assert not stale, (
        f"إدخالات بائتة في عقد الاستيراد المؤجَّل (أُعلِنت الحزمة أو زال الاستيراد): {stale} — أزِلها."
    )
