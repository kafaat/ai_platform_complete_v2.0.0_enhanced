"""سكربتُ TLS المشترك لخادمَي v9 الداخليَّين — سلوكُه الحقيقيّ يُشغَّل بـ``sh`` على مجلّداتٍ مؤقّتة.

``scripts/tls/ensure_service_tls.sh`` تُشغّله مهمّتا ``sahool-nats-tls-init`` و``sahool-postgres-tls-init``
(NATS-BROKER-HAS-NO-AUTHENTICATION-SO-ACTUATOR-COMMANDS-ARE-UNGUARDED-01 ·
POSTGRES-V9-HAS-NO-TLS-SO-EVERY-CLIENT-IS-PLAINTEXT-01). سياسةٌ واحدةٌ لا نسختان: مادّةٌ حاضرةٌ تُفحَص
ولا تُمَسّ؛ غائبةٌ تُولَّد **فقط** في تطويرٍ صريح (ويُحذَف مفتاحُ CA)؛ وخارجه الغائبُ والذاتيُّ ومادّةُ
التطوير المنسيّة كلُّها فشلٌ مُسمّى. وكلُّ شاهدٍ هنا يُشغَّل للخادمين معاً — لأنّ رمزَ الفشل واسمَ SAN
مُدخَلان، وخطأٌ في تمريرهما لأحدهما يُخفيه اختبارٌ يقيس الآخرَ وحدَه.

عقدُ compose لكلٍّ منهما في ``test_nats_tls_init.py`` و``test_postgres_tls.py``.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "tls" / "ensure_service_tls.sh"
SH = shutil.which("sh") or "/bin/sh"
DEV_ORG = "SAHOOL-DEV-SELF-SIGNED"
SERVICES = (("NATS", "sahool-nats"), ("POSTGRES", "sahool-postgres"))

#: الخادمُ الذي يُشغَّل له الشاهدُ الحاليّ — يضبطه المُثبِّتُ أدناه لكلّ معامل.
SERVICE: tuple[str, str] = SERVICES[0]

pytestmark = [pytest.mark.unit]
if not shutil.which("openssl"):  # pragma: no cover - كلُّ مِرقاةٍ في CI فيها openssl
    pytestmark.append(pytest.mark.skip(reason="openssl CLI غائب — سلوكُ السكربت لا يُقاس بلا أداته"))


@pytest.fixture(autouse=True, params=SERVICES, ids=[c for c, _ in SERVICES])
def _service(request, monkeypatch):
    monkeypatch.setattr(f"{__name__}.SERVICE", request.param)
    return request.param


def _run(
    tls_dir: Path,
    env_value: str | None,
    *,
    path: str | None = None,
    service: tuple[str, str] | None = None,
    extra: dict[str, str] | None = None,
):
    code, host = service or SERVICE
    env = {k: v for k, v in os.environ.items() if k != "SAHOOL_ENV" and not k.startswith("TLS_")}
    env.update({"TLS_DIR": str(tls_dir), "TLS_CODE": code, "TLS_SERVICE_HOST": host})
    env.update(extra or {})
    if env_value is not None:
        env["SAHOOL_ENV"] = env_value
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        [SH, str(SCRIPT)], env=env, capture_output=True, text=True, encoding="utf-8"
    )


def _snapshot(tls_dir: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(tls_dir)): p.read_bytes()
        for p in sorted(tls_dir.rglob("*"))
        if p.is_file()
    }


def _pem(cert: x509.Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def _write_material(
    tls_dir: Path,
    *,
    self_signed: bool = False,
    expired: bool = False,
    org: str | None = None,
    dns: tuple[str, ...] | None = None,
    foreign_ca: bool = False,
    bundle: bool = False,
) -> None:
    """مادّةُ مشغِّلٍ حقيقيّة بـcryptography: خادمٌ صادرٌ عن CA (أو ذاتيّ)، ساري أو منتهٍ."""
    dns = dns or (SERVICE[1],)
    now = dt.datetime.now(dt.UTC)
    not_after = now - dt.timedelta(days=1) if expired else now + dt.timedelta(days=30)

    def name(cn: str) -> x509.Name:
        attrs = [x509.NameAttribute(NameOID.COMMON_NAME, cn)]
        if org:
            attrs.insert(0, x509.NameAttribute(NameOID.ORGANIZATION_NAME, org))
        return x509.Name(attrs)

    def ca_cert(cn: str):
        key = ec.generate_private_key(ec.SECP256R1())
        cert = (
            x509.CertificateBuilder()
            .subject_name(name(cn))
            .issuer_name(name(cn))
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=2))
            .not_valid_after(now + dt.timedelta(days=60))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(key, hashes.SHA256())
        )
        return key, cert

    ca_key, ca = ca_cert("Operator Internal CA")
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    subject = name(SERVICE[1])
    issuer, signer = (subject, leaf_key) if self_signed else (ca.subject, ca_key)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=2))
        .not_valid_after(not_after)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(d) for d in dns]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(signer, hashes.SHA256())
    )
    trusted = ca_cert("Some Other CA")[1] if foreign_ca else ca
    (tls_dir / "server").mkdir(parents=True, exist_ok=True)
    (tls_dir / "ca").mkdir(parents=True, exist_ok=True)
    (tls_dir / "server" / "server.pem").write_bytes(_pem(leaf))
    (tls_dir / "server" / "server-key.pem").write_bytes(
        leaf_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    ca_pem = _pem(trusted) + (_pem(ca_cert("Second CA")[1]) if bundle else b"")
    (tls_dir / "ca" / "ca.pem").write_bytes(ca_pem)


def _cert(path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def test_fresh_development_checkout_gets_a_ca_and_a_server_certificate_that_chain(tmp_path):
    out = _run(tmp_path, "development")
    assert out.returncode == 0, out.stderr
    leaf = _cert(tmp_path / "server" / "server.pem")
    ca = _cert(tmp_path / "ca" / "ca.pem")
    assert leaf.issuer == ca.subject and leaf.subject != leaf.issuer, "الخادمُ ذاتيٌّ لا صادرٌ عن CA"
    ca.public_key().verify(
        leaf.signature, leaf.tbs_certificate_bytes, ec.ECDSA(leaf.signature_hash_algorithm)
    )
    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert SERVICE[1] in san.get_values_for_type(x509.DNSName), "العملاءُ يفحصون الاسم"
    for cert in (leaf, ca):
        orgs = [a.value for a in cert.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)]
        assert orgs == [DEV_ORG], "مادّةُ التطوير بلا وسمٍ يكشفها خارج التطوير"
    assert oct((tmp_path / "server" / "server-key.pem").stat().st_mode & 0o777) == "0o600"
    files = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
    hashed = [f for f in files if re.fullmatch(r"ca/[0-9a-f]{8}\.0", f)]
    assert len(hashed) == 1, f"لا فهرسَ ثقةٍ واحد لـSSL_CERT_DIR: {files}"
    assert (tmp_path / hashed[0]).read_bytes() == (tmp_path / "ca" / "ca.pem").read_bytes()
    assert set(files) == {"ca/ca.pem", hashed[0], "server/server.pem", "server/server-key.pem"}, (
        f"بقايا عمل — أو مفتاحُ CA — في المجلّد المُركَّب: {files}"
    )
    assert not any("key" in f for f in files if f.startswith("ca/")), "مفتاحٌ في مجلّد العملاء"


def test_existing_material_is_never_rewritten(tmp_path):
    assert _run(tmp_path, "development").returncode == 0
    before = _snapshot(tmp_path)
    again = _run(tmp_path, "development")
    assert again.returncode == 0, again.stderr
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("env_value", ["production", "PRODUCTION", "staging", "", None, "develop"])
def test_missing_material_outside_explicit_development_fails_loudly_and_writes_nothing(
    tmp_path, env_value
):
    out = _run(tmp_path, env_value)
    assert out.returncode == 1
    assert f"{SERVICE[0]}_TLS_MISSING" in out.stderr
    assert "server.pem" in out.stderr and "SAHOOL_ENV=development" in out.stderr
    assert list(tmp_path.iterdir()) == [], "خارج التطوير الصريح لا يُولَّد شيء"


def test_production_refuses_leftover_development_material(tmp_path):
    assert _run(tmp_path, "development").returncode == 0
    before = _snapshot(tmp_path)
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert f"{SERVICE[0]}_TLS_DEV_MATERIAL_OUTSIDE_DEV" in out.stderr
    assert _snapshot(tmp_path) == before


def test_production_refuses_a_self_signed_server_certificate(tmp_path):
    _write_material(tmp_path, self_signed=True, foreign_ca=True)
    # ذاتيٌّ لا يتسلسل إلى CA آخر؛ فلْيكن CA هو نفسُه كي يبلغ الفحصُ فرعَ «ذاتيّ التوقيع».
    shutil.copy(tmp_path / "server" / "server.pem", tmp_path / "ca" / "ca.pem")
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert f"{SERVICE[0]}_TLS_SELF_SIGNED_OUTSIDE_DEV" in out.stderr


def test_production_accepts_ca_issued_material_and_only_indexes_the_ca(tmp_path):
    _write_material(tmp_path)
    before = _snapshot(tmp_path)
    out = _run(tmp_path, "production")
    assert out.returncode == 0, out.stderr
    assert "issuer=[CN=Operator Internal CA]" in out.stdout
    after = _snapshot(tmp_path)
    added = sorted(set(after) - set(before))
    assert len(added) == 1 and re.fullmatch(r"ca/[0-9a-f]{8}\.0", added[0]), added
    assert {k: after[k] for k in before} == before, "مادّةُ المشغِّل مُسَّت"


def test_a_server_certificate_without_the_service_name_is_refused(tmp_path):
    _write_material(tmp_path, dns=("db.example.com",))
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert f"{SERVICE[0]}_TLS_NAME_MISMATCH" in out.stderr


def test_a_ca_that_did_not_issue_the_server_certificate_is_refused(tmp_path):
    _write_material(tmp_path, foreign_ca=True)
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert f"{SERVICE[0]}_TLS_CHAIN_INVALID" in out.stderr


def test_a_ca_bundle_is_refused_rather_than_half_trusted(tmp_path):
    _write_material(tmp_path, bundle=True)
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert f"{SERVICE[0]}_TLS_CA_BUNDLE_UNSUPPORTED" in out.stderr


def test_partial_material_fails_in_every_environment_without_overwriting(tmp_path):
    (tmp_path / "server").mkdir()
    (tmp_path / "server" / "server-key.pem").write_text("operator key\n", encoding="utf-8")
    before = _snapshot(tmp_path)
    for env_value in ("development", "production"):
        out = _run(tmp_path, env_value)
        assert out.returncode == 1
        assert f"{SERVICE[0]}_TLS_PARTIAL" in out.stderr
    assert _snapshot(tmp_path) == before


def test_a_key_that_does_not_match_the_certificate_is_refused(tmp_path):
    _write_material(tmp_path)
    other = tmp_path / "other"
    _write_material(other)
    shutil.copy(other / "server" / "server-key.pem", tmp_path / "server" / "server-key.pem")
    shutil.rmtree(other)
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert f"{SERVICE[0]}_TLS_KEY_MISMATCH" in out.stderr


def test_expired_generated_development_material_is_regenerated(tmp_path):
    _write_material(tmp_path, expired=True, org=DEV_ORG)
    out = _run(tmp_path, "development")
    assert out.returncode == 0, out.stderr
    assert _cert(tmp_path / "server" / "server.pem").not_valid_after_utc > dt.datetime.now(dt.UTC)


def test_expired_operator_material_is_refused_not_replaced(tmp_path):
    _write_material(tmp_path, expired=True)
    before = _snapshot(tmp_path)
    for env_value in ("development", "production"):
        out = _run(tmp_path, env_value)
        assert out.returncode == 1
        assert f"{SERVICE[0]}_TLS_EXPIRED" in out.stderr
    assert _snapshot(tmp_path) == before


def test_a_rotated_ca_drops_the_stale_trust_index(tmp_path):
    """CA قديمٌ يبقى موثوقاً ما بقي ملفُّه في ``SSL_CERT_DIR`` — والتدويرُ يُراد به إسقاطُه."""
    _write_material(tmp_path)
    (tmp_path / "ca" / "deadbeef.0").write_text("stale CA\n", encoding="utf-8")
    out = _run(tmp_path, "production")
    assert out.returncode == 0, out.stderr
    assert not (tmp_path / "ca" / "deadbeef.0").exists()


def test_missing_openssl_is_a_named_failure_not_a_silent_success(tmp_path):
    tools = tmp_path / "bin"
    tools.mkdir()
    for tool in ("tr", "sed", "mktemp", "cat", "chmod", "mv", "rm", "mkdir", "grep", "cp"):
        found = shutil.which(tool)
        assert found, tool
        (tools / tool).symlink_to(found)
    tls = tmp_path / "tls"
    tls.mkdir()
    out = _run(tls, "development", path=str(tools))
    assert out.returncode == 1
    assert f"{SERVICE[0]}_TLS_TOOLING_MISSING" in out.stderr
    assert list(tls.iterdir()) == []


def test_an_unknown_service_code_or_an_empty_host_is_refused_before_anything_is_written(tmp_path):
    for code, host, marker in (
        ("REDIS", "sahool-redis", "SERVICE_TLS_MISCONFIGURED"),
        ("", "sahool-nats", "SERVICE_TLS_MISCONFIGURED"),
        (SERVICE[0], "", f"{SERVICE[0]}_TLS_MISCONFIGURED"),
    ):
        out = _run(tmp_path, "development", service=(code, host))
        assert out.returncode == 1 and marker in out.stderr, (code, host, out.stderr)
    assert list(tmp_path.iterdir()) == []


def test_install_dir_receives_a_private_key_only_its_owner_can_read(tmp_path):
    """Postgres يرفض مفتاحاً يقرؤه غيرُ مالكه — فيُنسَخ الزوجُ إلى مجلّدِ الخادم ``0600``."""
    tls, install = tmp_path / "tls", tmp_path / "install"
    tls.mkdir()
    install.mkdir()
    owner = f"{os.getuid()}:{os.getgid()}"
    out = _run(
        tls, "development", extra={"TLS_INSTALL_DIR": str(install), "TLS_INSTALL_OWNER": owner}
    )
    assert out.returncode == 0, out.stderr
    assert sorted(p.name for p in install.iterdir()) == ["server-key.pem", "server.pem"]
    assert oct((install / "server-key.pem").stat().st_mode & 0o777) == "0o600"
    assert (install / "server.pem").read_bytes() == (tls / "server" / "server.pem").read_bytes()
    assert not (install / "ca.pem").exists(), "مجلّدُ الخادم لا يحمل CA العملاء"


def test_install_dir_without_an_owner_is_refused(tmp_path):
    out = _run(tmp_path, "development", extra={"TLS_INSTALL_DIR": str(tmp_path)})
    assert out.returncode == 1
    assert f"{SERVICE[0]}_TLS_MISCONFIGURED" in out.stderr
