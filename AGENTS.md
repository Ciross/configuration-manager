# Engineering guidance for agents

These rules apply to the entire repository. Read the existing code and
documentation before making changes, and prefer the smallest coherent change.

## Architecture

1. Do not introduce architectural patterns without first considering and
   preserving the existing architecture.
2. Public APIs must be fully typed. Production code must remain compatible with
   strict static type checking and the package's PEP 561 commitment.
3. High-level APIs must not expose raw dictionaries as their normal result type.
4. Keep transport concerns separate from domain and resource concerns.
5. Keep domain models separate from transport implementations.
6. High-level resources must eventually provide Pythonic abstractions over
   Configuration Manager concepts and hide irrelevant implementation details.
7. Preserve a low-level escape hatch to AdminService and SMS Provider
   functionality for knowledgeable users.
8. Never access the Configuration Manager SQL database directly as part of the
   SDK architecture. Use supported service/provider interfaces.
9. Do not implement undocumented assumptions as facts. Back behavior with tests
   and authoritative Microsoft documentation.
10. Keep runtime dependencies minimal; every addition must be necessary and
    justified.
11. Avoid unnecessary abstractions and premature generalization.
12. The initial public API is synchronous. An async API requires a separate
    design and must not distort the synchronous contracts.
13. Treat `docs/architecture.md` and accepted ADRs in `docs/adr/` as the
    foundational contract. Change an accepted decision deliberately, with a
    superseding ADR when appropriate.
14. AdminService is the first transport. Keep its versioned and WMI surfaces as
    distinct, first-class low-level namespaces.
15. Client construction performs no remote I/O. TLS verification is enabled by
    default, and credential material is never persisted or logged.
16. Domain models are immutable where practical and never perform network I/O.
    Resource managers own remote operations and return explicit typed pages.
17. The normal AdminService configuration is HTTPS-only. Do not expose a public
    protocol selector or an insecure HTTP test mode.
18. `raw.wmi` means the AdminService WMI route over HTTPS/OData, not direct
    WMI/DCOM. Direct WMI requires a separate ADR.
19. Do not promise client-controlled page size. `$top` is an OData result limit;
    server page boundaries and continuation remain server-driven and opaque.
20. AdminService authentication belongs to its implementation, not the generic
    transport contract. Injected transports arrive fully configured.

## Testing and quality

1. New functionality must include tests at the appropriate level.
2. Unit tests must never use the network or depend on a live Configuration
   Manager environment.
3. Integration tests must use controlled or mocked services.
4. Live tests must always be explicitly opt-in and must not run in the default
   test suite or CI invocation.
5. Run Ruff linting and formatting checks, Pyright, and pytest before submitting
   changes. Use the commands documented in `README.md`.

## Implementation scope

Implement new Configuration Manager functionality only after checking its
scope and sequencing against `docs/architecture.md`. Do not bypass supported
provider interfaces or turn documented future extensions into current facts.
