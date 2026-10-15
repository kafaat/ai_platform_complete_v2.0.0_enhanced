from . import field, investigation, reasoning, scene, spatial, water

FAMILIES: dict = {
    **spatial.FAMILIES,
    **field.FAMILIES,
    **scene.FAMILIES,
    **reasoning.FAMILIES,
    **investigation.FAMILIES,
    **water.FAMILIES,
}


def select(names: str | None) -> dict:
    """'all' / None -> every family; otherwise comma list of names or prefixes (e.g. 'soil.,spatial.bbox')."""
    if not names or names == "all":
        return dict(FAMILIES)
    wanted = [n.strip() for n in names.split(",") if n.strip()]
    out = {
        k: v
        for k, v in FAMILIES.items()
        if any(k == w or (w.endswith(".") and k.startswith(w)) for w in wanted)
    }
    unknown = [
        w
        for w in wanted
        if not any(k == w or (w.endswith(".") and k.startswith(w)) for k in FAMILIES)
    ]
    if unknown:
        raise SystemExit(f"unknown families: {unknown}. Known: {sorted(FAMILIES)}")
    return out
