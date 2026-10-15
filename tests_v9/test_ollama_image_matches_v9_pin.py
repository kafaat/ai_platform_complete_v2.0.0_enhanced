"""OLLAMA-UNIFIED-PINNED-0-3-0-01 — كلُّ ملفّ compose يشغّل Ollama يثبّت بصمةَ v9 نفسَها.

`docker-compose.unified.yml` كان على `ollama/ollama:0.3.0` و`docker-compose.fixed.yml` على
`0.30.8` بلا بصمة، بينما v9 على `0.32.5` ببصمة sha256. ملفٌّ بديلٌ يتأخّر عن المكدّس
القانونيّ يعيد ثغراتٍ أُغلقت فيه بصمت. **حدٌّ معلن:** يثبت التطابق مع v9، لا أنّ بصمة v9
نفسَها تحمل إصلاحَ CVE-2026-7482 (لم يُتحقَّق: OSV وNVD محجوبان بسياسة الخروج).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_DEFAULT = re.compile(r"^\$\{[A-Z_]+:-(?P<image>[^}]+)\}$")


def _ollama_images(path: Path) -> list[str]:
    services = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("services") or {}
    images = []
    for service in services.values():
        image = str((service or {}).get("image") or "")
        default = _DEFAULT.match(image)
        image = default.group("image") if default else image
        if image.startswith("ollama/ollama"):
            images.append(image)
    return images


def test_every_compose_ollama_image_is_the_v9_digest_pin() -> None:
    (v9_pin,) = _ollama_images(ROOT / "docker-compose.v9.yml")
    assert "@sha256:" in v9_pin, "v9 نفسُه بلا بصمة"
    drift = {
        path.name: image
        for path in sorted(ROOT.glob("docker-compose*.yml"))
        for image in _ollama_images(path)
        if image != v9_pin
    }
    assert drift == {}, f"ملفّات compose تشغّل Ollama بغير بصمة v9 ({v9_pin}): {drift}"
