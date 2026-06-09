"""حارس: تبعيّات الحاويات مكتملة — كلّ حزمة طرف-ثالث «ثقيلة» تستوردها خدمة
يجب أن تكون مُعلَنة في requirements الخاصّة بها، وإلّا تتعطّل الحاوية بـ
ModuleNotFoundError عند الإقلاع (ما لا يكشفه smoke المحلّي لأنّ بيئة المطوّر
تملك كلّ الحزم).

كشف هذا الاختبار سابقاً: prometheus_client/asyncpg مفقودة في mcp_servers،
وnumpy/scipy/PyYAML مفقودة في sahool-platform — فتعطّلت الحاويات فعليّاً.
"""

import os
import re

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
}


def _norm(s: str) -> str:
    return s.lower().replace("_", "-")


def _service_dirs():
    base = os.path.join(ROOT, "services")
    for s in sorted(os.listdir(base)):
        d = os.path.join(base, s)
        if os.path.isdir(d):
            yield s, d


def _req_text(service_dir: str) -> str | None:
    parts = []
    for pat in ("requirements.txt", "requirements_real.txt", "api/requirements.txt"):
        p = os.path.join(service_dir, pat)
        if os.path.isfile(p):
            parts.append(open(p, encoding="utf-8").read())
    return _norm(" ".join(parts)) if parts else None


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
