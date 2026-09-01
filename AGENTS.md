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
12. Do not add asynchronous APIs until they have been explicitly designed.

The architecture for authentication, transports, models, resources,
exceptions, pagination, OData queries, and the low-level API will be specified
separately before any of those areas are implemented. Do not pre-empt those
decisions.

## Testing and quality

1. New functionality must include tests at the appropriate level.
2. Unit tests must never use the network or depend on a live Configuration
   Manager environment.
3. Integration tests must use controlled or mocked services.
4. Live tests must always be explicitly opt-in and must not run in the default
   test suite or CI invocation.
5. Run Ruff linting and formatting checks, Pyright, and pytest before submitting
   changes. Use the commands documented in `README.md`.

## Bootstrap scope

Do not implement Configuration Manager functionality during this bootstrap
task. In particular, do not add clients, authentication, HTTP or WMI
communication, resources, domain models, query builders, OData abstractions, or
ConfigMgr-specific exceptions. Those features require separate design work.
