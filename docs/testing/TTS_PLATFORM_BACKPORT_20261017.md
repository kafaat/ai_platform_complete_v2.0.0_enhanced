# Platform policy contract v2 backport candidate

Gap: `TTS-PLATFORM-POLICY-CONTRACT-SKEW-IN-PRODUCTION-01`, still **open**.

This candidate is based on the observed staging platform source
`df16cc05c4b666397956bd8c721949045e59b680`. Source patch `11b2e732` copies only
`core/ai_policy_envelope.py` and `api/routers/me.py` from merged main
`0e5281614f008de1ff73783dfa567a04f1e3b33c`. It adds the versioned speech permission
to the existing `/api/v1/me` response and observable fail-closed policy reads.
Existing `allowed_providers` data supplies the explicit speech grant; no migration
or stored policy changes are made. No new route or external speech grant is added.

The current TTS reader requires this contract. The deployed staging TTS reader
is older and must be replaced with a separately reviewed compatible consumer;
deploying this platform candidate alone does not close the gap.

## Validation

The existing current-main cross-service contract test was run unchanged except
for its producer root, which points at this backport. Its consumer remains the
current-main TTS implementation. Before copying the two production files, the
same 43 cases yielded 24 failures and 19 passes. After copying them, all 43 passed.
Provider selection in that suite uses test doubles; it is not live speech or
runtime egress evidence. Two marker warnings came from running the frozen test
outside the repository test configuration.

The checked-in `services/sahool-platform/tests/test_me_ai_policy_envelope.py`
exercises the real route with a test database connection and authenticated-user
dependency override. Its v2 cases distinguish explicit speech permission from an
LLM grant and verify denied contracts when the policy is absent or unreadable.
The exact checked-in route suite yielded 11 failures and 4 passes on the deployed
base, then 15 passes after the source patch (no skipped cases). The base replay
restored only the two production files and restored the candidate in a finally
block; the test bytes were unchanged. Ruff check and format passed for the three
changed Python files. Generation and preflight are recorded separately at execution.

## Operational acceptance outstanding

As observed on 2026-10-17, both platforms retain their existing `deploy/*` refs;
staging TTS retains its earlier Claude branch. Production TTS has no
`PLATFORM_API_URL` name in service or shared environment variable inventories.
No variable values were retrieved. Resolve the platform's actual private origin
and port before configuring it; a guessed hostname is not an acceptance proof.

Build and test a compatible pair with exact source/image identities in staging.
With an authorized synthetic tenant, verify `/api/v1/me` v2, tenant matching,
`local_only`, and policy-denied synthesis/streaming with no forbidden egress.
Missing local voice support must remain explicit unavailability. Do not restore
legacy LLM-to-speech grants as rollback. Production promotion follows staging
acceptance and its own reviewed baseline.

No Railway deployment, migration, publisher activation, SoR cutover or GATE-01
change is performed by this candidate. The earlier read-only database probe was
not deployed because the deployment tool declined approval; this branch is not
an alternative route to that refused operation.

## Legacy branch validation prerequisites

The first full unit run reported 19 failures (7515 passed, 31 skipped). The same
19 failures reproduced on untouched deployed base df16cc05 in the four affected
test files (83 other cases passed). Nine came from expired fixed-date test
evidence, nine from the old RAG exception date, and one from the local SOCKS
transport lacking socksio. The candidate imports the existing current-main test
fixture repair and only the three owner-approved expiry/reason updates from
merged PR #1118 (892037437989c20c56b1a8b2520152d6ff096f0f). The approved horizon
remains 2026-10-31. It does not change a guard, extend that horizon, modify RAG
runtime code or enable a feature. socksio is installed locally for the executor's
proxy environment; repository runtime requirements are unchanged.

Seven additional existing UI waivers expired on 2026-10-11; only their expiry
and reason fields are synchronized from the already merged owner decision #1164
(29c09d0bb5959a24220ac3f420ef7c5ea2f3735a), preserving its 2026-10-31 horizon.
No waiver for a new route is imported.

The two accompanying #1118 test/registry adjustments are also copied exactly:
the expiry test derives the day after the configured deadline and checks the
deadline itself, and the existing waiver mutation uses the unique October 28
anchor. Mutation count and guard implementation are unchanged.


## Security prerequisite after PR #1203 CI

The first published head834c56cfa6291c273426a76f74b6972297a9cec4 failed Security Scan on python-jose3.5.0 (PYSEC-2026-4298). This follow-up ports the approved JWT portion of merged #1198 /239c01a47442df13d9cbb492017afae103b98dc8: PyJWT[crypto]==2.15.0, shared access-token verification, consumers, and compatibility witnesses. It does not copy the gateway/irrigation changes from that PR. The earlier two-production-file scope is therefore superseded by an explicit authentication prerequisite; shared/security/access_tokens.py and its callers now change. Observe mode remains the default; enforce, frozen paths, migrations and tenant policies do not change.

Before the port, the12 dependency/import/waiver witnesses failed. After it, all124 cases in test_python_jose_removed.py, test_jwt_decode_shared_decoder.py and the architecture JWT ratchet passed. The actual CI19-file audit is rerun without advisory exceptions; old ecdsa waiver is removed with the dependency. Generation, final preflight and CI must be measured again on the resulting tree. This remains a candidate without runtime deployment or live TTS acceptance.

The security CI mutation anchor is also copied exactly from #1198 after removal of the old audit waiver. All four existing ci.yml mutations were planted and killed by their named tests; no mutation or ceiling is removed or changed.
