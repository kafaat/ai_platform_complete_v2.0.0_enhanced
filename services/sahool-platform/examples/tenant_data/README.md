# Example Tenant Data (NOT shipped with SAHOOL core)

This directory contains **EXAMPLE** tenant and district data used during
development for testing and demonstration. It is **NOT** part of the
neutral core (`services/sahool-platform/core/`).

## Why it lives here

The core platform supports any tenant in any region of Yemen. The
`aljawf-142ha` data here is a sample from one farm during early
development. Production deployments provision tenant data via
configuration management, NOT by checking specific tenants into Git.

## Path before reorganization

Previously these lived at:
- `services/sahool-platform/districts/` ← MOVED HERE
- `services/sahool-platform/tenants/001-aljawf-142ha/` ← MOVED HERE

This move was a response to documentation review #10, which correctly
identified that having specific regions/farms as fixed paths in Git
broke the principle of geographic neutrality, even though `core/`
itself contained no such references.

## What core supports

The core supports tenant/district data via configuration loaders that
take paths as parameters. It does NOT hardcode any specific region.

For production, tenant data should be:
- Provisioned via deployment config (Helm values, env vars, secrets)
- Stored in tenant database (PostgreSQL `tenants` table)
- NEVER committed to Git
