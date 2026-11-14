"""Direct script startup exposes the same routes and module state as import startup."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_script_registers_routes_before_starting_server():
    script = """
import runpy, sys, types
uvicorn = types.ModuleType("uvicorn")
sys.modules["uvicorn"] = uvicorn

def inspect(app, **kwargs):
    paths = {getattr(route, 'path', None) for route in app.routes}
    assert '/healthz' in paths, paths
    assert '/runtime-identity' in paths, paths
    import main
    assert main.app is app
    assert main.ingest_reading.__globals__['main'].app is app
    print('SCRIPT_ROUTES_READY')
    raise SystemExit(0)

uvicorn.run = inspect
runpy.run_path('main.py', run_name='__main__')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT / "services/soil-service",
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SCRIPT_ROUTES_READY" in result.stdout


def test_video_processor_script_shares_one_main_module():
    """SOIL-01 sibling: routers `import main`; direct run must not load a second copy.

    Otherwise route handlers write ``main.STREAMS`` while the served app's lifespan cleans
    ``__main__.STREAMS`` (always empty), so live capture tasks survive shutdown.
    """
    script = """
import runpy, sys, types
uvicorn = types.ModuleType("uvicorn")
sys.modules["uvicorn"] = uvicorn

def inspect(app, **kwargs):
    import main
    import routers.streams as streams
    assert main.app is app
    assert streams.main.app is app
    assert streams.create_stream.__globals__['main'].STREAMS is main.STREAMS
    # the served module (whose lifespan cancels STREAMS) is the one handlers mutate
    assert sys.modules['__main__'].STREAMS is streams.main.STREAMS
    print('SCRIPT_SINGLE_MAIN')
    raise SystemExit(0)

uvicorn.run = inspect
runpy.run_path('main.py', run_name='__main__')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT / "services/video-processor",
        env={**os.environ, "PYTHONPATH": str(ROOT), "SAHOOL_ENV": "development"},
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SCRIPT_SINGLE_MAIN" in result.stdout
