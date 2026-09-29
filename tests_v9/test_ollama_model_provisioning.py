"""سلسلةُ الذكاء لا تبدأ قبل نماذجها — مهمّةُ ``sahool-ollama-models`` وعقدُ ترتيبها في compose.

``AI-CHAIN-STARTS-BEFORE-ITS-MODELS-01`` — تدقيقُ التشغيل الحيّ (2026-09-29، docker-compose.v9.yml على
آلةٍ نظيفة): فحصُ صحّة ``sahool-ollama`` هو ``ollama list``، ينجح وفي Ollama **صفرُ نماذج**؛ فأقلع
``qdrant-seed`` (``restart: no``) قبل أيّ نموذج وبقيت Qdrant بصفر مجموعات، وسحبَ ``local-ai-rag``
النماذجَ بنفسه ثمّ استسلم — ``rag-retrieval`` 503 و``ai-agronomist`` 502 وDocker يُظهرها ``healthy``.

أربعةُ أشطر:
  * **سلوكُ المُهيِّئ الحقيقيّ** (``scripts/ollama/provision_models.py``) أمام Ollama مُصطنَعٍ على
    المنفذ المحلّيّ بشكل الحالة الحيّة (API حيّ وصفرُ نماذج): يسحب، يُعيد بحدود، يُثبِت التضمين،
    ويفشل بسببٍ مُسمّى.
  * **عقدُ الترتيب في compose**: المستهلكون الثلاثة يشترطون اكتمالَه لا ``service_healthy`` على Ollama.
  * **«بالضبط ما يحتاجه المكدّس»**: قائمةُ السحب تُطابِق — لا تزيد ولا تنقص — نماذجَ المستهلكين
    كما تُشتَقّ من compose ومن عقد التضمين المحكوم ومن افتراض التوليد المحلّيّ في الشيفرة.
  * **السلسلةُ كاملة بشيفرتها الحقيقيّة**: البذرُ يخرج بغير صفر ولا يمسّ Qdrant حين لا يُضمِّن؛
    وجاهزيّةُ ``rag-retrieval`` تُسمّي المرحلةَ الغائبة (نموذج · مجموعة · مجموعةٌ فارغة) ولا تخضرّ
    إلّا بعد مُهيِّئٍ ثمّ بذرٍ حقيقيَّين.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.v9.yml"
SCRIPT = ROOT / "scripts" / "ollama" / "provision_models.py"
PROVISIONER = "sahool-ollama-models"
CONSUMERS = ("sahool-qdrant-seed", "sahool-local-ai-rag", "sahool-rag-retrieval")


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def prov():
    return _load("scripts/ollama/provision_models.py", "_ollama_provision_models")


def _canon(name: str) -> str:
    name = name.strip()
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"


class FakeOllama:
    """Ollama مُصطنَع على 127.0.0.1 بشكل الحالة الحيّة: API حيّ وصفرُ نماذج افتراضاً."""

    def __init__(self, *, installed=(), pull="ok", embed="ok", dim=768):
        self.installed = {_canon(m) for m in installed}
        self.pull_mode = pull
        self.embed_mode = embed
        self.dim = dim
        self.requests: list[str] = []
        self._server: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def _send(self, code: int, payload) -> None:
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                fake.requests.append(f"GET {self.path}")
                if self.path == "/api/version":
                    return self._send(200, {"version": "0.32.5"})
                if self.path == "/api/tags":
                    return self._send(
                        200, {"models": [{"name": m} for m in sorted(fake.installed)]}
                    )
                return self._send(404, {"error": "not found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                model = _canon(str(body.get("model") or body.get("name") or ""))
                fake.requests.append(f"POST {self.path} {model}")
                if self.path == "/api/pull":
                    return self._pull(model)
                if self.path == "/api/embeddings":
                    if model not in fake.installed or fake.embed_mode == "404":
                        return self._send(404, {"error": f'model "{model}" not found'})
                    vector = {
                        "ok": [0.01 * (i % 7 + 1) for i in range(fake.dim)],
                        "empty": [],
                        "nan": [float("nan")] * 4,
                    }[fake.embed_mode]
                    return self._send(200, {"embedding": vector})
                if self.path == "/api/show":
                    if model not in fake.installed:
                        return self._send(404, {"error": f"model '{model}' not found"})
                    return self._send(200, {"details": {"family": "fake"}})
                return self._send(404, {"error": "not found"})

            def _pull(self, model: str) -> None:
                if fake.pull_mode == "http500":
                    return self._send(
                        500,
                        {
                            "error": "pull model manifest: dial tcp: lookup registry.ollama.ai: no such host"
                        },
                    )
                lines = [{"status": "pulling manifest"}]
                if fake.pull_mode == "error_line":
                    lines.append({"error": "max retries exceeded: unexpected EOF"})
                else:
                    lines.append({"status": "pulling x", "total": 10, "completed": 10})
                    if fake.pull_mode != "no_success":
                        lines.append({"status": "success"})
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                for line in lines:
                    self.wfile.write((json.dumps(line) + "\n").encode())
                if fake.pull_mode == "ok":
                    fake.installed.add(model)
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, args=(0.05,), daemon=True).start()
        return self

    def __exit__(self, *_exc):
        assert self._server is not None
        self._server.shutdown()
        self._server.server_close()


def _cfg(prov, url: str, **overrides):
    values = {
        "base_url": url,
        "embed_model": "nomic-embed-text",
        "generation_model": "llama3.2:3b",
        "pull_attempts": 3,
        "backoff_base_s": 5.0,
        "backoff_cap_s": 60.0,
        "api_wait_s": 5.0,
        "stall_timeout_s": 5.0,
    }
    values.update(overrides)
    return prov.Config(**values)


def _quiet(_line: str) -> None:
    return None


# ── سلوكُ المُهيِّئ ──────────────────────────────────────────────────────────


def test_zero_model_ollama_is_provisioned_and_the_embedding_dimension_is_measured(prov):
    """الحالةُ الحيّة نفسُها (API حيّ، صفرُ نماذج) ⇒ سحبٌ ثمّ تضمينٌ فعليّ يُقاس بُعدُه."""
    with FakeOllama() as fake:
        summary = prov.provision(_cfg(prov, fake.url), sleep=lambda _s: None, out=_quiet)
        assert fake.installed == {"nomic-embed-text:latest", "llama3.2:3b"}
        pulls = [r for r in fake.requests if r.startswith("POST /api/pull")]
    assert pulls == ["POST /api/pull nomic-embed-text:latest", "POST /api/pull llama3.2:3b"]
    assert summary["embedding_dim"] == 768
    assert summary["pulled"] == ["nomic-embed-text:latest", "llama3.2:3b"]


def test_models_already_present_are_verified_not_pulled_again(prov):
    """الإقلاعُ الدافئ: لا سحبَ، والتحقّقُ من التضمين قائمٌ في كلّ تشغيل."""
    with FakeOllama(installed=("nomic-embed-text:latest", "llama3.2:3b")) as fake:
        summary = prov.provision(_cfg(prov, fake.url), sleep=lambda _s: None, out=_quiet)
        requests = list(fake.requests)
    assert not [r for r in requests if r.startswith("POST /api/pull")]
    assert "POST /api/embeddings nomic-embed-text:latest" in requests
    assert "POST /api/show llama3.2:3b" in requests
    assert summary["pulled"] == []


def test_a_failing_pull_is_retried_with_bounded_backoff_then_named(prov):
    slept: list[float] = []
    with FakeOllama(pull="http500") as fake:
        with pytest.raises(prov.ProvisionError) as info:
            prov.provision(_cfg(prov, fake.url), sleep=slept.append, out=_quiet)
        pulls = [r for r in fake.requests if r.startswith("POST /api/pull")]
    assert info.value.code == "OLLAMA_MODEL_PULL_FAILED"
    assert "nomic-embed-text:latest" in info.value.detail
    assert "no such host" in info.value.detail, "السببُ الحقيقيّ ضاع — كان يُسجَّل اسمُ النوع وحده"
    assert "gave up after 3 attempts" in info.value.detail
    assert len(pulls) == 3
    assert slept == [5.0, 10.0]


@pytest.mark.parametrize("mode", ["error_line", "no_success"])
def test_a_200_stream_without_success_is_not_success(prov, mode):
    with FakeOllama(pull=mode) as fake:
        with pytest.raises(prov.ProvisionError) as info:
            prov.provision(_cfg(prov, fake.url, pull_attempts=1), sleep=lambda _s: None, out=_quiet)
    assert info.value.code == "OLLAMA_MODEL_PULL_FAILED"


@pytest.mark.parametrize(
    "mode, code",
    [
        ("empty", "OLLAMA_EMBEDDING_INVALID"),
        ("nan", "OLLAMA_EMBEDDING_INVALID"),
        ("404", "OLLAMA_EMBEDDING_FAILED"),
    ],
)
def test_an_embedding_model_that_does_not_embed_blocks_the_chain(prov, mode, code):
    """«حاضرٌ في /api/tags» ليس «يُضمِّن»: البذرُ لا يبدأ فوق نموذجٍ لا يُعيد متّجهاً صالحاً."""
    with FakeOllama(installed=("nomic-embed-text", "llama3.2:3b"), embed=mode) as fake:
        with pytest.raises(prov.ProvisionError) as info:
            prov.provision(_cfg(prov, fake.url), sleep=lambda _s: None, out=_quiet)
    assert info.value.code == code


def test_an_unreachable_api_is_named_after_its_deadline(prov):
    ticks = iter(range(0, 1000, 3))
    slept: list[float] = []
    cfg = _cfg(prov, "http://127.0.0.1:9", api_wait_s=10.0)
    with pytest.raises(prov.ProvisionError) as info:
        prov.provision(cfg, sleep=slept.append, clock=lambda: float(next(ticks)), out=_quiet)
    assert info.value.code == "OLLAMA_UNREACHABLE"
    assert slept and all(s == 2.0 for s in slept)


def test_main_exit_codes_distinguish_ready_failed_and_misconfigured(prov, capsys, monkeypatch):
    monkeypatch.setattr(prov.time, "sleep", lambda _s: None)
    with FakeOllama() as fake:
        env = {
            "OLLAMA_BASE_URL": fake.url,
            "OLLAMA_REQUIRED_EMBED_MODEL": "nomic-embed-text",
            "OLLAMA_REQUIRED_GENERATION_MODEL": "llama3.2:3b",
        }
        assert prov.main(env=env) == 0
    assert "READY embed=nomic-embed-text:latest (dim=768)" in capsys.readouterr().out
    with FakeOllama(pull="http500") as fake:
        env = {**env, "OLLAMA_BASE_URL": fake.url, "OLLAMA_PROVISION_PULL_ATTEMPTS": "1"}
        assert prov.main(env=env) == 1
    assert "FATAL[ollama-models] OLLAMA_MODEL_PULL_FAILED" in capsys.readouterr().err
    assert prov.main(env={"OLLAMA_REQUIRED_EMBED_MODEL": "nomic-embed-text"}) == 2
    assert "OLLAMA_PROVISION_CONFIG" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["0", "-1", "abc", "nan"])
def test_invalid_retry_budget_is_a_config_error_not_a_silent_default(prov, value):
    env = {
        "OLLAMA_REQUIRED_EMBED_MODEL": "nomic-embed-text",
        "OLLAMA_REQUIRED_GENERATION_MODEL": "llama3.2:3b",
        "OLLAMA_PROVISION_PULL_ATTEMPTS": value,
    }
    with pytest.raises(prov.ProvisionError) as info:
        prov.load_config(env)
    assert info.value.code == "OLLAMA_PROVISION_CONFIG"


def test_model_names_compare_in_ollama_canonical_form(prov):
    assert prov.canonical("nomic-embed-text") == "nomic-embed-text:latest"
    assert prov.canonical("llama3.2:3b") == "llama3.2:3b"
    assert prov.canonical("registry:5000/team/model") == "registry:5000/team/model:latest"


# ── عقدُ الترتيب في compose ──────────────────────────────────────────────────


def _services() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def test_every_ai_consumer_waits_for_provisioning_not_for_api_liveness():
    services = _services()
    for name in CONSUMERS:
        deps = services[name]["depends_on"]
        assert deps.get(PROVISIONER, {}).get("condition") == "service_completed_successfully", (
            f"{name} يُقلِع قبل حضور النماذج — «الـAPI حيّ» كان يُقرَأ «النموذجُ حاضر»"
        )
        assert "sahool-ollama" not in deps, (
            f"{name} ما يزال يشترط service_healthy على sahool-ollama (`ollama list` ينجح بصفر نماذج)"
        )


def test_only_the_provisioner_gates_on_ollama_api_health():
    """فحصُ ``ollama list`` حيويّةٌ للـAPI: يصلح بوّابةً للساحب وحدَه، لا لمستهلكٍ يحتاج نموذجاً."""
    services = _services()
    gated = sorted(
        name
        for name, spec in services.items()
        if "sahool-ollama" in ((spec or {}).get("depends_on") or {})
    )
    assert gated == [PROVISIONER]
    provisioner = services[PROVISIONER]
    assert provisioner["depends_on"]["sahool-ollama"]["condition"] == "service_healthy"
    # ولو صار فحصُ Ollama شرطَ حضورِ نموذج لانتظر الساحبُ ما لم يسحبه بعد — قفلٌ على نفسه.
    health = " ".join(str(x) for x in services["sahool-ollama"]["healthcheck"]["test"])
    env = provisioner["environment"]
    for model in (env["OLLAMA_REQUIRED_EMBED_MODEL"], env["OLLAMA_REQUIRED_GENERATION_MODEL"]):
        assert model not in health


def test_the_provisioner_is_a_one_shot_running_the_repo_script_against_its_dependency():
    spec = _services()[PROVISIONER]
    assert str(spec["restart"]) == "no"
    mounts = [str(v) for v in spec["volumes"]]
    source = "./scripts/ollama/provision_models.py:"
    target = next(m.split(":")[1] for m in mounts if m.startswith(source))
    assert target in [str(x) for x in spec["entrypoint"]]
    host = re.match(r"https?://([^:/]+)", spec["environment"]["OLLAMA_BASE_URL"]).group(1)
    assert host in spec["depends_on"], "يسحب في Ollama غيرِ الذي ينتظره"


def _default(value: str) -> str:
    """``${VAR:-default}`` ⇒ ``default``؛ الحرفيّ كما هو."""
    match = re.fullmatch(r"\$\{[A-Z0-9_]+:-(?P<default>[^}]*)\}", str(value).strip())
    return match.group("default") if match else str(value).strip()


def test_the_provisioned_models_are_exactly_what_the_stack_consumes(monkeypatch):
    """لا نموذجَ يُستهلَك بلا سحب، ولا سحبَ لنموذجٍ لا يستهلكه أحد — مشتقّاً لا منسوخاً."""
    services = _services()
    env = services[PROVISIONER]["environment"]
    embed = _canon(env["OLLAMA_REQUIRED_EMBED_MODEL"])
    generation = _canon(env["OLLAMA_REQUIRED_GENERATION_MODEL"])

    embedding_consumers = {
        _canon(_default(services[svc]["environment"][key]))
        for svc, keys in {
            "sahool-qdrant-seed": ("EMBED_MODEL", "EMBEDDING_MODEL"),
            "sahool-local-ai-rag": ("EMBED_MODEL", "EMBEDDING_MODEL"),
            "sahool-rag-retrieval": ("EMBEDDING_MODEL",),
        }.items()
        for key in keys
    }
    contract = json.loads(
        (ROOT / "docs/architecture/rag_embedding_contract.json").read_text(encoding="utf-8")
    )
    assert embedding_consumers == {embed} == {_canon(contract["model"])}

    # التوليدُ المحلّيّ: local-ai-rag يقرؤه من compose، وai-agronomist والمنصّة من افتراض
    # الشيفرة حين AI_PROVIDER=local وAI_MODEL فارغ (قيمةُ compose الافتراضيّة).
    local_llm = _canon(_default(services["sahool-local-ai-rag"]["environment"]["LLM_MODEL"]))
    monkeypatch.setenv("AI_PROVIDER", "local")
    for var in ("AI_MODEL", "AI_MODELS", "LOCAL_LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    agronomist = _load("services/ai_agronomist/ai_generation.py", "_prov_contract_ai_gen")
    platform = _load("services/sahool-platform/api/ai_provider_config.py", "_prov_contract_ai_cfg")
    code_defaults = {
        _canon(agronomist.resolve_generation().model),
        _canon(platform.resolve_ai_provider().model),
    }
    assert {local_llm} | code_defaults == {generation}

    assert {embed, generation} == embedding_consumers | {local_llm} | code_defaults


# ── السلسلةُ كاملة: البذرُ ثمّ جاهزيّةُ rag-retrieval بشيفرتهما الحقيقيّة ─────────────


class FakeQdrant:
    """Qdrant REST مُصطنَع يكفي ما يقرؤه ``QdrantHttpClient``: ``points=None`` ⇒ المجموعةُ غائبة."""

    def __init__(self, *, collection: str = "sahool_agri_kb", dim: int = 768, points=None):
        self.collection = collection
        self.dim = dim
        self.points = points
        self.requests: list[str] = []
        self._server: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self):
        fake = self
        base = f"/collections/{self.collection}"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def _send(self, code: int, payload) -> None:
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _missing(self) -> None:
                self._send(
                    404,
                    {
                        "status": {
                            "error": f"Not found: Collection `{fake.collection}` doesn't exist!"
                        }
                    },
                )

            def do_GET(self):
                fake.requests.append(f"GET {self.path}")
                if self.path != base or fake.points is None:
                    return self._missing()
                vectors = {"size": fake.dim, "distance": "Cosine"}
                return self._send(
                    200,
                    {
                        "result": {
                            "points_count": len(fake.points),
                            "config": {"params": {"vectors": vectors}},
                        }
                    },
                )

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                fake.requests.append(f"POST {self.path}")
                if fake.points is None:
                    return self._missing()
                if self.path == f"{base}/points/count":
                    return self._send(200, {"result": {"count": len(fake.points)}})
                if self.path == f"{base}/points/scroll":
                    rows = [{"id": pid, "payload": payload} for pid, payload in fake.points]
                    return self._send(200, {"result": {"points": rows, "next_page_offset": None}})
                return self._missing()

            do_PUT = do_POST

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, args=(0.05,), daemon=True).start()
        return self

    def __exit__(self, *_exc):
        assert self._server is not None
        self._server.shutdown()
        self._server.server_close()


def test_the_seed_exits_non_zero_and_touches_no_storage_when_it_cannot_embed():
    """الحالةُ الحيّة: Ollama بلا نماذج ⇒ البذرُ الحقيقيّ (عمليّةٌ كما في الحاوية) يخرج بـ1
    **قبل** أيّ نداءٍ لـQdrant — لا مجموعةَ نصف مبذورة ولا «نجاحٌ» بصفر مجموعات."""
    with FakeOllama() as ollama, FakeQdrant() as qdrant:
        env = {
            **os.environ,
            "OLLAMA_BASE_URL": ollama.url,
            "EMBED_MODEL": "nomic-embed-text",
            "QDRANT_URL": qdrant.url,
            "SAHOOL_ENV": "development",
        }
        proc = subprocess.run(
            [sys.executable, "seed.py"],
            cwd=ROOT / "services" / "qdrant-seed",
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        embeds = [r for r in ollama.requests if r.startswith("POST /api/embeddings")]
        qdrant_calls = list(qdrant.requests)
    assert proc.returncode != 0, "البذرُ «نجح» بلا تضمين — Qdrant بصفر مجموعات تُقرَأ اكتمالاً"
    assert "required Qdrant seed embedding failed" in proc.stderr
    assert embeds == ["POST /api/embeddings nomic-embed-text:latest"], "404 ليس عطلاً عابراً يُعاد"
    assert qdrant_calls == [], "لمس Qdrant قبل أن يملك متّجهاً واحداً"


def _load_rag_retrieval(monkeypatch, *, ollama_url: str, qdrant_url: str):
    monkeypatch.setenv("OLLAMA_BASE_URL", ollama_url)
    monkeypatch.setenv("QDRANT_URL", qdrant_url)
    monkeypatch.setenv("QDRANT_COLLECTION", "sahool_agri_kb")
    monkeypatch.setenv("EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.delenv("QDRANT_API_KEY", raising=False)
    directory = ROOT / "services" / "rag-retrieval"
    monkeypatch.syspath_prepend(str(directory))
    name = f"_chain_rag_retrieval_{abs(hash((ollama_url, qdrant_url)))}"
    spec = importlib.util.spec_from_file_location(name, directory / "main.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _readyz(module):
    from fastapi.testclient import TestClient

    return TestClient(module.app).get("/readyz")


async def _real_seed_points(monkeypatch, ollama_url: str) -> list[tuple[str, dict]]:
    """يُشغّل ``seed()`` الحقيقيّ على محرّك qdrant_client المحلّيّ ويُعيد ما كتبه فعلاً."""
    from qdrant_client import AsyncQdrantClient

    monkeypatch.setenv("OLLAMA_BASE_URL", ollama_url)
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setenv("SAHOOL_ENV", "development")
    for var in ("QDRANT_SEED_TENANT_ID", "QDRANT_SEED_PROVENANCE_FILE", "COLLECTION_NAME"):
        monkeypatch.delenv(var, raising=False)
    directory = ROOT / "services" / "qdrant-seed"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("_chain_qdrant_seed", directory / "seed.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    store = AsyncQdrantClient(location=":memory:")

    async def _keep_open():  # seed() يُغلق عميله؛ المحرّكُ المحلّيّ يُقرَأ بعده
        return None

    close = store.close
    monkeypatch.setattr(store, "close", _keep_open)
    monkeypatch.setattr(seed, "AsyncQdrantClient", lambda **_kw: store)
    await seed.seed()
    points, _ = await store.scroll(seed.COLLECTION, limit=10_000, with_payload=True)
    info = await store.get_collection(seed.COLLECTION)
    assert info.config.params.vectors.size == 768
    await close()
    return [(str(p.id), p.payload) for p in points]


async def test_retrieval_readiness_names_each_missing_stage_and_turns_green_only_after_the_chain(
    prov, monkeypatch
):
    """من الحالة الحيّة إلى الجاهزيّة، بالشيفرة الحقيقيّة في كلّ خطوة:

    صفرُ نماذج ⇒ 503 ``embedding`` · بعد المُهيِّئ وقبل البذر ⇒ 503 ``collection`` ·
    مجموعةٌ فارغة ⇒ 503 ``corpus`` (الفراغُ ليس تكافؤاً) · بعد البذر ⇒ 200 وبُعدٌ 768.
    """
    with FakeOllama() as ollama:
        with FakeQdrant(points=None) as qdrant:
            live = _readyz(
                _load_rag_retrieval(monkeypatch, ollama_url=ollama.url, qdrant_url=qdrant.url)
            )
        assert live.status_code == 503
        assert "not ready: embedding[nomic-embed-text]: HTTP Error 404" in live.json()["detail"]

        prov.provision(_cfg(prov, ollama.url), sleep=lambda _s: None, out=_quiet)

        with FakeQdrant(points=None) as qdrant:
            no_seed = _readyz(
                _load_rag_retrieval(monkeypatch, ollama_url=ollama.url, qdrant_url=qdrant.url)
            )
        assert no_seed.status_code == 503
        assert "not ready: collection:" in no_seed.json()["detail"]
        assert "doesn't exist" in no_seed.json()["detail"]

        with FakeQdrant(points=[]) as qdrant:
            empty = _readyz(
                _load_rag_retrieval(monkeypatch, ollama_url=ollama.url, qdrant_url=qdrant.url)
            )
        assert empty.status_code == 503
        assert "corpus is empty" in empty.json()["detail"]

        seeded_points = await _real_seed_points(monkeypatch, ollama.url)
        assert seeded_points, "البذرُ لم يكتب شيئاً بعد حضور النماذج"
        with FakeQdrant(points=seeded_points) as qdrant:
            ready = _readyz(
                _load_rag_retrieval(monkeypatch, ollama_url=ollama.url, qdrant_url=qdrant.url)
            )
    assert ready.status_code == 200, ready.text
    body = ready.json()
    assert body["vector_size"] == 768
    assert body["sparse_index_count"] == len(seeded_points)
