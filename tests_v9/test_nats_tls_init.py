"""وسيطُ NATS يُلزِم TLS، ولا يعمل بمادّةٍ ذاتيّةٍ أو تطويريّةٍ في الإنتاج بصمت.

**العطلُ مقيسٌ على main@1cb6cd6c:** منفذ العملاء 4222 نصٌّ صريح — `nats/nats.conf` بلا كتلة
``tls``، فكلماتُ مرور الخدمات في ``CONNECT`` والأحداثُ كلُّها تعبر ``sahool-internal`` مقروءة.
صار الوسيطُ يُلزِم TLS، والمادّةُ لا تُلتزَم: ``sahool-nats-tls-init`` يسبقه ويفحصها، ويولّد CA
تطويرٍ وشهادةَ خادمٍ **فقط** حين تغيب و``SAHOOL_ENV`` صريحةٌ غيرُ إنتاجيّة — سياسةُ
``sahool-nginx-tls-init`` نفسُها (``tests_v9/test_gateway_tls_init.py``)، بملفّاتٍ مستقلّة.

شطران: **عقدُ compose** (الترتيب · التركيب · الافتراض · ما يبلغ العملاء)، و**سلوكُ السكربت
الحقيقيّ** يُشغَّل بـ``sh`` على مجلّداتٍ مؤقّتة. والتحقّقُ الحيّ على nats-server حقيقيّ في
``tests_v9/test_nats_least_privilege.py``.
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
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.v9.yml"
CONF = ROOT / "nats" / "nats.conf"
SCRIPT = ROOT / "scripts" / "nats" / "ensure_nats_tls.sh"
INIT = "sahool-nats-tls-init"
BROKER = "sahool-nats"
SH = shutil.which("sh") or "/bin/sh"
DEV_VALUES = {"development", "dev", "local", "test"}
DEV_ORG = "SAHOOL-DEV-SELF-SIGNED"
CLIENT_CA_DIR = "/etc/sahool/nats-ca"

pytestmark = [pytest.mark.unit]
if not shutil.which("openssl"):  # pragma: no cover - كلُّ مِرقاةٍ في CI فيها openssl
    pytestmark.append(pytest.mark.skip(reason="openssl CLI غائب — سلوكُ السكربت لا يُقاس بلا أداته"))


def _services() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def _conf_body() -> str:
    return "\n".join(
        line
        for line in CONF.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def _nats_clients() -> dict[str, dict]:
    return {
        name: svc
        for name, svc in _services().items()
        if isinstance(svc.get("environment"), dict) and "NATS_URL" in svc["environment"]
    }


# ── عقدُ compose ─────────────────────────────────────────────────────────────


def test_the_broker_config_requires_tls_from_the_mounted_pair():
    body = _conf_body()
    block = re.search(r"^tls\s*\{(?P<body>[^}]*)\}", body, re.M)
    assert block, "لا كتلةَ `tls` في nats.conf — 4222 نصٌّ صريحٌ يحمل كلماتِ المرور"
    cert = re.search(r'cert_file:\s*"([^"]+)"', block["body"])
    key = re.search(r'key_file:\s*"([^"]+)"', block["body"])
    assert cert and key
    assert os.path.dirname(cert[1]) == os.path.dirname(key[1]) == "/etc/nats/tls"
    assert "verify_and_map" not in block["body"] and "insecure" not in block["body"]
    mounts = [str(v) for v in _services()[BROKER]["volumes"]]
    assert "./nats/tls/server:/etc/nats/tls:ro" in mounts, "الوسيطُ لا يُركِّب زوجَه حيث يقرؤه"


def test_the_broker_waits_for_the_tls_gate():
    deps = _services()[BROKER].get("depends_on") or {}
    assert deps.get(INIT, {}).get("condition") == "service_completed_successfully", (
        "sahool-nats يُقلِع بلا بوّابة TLS — شهادةٌ غائبة تصير حلقةَ إعادة تشغيل"
    )
    init = _services()[INIT]
    assert str(init.get("restart")) == "no"
    assert init.get("network_mode") == "none", "المهمّةُ تقرأ وتكتب مجلّداً فقط — لا شبكةَ لها"
    assert "./nats/tls:/etc/nats-tls" in [str(v) for v in init["volumes"]]
    assert "ensure_nats_tls.sh" in " ".join(str(x) for x in init["entrypoint"])


def test_the_gate_never_defaults_to_a_development_environment():
    raw = str(_services()[INIT]["environment"]["SAHOOL_ENV"])
    match = re.fullmatch(r"\$\{SAHOOL_ENV(?::?-(?P<default>[^}]*)|:\?[^}]*)?\}", raw)
    assert match, f"SAHOOL_ENV في {INIT} ليس تمريراً من البيئة: {raw!r}"
    assert (match.group("default") or "").strip().lower() not in DEV_VALUES, (
        f"{INIT} يفترض بيئةَ تطوير ({raw}) — نشرٌ بلا SAHOOL_ENV يولّد CA ذاتيّاً ويعمل به"
    )


def test_every_client_verifies_the_broker_with_its_ca_and_never_sees_the_key():
    """nats-py يُرقّي بـ``ssl.create_default_context()`` — ``CERT_REQUIRED`` وفحصُ الاسم.

    فالتحقّقُ قائمٌ بلا شيفرة، والناقصُ **الثقة**: CA الوسيط يصل عبر ``SSL_CERT_DIR``
    (إضافةً إلى مخزن النظام، لا استبدالاً) ومجلّدٍ لا مفتاحَ فيه.
    """
    offenders = []
    for name, svc in _nats_clients().items():
        env = svc["environment"]
        url = str(env["NATS_URL"])
        mounts = [str(v) for v in svc.get("volumes") or []]
        dirs = str(env.get("SSL_CERT_DIR") or "").split(":")
        if not url.startswith("tls://") or not url.endswith("@sahool-nats:4222"):
            offenders.append(f"{name}: {url[:40]}… ليس tls://…@sahool-nats:4222")
        if CLIENT_CA_DIR not in dirs or "/etc/ssl/certs" not in dirs:
            offenders.append(f"{name}: SSL_CERT_DIR={env.get('SSL_CERT_DIR')!r}")
        if f"./nats/tls/ca:{CLIENT_CA_DIR}:ro" not in mounts:
            offenders.append(f"{name}: لا يُركِّب CA الوسيط")
        if any(m.startswith(("./nats/tls/server", "./nats/tls:")) for m in mounts):
            offenders.append(f"{name}: يُركِّب مجلّدَ مفتاح الوسيط")
    assert _nats_clients(), "انهار الاستخراج — شرطٌ على لا عملاء يمرّ دائماً"
    assert not offenders, "\n  ".join(["عملاءُ لا يتحقّقون من الوسيط:", *offenders])


def test_no_broker_tls_material_can_be_committed():
    for name in ("server/server-key.pem", "server/server.pem", "ca/ca.pem", "ca/34fbece9.0"):
        rc = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", f"nats/tls/{name}"], cwd=ROOT, check=False
        ).returncode
        assert rc == 0, f"nats/tls/{name} غير مُتجاهَل — مادّةُ الوسيط قد تُلتزَم"


# ── سلوكُ السكربت الحقيقيّ ────────────────────────────────────────────────────


def _run(tls_dir: Path, env_value: str | None, *, path: str | None = None):
    env = {k: v for k, v in os.environ.items() if k != "SAHOOL_ENV"}
    env["NATS_TLS_DIR"] = str(tls_dir)
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
    dns: tuple[str, ...] = ("sahool-nats",),
    foreign_ca: bool = False,
    bundle: bool = False,
) -> None:
    """مادّةُ مشغِّلٍ حقيقيّة بـcryptography: خادمٌ صادرٌ عن CA (أو ذاتيّ)، ساري أو منتهٍ."""
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

    ca_key, ca = ca_cert("Operator NATS CA")
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    subject = name("sahool-nats")
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
    assert "sahool-nats" in san.get_values_for_type(x509.DNSName), "العملاءُ يفحصون الاسم"
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
    assert "NATS_TLS_MISSING" in out.stderr
    assert "server.pem" in out.stderr and "SAHOOL_ENV=development" in out.stderr
    assert list(tmp_path.iterdir()) == [], "خارج التطوير الصريح لا يُولَّد شيء"


def test_production_refuses_leftover_development_material(tmp_path):
    assert _run(tmp_path, "development").returncode == 0
    before = _snapshot(tmp_path)
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert "NATS_TLS_DEV_MATERIAL_OUTSIDE_DEV" in out.stderr
    assert _snapshot(tmp_path) == before


def test_production_refuses_a_self_signed_broker_certificate(tmp_path):
    _write_material(tmp_path, self_signed=True, foreign_ca=True)
    # ذاتيٌّ لا يتسلسل إلى CA آخر؛ فلْيكن CA هو نفسُه كي يبلغ الفحصُ فرعَ «ذاتيّ التوقيع».
    shutil.copy(tmp_path / "server" / "server.pem", tmp_path / "ca" / "ca.pem")
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert "NATS_TLS_SELF_SIGNED_OUTSIDE_DEV" in out.stderr


def test_production_accepts_ca_issued_material_and_only_indexes_the_ca(tmp_path):
    _write_material(tmp_path)
    before = _snapshot(tmp_path)
    out = _run(tmp_path, "production")
    assert out.returncode == 0, out.stderr
    assert "issuer=[CN=Operator NATS CA]" in out.stdout
    after = _snapshot(tmp_path)
    added = sorted(set(after) - set(before))
    assert len(added) == 1 and re.fullmatch(r"ca/[0-9a-f]{8}\.0", added[0]), added
    assert {k: after[k] for k in before} == before, "مادّةُ المشغِّل مُسَّت"


def test_a_broker_certificate_without_the_service_name_is_refused(tmp_path):
    _write_material(tmp_path, dns=("nats.example.com",))
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert "NATS_TLS_NAME_MISMATCH" in out.stderr


def test_a_ca_that_did_not_issue_the_broker_certificate_is_refused(tmp_path):
    _write_material(tmp_path, foreign_ca=True)
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert "NATS_TLS_CHAIN_INVALID" in out.stderr


def test_a_ca_bundle_is_refused_rather_than_half_trusted(tmp_path):
    _write_material(tmp_path, bundle=True)
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert "NATS_TLS_CA_BUNDLE_UNSUPPORTED" in out.stderr


def test_partial_material_fails_in_every_environment_without_overwriting(tmp_path):
    (tmp_path / "server").mkdir()
    (tmp_path / "server" / "server-key.pem").write_text("operator key\n", encoding="utf-8")
    before = _snapshot(tmp_path)
    for env_value in ("development", "production"):
        out = _run(tmp_path, env_value)
        assert out.returncode == 1
        assert "NATS_TLS_PARTIAL" in out.stderr
    assert _snapshot(tmp_path) == before


def test_a_key_that_does_not_match_the_certificate_is_refused(tmp_path):
    _write_material(tmp_path)
    other = tmp_path / "other"
    _write_material(other)
    shutil.copy(other / "server" / "server-key.pem", tmp_path / "server" / "server-key.pem")
    shutil.rmtree(other)
    out = _run(tmp_path, "production")
    assert out.returncode == 1
    assert "NATS_TLS_KEY_MISMATCH" in out.stderr


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
        assert "NATS_TLS_EXPIRED" in out.stderr
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
    assert "NATS_TLS_TOOLING_MISSING" in out.stderr
    assert list(tls.iterdir()) == []
