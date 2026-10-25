#!/usr/bin/env python3
"""Fail closed on MinIO/S3 credential drift in docker-compose/.env templates.

The local incident this gate prevents:
- MinIO container was hardcoded with MINIO_ROOT_USER=sahool-admin.
- .env advertised MINIO_ROOT_USER=sahool and MINIO_ACCESS_KEY=${MINIO_ROOT_USER}.
- Network/health passed, but any backend using .env S3 credentials would fail auth.

This static gate keeps the credential source-of-truth explicit and aligned.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا السكربت عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نتيجته (UnicodeEncodeError) ⇒ خروجٌ بغير صفر يُقرَأ حجباً وهو قد مرّ.
# **عند التحميل لا داخل `main()`** — بعضُ المخرَج يُطبَع من جسد الوحدة قبل أيّ نداء.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.v9.yml"
ENV_EXAMPLE = ROOT / ".env.example"


def fail(msg: str) -> None:
    print(f"❌ {msg}")
    sys.exit(1)


# MINIO-IMAGES-DELETED-FROM-DOCKER-HUB-01: المستودعُ نفسُه محذوف، فيُرفَض بأيّ شكلٍ للمرجع —
# وسمٌ (``:``) أو دايجست (``@``) أو بلا لاحقة، وبـ``docker.io/`` أو بدونه (مراجعة Copilot على #1139:
# البادئةُ ``minio/minio:`` وحدها كانت تُفلت ``minio/minio@sha256:…``).
_DELETED_REPO = re.compile(r"^(?:docker\.io/)?minio/(?:minio|mc)(?=[:@]|$)")
_SERVICE = re.compile(r"^  [A-Za-z0-9_.-]+:\s*$")
_TOP_LEVEL_KEY = re.compile(r"^[A-Za-z0-9_.-]+:")


def is_deleted_repo(ref: str) -> bool:
    return bool(_DELETED_REPO.match(ref.strip().strip("'\"")))


# MINIO-IMAGES-DELETED-FROM-DOCKER-HUB-01 (توسيعٌ 2026-10-11): ``is_deleted_repo`` يبقى على معناه —
# المحذوفُ من Docker Hub؛ و``quay.io/minio/minio`` موجودٌ لكنّه يشترط الدخول، فلا يُعَدّ محذوفاً.
# غير أنّ سحبه يفشل كذلك على آلةٍ جديدة، ومثلُه صورةُ MinIO من مساحةٍ أخرى أو بوسمٍ بلا دايجست:
# فأيُّ مرجعٍ مستودعُه MinIO — أيّاً كان السجلّ أو المساحة — يجب أن يكون الإبرةَ المثبَّتة عبر متغيّرها.
_MINIO_REPO = re.compile(r"(?:^|/)(?:minio|minio-client|minio/mc)(?=[:@]|$)")
# العميلُ (`mc`) لا الخادم: يحدّد متغيّرَ التجاوز الصحيح في رسالة الإصلاح حين يكون المرجعُ عارياً.
_MINIO_CLIENT_REPO = re.compile(r"(?:^|/)(?:minio-client|mc)(?=[:@]|$)")
# فحصُ الصحّة: الصورة بلا curl **ولا wget** (مقيسٌ من طبقاتها)، فأيٌّ منهما يُبقي الخادم unhealthy
# أيّاً كان المسارُ الذي يطلبه — لا ``minio/health`` وحده.
_HTTP_CLIENT = re.compile(r"(?<![\w.-])(?:curl|wget)(?![\w.-])")
_TRAILING_COMMENT = re.compile(r"\s+#.*$")


def is_minio_image(ref: str) -> bool:
    return bool(_MINIO_REPO.search(ref.strip().strip("'\"")))


def healthcheck_probe(block: list[str]) -> str:
    """نصُّ قسم ``healthcheck:`` وحده من كتلة خدمة، بلا تعليقات — التعليقُ الذي يشرح غيابَ curl
    (كما في ``sahool-minio``) ليس فحصاً، وما بعد القسم (``volumes:`` …) ليس منه."""
    out: list[str] = []
    indent: int | None = None
    for raw in block:
        body = raw.strip()
        if indent is None:
            if body.startswith("healthcheck:"):
                indent = len(raw) - len(raw.lstrip())
                out.append(_TRAILING_COMMENT.sub("", body))
            continue
        if not body or body.startswith("#"):
            continue
        if len(raw) - len(raw.lstrip()) <= indent:
            break
        out.append(_TRAILING_COMMENT.sub("", body))
    return "\n".join(out)


# مراجعة Copilot على #1162: سطرٌ فيه «image:» ليس مرجعاً بالضرورة — التعليقُ (``# from image: …``)
# ونصُّ مفتاحٍ آخر (``command: echo "image: …"``) لا يسحبهما Compose. فالمرجعُ هو قيمةُ مفتاحٍ
# ينتهي بـ``image:`` وحده (``image:`` أو حقلُ امتدادٍ كـ``x-minio-image:``)، بلا تعليقه، وبلا مرساة ``&name``.
_IMAGE_KEY = re.compile(r"^(?:-\s+)?[A-Za-z0-9_.-]*image:(?:\s+(.*))?$")
_ANCHOR = re.compile(r"^&\S+\s*")


def image_ref(raw: str) -> str | None:
    """مرجعُ الصورة في سطر مفتاح ``image:``، أو None لكلّ سطرٍ ليس مفتاحَ صورة."""
    s = _TRAILING_COMMENT.sub("", raw.strip())
    if not s or s.startswith("#"):
        return None
    m = _IMAGE_KEY.match(s)
    if not m:
        return None
    ref = _ANCHOR.sub("", (m.group(1) or "").strip()).strip().strip("'\"")
    if ref.startswith("${") and ":-" in ref:  # ${VAR:-default} ⇒ the default ref
        ref = ref.split(":-", 1)[1].rstrip("}")
    return ref


def block_is_minio(block: list[str]) -> bool:
    """كتلةُ خدمة MinIO بمفتاح صورتها لا بذكر المتغيّر في تعليقٍ داخلها (Copilot على #1162)."""
    for raw in block:
        ref = image_ref(raw)
        if ref is None:
            continue
        s = _TRAILING_COMMENT.sub("", raw.strip())
        if "MINIO_IMAGE" in s or "MINIO_MC_IMAGE" in s or is_minio_image(ref):
            return True
    return False


def service_blocks(lines: list[str]) -> list[list[str]]:
    """كتلُ الخدمات بالإزاحة **داخل ``services:`` وحده** — مفتاحٌ علويّ آخر (``volumes:`` …) يُنهي الكتلة
    الأخيرة، فلا تبتلع ما بعد القسم (مراجعة Copilot على #1139)."""
    blocks: list[list[str]] = []
    in_services = False
    current: list[str] | None = None
    for raw in lines:
        if _TOP_LEVEL_KEY.match(raw):
            in_services = raw.split(":", 1)[0] == "services"
            current = None
            continue
        if not in_services:
            continue
        if _SERVICE.match(raw):
            current = []
            blocks.append(current)
        if current is not None:
            current.append(raw)
    return blocks


# TITILER-LEGACY-USES-SHARED-ADMIN-S3-KEY-01: the legacy TiTiler's account may list and read
# the raster bucket and nothing else — no write, no delete, no other bucket, no wildcard action,
# no condition that could widen it. Exact, so any added statement or action fails.
LEGACY_TITILER_POLICY = {
    ("Allow", ("s3:ListBucket",), ("arn:aws:s3:::sahool-rasters",)),
    ("Allow", ("s3:GetObject",), ("arn:aws:s3:::sahool-rasters/*",)),
}


def legacy_titiler_policy_errors(policy: object) -> list[str]:
    statements = policy.get("Statement") if isinstance(policy, dict) else None
    if not isinstance(statements, list):
        return ["legacy-titiler policy has no Statement list"]
    seen = set()
    for statement in statements:
        if not isinstance(statement, dict) or set(statement) != {"Effect", "Action", "Resource"}:
            return [
                f"legacy-titiler statement must carry only Effect/Action/Resource: {statement!r}"
            ]
        actions, resources = statement["Action"], statement["Resource"]
        if not (isinstance(actions, list) and isinstance(resources, list)):
            return [f"legacy-titiler Action/Resource must be lists: {statement!r}"]
        seen.add((statement["Effect"], tuple(sorted(actions)), tuple(sorted(resources))))
    if len(seen) != len(statements) or seen != LEGACY_TITILER_POLICY:
        return [
            "legacy-titiler policy must be exactly s3:ListBucket on sahool-rasters and "
            f"s3:GetObject on sahool-rasters/* (read-only), got {sorted(seen)!r}"
        ]
    return []


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    if not COMPOSE.exists():
        fail("docker-compose.v9.yml is missing")
    if not ENV_EXAMPLE.exists():
        fail(".env.example is missing")

    compose = COMPOSE.read_text(encoding="utf-8", errors="replace")
    env = load_env(ENV_EXAMPLE)

    # MinIO root user must be interpolated from env, not hardcoded to a value that
    # can diverge from MINIO_ACCESS_KEY/S3_ACCESS_KEY.
    for line in compose.splitlines():
        stripped = line.strip()
        if stripped.startswith("MINIO_ROOT_USER:"):
            value = stripped.split(":", 1)[1].strip()
            if not value.startswith("${MINIO_ROOT_USER"):
                fail(
                    "docker-compose.v9.yml must not hardcode MINIO_ROOT_USER; use ${MINIO_ROOT_USER:-...}"
                )

    root = env.get("MINIO_ROOT_USER", "")
    access = env.get("MINIO_ACCESS_KEY", "")
    s3_access = env.get("S3_ACCESS_KEY", "")
    if not root:
        fail(".env.example must define MINIO_ROOT_USER")
    if access not in {"${MINIO_ROOT_USER}", root}:
        fail(
            "MINIO_ACCESS_KEY must resolve from MINIO_ROOT_USER unless a dedicated documented service account is used"
        )
    if s3_access and s3_access not in {"${MINIO_ACCESS_KEY}", "${MINIO_ROOT_USER}", root, access}:
        fail(
            "S3_ACCESS_KEY must resolve from MINIO_ACCESS_KEY/MINIO_ROOT_USER in the default template"
        )

    required_env = [
        "S3_ENDPOINT",
        "S3_BUCKET",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "S3_REGION",
        "S3_USE_SSL",
        "S3_ALLOW_FILE_FALLBACK",
    ]
    missing = [k for k in required_env if k not in env]
    if missing:
        fail(f".env.example missing S3 contract keys: {', '.join(missing)}")

    required_compose_keys = [
        "S3_ENDPOINT:",
        "S3_BUCKET:",
        "S3_ACCESS_KEY:",
        "S3_SECRET_KEY:",
        "S3_REGION:",
        "S3_USE_SSL:",
        "S3_ALLOW_FILE_FALLBACK:",
    ]
    missing_compose = [k for k in required_compose_keys if k not in compose]
    if missing_compose:
        fail(
            f"docker-compose.v9.yml missing raster S3 environment keys: {', '.join(missing_compose)}"
        )

    for required in (
        "sahool-minio-init:",
        "deploy/minio/policies",
        "scripts/minio/provision.sh",
        "SCOUT_INGEST_S3_ACCESS_KEY:",
        "RASTER_S3_ACCESS_KEY:",
    ):
        if required not in compose:
            fail(f"docker-compose.v9.yml missing MinIO least-privilege provisioning: {required}")
    provision = (ROOT / "scripts/minio/provision.sh").read_text(encoding="utf-8")
    for denial in (
        "scout/sahool-rasters",
        "raster/sahool-scout-ingest",
        "titiler/sahool-scout-ingest",
        "titiler/sahool-rasters/.legacy-titiler-write-probe",
    ):
        if denial not in provision:
            fail(f"MinIO provisioning lacks cross-scope negative check: {denial}")
    policy_path = ROOT / "deploy/minio/policies/legacy-titiler.json"
    if not policy_path.is_file():
        fail("deploy/minio/policies/legacy-titiler.json is missing (read-only TiTiler policy)")
    for err in legacy_titiler_policy_errors(json.loads(policy_path.read_text(encoding="utf-8"))):
        fail(err)

    # MinIO version pin: the community admin console was gutted in RELEASE.2025-05-24,
    # the repo was archived (2026-04), and later Docker Hub images carry a HIGH CVE and
    # were pulled. This deployment relies on the console (--console-address :9001), so we
    # pin the LAST full-console release and forbid drift/bare hardcodes across compose.
    # Operators may still override via MINIO_IMAGE / MINIO_MC_IMAGE. See COMPOSE_ENV_CONTRACT.
    #
    # MINIO-IMAGES-DELETED-FROM-DOCKER-HUB-01 (2026-10-05): MinIO deleted `minio/minio` and
    # `minio/mc` from Docker Hub (2026-09-11..14) and quay.io now requires a login, so every
    # fresh `docker compose up` failed with "pull access denied for minio/mc". The pin keeps
    # the SAME release tag from a third party, digest-pinned so it cannot drift. It is not
    # MinIO's own image: coollabsio's CI rebuilt the server from that tag (its unsigned
    # attestation claims so) and ships MinIO's signed `mc` — MINIO-MIRROR-PROVENANCE-UNVERIFIED-01, checked
    # by .github/workflows/minio-image-provenance.yml. Measured from its layers: it ships
    # `minio`, `mc` and bash but NO curl/wget — so the init job runs on the same image and the
    # healthcheck is `mc ready local`, never curl.
    FULL_CONSOLE_PIN = (
        "coollabsio/minio:2025-04-22T22-12-26Z"
        "@sha256:a4938f37f1be1841b8e7b627ad0207b265345fd0d063e42d7410c78af0e63e68"
    )
    for key in ("MINIO_IMAGE", "MINIO_MC_IMAGE"):
        env_pin = env.get(key, "")
        if env_pin != FULL_CONSOLE_PIN:
            fail(
                f".env.example {key} must pin the last full-console release from a pullable "
                f"source, digest-pinned: {FULL_CONSOLE_PIN} (got {env_pin!r})"
            )
    for cf in sorted(ROOT.glob("docker-compose*.yml")):
        text = cf.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        for idx, raw in enumerate(lines):
            ref = image_ref(raw)
            if ref is None:  # not an image key: a comment or another key's text is never pulled
                continue
            s = _TRAILING_COMMENT.sub("", raw.strip())
            if is_deleted_repo(ref):
                fail(
                    f"{cf.name}:{idx + 1}: {s} — minio/minio and minio/mc were deleted from "
                    "Docker Hub; a fresh pull fails (MINIO-IMAGES-DELETED-FROM-DOCKER-HUB-01)"
                )
            if (
                "MINIO_IMAGE" in s
                or "MINIO_MC_IMAGE" in s
                or "coollabsio/minio" in s
                or is_minio_image(ref)
            ):
                # Must use the override form with the pinned default — a bare hardcode, a
                # floating tag, or MinIO from another registry/namespace (quay.io needs a login)
                # risks a failed pull or a console-stripped / CVE / swapped image.
                if (
                    not ("${MINIO_IMAGE" in s or "${MINIO_MC_IMAGE" in s)
                    or FULL_CONSOLE_PIN not in s
                ):
                    # من السطر إن سمّى المتغيّر، وإلّا من المرجع نفسِه (مرجعٌ عارٍ لا يسمّي شيئاً).
                    client = "MINIO_MC_IMAGE" in s or bool(_MINIO_CLIENT_REPO.search(ref))
                    var = "MINIO_MC_IMAGE" if client else "MINIO_IMAGE"
                    fail(
                        f"{cf.name}:{idx + 1}: MinIO image must be ${{{var}:-{FULL_CONSOLE_PIN}}} "
                        f"(no bare hardcode / no undigested tag / no other registry or namespace) — got: {s}"
                    )
        # The pinned image has no curl/wget: such a healthcheck keeps sahool-minio unhealthy
        # forever, and service_healthy dependents (sahool-minio-init) never start.
        # Service blocks by indentation, not by name (`minio`, `evidence-minio`, `sahool-minio`
        # all exist across these files); the MinIO block is the one whose image is the pin.
        # Only the healthcheck section is read, without comments: a comment explaining that
        # the image lacks curl is not a probe, and a curl probe on any path is still curl.
        for blk in service_blocks(lines):
            if not block_is_minio(blk):
                continue
            client = _HTTP_CLIENT.search(healthcheck_probe(blk))
            if client:
                fail(
                    f"{cf.name}: MinIO healthcheck uses {client.group(0)}, which the pinned image "
                    "does not ship — use `mc ready local`"
                )

    # TiTiler should be able to inspect local file COGs in dev and S3 COGs in prod.
    if "sahool-titiler:" in compose:
        titiler_block = compose.split("\n  sahool-titiler:", 1)[1].split("\n  sahool-", 1)[0]
        if "raster-data:/data/rasters:ro" not in titiler_block:
            fail(
                "sahool-titiler must mount raster-data read-only for local file:// COG diagnostics"
            )
        # TITILER-LEGACY-S3-BYPASSES-ENDPOINT-POLICY-01: the upstream image cannot run the
        # endpoint policy, so its GDAL variables must come from the entry gate, never from
        # Compose (a raw AWS_HTTPS let an external host through over plaintext).
        entrypoint = titiler_block.split("\n    entrypoint:", 1)[-1].split("\n    command:", 1)[0]
        if (
            "\n    entrypoint:" not in titiler_block
            or "/opt/sahool/storage/gdal_s3_env_gate.py" not in entrypoint
        ):
            fail("sahool-titiler must use shared/storage/gdal_s3_env_gate.py as its entrypoint")
        if "S3_ENDPOINT:" not in titiler_block:
            fail("sahool-titiler must receive S3_ENDPOINT for the endpoint policy gate")
        for raw_key in ("AWS_S3_ENDPOINT:", "AWS_HTTPS:", "AWS_VIRTUAL_HOSTING:"):
            if raw_key in titiler_block:
                fail(f"sahool-titiler must not set {raw_key[:-1]} directly; the gate derives it")

    print("✓ MinIO/S3 credential and storage contract is consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
