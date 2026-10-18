"""Request-bound native QA for CDSE Process API indicator products.

The four-band response carries the unmasked index, SCL, dataMask and a
one-based contributor ordinal. We apply the mask locally; asking CDSE to mask
is never accepted as proof that it did. Metadata is received in the same TAR,
not inferred from a catalogue candidate or a requested date.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime

SCHEMA = "sahool.cdse_native_product/1"
MASK_VERSION = "cdse-native-scl-datamask/2"
MAX_RESPONSE_BYTES = 128 * 1024 * 1024
MAX_METADATA_BYTES = 65536


class CdseNoContributingScene(ValueError):
    """CDSE reported that no tile fed the output.

    ``updateOutputMetadata`` lists the tiles the provider mosaicked. An empty list
    is the provider's own statement that no acquisition passed the request's
    ``dataFilter`` (time window and ``maxCloudCoverage``), so the output carries no
    observation. It is a ``ValueError`` like every other rejection here, so callers
    still fail closed; only the reason differs from a malformed response.
    """


@dataclass(frozen=True)
class NativeProduct:
    tiff: bytes
    tiff_sha256: str
    evalscript_sha256: str
    tiles: tuple[tuple[str, str], ...]
    request_sha256: str | None = None
    expected_width: int | None = None
    expected_height: int | None = None


def request_digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def build_evalscript(index: str, expressions: dict) -> str:
    if index not in expressions:
        raise ValueError("unsupported_cdse_native_indicator")
    bands, expression = expressions[index]
    inputs = json.dumps([*bands, "SCL", "dataMask"])
    return (
        "//VERSION=3\n"
        "function setup() { return { "
        f"input: [{{bands: {inputs}}}], "
        'output: {bands: 4, sampleType: "FLOAT32"}, mosaicking: "TILE" }; }\n'
        "function evaluatePixel(samples) {\n"
        "  for (let i = 0; i < samples.length; i++) {\n"
        "    const s = samples[i];\n"
        f"    if (s.dataMask === 1) {{ const v = {expression}; "
        "return [v, s.SCL, s.dataMask, i + 1]; }\n"
        "  }\n"
        "  return [NaN, 0, 0, 0];\n"
        "}\n"
        "function updateOutputMetadata(scenes, inputMetadata, outputMetadata) {\n"
        f"  outputMetadata.userData = {{schema: {json.dumps(SCHEMA)}, "
        "tiles: scenes.tiles.map(t => ({id: String(t.shId), date: t.date}))};\n"
        "}\n"
    )


def decode_response(
    content: bytes, evalscript: str, *, request_payload: dict | None = None
) -> NativeProduct:
    """Read two bounded regular TAR members as bytes; never extract archive paths."""
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("cdse_native_response_too_large")
    parts: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:") as archive:
        for member in archive:
            if (
                member.name not in {"default.tif", "userdata.json"}
                or member.name in parts
                or not member.isfile()
            ):
                raise ValueError("cdse_native_response_members_invalid")
            limit = MAX_METADATA_BYTES if member.name == "userdata.json" else MAX_RESPONSE_BYTES
            if not 0 < member.size <= limit:
                raise ValueError("cdse_native_response_member_size_invalid")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("cdse_native_response_member_missing")
            parts[member.name] = stream.read(limit + 1)
    if set(parts) != {"default.tif", "userdata.json"}:
        raise ValueError("cdse_native_response_incomplete")
    metadata = json.loads(parts["userdata.json"])
    if not isinstance(metadata, dict) or metadata.get("schema") != SCHEMA:
        raise ValueError("cdse_native_metadata_schema_invalid")
    tiles = metadata.get("tiles")
    if isinstance(tiles, list) and not tiles:
        raise CdseNoContributingScene("cdse_native_no_contributing_scene")
    if not isinstance(tiles, list) or not 1 <= len(tiles) <= 256:
        raise ValueError("cdse_native_tiles_invalid")
    normalized = []
    for tile in tiles:
        if not isinstance(tile, dict):
            raise ValueError("cdse_native_tile_invalid")
        scene = tile.get("id")
        if (
            not isinstance(scene, str)
            or not scene.isascii()
            or not scene.isdigit()
            or len(scene) > 32
        ):
            raise ValueError("cdse_native_scene_identity_missing")
        try:
            date = datetime.fromisoformat(str(tile.get("date", "")).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("cdse_native_acquisition_invalid") from None
        if date.tzinfo is None:
            raise ValueError("cdse_native_acquisition_timezone_missing")
        normalized.append((f"cdse:sh:{scene}", date.astimezone(UTC).isoformat()))
    return NativeProduct(
        tiff=parts["default.tif"],
        tiff_sha256=hashlib.sha256(parts["default.tif"]).hexdigest(),
        evalscript_sha256=hashlib.sha256(evalscript.encode()).hexdigest(),
        tiles=tuple(normalized),
        request_sha256=request_digest(request_payload) if request_payload else None,
        expected_width=request_payload["output"]["width"] if request_payload else None,
        expected_height=request_payload["output"]["height"] if request_payload else None,
    )


def measured_pixels(src, product: NativeProduct, source_path: str):
    """Apply returned native QA and bind a single actual contributor to pixels."""
    import numpy as np
    from imagery_product_identity import canonical_processing_version

    with open(source_path, "rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != product.tiff_sha256:
            raise ValueError("cdse_native_product_checksum_mismatch")
    if src.crs is None:
        raise ValueError("cdse_native_crs_missing")
    if src.count != 4:
        raise ValueError("cdse_native_product_band_count_invalid")
    if not 0 < src.width <= 2500 or not 0 < src.height <= 2500:
        raise ValueError("cdse_native_dimensions_out_of_bounds")
    if product.expected_width is not None and (src.width, src.height) != (
        product.expected_width,
        product.expected_height,
    ):
        raise ValueError("cdse_native_dimensions_do_not_match_request")
    value, scl, data_mask, contributor = src.read().astype("float32")
    value = np.where(src.read_masks(1) > 0, value, np.nan)
    present = data_mask == 1
    if not np.isin(data_mask, [0, 1]).all():
        raise ValueError("cdse_native_data_mask_invalid")
    if not np.isin(scl[present], range(12)).all():
        raise ValueError("cdse_native_scl_invalid")
    if not np.isin(contributor[present], range(1, len(product.tiles) + 1)).all():
        raise ValueError("cdse_native_contributor_invalid")
    # Native SCL 0 (no data) and 1 (saturated/defective) are never usable.
    cloud = present & np.isin(scl, [3, 8, 9, 10, 11])
    keep = present & np.isin(scl, [2, 4, 5, 6, 7]) & np.isfinite(value)
    contributors = np.unique(contributor[keep]).astype("int64")
    if len(contributors) != 1:
        raise ValueError("cdse_native_single_contributor_required")
    scene_id, acquired = product.tiles[int(contributors[0]) - 1]
    cloud_pct = float(cloud.sum()) * 100.0 / int(present.sum())
    return np.where(keep, value, np.nan), {
        "scene_id": scene_id,
        "acquisition_datetime": acquired,
        "algorithm_version": f"cdse-evalscript-sha256:{product.evalscript_sha256}",
        "qa_mask_version": MASK_VERSION,
        "input_checksum": product.tiff_sha256,
        "request_sha256": product.request_sha256,
        "local_processing_version": canonical_processing_version(),
        "native_invalid_scl_pixels": int((present & np.isin(scl, [0, 1])).sum()),
        "cloud_pct": cloud_pct,
        "native_present_pixels": int(present.sum()),
        "native_cloud_pixels": int(cloud.sum()),
        "native_valid_pixels": int(keep.sum()),
    }
