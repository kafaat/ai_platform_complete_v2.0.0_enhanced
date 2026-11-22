"""The frontend container stamps the runtime Railway deployment into /build-info.json.

``frontend/scripts/write-build-info.mjs`` writes the file at image build time, when
Railway gives the commit but not ``RAILWAY_DEPLOYMENT_ID`` (the build logs of #1565 show
it empty on staging and production). ``deploy/railway/render_frontend.py`` runs at every
container start and sets ``build_id`` from the runtime value, so it names the real
deployment, also when Railway reuses an image without rebuilding. Only that key changes,
and nothing here may stop nginx from starting.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_RENDER = ROOT / "deploy/railway/render_frontend.py"
_DOCKERFILE = ROOT / "deploy/railway/Dockerfile.frontend"
SHA = "0123456789abcdef0123456789abcdef01234567"
BUILT = {"service": "sahool-frontend", "git_sha": SHA, "build_id": f"railway-{SHA[:12]}"}


def _render():
    spec = importlib.util.spec_from_file_location("railway_render_frontend_build_info", _RENDER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _file(tmp_path: Path, content: str | None = None) -> Path:
    path = tmp_path / "build-info.json"
    path.write_text(json.dumps(BUILT) + "\n" if content is None else content, encoding="utf-8")
    return path


def test_the_runtime_deployment_id_replaces_only_build_id(tmp_path):
    path = _file(tmp_path)
    result = _render().stamp_build_id(
        path, {"RAILWAY_DEPLOYMENT_ID": "3e048e58-aaaa-bbbb-cccc-0123456789ab"}
    )
    assert result.startswith("stamped")
    info = json.loads(path.read_text(encoding="utf-8"))
    assert info == {**BUILT, "build_id": "railway-3e048e58-aaaa-bbbb-cccc-0123456789ab"}
    assert info["git_sha"] == SHA


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"RAILWAY_DEPLOYMENT_ID": ""},
        {"RAILWAY_DEPLOYMENT_ID": "  "},
        {"RAILWAY_DEPLOYMENT_ID": "bad id; with spaces"},
    ],
)
def test_without_a_valid_deployment_id_the_build_time_value_stays(tmp_path, env):
    path = _file(tmp_path)
    before = path.read_bytes()
    assert _render().stamp_build_id(path, env).startswith("kept")
    assert path.read_bytes() == before


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_an_unreadable_file_is_left_alone_and_never_raises(tmp_path, content):
    path = _file(tmp_path, content)
    assert _render().stamp_build_id(path, {"RAILWAY_DEPLOYMENT_ID": "dep-1"}).startswith("left")
    assert path.read_text(encoding="utf-8") == content


def test_a_missing_file_never_raises(tmp_path):
    result = _render().stamp_build_id(tmp_path / "absent.json", {"RAILWAY_DEPLOYMENT_ID": "dep-1"})
    assert result.startswith("left")


def test_main_stamps_the_file_after_rendering_nginx(tmp_path, monkeypatch, capsys):
    module = _render()
    source = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    (tmp_path / "nginx.conf").write_text(source, encoding="utf-8")
    (tmp_path / "resolv.conf").write_text("nameserver 127.0.0.11\n", encoding="utf-8")
    path = _file(tmp_path)
    monkeypatch.setenv("SAHOOL_AUTH_UPSTREAM", "sahool-auth-main.railway.internal:8000")
    monkeypatch.setenv("SAHOOL_PLATFORM_UPSTREAM", "sahool-platform.railway.internal:8000")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "dep-42")
    monkeypatch.setattr(
        "sys.argv",
        [
            "render_frontend.py",
            "--source",
            str(tmp_path / "nginx.conf"),
            "--output",
            str(tmp_path / "out.conf"),
            "--resolv-conf",
            str(tmp_path / "resolv.conf"),
            "--build-info",
            str(path),
        ],
    )
    module.main()
    assert json.loads(path.read_text(encoding="utf-8"))["build_id"] == "railway-dep-42"
    assert "stamped build_id=railway-dep-42" in capsys.readouterr().out


def test_the_image_gives_the_nginx_user_this_one_file_only():
    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")
    copy = dockerfile.index("COPY --from=builder /app/dist /usr/share/nginx/html")
    chown = dockerfile.index("chown nginx:nginx /usr/share/nginx/html/build-info.json")
    user = dockerfile.index("USER nginx")
    assert copy < chown < user
    # Conditional, so a build whose writer left the file out still builds.
    assert "if [ -e /usr/share/nginx/html/build-info.json ]" in dockerfile
    assert "chown -R nginx:nginx /usr/share/nginx/html" not in dockerfile
