"""scripts/check_compose_host_ports.py: names the busy host port, its service and the variable that moves it.

Motivated by a Windows ``docker compose up`` that died on ``127.0.0.1:8554`` (sahool-zlmediakit
RTSP) with no hint of which service held the port or how to move it.
"""

from __future__ import annotations

import importlib.util
import socket
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_compose_host_ports.py"
_spec = importlib.util.spec_from_file_location("check_compose_host_ports", SCRIPT)
ports = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ports
_spec.loader.exec_module(ports)


def _free_port(kind: int = socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _compose(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "docker-compose.yml"
    path.write_text(body, encoding="utf-8")
    return path


def _one_service(var: str, port: int, proto: str = "") -> str:
    suffix = f"/{proto}" if proto else ""
    return (
        "services:\n"
        "  media:\n"
        "    image: example\n"
        "    ports:\n"
        f'    - "127.0.0.1:${{{var}:-{port}}}:554{suffix}"\n'
    )


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("COMPOSE_FILE", "T_RTSP_HOST_PORT", "T_RTP_HOST_PORT"):
        monkeypatch.delenv(name, raising=False)


def test_a_busy_tcp_port_is_reported_with_the_variable_that_moves_it(tmp_path, capsys, clean_env):
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    busy = holder.getsockname()[1]
    try:
        compose = _compose(tmp_path, _one_service("T_RTSP_HOST_PORT", busy))
        rc = ports.main(["-f", str(compose)])
    finally:
        holder.close()
    out = capsys.readouterr().out
    assert rc == 1
    assert f"BUSY     127.0.0.1:{busy}/tcp" in out
    assert "media" in out and "docker-compose.yml:5" in out
    assert "set T_RTSP_HOST_PORT=" in out
    assert f"netstat -ano | findstr :{busy}" in out


def test_the_same_port_once_released_passes(tmp_path, capsys, clean_env):
    free = _free_port()
    compose = _compose(tmp_path, _one_service("T_RTSP_HOST_PORT", free))
    assert ports.main(["-f", str(compose)]) == 0
    assert "all host ports can be bound" in capsys.readouterr().out


def test_a_busy_udp_port_is_reported(tmp_path, capsys, clean_env):
    holder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    holder.bind(("127.0.0.1", 0))
    busy = holder.getsockname()[1]
    try:
        compose = _compose(tmp_path, _one_service("T_RTP_HOST_PORT", busy, "udp"))
        rc = ports.main(["-f", str(compose)])
    finally:
        holder.close()
    out = capsys.readouterr().out
    assert rc == 1
    assert f"127.0.0.1:{busy}/udp" in out and "T_RTP_HOST_PORT" in out


def test_dot_env_moves_the_port_and_the_shell_beats_dot_env(
    tmp_path, capsys, clean_env, monkeypatch
):
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    busy = holder.getsockname()[1]
    try:
        compose = _compose(tmp_path, _one_service("T_RTSP_HOST_PORT", busy))
        (tmp_path / ".env").write_text(
            f"# moved off the busy port\nT_RTSP_HOST_PORT={_free_port()}\n", encoding="utf-8"
        )
        assert ports.main(["-f", str(compose)]) == 0  # .env next to the compose file is read
        monkeypatch.setenv("T_RTSP_HOST_PORT", str(busy))  # shell env wins, as in Compose
        assert ports.main(["-f", str(compose)]) == 1
    finally:
        holder.close()
    assert f"127.0.0.1:{busy}/tcp" in capsys.readouterr().out


def test_two_services_on_one_host_port_are_a_conflict_even_when_free(tmp_path, capsys, clean_env):
    free = _free_port()
    compose = _compose(
        tmp_path,
        "services:\n"
        "  a:\n"
        f"    ports: ['127.0.0.1:${{A_PORT:-{free}}}:80']\n"
        "  b:\n"
        "    ports:\n"
        f"      - {free}:81\n",
    )
    assert ports.main(["-f", str(compose)]) == 1
    out = capsys.readouterr().out
    assert out.count("CONFLICT") == 2
    assert "set A_PORT=" in out and "hard-coded in docker-compose.yml:6" in out


def test_interpolation_follows_compose_semantics():
    env = {"SET": "1", "EMPTY": ""}
    assert ports.interpolate("${SET:-9}", env)[0] == "1"
    assert ports.interpolate("${EMPTY:-9}", env)[0] == "9"
    assert ports.interpolate("${EMPTY-9}", env)[0] == ""
    assert ports.interpolate("${UNSET-9}", env)[0] == "9"
    assert ports.interpolate("$$SET", env)[0] == "$SET"
    value, names, errors = ports.interpolate("${UNSET:?needed}", env)
    assert value == "" and names == ["UNSET"] and errors


def test_ephemeral_and_long_form_entries(tmp_path, clean_env):
    free = _free_port()
    compose = _compose(
        tmp_path,
        "services:\n"
        "  pg:\n"
        "    ports:\n"
        "      - '127.0.0.1::5432'\n"
        "      - '5432'\n"
        "      - target: 80\n"
        f"        published: '${{LONG_PORT:-{free}}}'\n"
        "        host_ip: 127.0.0.1\n"
        "        protocol: udp\n",
    )
    bindings = []
    for entry in ports.read_ports(compose):
        bindings.extend(ports.resolve(entry, {})[0])
    assert [(b.host_ip, b.host_port, b.protocol, b.variables) for b in bindings] == [
        ("127.0.0.1", free, "udp", ["LONG_PORT"])
    ]


def test_runs_as_a_plain_script_without_bash(tmp_path, clean_env):
    compose = _compose(tmp_path, _one_service("T_RTSP_HOST_PORT", _free_port()))
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "-f", str(compose), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert '"blocking": 0' in proc.stdout


# ── the repository's own compose files ──────────────────────────────────────────────────────

_REPO_COMPOSE = sorted(ROOT.glob("docker-compose*.yml"))


@pytest.mark.parametrize("compose", _REPO_COMPOSE, ids=lambda p: p.name)
def test_line_scanner_reads_the_same_ports_as_pyyaml(compose):
    """The stdlib scanner must see exactly what YAML sees, or it misses a busy port silently."""
    doc = yaml.safe_load(compose.read_text(encoding="utf-8")) or {}
    expected = {
        name: [str(p) if not isinstance(p, dict) else {k: str(v) for k, v in p.items()} for p in sv]
        for name, spec in (doc.get("services") or {}).items()
        if (sv := (spec or {}).get("ports"))
    }
    got: dict[str, list] = {}
    for entry in ports.read_ports(compose):
        got.setdefault(entry.service, []).append(entry.spec)
    assert got == expected


@pytest.mark.parametrize("compose", _REPO_COMPOSE, ids=lambda p: p.name)
def test_every_fixed_host_port_in_the_repo_is_movable_by_a_variable(compose):
    """A hard-coded host port leaves an operator whose port is taken no way out but editing compose."""
    hard_coded = []
    for entry in ports.read_ports(compose):
        for b in ports.resolve(entry, {})[0]:
            if not b.variables:
                hard_coded.append(f"{compose.name}:{b.line} {b.service} {b.raw}")
    assert hard_coded == []


def test_zlmediakit_rtsp_8554_is_moved_by_zlm_rtsp_host_port_and_stays_on_loopback():
    compose = ROOT / "docker-compose.v9.yml"
    by_default = {}
    moved = {}
    for entry in ports.read_ports(compose):
        if entry.service != "sahool-zlmediakit":
            continue
        for b in ports.resolve(entry, {})[0]:
            by_default[(b.host_port, b.protocol)] = (b.host_ip, b.variables)
        for b in ports.resolve(entry, {"ZLM_RTSP_HOST_PORT": "18554"})[0]:
            moved[(b.host_port, b.protocol)] = b.host_ip
    assert by_default == {
        (8188, "tcp"): ("127.0.0.1", ["ZLM_HTTP_HOST_PORT"]),
        (8554, "tcp"): ("127.0.0.1", ["ZLM_RTSP_HOST_PORT"]),
        (1935, "tcp"): ("127.0.0.1", ["ZLM_RTMP_HOST_PORT"]),
        (10000, "udp"): ("127.0.0.1", ["ZLM_RTP_HOST_PORT"]),
    }
    assert (18554, "tcp") in moved and (8554, "tcp") not in moved
    assert set(moved.values()) == {"127.0.0.1"}


def test_every_port_variable_is_in_env_example_with_the_compose_default():
    declared = ports.read_env_file(ROOT / ".env.example")
    mismatched = []
    for compose in _REPO_COMPOSE:
        for entry in ports.read_ports(compose):
            for b in ports.resolve(entry, {})[0]:
                for var in b.variables:
                    if declared.get(var) != str(b.host_port):
                        mismatched.append(
                            f"{var}: .env.example={declared.get(var)!r} compose={b.host_port}"
                        )
    assert mismatched == []


def test_a_dot_env_saved_with_a_bom_still_moves_the_port(tmp_path, capsys, clean_env):
    """Windows PowerShell 5 ``Set-Content -Encoding UTF8`` prefixes a BOM; the first key must survive."""
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    busy = holder.getsockname()[1]
    try:
        compose = _compose(tmp_path, _one_service("T_RTSP_HOST_PORT", busy))
        (tmp_path / ".env").write_bytes(
            b"\xef\xbb\xbfT_RTSP_HOST_PORT=" + str(_free_port()).encode() + b"\r\n"
        )
        rc = ports.main(["-f", str(compose)])
    finally:
        holder.close()
    assert rc == 0, capsys.readouterr().out
