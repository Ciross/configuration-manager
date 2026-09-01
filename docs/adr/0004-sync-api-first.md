# ADR 0004: Ship a synchronous API first

- **Status:** Accepted
- **Date:** 2026-09-01

## Context

Windows enterprise authentication and ConfigMgr administration are naturally
served by a conventional synchronous client. Designing two execution models
before validating one would multiply lifecycle, iterator, authentication, and
test contracts.

## Decision

The initial SDK is synchronous only. `ConfigManager` supports deterministic
`close()` and the synchronous context-manager protocol. Pagination exposes
synchronous page retrieval and an explicitly named synchronous iterator.

Public domain models, exception meanings, query option values, and resource
naming should remain reusable by a future async client, but transports and
iterators are not forced into dual-mode abstractions. A future async API needs a
separate ADR, distinct client/transport types, and native async authentication
and cleanup rather than wrappers around blocking work.

## Consequences

- The initial surface and tests stay small and unsurprising.
- Adding async later may require parallel resource implementations or shared
  pure mapping helpers.
- No implied async compatibility is promised merely because `httpx` offers an
  async client.
