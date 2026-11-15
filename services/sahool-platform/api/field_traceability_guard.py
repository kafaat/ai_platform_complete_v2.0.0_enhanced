"""A field with harvest lots is not deleted, merged away or split away.

v278 made ``harvest_lots.field_id`` ON DELETE RESTRICT: before it, deleting a field (directly,
or as the source of a merge or split) cascaded to its harvest lots and from them to their custody
chain, erasing the traceability record of everything harvested there. With RESTRICT the DELETE
fails inside the transaction; this check answers 409 with the reason first, instead of letting the
foreign-key error surface as the generic 503 of the field routes.

Lots keep naming the field they were harvested from: re-pointing them to a merged or split field
would change where the produce came from, so the operator resolves it explicitly.
"""

from __future__ import annotations

from fastapi import HTTPException


async def refuse_if_fields_have_harvest_lots(conn, field_ids: list[str], action_ar: str) -> None:
    ids = [str(f) for f in field_ids if f]
    if not ids:
        return
    held = await conn.fetchval(
        "SELECT count(*) FROM harvest_lots WHERE field_id = ANY($1::text[])",
        ids,
    )
    if held and int(held) > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"لا يمكن {action_ar}: للحقل دفعات حصاد مسجَّلة ({int(held)}) وسلسلة حيازتها "
                "سجلّ تتبّع لا يُمحى. يبقى الحقل ما دامت دفعاته قائمة."
            ),
        )
