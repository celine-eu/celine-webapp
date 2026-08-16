# ADR-0001 — The test suite runs against no live service

**Date:** 2026-08-15
**Status:** accepted

## Context

The suite required a live PostgreSQL and a live Keycloak, and had been red long enough
that the failures read as ambient noise: three tests failing `401 != 200` and four
erroring during fixture setup, against thirty-eight passing.

Neither failure was environmental in the way it appeared.

- The 401s came from the test fixture minting an `{"alg": "none"}` JWT with no key id.
  `JwtUser.from_token` resolves the signing key from Keycloak's JWKS by `kid` and rejects
  anything it cannot verify, so that token could never be accepted — on any machine, with
  or without a reachable Keycloak. The auth layer was working; the fixture was forging.
- The four errors came from `src/celine/webapp/db/session.py` building its async engine as a module global
  at import time. Its pooled asyncpg connections outlived the per-test event loop, so a
  connection opened on one loop was handed to another. Those tests errored in *setup* and
  never ran a body — which is how an assertion on `has_smart_meter`, a field deleted from
  `MeResponse` in `05d9dd3`, survived unnoticed.

The second point is the one that forced a decision rather than a repair. An error is not a
failure: the run reported a plausible-looking pass count while four tests produced no
verdict at all. Any fix that kept a real database kept that failure mode available.

Meanwhile the suite covered almost nothing of what this service is. It is a
backend-for-frontend whose own logic is the *composition* of four upstream APIs, and no
test exercised a fan-out. `test_overview_endpoint` asserted that four keys existed and
that the trend had seven entries — all true of the all-nulls response the endpoint returns
when every upstream call fails.

Two sibling repositories, `celine-policies` and `celine-ai-assistant`, had already gone
hermetic and could be followed rather than invented.

## Decision

No test reaches a live service. Specifically:

**Verify identity for real; fake only the JWKS fetch.** Tests sign genuine RS256 tokens
with a throwaway key, and `_get_jwks_client` is replaced to return the matching public
key. Signature, `exp`, `nbf` and `iss` verification all stay in force.

Do **not** override `get_user_from_request`. It is the easier route and it is worthless: a
suite that stubs the validator proves the stub was called, and can never catch a token
this service should have rejected. The forged-token cases in `tests/test_auth_boundary.py`
only mean anything because the real verifier is running.

**Use SQLite over `aiosqlite`, one file per test, with `NullPool`.** Every connection is
opened and closed on the loop that uses it. A shared in-memory database was rejected:
`TestClient` runs the app in its own thread and loop, so the `StaticPool` connection it
would require reintroduces the cross-loop defect in a new form.

**Redirect `init_db` at the test engine rather than disabling it**, so schema creation
happens inside the app's lifespan — on the same loop that later serves every request.

**Fake the four upstreams at the dependency-injection boundary** in `src/celine/webapp/api/deps.py`, and
cover the composition logic that fan-out represents.

**Run the suite in CI**, with no service containers declared. A job that needed one would
be the signal that this decision had been lost.

## Consequences

The suite runs on a clean checkout and in CI, and grew from 45 tests to 110 plus 5 pinned
`xfail`s. Two previously invisible defects surfaced while writing them, both user-facing:
a mistyped email address in settings returns 500 rather than 422, and a member with
delivery points has their meter queried by the first *character* of the meter id.

**What this costs, and it is not small: every upstream is now a fake this repository
wrote.** `tests/fakes.py` reproduces the shape `celine-sdk` returned on 2026-08-15 and
verifies nothing about the real contract. A green suite says the composition is correct
against that recorded shape. An SDK version bump can change this service's behaviour with
no file here changing and the suite still green — which is why the playbook requires an
SDK bump to be reported as a change to this service.

Nothing here replaces integration testing against the real four. It makes the absence of
that testing explicit rather than disguised by a suite that needed a database and still
tested none of it.

**What will tempt someone to undo it:** the fakes drifting from the SDK. The pull will be
to point the tests at a real service to "test it properly". That trades a known, stated
gap for an unknown one, and brings back a suite nobody can run — which is how this
started. The fix for drift is contract testing against the SDK, not a live dependency in
the unit suite.
