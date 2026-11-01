"""S9 — سرّ ZLMediaKit لا يظهر في السجلّ أبداً.

على origin/main cc0d2e295 كان ``check_video_dependencies`` يرسل ``secret`` في استعلام
الرابط، وhttpx يسجّل رابط كلّ طلب INFO ⇒ السرّ في السجلّ عند كلّ فحص جاهزيّة (مقيس).
الإصلاح: السرّ في جسم JSON (ZLMediaKit يدمجه مع وسائط الرابط) + httpx/httpcore إلى
WARNING في معالِج ``setup_logging`` + مرشّح تنقيح ``secret=``… في ``shared/logging_config``.

الفحص السلوكيّ يُشغَّل في عمليّة فرعيّة (cwd=services/video-processor) فيُلتقَط **كلّ**
ما يكتبه معالِج السجلّ الحقيقيّ إلى stdout/stderr، بلا تصادم ``import main``.
"""

from __future__ import annotations

import importlib.util
import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "services" / "video-processor"
SECRET = "zlm-S9-canary-7f3a91c2"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_readiness_probe_never_writes_the_zlm_secret_to_logs():
    pytest.importorskip("fastapi")
    pytest.importorskip("numpy")
    script = f"""
import asyncio, json
import httpx

seen = {{"urls": [], "bodies": []}}

def handler(request):
    seen["urls"].append(str(request.url))
    seen["bodies"].append(request.content.decode("utf-8", "replace"))
    return httpx.Response(200, json={{"code": 0, "data": []}})

_Orig = httpx.AsyncClient

class _Mocked(_Orig):
    def __init__(self, *a, **k):
        k["transport"] = httpx.MockTransport(handler)
        super().__init__(*a, **k)

httpx.AsyncClient = _Mocked
import main  # يضبط setup_logging("video-processor") الحقيقيّ عند الاستيراد

out = asyncio.run(main.check_video_dependencies())
zlm = [i for i, u in enumerate(seen["urls"]) if "getMediaList" in u]
print(json.dumps({{
    "ok": out["zlmediakit"]["ok"],
    "probed": bool(zlm),
    "secret_in_url": any({SECRET!r} in seen["urls"][i] for i in zlm),
    "secret_in_body": any({SECRET!r} in seen["bodies"][i] for i in zlm),
}}))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=VIDEO,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT),
            "ZLMEDIAKIT_API_SECRET": SECRET,
            "SAHOOL_ENV": "development",
            "LOG_LEVEL": "DEBUG",
            "ZLMEDIA_API_URL": "http://zlm.invalid",
            "EDGE_INFERENCE_URL": "http://edge.invalid",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    res = json.loads(proc.stdout.splitlines()[-1])
    assert res["probed"] and res["ok"], res
    # السرّ ما زال يُرسَل (المصادقة تعمل) — لكن في الجسم لا في الرابط.
    assert res["secret_in_body"] is True, res
    assert res["secret_in_url"] is False, res
    logs = proc.stdout + proc.stderr
    assert SECRET not in logs, "سرّ ZLMediaKit ظهر في السجلّ:\n" + logs[-2000:]


def test_zlmedia_client_default_transport_keeps_secret_out_of_url(monkeypatch):
    httpx = pytest.importorskip("httpx")
    zc = _load("zlmedia_client_s9", VIDEO / "zlmedia_client.py")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": 0})

    orig = httpx.Client

    class _Mocked(orig):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **k)

    monkeypatch.setattr(zc.httpx, "Client", _Mocked)
    out = zc.ZLMediaKitClient(base_url="http://zlm.invalid", secret=SECRET).get_media_list()
    assert out["ok"] is True
    assert SECRET not in str(seen[0].url)
    assert json.loads(seen[0].content)["secret"] == SECRET


def test_logging_config_redacts_secret_params_and_quiets_httpx():
    lc = _load("logging_config_s9", ROOT / "shared" / "logging_config.py")
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(lc.JSONFormatter("t"))
    handler.addFilter(lc.SecretRedactionFilter())
    log = logging.getLogger("s9.redaction.probe")
    log.propagate = False
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        log.info(
            'HTTP Request: %s %s "HTTP/1.1 200 OK"',
            "GET",
            f"http://zlm/index/api/getMediaList?app=live&secret={SECRET}&token=tok-{SECRET}",
        )
        try:
            raise RuntimeError(f"boom http://zlm/x?api_key={SECRET}")
        except RuntimeError:
            log.exception("failed")
    finally:
        log.removeHandler(handler)
    text = buf.getvalue()
    assert SECRET not in text, text
    assert "secret=***" in text and "token=***" in text and "app=live" in text

    # setup_logging يُسقط سجلّات httpx/httpcore دون WARNING **في معالِجه** دون أن يخفض
    # مستوى المُسجِّلَين عالميّاً (خفضٌ عالميّ أسكت مرشّح تنقيح رابط بوت Telegram في
    # agents/notification — test_tts_voice_delivery_receipt). عمليّة فرعيّة: لا يمسّ جذر pytest.
    probe = (
        "import logging; from shared.logging_config import setup_logging; "
        "setup_logging('t'); "
        f"u = 'http://zlm/index/api/getMediaList?app=live&secret={SECRET}'; "
        "logging.getLogger('httpx').info('HTTP Request: GET %s', u + '&probe=info'); "
        "logging.getLogger('httpcore.http11').debug('send %s', u + '&probe=debug'); "
        "logging.getLogger('httpx').warning('HTTP Request: GET %s', u + '&probe=warning'); "
        "logging.getLogger('t').info('app line kept'); "
        "print('LEVELS', logging.getLogger('httpx').level, logging.getLogger('httpcore').level)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT), "LOG_LEVEL": "DEBUG"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout + proc.stderr
    assert SECRET not in out, out
    assert "probe=info" not in out and "probe=debug" not in out, out
    assert "probe=warning" in out and "secret=***" in out, out
    assert "app line kept" in out, out
    assert "LEVELS 0 0" in out, out  # لا حالة عالميّة على المُسجِّلَين
