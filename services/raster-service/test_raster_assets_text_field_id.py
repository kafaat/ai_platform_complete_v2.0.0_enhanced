"""Regression: raster_assets persistence accepts Sahool text field IDs.

Runtime logs showed successful CDSE processing followed by:
``raster_assets persist skipped: missing/invalid field_id='fld_...'``.
That was caused by UUID-only validation even though ``raster_assets.field_id`` is
``VARCHAR(50)`` and production fields use IDs like ``fld_demo_001``.
"""

from __future__ import annotations

import uuid


def test_db_persist_accepts_sahool_text_field_ids():
    import db_persist

    assert db_persist._valid_field_id_text("fld_b1c8ff30d02c") is True
    assert db_persist._valid_field_id_text("fld_demo_001") is True
    assert db_persist._valid_field_id_text(str(uuid.uuid4())) is True


def test_db_persist_rejects_unsafe_or_overlong_field_ids():
    import db_persist

    assert db_persist._valid_field_id_text("") is False
    assert db_persist._valid_field_id_text("   ") is False
    assert db_persist._valid_field_id_text("fld/../../evil") is False
    assert db_persist._valid_field_id_text("x" * 51) is False


def test_asset_persistence_guard_uses_text_field_contract():
    import raster_asset_persistence

    assert raster_asset_persistence._is_valid_field_id_text("fld_b1c8ff30d02c") is True
    assert raster_asset_persistence._is_valid_field_id_text("fld_demo_001") is True
    assert raster_asset_persistence._is_valid_field_id_text(str(uuid.uuid4())) is True
    assert raster_asset_persistence._is_valid_field_id_text("fld/../../evil") is False
