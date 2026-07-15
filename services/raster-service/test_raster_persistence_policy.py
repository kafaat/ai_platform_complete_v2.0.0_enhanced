from __future__ import annotations

import pytest
from raster_persistence_policy import PersistenceMode, persistence_mode, terminal_status


def test_required_mode_fails_when_persistence_fails(monkeypatch):
    monkeypatch.setenv("RASTER_PERSISTENCE_MODE", "required")
    assert persistence_mode() is PersistenceMode.REQUIRED
    assert terminal_status(persisted=False) == (
        "failed",
        "raster_asset_persistence_failed",
    )


def test_best_effort_is_honestly_unpublished(monkeypatch):
    monkeypatch.setenv("RASTER_PERSISTENCE_MODE", "best_effort")
    assert terminal_status(persisted=False) == (
        "processed_unpublished",
        "raster_asset_not_persisted",
    )


def test_persisted_is_completed_in_both_modes(monkeypatch):
    for mode in ("required", "best_effort"):
        monkeypatch.setenv("RASTER_PERSISTENCE_MODE", mode)
        assert terminal_status(persisted=True) == ("completed", None)


def test_invalid_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("RASTER_PERSISTENCE_MODE", "optional")
    with pytest.raises(RuntimeError):
        persistence_mode()
