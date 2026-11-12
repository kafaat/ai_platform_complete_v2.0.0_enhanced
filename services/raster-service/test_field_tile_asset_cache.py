from pathlib import Path

import main
import pytest
import tile_render
from fastapi.testclient import TestClient
from routers import fields


@pytest.fixture
def tiles(monkeypatch, tmp_path):
    state = {}
    cache = {}
    path = tmp_path / "field.tif"
    path.write_bytes(b"asset one")
    state["layer"] = {
        "cog_url": path.as_uri(),
        "acquisition_date": "2025-01-02",
        "created_at": "v1",
    }

    async def authorized(*args):
        pass

    async def resolve(*args):
        return state["layer"]

    monkeypatch.setattr(fields, "_require_field_tenant", authorized)
    monkeypatch.setattr(fields, "_resolve_field_layer", resolve)
    monkeypatch.setattr(fields, "_read_tile_cache", cache.get)
    monkeypatch.setattr(fields, "_write_tile_cache", cache.__setitem__)
    monkeypatch.setattr(
        tile_render, "render_tile_png", lambda source, *_: Path(source).read_bytes()
    )
    client = TestClient(main.app)

    def get(**params):
        return client.get("/v1/fields/F-cache/tiles/0/0/0.png", params=params)

    return state, path, get


def test_latest_moves_to_next_acquisition(tiles):
    state, path, get = tiles
    assert get().content == b"asset one"
    assert get().headers["X-Sahool-Tile-Cache"] == "hit"
    new = path.with_name("next.tif")
    new.write_bytes(b"asset two")
    state["layer"].update(cog_url=new.as_uri(), acquisition_date="2025-02-02")
    response = get()
    assert response.content == b"asset two"
    assert response.headers["X-Sahool-Tile-Date"] == "2025-02-02"
    assert "no-cache" in response.headers["Cache-Control"]


@pytest.mark.parametrize("change", ["metadata", "local_replacement"])
def test_same_date_and_client_version_revalidated_on_server(tiles, change):
    state, path, get = tiles
    params = {"date": "2025-01-02", "v": "client1"}
    assert get(**params).content == b"asset one"
    if change == "metadata":
        state["layer"]["created_at"] = "v2"
    else:
        new = path.with_name("replacement.tif")
        new.write_bytes(b"asset two")
        new.replace(path)
    response = get(**params)
    assert response.headers["X-Sahool-Tile-Cache"] == "miss"
    assert response.headers["X-Sahool-Tile-Version"] == "client1"
    assert response.content == path.read_bytes()
    assert get(**params).headers["X-Sahool-Tile-Cache"] == "hit"


def test_source_removed_after_hit_returns_transparent(tiles):
    state, _, get = tiles
    assert get().content == b"asset one"
    state["layer"] = None
    result = get()
    assert result.content == fields._TRANSPARENT_PNG
    assert result.headers["X-Sahool-Tile-Cache"] == "transparent"
    assert "no-store" in result.headers["Cache-Control"]


def test_mutable_remote_source_without_revision_reopens_each_time(tiles, monkeypatch):
    state, _, get = tiles
    state["layer"] = {"cog_url": "s3://fields/pivot.tif", "acquisition_date": "2025-01-02"}
    content = iter([b"before upload", b"after upload"])
    monkeypatch.setattr(tile_render, "render_tile_png", lambda *_: next(content))
    params = {"date": "2025-01-02", "v": "same-client-token"}
    assert get(**params).content == b"before upload"
    response = get(**params)
    assert response.content == b"after upload"
    assert "no-cache" in response.headers["Cache-Control"]
