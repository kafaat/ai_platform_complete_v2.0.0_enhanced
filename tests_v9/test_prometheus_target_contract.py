"""عقدُ أهداف Prometheus — «مُعلَنٌ في الإعدادات» ليس «مكشوفٌ في الخدمة».

وُلد من جولةٍ حيّة على مكدّس محلّيّ (2026-09-16) أبلغت **ثلاثة أهداف ساقطة**، وتبيّن
أنّ الثلاثة ليست عطلَ تشغيلٍ بل تعارضاً دائماً بين الإعدادات والشيفرة:

- `indicators-service` و`weather-service` يُسحَبان على `/metrics` ولا يُعرّفان النقطة
  ⇒ ٤٠٤ ⇒ `up=0` أبداً.
- `edge-inference` كان هدفُه `sahool-edge:8000` بينما الخدمة تُصرّح `EXPOSE 8100`
  وتُشغّل uvicorn عليه ⇒ **رفضُ اتّصال** لا ٤٠٤.

وكلّها صامتة بالمعنى الأسوأ: `prometheus/alerts.yml` يُنبّه على `up == 0` لهذه الوظائف
بالاسم، فالتنبيهُ يُطلِق أبداً حتّى يصير ضجيجاً يُتجاهَل — والمراقبةُ التي تكذب دائماً
أسوأ من غيابها. وسبق أن أُصلح الصنفُ نفسه يدويّاً مرّتين بأسماء DNS خاطئة، ومكتوبٌ
في `prometheus.yml` نفسه؛ فالحارس هنا ليكفّ التكرار.

الحدّ المُعلَن: ساكن. يُثبِت أنّ النقطة مُعرَّفة والمنفذ مطابق، لا أنّ الخدمة تردّ حيّاً.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.v9.yml"
PROM = ROOT / "prometheus/prometheus.yml"
ALERTS = ROOT / "prometheus/alerts.yml"
pytestmark = pytest.mark.unit


def _compose_services() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8")).get("services", {})


def _scrape_targets() -> list[tuple[str, str, str, str]]:
    """(job, host, port, metrics_path) لكلّ هدف ساكن."""
    cfg = yaml.safe_load(PROM.read_text(encoding="utf-8"))
    rows = []
    for job in cfg.get("scrape_configs", []):
        path = job.get("metrics_path", "/metrics")
        for static in job.get("static_configs", []) or []:
            for target in static.get("targets", []) or []:
                host, _, port = target.partition(":")
                rows.append((job["job_name"], host, port, path))
    return rows


def _dockerfile_for(service: dict) -> Path | None:
    """ملفُّ الصورة كما تُسمّيه compose، لا أوّلَ ما يُصادَف في جذر السياق."""
    build = service.get("build")
    if not isinstance(build, dict):
        return None
    named = build.get("dockerfile")
    context = ROOT / (build.get("context") or ".")
    if named:
        candidate = (context / named).resolve()
        return candidate if candidate.is_file() else None
    files = sorted(context.glob("Dockerfile*"))
    return files[0].resolve() if files else None


def _service_root(service: dict) -> Path | None:
    """شجرةُ الخدمة نفسها — **لا سياقُ البناء**.

    مراجعة #1010: كلُّ خدمة هنا تُبنى بـ``context: .`` أي جذرُ المستودع، فالبحثُ
    في السياق كان يمسح الشجرة كلَّها — بما فيها هذا الملفُّ نفسه وهو يحوي النصَّ
    المبحوثَ عنه. فكان الحارسُ يمرّ **ولو حذفت الخدمةُ نقطتَها**: تأكيدٌ كاذب،
    وهو أسوأ من غياب الحارس لأنّه يُقرَأ ضماناً.

    الموضعُ الصحيح مُشتَقٌّ من ``dockerfile`` الذي تُسمّيه compose: مجلّدُه هو شجرةُ
    الخدمة. وإن آل إلى جذر المستودع فالحارسُ **لا يستطيع القياس** ويقول ذلك بدل
    أن يمرّ على مسحٍ شامل.
    """
    dockerfile = _dockerfile_for(service)
    if dockerfile is None:
        return None
    root = dockerfile.parent
    return root if root != ROOT.resolve() and root.is_dir() else None


def _owned_targets():
    """الأهدافُ التي نملك شيفرتها — لا صور منبعيّة جاهزة ولا exporters."""
    services = _compose_services()
    for job, host, port, path in _scrape_targets():
        service = services.get(host)
        if not service or not isinstance(service.get("build"), dict):
            continue
        root = _service_root(service)
        if root is None:
            continue
        yield job, host, port, path, service, root


def _defines_path(root: Path, path: str) -> bool:
    needle = f'"{path}"'
    return any(
        needle in source.read_text(encoding="utf-8", errors="ignore")
        for source in root.rglob("*.py")
        if "__pycache__" not in source.parts
    )


def _alert_job_names() -> set[str]:
    """أسماءُ الوظائف في قواعد التوفّر — بالصيغتين.

    مراجعة #1010: المُحلِّلُ كان يقرأ ``job=~`` وحدها، والقواعدُ تستعمل أيضاً
    ``job="postgres-exporter"`` الحرفيّة؛ فحذفُ هدفِ سحبٍ لأيٍّ منهما كان يمرّ
    والادّعاءُ المُعلَن في هذا الملفّ يصير كاذباً.
    """
    text = ALERTS.read_text(encoding="utf-8")
    names: set[str] = set()
    for match in re.findall(r'job=~"([^"]+)"', text):
        names.update(part for part in match.split("|") if part)
    names.update(re.findall(r'job="([^"|]+)"', text))
    return names


def test_every_scraped_service_we_build_defines_the_scraped_path():
    missing = []
    checked = 0
    for job, host, _port, path, _service, root in _owned_targets():
        checked += 1
        if not _defines_path(root, path):
            missing.append(f"{job} → {host}{path} (لا تعريف في {root.name}/)")
    assert checked >= 10, f"الحارس لم يفحص إلّا {checked} هدفاً — اشتقاقُ شجرة الخدمة انكسر"
    assert not missing, (
        "هدفٌ مُعلَنٌ لخدمةٍ لا تُعرّف النقطة ⇒ ٤٠٤ ⇒ up=0 دائماً وتنبيهٌ يُطلِق أبداً: " + " · ".join(missing)
    )


def _image_ports(dockerfile: Path) -> list[str]:
    """المنافذُ التي تُصرّح بها الصورة: ``EXPOSE`` وإلّا منفذُ أمر التشغيل.

    مراجعة #1010 (مكتومة): كان الفحصُ يتخطّى بصمتٍ كلَّ صورةٍ بلا ``EXPOSE``،
    و`indicators-service` إحدى الخدمات المسحوبة حديثاً وليس في صورتها ``EXPOSE``
    أصلاً — فمنفذُها لم يكن مفحوصاً قطّ، وانزياحُ منفذِ الأمر مستقبلاً كان يمرّ.
    فيُقرأ ``--port N`` و``${PORT:-N}`` من ``CMD``/``ENTRYPOINT`` حين يغيب الإعلان.
    """
    text = dockerfile.read_text(encoding="utf-8")
    ports = re.findall(r"^EXPOSE\s+(\d+)", text, re.M)
    if ports:
        return ports
    ports = re.findall(r'--port["\s,]+\$\{PORT:-(\d+)\}', text)
    ports += re.findall(r'--port["\s,]+(\d+)', text)
    return ports


def test_scrape_port_matches_the_port_the_image_actually_exposes():
    drift, unknown = [], []
    for job, host, port, _path, service, _root in _owned_targets():
        dockerfile = _dockerfile_for(service)
        if dockerfile is None:
            unknown.append(f"{job} → {host} (لا Dockerfile مُسمّى)")
            continue
        declared = _image_ports(dockerfile)
        if not declared:
            # فشلٌ مغلق: منفذٌ لا يُعرَف لا يُعَدّ مطابقاً.
            unknown.append(f"{job} → {host} ({dockerfile.name} بلا EXPOSE ولا منفذِ أمر)")
        elif port not in declared:
            drift.append(f"{job} → {host}:{port} بينما {dockerfile.name} يُصرّح {'/'.join(declared)}")
    assert not unknown, (
        "منفذُ الصورة غيرُ معروف فلا يُقاس التطابق — يُعلَن `EXPOSE` بدل التخطّي الصامت: "
        + " · ".join(unknown)
    )
    assert not drift, (
        "منفذُ السحب يخالف ما تكشفه الصورة ⇒ **رفضُ اتّصال** لا ٤٠٤، وهو أصعب تشخيصاً: "
        + " · ".join(drift)
    )


def test_alerting_on_a_job_requires_that_job_to_exist_in_the_scrape_config():
    """تنبيهٌ باسم وظيفةٍ غير مسحوبة لا يُطلِق أبداً — صمتٌ يُقرأ سلامةً."""
    jobs = {job for job, *_ in _scrape_targets()}
    named = _alert_job_names()
    assert "postgres-exporter" in named, 'المُحلِّل لا يرى الصيغة الحرفيّة job="…"'
    unknown = sorted(named - jobs)
    assert not unknown, f"قاعدةُ تنبيهٍ تسمّي وظائفَ لا يسحبها الإعداد: {unknown}"


def test_the_three_targets_the_live_round_reported_are_covered_now():
    """تثبيتُ الواقعة: الثلاثةُ المُبلَّغ عنها تمرّ الآن بالحارسَين أعلاه."""
    services = _compose_services()
    by_host = {host: (job, port, path) for job, host, port, path in _scrape_targets()}
    for host, expected_port in (
        ("sahool-indicators-service", "8000"),
        ("sahool-weather-service", "8000"),
        ("sahool-edge", "8100"),
    ):
        assert host in by_host, f"{host} لم يعد هدفاً — لا يُحذَف الهدفُ لإسكات التنبيه"
        assert host in services
        _job, port, path = by_host[host]
        assert port == expected_port
        # المسارُ نفسه جزءٌ من العقد: تحويلُ الهدف إلى `/healthz` كان يمرّ لأنّ ذلك
        # المسار موجودٌ في المصدر أيضاً، فيضيع عقدُ Prometheus بلا أن يحمرّ شيء.
        assert path == "/metrics", f"{host} يُسحَب على {path} لا /metrics"
        root = _service_root(services[host])
        assert root is not None and root != ROOT.resolve()
        assert _defines_path(root, path)


@pytest.mark.parametrize(
    ("folder", "host"),
    [
        ("weather-service", "sahool-weather-service"),
        ("indicators-service", "sahool-indicators-service"),
    ],
)
def test_the_advertised_endpoint_actually_answers(monkeypatch, folder, host):
    """مراجعة #1010 (مكتومة): نصُّ المصدر ليس سلوكَ التشغيل.

    تسجيلٌ مكسور أو تبعيّةٌ غائبة أو استثناءٌ في المُعالِج كلُّها تمرّ على فحصٍ نصّيّ
    بينما يستقبل Prometheus ٤٠٤ أو ٥٠٠. هنا يُستورَد التطبيق فعلاً ويُستدعى المسار.

    الحدّ المُعلَن: الخدمتان اللتان تُستورَدان في بيئة الاختبار وحدهما. `edge-inference`
    و`raster-tiler-service` تحتاجان تبعيّاتٍ منبعيّة غير مثبَّتة هنا، فيبقى عليهما
    الفحصُ الساكن أعلاه — ويُعلَن ذلك بدل أن يُقرأ سكوتُهما تغطية.
    """
    import importlib.util

    from fastapi.testclient import TestClient

    directory = ROOT / "services" / folder
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(f"prom_contract_{folder}", directory / "main.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)

    response = TestClient(module.app).get("/metrics")
    assert response.status_code == 200, f"{host} يُعلِن /metrics ويردّ {response.status_code}"
    assert response.headers["content-type"].startswith("text/plain"), (
        "نوعُ المحتوى ليس صيغةَ Prometheus النصّيّة"
    )
