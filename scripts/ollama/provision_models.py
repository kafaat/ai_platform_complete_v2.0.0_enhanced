#!/usr/bin/env python3
"""provision_models.py — تهيئةُ نماذج Ollama لمرّةٍ واحدة قبل مستهلكيها (``sahool-ollama-models``).

**العطلُ المقيس** (تدقيقُ التشغيل الحيّ 2026-09-29، ``docker-compose.v9.yml`` على آلةٍ نظيفة):
فحصُ صحّة ``sahool-ollama`` هو ``ollama list`` — ينجح وفي Ollama **صفرُ نماذج**. و``sahool-qdrant-seed``
(``restart: no``) كان يشترط ``service_healthy`` عليه وحده، فأقلع قبل وجود أيّ نموذج: أوّلُ تضمينٍ عاد
``404 model not found`` فخرج البذرُ بـ1 ولم يُعِده أحد — Qdrant بصفر مجموعات. وسحبَ ``local-ai-rag``
النماذجَ بنفسه ثمّ استسلم بعد محاولاته، فأعاد ``rag-retrieval`` 503 و``ai-agronomist`` 502 بينما
Docker يُظهرها كلَّها ``healthy``. فـ«الـAPI حيّ» كان يُقرَأ «النموذجُ حاضر».

**العقد:** يخرج ``0`` فقط حين يكون كلُّ نموذجٍ مطلوب حاضراً في Ollama **ونموذجُ التضمين يُضمِّن
فعلاً** (متّجهٌ منتهٍ غيرُ فارغ — بُعدُه يُقاس ويُطبَع، لا يُفترَض). وإلّا يخرج ``1`` بسببٍ مُسمّى،
فلا يُقلِع ``qdrant-seed`` ولا ``local-ai-rag`` ولا ``rag-retrieval``
(``depends_on: service_completed_successfully``) — فشلٌ عند ``compose up`` بدل خُضرةٍ فوق 503.

* السحبُ متدفّق (NDJSON) بمهلةِ **ركود** لا مهلةٍ كلّيّة: نموذجٌ بـ2GB على خطٍّ بطيء ليس فشلاً ما دام
  التقدّمُ يصل، وسطرُ ``{"error": …}`` داخل التدفّق فشلٌ ولو كان الردّ 200.
* كلُّ سحبٍ يُعاد بحدود (``OLLAMA_PROVISION_PULL_ATTEMPTS``) وتراجعٍ أسّيٍّ مسقوف؛ Ollama يستأنف
  الطبقاتِ الجزئيّة، فالإعادةُ لا تبدأ من الصفر.
* نموذجُ التوليد يُثبَت حضورُه (``/api/show``) ولا يُحمَّل — تحميلُه بارداً كلفةُ أوّلِ استعمال.

مكتبةٌ قياسيّة فقط: يعمل في ``python:3.11-slim-bookworm`` بلا ``pip``. الاختبار:
``tests_v9/test_ollama_model_provisioning.py``.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass

DEFAULT_BASE_URL = "http://sahool-ollama:11434"
EMBED_PROBE_PROMPT = "SAHOOL model provisioning probe"


class ProvisionError(Exception):
    """فشلٌ مُسمّى: ``code`` ثابتٌ يُبحَث عنه في السجلّ، و``detail`` يقول ما قِيس."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Config:
    base_url: str
    embed_model: str
    generation_model: str
    pull_attempts: int = 5
    backoff_base_s: float = 5.0
    backoff_cap_s: float = 60.0
    api_wait_s: float = 300.0
    stall_timeout_s: float = 600.0


def canonical(name: str) -> str:
    """Ollama يُعيد وسم ``latest`` صراحةً لطلبٍ بلا وسم — المقارنةُ على الشكل القانونيّ."""
    name = name.strip()
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"


def _number(env: Mapping[str, str], key: str, default: float, *, integer: bool = False) -> float:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw) if integer else float(raw)
    except ValueError as exc:
        raise ProvisionError("OLLAMA_PROVISION_CONFIG", f"{key}={raw!r} is not a number") from exc
    if not math.isfinite(value) or value < (1 if integer else 0):
        raise ProvisionError("OLLAMA_PROVISION_CONFIG", f"{key}={raw!r} is out of range")
    return value


def load_config(env: Mapping[str, str]) -> Config:
    embed = (env.get("OLLAMA_REQUIRED_EMBED_MODEL") or "").strip()
    generation = (env.get("OLLAMA_REQUIRED_GENERATION_MODEL") or "").strip()
    missing = [
        key
        for key, value in (
            ("OLLAMA_REQUIRED_EMBED_MODEL", embed),
            ("OLLAMA_REQUIRED_GENERATION_MODEL", generation),
        )
        if not value
    ]
    if missing:
        # لا افتراضَ صامت لاسم نموذج: القائمةُ تُعلَن في compose بجوار مستهلكيها وتُطابَق باختبار.
        raise ProvisionError("OLLAMA_PROVISION_CONFIG", f"required model not declared: {missing}")
    return Config(
        base_url=((env.get("OLLAMA_BASE_URL") or "").strip() or DEFAULT_BASE_URL).rstrip("/"),
        embed_model=embed,
        generation_model=generation,
        pull_attempts=int(_number(env, "OLLAMA_PROVISION_PULL_ATTEMPTS", 5, integer=True)),
        backoff_base_s=_number(env, "OLLAMA_PROVISION_BACKOFF_BASE_S", 5.0),
        backoff_cap_s=_number(env, "OLLAMA_PROVISION_BACKOFF_CAP_S", 60.0),
        api_wait_s=_number(env, "OLLAMA_PROVISION_API_WAIT_S", 300.0),
        stall_timeout_s=_number(env, "OLLAMA_PROVISION_STALL_TIMEOUT_S", 600.0),
    )


def backoff_seconds(attempt: int, *, base: float, cap: float) -> float:
    """``base·2^(attempt-1)`` مسقوفاً بـ``cap`` — بمضاعفةٍ محدودة لا أسٍّ مفتوح."""
    delay = float(base)
    for _ in range(max(0, attempt - 1)):
        if delay >= cap:
            break
        delay *= 2
    return float(min(cap, delay))


def _error_text(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — جسمٌ غير مقروء لا يُخفي رمز الحالة
        body = ""
    try:
        return str(json.loads(body).get("error") or body)[:300]
    except (ValueError, AttributeError):
        return body[:300]


class OllamaClient:
    """عميلُ HTTP صغير لـOllama (``urllib``) — ما يقرؤه المستهلكون بالضبط، لا واجهةٌ أوسع."""

    def __init__(self, base_url: str, *, timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _json(
        self, method: str, path: str, payload: dict | None = None, timeout: float | None = None
    ):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with urllib.request.urlopen(req, timeout=timeout or self.timeout_s) as resp:  # noqa: S310 - internal Ollama URL
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}

    def version(self) -> str:
        return str(self._json("GET", "/api/version").get("version") or "")

    def installed(self) -> set[str]:
        models = self._json("GET", "/api/tags").get("models") or []
        return {
            canonical(str(m.get("name") or m.get("model") or ""))
            for m in models
            if isinstance(m, dict)
        }

    def pull(self, model: str, *, stall_timeout_s: float, progress: Callable[[str], None]) -> None:
        """سحبٌ متدفّق؛ النجاحُ **فقط** بسطر ``{"status": "success"}`` أخير وبلا ``error``."""
        req = urllib.request.Request(
            f"{self.base_url}/api/pull",
            data=json.dumps({"model": model, "name": model, "stream": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        last_status = None
        last_report: tuple[str, int] | None = None
        try:
            # مهلةُ المقبس تسري على كلّ قراءة: ركودٌ أطولُ منها فشل، والتدفّقُ الحيّ لا ينتهي بها.
            with urllib.request.urlopen(req, timeout=stall_timeout_s) as resp:  # noqa: S310 - internal Ollama URL
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    try:
                        message = json.loads(line)
                    except ValueError as exc:
                        raise ProvisionError(
                            "OLLAMA_MODEL_PULL_FAILED",
                            f"{model}: malformed progress line {line[:120]!r}",
                        ) from exc
                    if message.get("error"):
                        raise ProvisionError(
                            "OLLAMA_MODEL_PULL_FAILED", f"{model}: {message['error']}"
                        )
                    last_status = str(message.get("status") or "")
                    total, completed = message.get("total"), message.get("completed")
                    if isinstance(total, int) and total > 0 and isinstance(completed, int):
                        bucket = min(100, completed * 100 // total) // 10 * 10
                        report = (last_status, bucket)
                    else:
                        report = (last_status, -1)
                    if report != last_report:
                        last_report = report
                        suffix = f" {report[1]}%" if report[1] >= 0 else ""
                        progress(f"{model}: {last_status}{suffix}")
        except urllib.error.HTTPError as exc:
            raise ProvisionError(
                "OLLAMA_MODEL_PULL_FAILED", f"{model}: HTTP {exc.code}: {_error_text(exc)}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProvisionError(
                "OLLAMA_MODEL_PULL_FAILED", f"{model}: {type(exc).__name__}: {exc}"
            ) from exc
        if last_status != "success":
            raise ProvisionError(
                "OLLAMA_MODEL_PULL_FAILED",
                f"{model}: stream ended without success (last status: {last_status!r})",
            )

    def embed(self, model: str, prompt: str) -> list:
        # المسارُ نفسُه الذي يستدعيه qdrant-seed وrag-retrieval (/api/embeddings) — يُثبَت ما سيُستعمَل.
        return self._json(
            "POST", "/api/embeddings", {"model": model, "prompt": prompt}, timeout=300.0
        ).get("embedding")

    def show(self, model: str) -> dict:
        return self._json("POST", "/api/show", {"model": model, "name": model})


def wait_for_api(
    client: OllamaClient,
    *,
    deadline_s: float,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> str:
    start = clock()
    last = "no attempt yet"
    while True:
        try:
            return client.version() or "unknown"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last = f"{type(exc).__name__}: {exc}"
        if clock() - start >= deadline_s:
            raise ProvisionError(
                "OLLAMA_UNREACHABLE",
                f"{client.base_url}/api/version did not answer within {deadline_s:.0f}s ({last})",
            )
        sleep(2.0)


def pull_with_retry(
    client: OllamaClient,
    model: str,
    cfg: Config,
    *,
    sleep: Callable[[float], None],
    out: Callable[[str], None],
) -> int:
    last_detail = "no attempt made"
    for attempt in range(1, cfg.pull_attempts + 1):
        out(f"pulling {model} (attempt {attempt}/{cfg.pull_attempts})")
        try:
            client.pull(model, stall_timeout_s=cfg.stall_timeout_s, progress=out)
            return attempt
        except ProvisionError as exc:
            last_detail = exc.detail
            if attempt < cfg.pull_attempts:
                delay = backoff_seconds(attempt, base=cfg.backoff_base_s, cap=cfg.backoff_cap_s)
                out(f"pull failed ({exc.detail}) — retrying in {delay:.0f}s")
                sleep(delay)
    raise ProvisionError(
        "OLLAMA_MODEL_PULL_FAILED", f"{last_detail} — gave up after {cfg.pull_attempts} attempts"
    )


def verify_embedding(client: OllamaClient, model: str) -> int:
    try:
        vector = client.embed(model, EMBED_PROBE_PROMPT)
    except urllib.error.HTTPError as exc:
        raise ProvisionError(
            "OLLAMA_EMBEDDING_FAILED", f"{model}: HTTP {exc.code}: {_error_text(exc)}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise ProvisionError(
            "OLLAMA_EMBEDDING_FAILED", f"{model}: {type(exc).__name__}: {exc}"
        ) from exc
    if (
        not isinstance(vector, list)
        or not vector
        or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)
    ):
        raise ProvisionError(
            "OLLAMA_EMBEDDING_INVALID",
            f"{model}: /api/embeddings returned no finite non-empty vector",
        )
    return len(vector)


def provision(
    cfg: Config,
    *,
    client: OllamaClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    out: Callable[[str], None] = lambda line: print(f"ollama-models: {line}", flush=True),
) -> dict:
    client = client or OllamaClient(cfg.base_url)
    version = wait_for_api(client, deadline_s=cfg.api_wait_s, sleep=sleep, clock=clock)
    required = list(dict.fromkeys(canonical(m) for m in (cfg.embed_model, cfg.generation_model)))
    out(f"Ollama {version} at {cfg.base_url}; required: {', '.join(required)}")
    try:
        present = client.installed()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise ProvisionError(
            "OLLAMA_UNREACHABLE", f"/api/tags: {type(exc).__name__}: {exc}"
        ) from exc
    pulled: list[str] = []
    for model in required:
        if model in present:
            out(f"{model}: already present")
            continue
        pull_with_retry(client, model, cfg, sleep=sleep, out=out)
        pulled.append(model)
    try:
        present = client.installed()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise ProvisionError(
            "OLLAMA_UNREACHABLE", f"/api/tags: {type(exc).__name__}: {exc}"
        ) from exc
    absent = [m for m in required if m not in present]
    if absent:
        raise ProvisionError(
            "OLLAMA_MODEL_MISSING", f"still absent after pull: {', '.join(absent)}"
        )
    dim = verify_embedding(client, cfg.embed_model)
    generation = canonical(cfg.generation_model)
    try:
        client.show(generation)
    except urllib.error.HTTPError as exc:
        raise ProvisionError(
            "OLLAMA_MODEL_MISSING", f"{generation}: /api/show HTTP {exc.code}: {_error_text(exc)}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise ProvisionError(
            "OLLAMA_UNREACHABLE", f"/api/show: {type(exc).__name__}: {exc}"
        ) from exc
    summary = {
        "embed_model": canonical(cfg.embed_model),
        "embedding_dim": dim,
        "generation_model": generation,
        "pulled": pulled,
    }
    out(
        f"READY embed={summary['embed_model']} (dim={dim}) generation={generation} "
        f"pulled={pulled or 'none'}"
    )
    return summary


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    del argv  # لا وسائط: الإعدادُ كلُّه من بيئة compose
    try:
        cfg = load_config(os.environ if env is None else env)
    except ProvisionError as exc:
        print(f"FATAL[ollama-models] {exc.code}: {exc.detail}", file=sys.stderr, flush=True)
        return 2
    try:
        provision(cfg)
    except ProvisionError as exc:
        print(f"FATAL[ollama-models] {exc.code}: {exc.detail}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
