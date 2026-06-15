"""Tests for the vegetation index registry — the single metadata source for spectral indices."""

from api.index_registry import (
    VegetationIndex,
    get_index,
    known_ids,
    list_indices,
)


class TestIndexRegistry:
    def test_lists_core_indices(self):
        ids = {entry["id"] for entry in list_indices()}
        assert {"ndvi", "savi", "gndvi"} <= ids

    def test_list_is_sorted(self):
        listed = [entry["id"] for entry in list_indices()]
        assert listed == sorted(listed)

    def test_ndvi_bands_match_vegetation_service(self):
        # mirrors vegetation-analysis main.py: (B08 - B04) / (B08 + B04 + eps)
        ndvi = get_index("ndvi")
        assert ndvi is not None
        assert ndvi["bands"] == ("B08", "B04")

    def test_gndvi_bands(self):
        # mirrors vegetation-analysis main.py: (B08 - B03) / (B08 + B03 + eps)
        assert get_index("gndvi")["bands"] == ("B08", "B03")

    def test_savi_uses_nir_red(self):
        assert get_index("savi")["bands"] == ("B08", "B04")

    def test_unknown_index_returns_none(self):
        assert get_index("__nope__") is None

    def test_ids_are_unique(self):
        ids = [entry["id"] for entry in list_indices()]
        assert len(ids) == len(set(ids))

    def test_known_ids_match_listing(self):
        assert known_ids() == [entry["id"] for entry in list_indices()]

    def test_every_entry_has_formula_and_bands(self):
        for entry in list_indices():
            assert entry["formula"].strip(), entry["id"]
            assert entry["bands"], entry["id"]
            assert all(b.strip() for b in entry["bands"]), entry["id"]

    def test_every_entry_has_arabic_metadata(self):
        for entry in list_indices():
            assert entry["name_ar"].strip(), entry["id"]
            assert entry["description_ar"].strip(), entry["id"]
            assert entry["units"].strip(), entry["id"]
            assert entry["colormap"].strip(), entry["id"]

    def test_dataclass_is_frozen(self):
        idx = VegetationIndex(
            id="x",
            name_ar="أ",
            name_en="x",
            formula="B08",
            bands=("B08",),
            colormap="rdylgn",
            units="dimensionless",
            description_ar="وصف",
        )
        try:
            idx.id = "y"  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("VegetationIndex should be frozen")

    def test_to_dict_returns_copy_of_thresholds(self):
        # mutating the returned dict must not corrupt the registry
        ndvi = get_index("ndvi")
        ndvi["thresholds"]["low"] = 999
        assert get_index("ndvi")["thresholds"].get("low") != 999
