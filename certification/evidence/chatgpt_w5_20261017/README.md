# W5 — remaining gap evidence, one PR

Base: `ec3927cef45a3da53aaa14950093e734ce8e072a`. Scope excludes #1204 and
Claude's Redis, learning, PR-finding guard and architecture remeasurement files.
This pack changes tests/documentation/evaluation tooling only. No migration,
serving model, seed, prefix, deployment, Railway setting or gap status changes.

| Slice | Local evidence | Staging | Production |
| --- | --- | --- | --- |
| TEXT-GUARD | 7 render/event tests pass; 3 deliberately broken implementations fail | Not run | Not run |
| RAG 02/05/06/08/12 | 32 versioned queries; current-stack attempt BLOCKED (Qdrant/Ollama absent); separately labelled snapshot BM25 | Not run | Not run |
| Database gaps | 54 existing migrator/SAM2 regression cases pass; 4 new PG16 cases collect in the existing 034 test module; execution delegated to existing isolated PG16 CI job | Not run | Not run |
| SAM2 | Official weight stream SHA256 matches the pinned publisher pointer; no model deserialization | Not run | Not run |

All affected gaps remain **open**. Existing partial source fixes are not undone,
and no source state is promoted to verified. CI execution results are bound to
the final PR SHA and its uploaded JUnit, not inferred from collection locally.

## TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01

`frontend/src/sections/FieldWorkspaceRouteShell.behavior.test.tsx` renders the
actual shell with real router/tab transitions. The map component boundary is a
sentinel: it proves the shell mounts that imported component with the right
field and picker contract. It does not prove Leaflet rendering or network data.
Other panels and selected-field discovery are isolated from network calls.

`frontend/src/components/AddFieldWithMap.pivot.behavior.test.tsx` renders the
actual field editor and uses actual Leaflet geometry and Evented dispatch. Only
map DOM attachment and leaflet-draw's editing methods are test doubles. It checks
creation, center drag, radius resize and the ordinary-polygon positive control.
The old regex assertion for pivot vertex editing was removed; unrelated static
DrawingTools checks remain. No text-search guard is presented as semantic proof.

```bash
cd frontend
npm exec -- vitest run src/sections/FieldWorkspaceRouteShell.behavior.test.tsx \
  src/components/AddFieldWithMap.pivot.behavior.test.tsx
npm run typecheck
```

`text_guard/mutation_results.json` specifies exact path, original source digest,
replacement and command for each mutation. Apply each replacement independently
to the base source, run the same command, and restore the original bytes before
the next case. Raw stdout/stderr is retained next to the manifest. Baseline = 7
passing tests. Removing both map-card render sites, enabling pivot vertices at
creation, or enabling them after center drag each yields exit 1. Production
source was restored byte-for-byte after every run.

The broader semantic class (an anchor bound to a live symbol while the actual
property resides elsewhere) remains open. These are two measured component
contracts, not a proof about every guard in the repository. Browser pointer
interaction, visual handles, staging and production remain unmeasured.

## Other evidence

- [RAG method and limits](rag/README.md)
- [Database reproduction and proposed migrations](database-analysis.md)
- [SAM2 official artifact and provisioning boundary](sam2/README.md)
- [Source locations and byte digests](source-locations.json)
