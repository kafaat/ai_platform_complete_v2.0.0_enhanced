"""Georeference zoned cells using their own raster grid, then constrain them to the field."""

from __future__ import annotations

import json
import math

from .field_boundary_ai import normalize_bbox
from .productivity_zones_clustering import _grid_identity, _grid_source


class GridGeometryError(ValueError):
    """A geographic grid cannot be used at the requested location."""


class ZoningGridGeometry:
    def __init__(self, grid, params, evidence, requested_bbox, boundary):
        from shapely.errors import GEOSException
        from shapely.geometry import Polygon, box, shape

        self.rows, self.cols = len(grid), len(grid[0])
        if not self.cols or any(len(row) != self.cols for row in grid):
            raise GridGeometryError("invalid_ndvi_grid_shape")
        if boundary is None and "bbox" in params and requested_bbox is None:
            raise GridGeometryError("invalid_requested_field_extent")
        source = _grid_source(params, evidence)
        self.owner = "field_evidence" if source is evidence else "caller"
        supplied = source.get("grid_metadata")
        meta = supplied.get("ndvi") if isinstance(supplied, dict) else None
        self.declared = meta is None and supplied is None
        self.crs = "EPSG:4326"
        self.projected = False
        if self.declared:
            if requested_bbox is None:
                raise GridGeometryError("missing_or_invalid_boundary")
            if evidence and source is evidence:
                self.source = "caller_extent_for_legacy_evidence"
            else:
                self.source = "caller_declared_extent"
            west, south, east, north = requested_bbox
            affine = ((east - west) / self.cols, 0, west, 0, (south - north) / self.rows, north)
        else:
            ident = _grid_identity(meta, self.rows, self.cols) if isinstance(meta, dict) else None
            if not ident:
                raise GridGeometryError("invalid_ndvi_grid_identity")
            self.crs, affine, _revision = ident
            self.source = "grid_metadata.ndvi.grid_identity"
            try:
                from rasterio.crs import CRS
                from rasterio.warp import transform, transform_bounds

                crs = CRS.from_user_input(self.crs)
                self.projected = crs != CRS.from_epsg(4326)
            except ImportError as exc:
                raise GridGeometryError("grid_reprojection_unavailable") from exc
            except ValueError as exc:
                raise GridGeometryError("unsupported_ndvi_grid_crs") from exc

        a, b, c, d, e, f = affine
        native_corners = [
            (a * x + b * y + c, d * x + e * y + f) for y in (0, self.rows) for x in (0, self.cols)
        ]
        xs, ys = zip(*native_corners, strict=True)
        native_bounds = min(xs), min(ys), max(xs), max(ys)
        X, Y = zip(
            *[
                (a * x + b * y + c, d * x + e * y + f)
                for y in range(self.rows + 1)
                for x in range(self.cols + 1)
            ],
            strict=True,
        )
        try:
            if self.projected:
                X, Y = transform(crs, "EPSG:4326", X, Y)
                bounds = transform_bounds(crs, "EPSG:4326", *native_bounds)
            else:
                bounds = native_bounds
        except Exception as exc:
            raise GridGeometryError("ndvi_grid_reprojection_failed") from exc
        self.bbox = normalize_bbox(bounds)
        if self.bbox is None or not all(math.isfinite(v) for v in (*X, *Y)):
            raise GridGeometryError("invalid_ndvi_grid_extent")
        if not self.declared and "bbox" in meta:
            documented = normalize_bbox(meta["bbox"])
            # Raster facade expresses WGS84 bounds rounded to six decimals.
            if (
                not documented
                or max(abs(u - v) for u, v in zip(documented, self.bbox, strict=True)) > 1.1e-6
            ):
                raise GridGeometryError("ndvi_bbox_affine_mismatch")
            self.source = "grid_metadata.ndvi.bbox_and_grid_identity"
            self.bbox = documented
        self.vertices = list(zip(X, Y, strict=True))
        self.clip = None
        if boundary is not None:
            try:
                field = shape(boundary)
            except (TypeError, ValueError, KeyError, GEOSException) as exc:
                raise GridGeometryError("invalid_field_polygon") from exc
            if (
                field.geom_type not in ("Polygon", "MultiPolygon")
                or field.is_empty
                or not field.is_valid
            ):
                raise GridGeometryError("invalid_field_polygon")
        elif requested_bbox is not None:
            field = box(*requested_bbox)
        else:
            field = None
        outline = self.ring(
            [(0, self.rows), (self.cols, self.rows), (self.cols, 0), (0, 0), (0, self.rows)]
        )
        footprint = Polygon(outline)
        if not footprint.is_valid or footprint.is_empty:
            raise GridGeometryError("invalid_ndvi_grid_extent")
        self.field_coverage = None
        if field is not None:
            covered = footprint.intersection(field).area
            if not covered:
                raise GridGeometryError("ndvi_grid_outside_field")
            self.field_coverage = min(1.0, covered / field.area)
            if not field.covers(footprint):
                self.clip = field

    def ring(self, ring):
        """The clustering kernel uses a north-up pixel box; its y increases northward."""
        out = []
        for (x0, y0), (x1, y1) in zip(ring, ring[1:], strict=False):
            dx, dy = x1 - x0, y1 - y0
            steps = int(max(abs(dx), abs(dy))) if self.projected else 1
            for i in range(steps):
                c = round(x0 + dx * i / steps)
                r = self.rows - round(y0 + dy * i / steps)
                out.append(self.vertices[r * (self.cols + 1) + c])
        return out + [out[0]]

    def masked_grid(self, grid):
        if self.clip is None:
            return grid
        from shapely.geometry import Polygon

        # Count intersecting edge cells only when they share positive area with
        # the field. Clip the zone footprints to that same polygon on output.
        result = []
        stride = self.cols + 1
        for r, row in enumerate(grid):
            kept = []
            for c, value in enumerate(row):
                i = r * stride + c
                corners = [self.vertices[k] for k in (i, i + 1, i + 1 + stride, i + stride)]
                cell = Polygon(corners)
                kept.append(
                    value
                    if value is not None and self.clip.relate_pattern(cell, "T********")
                    else None
                )
            result.append(kept)
        return result

    def zone(self, polygon):
        from shapely import to_geojson
        from shapely.geometry import Polygon
        from shapely.ops import unary_union

        shell, *holes = [self.ring(ring) for ring in polygon["coordinates"]]
        geom = Polygon(shell, holes)
        if self.clip is not None:
            geom = geom.intersection(self.clip)
        if geom.geom_type == "GeometryCollection":
            geom = unary_union(
                [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
            )
        if geom.is_empty or not geom.area:
            return None
        # Same local equirectangular approximation as the field area helper.
        lat = (self.bbox[1] + self.bbox[3]) / 2
        ha = geom.area * 111320 * 110574 * max(math.cos(math.radians(lat)), 0.01) / 10_000
        return json.loads(to_geojson(geom)), round(ha, 3)
