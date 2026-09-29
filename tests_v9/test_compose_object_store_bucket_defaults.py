"""S3-BUCKET-EMPTY-SILENT-FILE-STORAGE-01 — الدلوُ الافتراضيّ هو ما يُنشئه `sahool-minio-init`.

كانت الخدمات الأربع في `docker-compose.v9.yml` تحمل `S3_BUCKET: ${S3_BUCKET:-}` و`.env.example`
فارغ، و`S3_BUCKET` هو مفتاحُ التفعيل في `object_store.enabled()` و`blob_store.s3_enabled()`
⇒ كلُّ COG وكلُّ مرفق دفترٍ يُكتَب `file://` على قرص الحاوية **بلا تحذير**، مع أنّ النقطة
والمفاتيح المقيَّدة والدلوَ والسياسةَ موصولةٌ كلُّها.

والتوقُّع هنا **مُشتقٌّ لا منسوخ**: مفتاحُ الخدمة (`S3_ACCESS_KEY: ${X_S3_ACCESS_KEY…}`) ⇒
السياسةُ التي يربطها `provision.sh` بذلك المفتاح ⇒ الدلوُ الذي تسمّيه السياسة ⇒ ويجب أن
يكون `mc mb` قد أنشأه. فلو تغيّرت السياسة أو الدلو احمرّ الاختبار بدل أن يمرّ على نسخةٍ بائتة.

الحدّ المُعلَن: ساكن. لا يُشغّل MinIO؛ ولا يُثبِت ترتيبَ الإقلاع (الخدمات الأربع لا تعتمد
`sahool-minio-init` في `depends_on`، فرفعٌ في الثواني الأولى قبل اكتمال التهيئة يفشل مغلقاً
`ObjectStoreUploadError`/`BlobStoreError` — مرئيّاً لا صامتاً).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.v9.yml"
PROVISION = ROOT / "scripts/minio/provision.sh"
POLICIES = ROOT / "deploy/minio/policies"
SERVICES = (
    "sahool-scout-ingest",
    "sahool-raster-service",
    "sahool-raster-cache-invalidation-worker",
    "sahool-raster-backfill-scan-worker",
)
_INTERP = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?:(:-|:\?)([^{}]*))?\}")


def _env_example() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def _interpolate(value: object, env: dict[str, str]) -> str:
    text = str(value)
    while True:
        match = _INTERP.search(text)
        if match is None:
            return text
        name, op, arg = match.groups()
        current = env.get(name, "")
        if op == ":?" and not current:
            raise LookupError(f"{name} required")
        replacement = current or (arg if op == ":-" else "")
        text = text[: match.start()] + replacement + text[match.end() :]


def _services() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def _bucket_for_credential(credential_var: str) -> str:
    """المفتاح ⇒ السياسة المربوطة به في provision.sh ⇒ الدلو الذي تسمّيه السياسة."""
    provision = PROVISION.read_text(encoding="utf-8")
    attach = re.search(
        rf"mc admin policy attach sahool (\S+) --user \"\${credential_var}\"", provision
    )
    assert attach, f"provision.sh لا يربط سياسةً بالمفتاح {credential_var}"
    policy = json.loads((POLICIES / f"{attach.group(1)}.json").read_text(encoding="utf-8"))
    buckets = {
        resource.removeprefix("arn:aws:s3:::").split("/", 1)[0]
        for statement in policy["Statement"]
        for resource in statement["Resource"]
    }
    assert len(buckets) == 1, f"سياسة {attach.group(1)} تسمّي أكثر من دلو: {buckets}"
    return buckets.pop()


def _created_buckets() -> set[str]:
    made = re.search(r"^mc mb --ignore-existing (.+)$", PROVISION.read_text(encoding="utf-8"), re.M)
    assert made, "provision.sh لم يعد يُنشئ الدلاء"
    return {target.split("/", 1)[1] for target in made.group(1).split()}


@pytest.mark.parametrize("name", SERVICES)
def test_default_bucket_is_the_one_minio_init_provisions_for_its_key(name):
    environment = _services()[name]["environment"]
    env = _env_example()
    assert env.get("S3_BUCKET", "") == "", "الافتراضُ المختبَر هو الفارغ في .env.example"
    bucket = _interpolate(environment["S3_BUCKET"], env)
    assert bucket, f"{name}: S3_BUCKET فارغ ⇒ تخزين file:// صامت على قرص الحاوية"
    credential = re.fullmatch(r"\$\{([A-Z0-9_]+):\?.*\}", str(environment["S3_ACCESS_KEY"]))
    assert credential, f"{name}: S3_ACCESS_KEY لم يعد مفتاحاً مقيَّداً إلزاميّاً"
    assert bucket == _bucket_for_credential(credential.group(1))
    assert bucket in _created_buckets()
    endpoint = _interpolate(environment["S3_ENDPOINT"], env)
    assert endpoint == "http://sahool-minio:9000" and "sahool-minio" in _services()


@pytest.mark.parametrize(
    ("name", "override_var"),
    [
        ("sahool-scout-ingest", "SCOUT_INGEST_S3_BUCKET"),
        ("sahool-raster-service", "S3_BUCKET"),
        ("sahool-raster-cache-invalidation-worker", "S3_BUCKET"),
        ("sahool-raster-backfill-scan-worker", "S3_BUCKET"),
    ],
)
def test_explicit_bucket_override_still_wins(name, override_var):
    environment = _services()[name]["environment"]
    env = {**_env_example(), override_var: "operator-bucket"}
    assert _interpolate(environment["S3_BUCKET"], env) == "operator-bucket"


def test_shared_s3_bucket_override_cannot_cross_into_the_scout_scope():
    """`S3_BUCKET` مُوثَّقٌ دلواً للـCOG؛ ضبطُه لا يجوز أن يُحوِّل مرفقات scout إلى دلوٍ
    ترفض سياستُها مفاتيحَها (provision.sh يُثبِت الرفض المتقاطع بنفسه)."""
    environment = _services()["sahool-scout-ingest"]["environment"]
    env = {**_env_example(), "S3_BUCKET": "sahool-rasters"}
    assert _interpolate(environment["S3_BUCKET"], env) == "sahool-scout-ingest"
