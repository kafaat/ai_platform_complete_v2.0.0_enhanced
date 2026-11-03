# SAHOOL — Four-surface UI source observation (review only)

This optional workflow uses the real Impeccable 4.8.0 deterministic source scanner, **not a LLM redesign**, on four current SAHOOL components: MapHubShell, FieldWorkspaceRouteShell, FieldWorkspaceIrrigationPanel and SatellitePage. It records the Git SHA, per-file source SHA256, detector-output SHA256 and number of primary findings without copying user data or modifying the UI.

The CI job mounts **one TSX file at a time** inside a Docker container as read-only, runs with no network, a non-root user, dropped capabilities, no-new-privileges, a read-only root FS and strict resource limits. No application API, PostgreSQL, Railway or browser is started. npm install scripts are disabled and package version is pinned; this is not a full software supply chain audit.

The source gate rejects detector failures (exit 1), invalid/duplicate/nonfinite JSON, symlinks and inconsistent exit-status/findings counts. Existing visual/style findings are **reported, not converted to a new release blocker**; advisory findings are excluded with `--no-advisory`. No existing CI, frontend code, API route, VRI/irrigation, imagery or TrueColor behavior is changed.

Validation steps: run `python -m unittest discover -s experiments/ui-quality-observation -p 'test_*.py' -v` then the pinned CI job. This output is `OBSERVED_FOR_REVIEW` only. Next functional acceptance must separately test MapHub map rendering, field-season binding, Irrigation states and Satellite scene dates using the actual Playwright app and keyboard/mobile viewports. **A static scanner cannot certify WCAG, visual polish or functional E2E.**

Factory D-08, Hospital DB-OBS-001, all current SAHOOL decision gates and production deployment remain unchanged.
