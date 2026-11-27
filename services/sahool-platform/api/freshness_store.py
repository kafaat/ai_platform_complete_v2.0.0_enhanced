"""Batch the three freshness signals on the caller's tenant-scoped connection."""

from collections import defaultdict

from api.soil_telemetry import pick_latest_soil_moisture

PAGE_SIZE = 100


async def read_freshness_page(
    conn, tenant_id: str, after: str | None
) -> list[tuple[str, float | None, float | None, float | None]]:
    """Read ordered (field_id, NDVI, soil, weather) rows. Timestamps are epoch seconds."""
    # A distinct continuation statement keeps the cursor in the index condition even when
    # PostgreSQL switches a frequently reused prepared statement to a generic plan.
    params = [tenant_id, PAGE_SIZE]
    cursor_filter = ""
    if after is not None:
        cursor_filter = "AND field_id > $3"
        params.append(after)

    fields = await conn.fetch(
        f"""
        WITH page AS (
            SELECT field_id FROM fields
            WHERE tenant_id = $1::uuid {cursor_filter}
            ORDER BY field_id
            LIMIT $2
        )
        SELECT p.field_id,
               extract(epoch FROM i.last_ndvi_date::timestamptz)::float8 AS ndvi_at,
               extract(epoch FROM w.fetched_at)::float8 AS weather_at
        FROM page p
        LEFT JOIN imagery_automation_fields i ON i.field_id = p.field_id AND i.tenant_id = $1
        LEFT JOIN LATERAL (
            SELECT c.fetched_at
            FROM weather_automation_locations l JOIN weather_automation_cache c USING (location_key)
            WHERE l.field_id = p.field_id
            ORDER BY c.fetched_at DESC
            LIMIT 1
        ) w ON true
        ORDER BY p.field_id
        """,
        *params,
    )
    if not fields:
        return []

    # Keep the same per-field candidate window and value/unit validation as _latest_soil_moisture.
    soils = await conn.fetch(
        """
        SELECT f.field_id, s.value, s.unit, s.recorded_at
        FROM unnest($1::text[]) AS f(field_id)
        CROSS JOIN LATERAL (
            SELECT o.value_json AS value, o.unit, o.observed_at AS recorded_at
            FROM soil_observations o
            WHERE o.tenant_id = $2::uuid AND o.field_id = f.field_id
              AND o.property = 'soil_moisture' AND o.source_type = 'sensor'
              AND o.quality_status <> 'rejected'
            ORDER BY o.observed_at DESC
            LIMIT 50
        ) s
        """,
        [field["field_id"] for field in fields],
        tenant_id,
    )
    by_field = defaultdict(list)
    for soil in soils:
        by_field[soil["field_id"]].append(soil)

    result = []
    for field in fields:
        field_id = field["field_id"]
        reading = pick_latest_soil_moisture(by_field[field_id])
        soil_at = reading.recorded_at.timestamp() if reading else None
        result.append((field_id, field["ndvi_at"], soil_at, field["weather_at"]))
    return result
