"""البوّابة تُقلِع على نسخةٍ نظيفة للتطوير، ولا تخدم شهادةً ذاتيّةً في الإنتاج بصمت.

``GATEWAY-TLS-ABSENT-ON-FRESH-CHECKOUT-01`` — تدقيقُ التشغيل الحيّ (2026-09-29، docker-compose.v9.yml
على آلةٍ نظيفة): ``nginx.v9.conf`` يُعلن ``listen 443 ssl`` بـ``/etc/nginx/ssl/fullchain.pem``،
والمستودعُ بلا ``nginx/ssl`` ولا مولِّد. فأنشأ Docker مجلّدَ التركيب فارغاً، ومات nginx على
``cannot load certificate`` وأُعيد تشغيلُه **31 مرّة** — البوّابةُ العامّة كلُّها ساقطة.

العلاج مهمّةٌ لمرّةٍ واحدة (``sahool-nginx-tls-init``) يسبق nginx بـ``service_completed_successfully``.
هنا شطران: **عقدُ compose** (الترتيب والتركيب نفسُه والافتراض)، و**سلوكُ السكربت الحقيقيّ** يُشغَّل
بـ``sh`` (dash في Debian وفي صورة التهيئة) على مجلّداتٍ مؤقّتة — لا نصُّه.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.v9.yml"
NGINX_CONF = ROOT / "nginx" / "nginx.v9.conf"
SCRIPT = ROOT / "scripts" / "nginx" / "ensure_gateway_tls.sh"
INIT = "sahool-nginx-tls-init"
#: مسارٌ مطلق: اختبارُ «openssl غائب» يستبدل PATH، فلا يُبحَث عن الصَّدَفة فيه.
SH = shutil.which("sh") or "/bin/sh"
DEV_VALUES = {"development", "dev", "local", "test"}


def _services() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def _conf_tls_dir() -> str:
    """المجلّدُ الذي يقرأ منه nginx زوجَه — من الكونف نفسه لا من ثابتٍ في الاختبار."""
    text = NGINX_CONF.read_text(encoding="utf-8")
    cert = re.search(r"^\s*ssl_certificate\s+(\S+);", text, re.M)
    key = re.search(r"^\s*ssl_certificate_key\s+(\S+);", text, re.M)
    assert cert and key, "nginx.v9.conf لم يعد يُعلن ssl_certificate/ssl_certificate_key"
    assert os.path.dirname(cert.group(1)) == os.path.dirname(key.group(1))
    return os.path.dirname(cert.group(1))


# ── عقدُ compose ─────────────────────────────────────────────────────────────


def test_gateway_waits_for_the_tls_gate_to_complete_successfully():
    deps = _services()["sahool-nginx"]["depends_on"]
    assert deps.get(INIT, {}).get("condition") == "service_completed_successfully", (
        "sahool-nginx يُقلِع بلا بوّابة TLS — شهادةٌ غائبة تعود حلقةَ إعادة تشغيلٍ صامتة (31 مرّة حيّاً)"
    )
    init = _services()[INIT]
    assert str(init.get("restart")) == "no", "مهمّةٌ لمرّةٍ واحدة: restart يعيدها حلقةً"


def test_the_gate_writes_exactly_the_directory_nginx_reads():
    """التركيبُ نفسُه في الجهتين: مضيفٌ واحد ومسارٌ داخليٌّ واحد — وnginx يقرؤه للقراءة فقط."""
    tls_dir = _conf_tls_dir()
    services = _services()
    nginx_mounts = [str(v) for v in services["sahool-nginx"]["volumes"]]
    init_mounts = [str(v) for v in services[INIT]["volumes"]]
    assert f"./nginx/ssl:{tls_dir}:ro" in nginx_mounts
    assert f"./nginx/ssl:{tls_dir}" in init_mounts, (
        f"{INIT} لا يكتب في المجلّد الذي يقرأ منه nginx ({tls_dir})"
    )
    assert any(m.startswith("./scripts/nginx/ensure_gateway_tls.sh:") for m in init_mounts)
    entry = " ".join(str(x) for x in services[INIT]["entrypoint"])
    assert "ensure_gateway_tls.sh" in entry


def test_the_gate_never_defaults_to_a_development_environment():
    """«صريحةٌ غيرُ إنتاجيّة»: غيابُ SAHOOL_ENV لا يجوز أن يصير رخصةَ توليد."""
    raw = str(_services()[INIT]["environment"]["SAHOOL_ENV"])
    match = re.fullmatch(r"\$\{SAHOOL_ENV(?::?-(?P<default>[^}]*)|:\?[^}]*)?\}", raw)
    assert match, f"SAHOOL_ENV في {INIT} ليس تمريراً من البيئة: {raw!r}"
    assert (match.group("default") or "").strip().lower() not in DEV_VALUES, (
        f"{INIT} يفترض بيئة تطوير ({raw}) — نشرٌ بلا SAHOOL_ENV يُولِّد شهادةً ذاتيّة ويخدمها"
    )


def test_no_private_key_can_be_committed_from_the_mounted_directory():
    for name in ("privkey.pem", "fullchain.pem", ".gateway-tls.abc123/req.cnf"):
        rc = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", f"nginx/ssl/{name}"],
            cwd=ROOT,
            check=False,
        ).returncode
        assert rc == 0, f"nginx/ssl/{name} غير مُتجاهَل في .gitignore — مفتاحٌ خاصّ قد يُلتزَم"


# ── سلوكُ السكربت الحقيقيّ ────────────────────────────────────────────────────


def _run(
    tls_dir: Path, env_value: str | None, *, domain: str | None = None, path: str | None = None
):
    env = {k: v for k, v in os.environ.items() if k not in {"SAHOOL_ENV", "DOMAIN"}}
    env["GATEWAY_TLS_DIR"] = str(tls_dir)
    if env_value is not None:
        env["SAHOOL_ENV"] = env_value
    if domain is not None:
        env["DOMAIN"] = domain
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        [SH, str(SCRIPT)], env=env, capture_output=True, text=True, encoding="utf-8"
    )


def _snapshot(tls_dir: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(tls_dir.iterdir())}


def _write_pair(
    tls_dir: Path, *, self_signed: bool, expired: bool = False, org: str | None = None
) -> None:
    """زوجٌ حقيقيّ بـcryptography: ذاتيّ أو صادرٌ عن CA، ساري أو منتهٍ."""
    now = dt.datetime.now(dt.UTC)
    not_after = now - dt.timedelta(days=1) if expired else now + dt.timedelta(days=30)
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, "gateway.example")]
    if org:
        attrs.insert(0, x509.NameAttribute(NameOID.ORGANIZATION_NAME, org))
    subject = x509.Name(attrs)
    if self_signed:
        issuer, signer, chain = subject, leaf_key, []
    else:
        ca_key = ec.generate_private_key(ec.SECP256R1())
        issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Issuing CA")])
        ca = (
            x509.CertificateBuilder()
            .subject_name(issuer)
            .issuer_name(issuer)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=2))
            .not_valid_after(now + dt.timedelta(days=60))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(ca_key, hashes.SHA256())
        )
        signer, chain = ca_key, [ca]
    leaf = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=2))
        .not_valid_after(not_after)
        .sign(signer, hashes.SHA256())
    )
    pem = b"".join(c.public_bytes(serialization.Encoding.PEM) for c in [leaf, *chain])
    (tls_dir / "fullchain.pem").write_bytes(pem)
    (tls_dir / "privkey.pem").write_bytes(
        leaf_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def _cert(tls_dir: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate((tls_dir / "fullchain.pem").read_bytes())


def test_fresh_development_checkout_gets_a_usable_generated_pair(tmp_path):
    out = _run(tmp_path, "development", domain="localhost")
    assert out.returncode == 0, out.stderr
    cert = _cert(tmp_path)
    key = serialization.load_pem_private_key((tmp_path / "privkey.pem").read_bytes(), None)
    assert cert.public_key().public_numbers() == key.public_key().public_numbers()
    orgs = cert.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
    assert [a.value for a in orgs] == ["SAHOOL-DEV-SELF-SIGNED"], "شهادةُ التطوير بلا وسمٍ يكشفها"
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "localhost" in san.get_values_for_type(x509.DNSName)
    assert oct((tmp_path / "privkey.pem").stat().st_mode & 0o777) == "0o600"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["fullchain.pem", "privkey.pem"], (
        "بقايا عمل (مجلّد مؤقّت/إعداد) في المجلّد المُركَّب"
    )


def test_an_existing_pair_is_never_rewritten(tmp_path):
    assert _run(tmp_path, "development").returncode == 0
    before = _snapshot(tmp_path)
    again = _run(tmp_path, "development")
    assert again.returncode == 0, again.stderr
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("env_value", ["production", "PRODUCTION", "staging", "", None, "develop"])
def test_missing_pair_outside_explicit_development_fails_loudly_and_writes_nothing(
    tmp_path, env_value
):
    out = _run(tmp_path, env_value)
    assert out.returncode == 1
    assert "GATEWAY_TLS_MISSING" in out.stderr
    assert "fullchain.pem" in out.stderr and "SAHOOL_ENV=development" in out.stderr, (
        "الرسالةُ لا تُسمّي الملفّ ولا العلاج"
    )
    assert list(tmp_path.iterdir()) == [], "خارج التطوير الصريح لا يُولَّد شيء"


def test_production_refuses_the_leftover_development_certificate(tmp_path):
    assert _run(tmp_path, "development").returncode == 0
    before = _snapshot(tmp_path)
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert "GATEWAY_TLS_SELF_SIGNED_OUTSIDE_DEV" in out.stderr
    assert "SAHOOL-DEV-SELF-SIGNED" in out.stderr
    assert _snapshot(tmp_path) == before


def test_production_refuses_any_self_signed_certificate(tmp_path):
    _write_pair(tmp_path, self_signed=True)
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert "GATEWAY_TLS_SELF_SIGNED_OUTSIDE_DEV" in out.stderr


def test_production_accepts_a_ca_issued_pair_untouched(tmp_path):
    _write_pair(tmp_path, self_signed=False)
    before = _snapshot(tmp_path)
    out = _run(tmp_path, "production")
    assert out.returncode == 0, out.stderr
    assert "issuer=[CN=Test Issuing CA]" in out.stdout
    assert _snapshot(tmp_path) == before


def test_half_a_pair_fails_in_every_environment_without_overwriting(tmp_path):
    (tmp_path / "privkey.pem").write_text("operator key\n", encoding="utf-8")
    before = _snapshot(tmp_path)
    for env_value in ("development", "production"):
        out = _run(tmp_path, env_value)
        assert out.returncode == 1
        assert "GATEWAY_TLS_PARTIAL" in out.stderr
    assert _snapshot(tmp_path) == before


def test_a_key_that_does_not_match_the_certificate_is_refused(tmp_path):
    _write_pair(tmp_path, self_signed=False)
    other = tmp_path / "other"
    other.mkdir()
    _write_pair(other, self_signed=False)
    shutil.copy(other / "privkey.pem", tmp_path / "privkey.pem")
    shutil.rmtree(other)
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert "GATEWAY_TLS_KEY_MISMATCH" in out.stderr


def test_an_expired_generated_development_certificate_is_regenerated(tmp_path):
    _write_pair(tmp_path, self_signed=True, expired=True, org="SAHOOL-DEV-SELF-SIGNED")
    out = _run(tmp_path, "development")
    assert out.returncode == 0, out.stderr
    assert _cert(tmp_path).not_valid_after_utc > dt.datetime.now(dt.UTC)


def test_an_expired_operator_certificate_is_refused_not_replaced(tmp_path):
    _write_pair(tmp_path, self_signed=False, expired=True)
    before = _snapshot(tmp_path)
    for env_value in ("development", "production"):
        out = _run(tmp_path, env_value)
        assert out.returncode == 1
        assert "GATEWAY_TLS_EXPIRED" in out.stderr
    assert _snapshot(tmp_path) == before


def test_a_domain_that_would_inject_into_the_subject_is_refused(tmp_path):
    out = _run(tmp_path, "development", domain="evil/CN=attacker")
    assert out.returncode == 1
    assert "GATEWAY_TLS_BAD_DOMAIN" in out.stderr
    assert list(tmp_path.iterdir()) == []


def test_missing_openssl_is_a_named_failure_not_a_silent_success(tmp_path):
    tools = tmp_path / "bin"
    tools.mkdir()
    for tool in ("tr", "sed", "mktemp", "cat", "chmod", "mv", "rm"):
        found = shutil.which(tool)
        assert found, tool
        (tools / tool).symlink_to(found)
    tls = tmp_path / "tls"
    tls.mkdir()
    out = _run(tls, "development", path=str(tools))
    assert out.returncode == 1
    assert "GATEWAY_TLS_TOOLING_MISSING" in out.stderr
    assert list(tls.iterdir()) == []
