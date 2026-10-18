"""Verify operator cwd independence and imports in the actual Docker COPY layout.

Uses installed Python dependencies; this is packaging/import evidence, not a
Docker build or a live-service acceptance claim.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

repo = Path(__file__).resolve().parents[4]
with tempfile.TemporaryDirectory(prefix="rag-owner-layout-") as temporary:
    image = Path(temporary) / "app"
    image.mkdir()
    copied = []
    for line in (
        (repo / "services/rag-retrieval/Dockerfile").read_text(encoding="utf-8").splitlines()
    ):
        if not line.startswith("COPY "):
            continue
        _, source, destination = line.split()
        if destination == ".":
            continue
        target = image / Path(destination).relative_to("/app")
        origin = repo / source
        if origin.is_dir():
            shutil.copytree(origin, target, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)
        copied.append(source)
    program = "\n".join(
        [
            "import sys, pathlib, json",
            f"sys.path.insert(0, {str(image)!r})",
            "import main, retrieval_profile, reindex_manifest, runtime_transport",
            "modules = [main, retrieval_profile, reindex_manifest, runtime_transport]",
            f"assert all(pathlib.Path(m.__file__).parent == pathlib.Path({str(image)!r}) for m in modules)",
            "assert main._profile is None",
            "print(json.dumps({'canonical_imports': [m.__name__ for m in modules], 'legacy_default_preserved': True}))",
        ]
    )
    runtime = subprocess.run(
        [sys.executable, "-I", "-c", program],
        cwd=temporary,
        capture_output=True,
        text=True,
        check=True,
    )
    operator = subprocess.run(
        [sys.executable, "-I", str(repo / "services/qdrant-seed/reindex.py"), "--help"],
        cwd=temporary,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--prepare-shadow" in operator.stdout
    print(
        json.dumps(
            {
                "copied_paths": copied,
                "image_layout_import": json.loads(runtime.stdout),
                "operator_outside_repo_cwd": True,
                "docker_engine_used": False,
                "network_or_database_contact": False,
            },
            indent=2,
        )
    )
