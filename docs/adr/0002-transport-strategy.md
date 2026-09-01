# ADR 0002: Use an AdminService-first, capability-shaped transport strategy

- **Status:** Accepted
- **Date:** 2026-09-01

## Context

AdminService presents OData over HTTPS, while a possible future direct WMI
backend has different mechanics. A generic `request(method, url, ...)`
contract would make HTTP an architectural requirement; an all-purpose backend
interface would speculate about untested equivalence.

## Decision

The high-level transport boundary is a small set of provider capabilities:
query entities, get one entity, and invoke a named provider method. Typed
request values carry entity/class name, key, query options, parameters,
continuation, and timeout policy without URLs or HTTP verbs. They do not carry a
client-controlled page-size preference; server continuation and page boundaries
remain opaque. Results carry raw records and opaque continuation information.
Capabilities are added only when a resource needs them.

AdminService also has a concrete, internal HTTP execution boundary responsible
for URL construction, OData encoding, authentication application, pooling,
TLS, response decoding, and error translation. The first-class raw
AdminService namespaces use that concrete service directly because `/v1.0/`
and `/wmi/` semantics need not be portable to direct WMI.

The public authentication strategy belongs to this built-in AdminService
implementation, not to every capability transport. A fully configured injected
transport supplies its own authentication/configuration, so `transport=` is
normally mutually exclusive with AdminService inputs such as `auth=`. A future
direct WMI backend requires a separate authentication design.

`httpx` is the leading implementation candidate for its synchronous client,
pooling, timeout model, and authentication extension points, but dependency and
authentication-adapter selection are deferred to implementation validation. No
runtime dependency is added by this ADR.

## Consequences

- High-level resources can later target a proven WMI implementation without API
  changes where capabilities genuinely match.
- AdminService fidelity is not weakened by a lowest-common-denominator API.
- Direct WMI is not promised for v0.1 and requires its own design evidence.
- Every transport owns cleanup and translates implementation exceptions into
  SDK exceptions.
