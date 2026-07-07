"""تحقّق دخانيّ — رِندرِر خريطة النشر ينتج PNG صالحاً (يتطلّب matplotlib/numpy).

يُتخطّى إن غابت المكتبات الرسوميّة (importorskip) — فلا يكسر بيئة بلا matplotlib.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("matplotlib")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from map_layout import build_map_layout  # noqa: E402
from publication_map import render_publication_png  # noqa: E402

pytestmark = pytest.mark.unit

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_render_returns_valid_png_bytes():
    import numpy as np

    values = np.linspace(0, 1, 16).reshape(4, 4)
    layout = build_map_layout(
        {
            "title": "اختبار",
            "map_width_m": 4000,
            "classes": [{"label": "منخفض", "color": "#ffffcc"}],
            "meta": {"source": "CDSE", "resolution_m": 10, "quality_score": 0.9},
        }
    )
    png = render_publication_png(values, layout, cmap="viridis", vmin=0, vmax=1, dpi=150)
    assert isinstance(png, bytes) and png.startswith(_PNG_MAGIC)
    assert len(png) > 1000  # صورة حقيقيّة لا فارغة


def test_render_rejects_empty_or_non_2d():
    import numpy as np

    layout = build_map_layout({"title": "x", "map_width_m": 1000})
    with pytest.raises(ValueError):
        render_publication_png(np.array([]), layout)
    with pytest.raises(ValueError):
        render_publication_png(np.array([1, 2, 3]), layout)  # 1D
