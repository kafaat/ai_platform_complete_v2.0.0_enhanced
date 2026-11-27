# Farmland P2 — GIS levelling design (cut/fill)

Module: `services/raster-service/levelling_design.py` (`compute_levelling_design`), tests in
`test_levelling_design.py`. Pure function; not routed, not persisted, no execution authority
(`execution_authorized` is always false; status `design_proposal_not_for_construction`).

Contract: explicit projected metre CRS (EPSG), explicit vertical datum, cell size and grid origin,
caller-supplied elevation grid with `nodata`; polygon exterior and holes in the grid CRS;
>= 95% valid coverage or refusal; flat or plane (|slope| <= 5%) design balanced for a shrink factor;
optional topsoil strip/respread volumes (excluded from cut/fill); RTK points are evidence only
(fixed solutions, datum must match, >= 5 fixed and RMSE <= 0.10 m for `rtk_checked`); cost =
quantities, money only from caller-supplied unit prices.

Reuse: refusal envelope and honesty rules follow `terrain_analysis.py`. It does not call that
module's lon/lat window/mask path because levelling needs a projected CRS.

Gaps: no haul/mass-haul, no TIN refinement, no drainage-grade check, no API route or DEM-reading
adapter yet, no real survey data fixtures (tests use synthetic grids).
