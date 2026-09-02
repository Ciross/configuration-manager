# Foundational SDK architecture

This document is the implementation contract for the first public versions of
`configuration-manager`. It describes intended interfaces; none of the examples
below are implemented. The accepted decisions are split into [layering](adr/0001-sdk-layering.md),
[transport strategy](adr/0002-transport-strategy.md), [domain models](adr/0003-domain-model-strategy.md),
and [synchronous-first API](adr/0004-sync-api-first.md). The implemented HTTP,
TLS, and Windows authentication choices are recorded in
[ADR 0005](adr/0005-adminservice-http-authentication.md).

## Evidence and limits

The design was reviewed against these authoritative sources on 2026-09-01:

- Microsoft describes the [administration service overview](https://learn.microsoft.com/en-us/intune/configmgr/develop/adminservice/overview)
  as an HTTPS REST API based on OData v4. It documents two surfaces:
  `/AdminService/wmi/<ClassName>` (GET and POST across provider classes) and
  `/AdminService/v1.0/<ClassName>` (versioned functionality).
- Microsoft's [usage examples](https://learn.microsoft.com/en-us/intune/configmgr/develop/adminservice/usage)
  confirm JSON results, Windows default credentials, entity-by-key queries,
  `$filter`, `$select`, `$expand`, v1 actions, and a static WMI method POST.
- Microsoft's [setup guidance](https://learn.microsoft.com/en-us/intune/configmgr/develop/adminservice/set-up)
  requires HTTPS, documents port 443, site-generated self-signed certificates,
  optional PKI certificates, metadata endpoints, and CMG base paths.
- Microsoft's [SMS Provider planning guidance](https://learn.microsoft.com/en-us/intune/configmgr/core/plan-design/hierarchy/plan-for-the-sms-provider)
  identifies the provider as the security-enforcing WMI intermediary, states
  that it returns only authorized information, and discusses multiple provider
  instances and connection behavior.
- Microsoft's [role-based administration fundamentals](https://learn.microsoft.com/en-us/intune/configmgr/core/understand/fundamentals-of-role-based-administration)
  explain that effective administrative scope combines security roles,
  security scopes, and collections.
- The [AdminService release notes](https://learn.microsoft.com/en-us/intune/configmgr/develop/adminservice/release-notes)
  demonstrate that route capabilities vary by ConfigMgr version, including the
  addition of static WMI methods and OData functions.
- The [OData JSON 4.0 specification](https://docs.oasis-open.org/odata/odata-json-format/v4.0/odata-json-format-v4.0.html)
  defines `@odata.nextLink`, but the reviewed ConfigMgr documentation does not
  specify AdminService page-size and continuation behavior comprehensively.

The documentation does **not** justify treating all OData v4 features as
supported by every AdminService route or ConfigMgr release. It also does not
fully specify authentication negotiation, error schemas, pagination limits,
instance-method invocation, or cross-platform behavior. Those are explicit lab
validation items, not implementation facts.

## Design goals

1. Give application developers a typed, Pythonic API that hides provider and
   wire details.
2. Give ConfigMgr experts a supported, discoverable raw AdminService API without
   waiting for high-level coverage.
3. Start with AdminService while preserving high-level contracts where a later
   direct WMI backend can genuinely provide equivalent capabilities.
4. Preserve provider RBAC rather than attempting authorization in the SDK.
5. Minimize dependencies, hidden I/O, and undocumented behavior.

## Public entry point

The intended name is `ConfigManager`, exported from `configuration_manager`.
It reflects the current Microsoft product name, is concise in use, and avoids
making the legacy acronym SCCM the package's primary vocabulary.

```python
from configuration_manager import ConfigManager

with ConfigManager(server="cm01.contoso.com") as client:
    device = client.devices.get(name="PC001")
    first_page = client.collections.list(filter="Name ne null")

    raw_page = client.raw.wmi.list(
        "SMS_R_System",
        filter="Client eq true",
        select=("ResourceId", "Name"),
    )
```

Names in examples are proposed public contracts, subject to deliberate
pre-1.0 refinement; examples do not claim every named resource or filter is
available in every ConfigMgr release.

### Responsibilities and configuration

`ConfigManager` is a composition root and lifecycle owner. It validates and
normalizes configuration, constructs the built-in AdminService transport or
accepts a fully configured transport, owns resource-manager and raw namespace
access, and closes what it owns. It does not contain resource mapping or
provider business rules.

Construction performs validation and local object creation only—never DNS,
metadata discovery, authentication, or other remote I/O. Configuration is an
immutable value after construction. Proposed public constructor inputs are:

| Input | Policy |
| --- | --- |
| `server` | Required SMS Provider FQDN or host name; implies HTTPS and accepts no scheme, path, query, fragment, or embedded credentials. |
| `port` | Not frozen into the initial public signature. An optional non-default HTTPS port requires a demonstrated supported deployment before implementation. |
| `auth` | Optional authentication strategy for the built-in AdminService transport; omission means the platform-appropriate current-credential strategy if supported. |
| `timeout` | A typed total/phase timeout policy, never an unbounded implicit wait. Exact defaults require implementation testing. |
| `verify_tls` | `True` by default; `False` requires an explicit argument. A CA bundle/path may be considered during implementation. |
| `user_agent` | Optional additive application token; the SDK's name/version remains present and values are validated. |
| `base_url` | Advanced HTTPS alternative for CMG/reverse-proxy paths; mutually exclusive with `server` and never inferred from arbitrary URLs. |
| `transport` | Advanced injection point for a fully configured supported backend; mutually exclusive with built-in AdminService construction inputs, including `server`, `base_url`, `auth`, TLS, and timeout options. |

`site_code` is not required for AdminService: the documented routes are rooted
at an SMS Provider host and do not take a site code. A future direct WMI
transport may need it, and site information may be discovered remotely on first
use where reliable. Discovery must not happen in the constructor.

The host-oriented form always means HTTPS. Normalization lowercases the DNS
host, rejects schemes, ports, user-info, and route suffixes supplied as a
`server`, removes no meaningful path from an advanced HTTPS `base_url`, and
builds the two route roots internally. The simple form is a host, not
`https://host/AdminService`; an advanced base URL must still use HTTPS in
supported production configuration. Tests use transport injection or controlled
internal seams, never a public insecure HTTP mode. IPv6, internationalized-name,
and non-default HTTPS port support remain implementation-review items.
Redirects must not silently cross origins with credentials.

### Lifetime and ownership

- A client owns transports it creates and closes them from `close()`.
- An injected transport has an explicit ownership option; the safe default is
  that the injector retains ownership. This must be finalized with the concrete
  constructor rather than guessed by duck typing.
- A fully constructed injected transport already owns or references whatever
  authentication and configuration it needs. The client does not apply an
  AdminService authentication strategy to it.
- The synchronous context manager returns the client and always calls
  `close()`. `close()` is idempotent.
- Any operation after close raises an SDK lifecycle/configuration error; already
  materialized immutable models remain usable.
- Resource-manager objects and raw namespace facades are created lazily or
  eagerly without I/O and cached by identity for the client's lifetime. Query
  results and mutable server state are never implicitly cached.
- One client should be reused to benefit from HTTP connection pooling.
- The initial contract does **not** promise that a client, its built-in
  AdminService auth strategy, or iterators are thread-safe. Separate clients per
  concurrently executing thread are the portable rule until authentication
  adapters and transport behavior are validated. Immutable models are safe to
  share.

## Layering and dependency rules

The conceptual paths are:

```text
ConfigManager ──> resource manager ──> capability contract ──> AdminService
                         │                       │
                         └─ mapper <── raw record┘
                              │
                              └─> immutable domain model

ConfigManager ──> raw.v1 / raw.wmi ──> AdminService service ──> HTTPS/OData
```

“Domain Models” in a vertical summary means the high-level result boundary; a
passive model does not invoke a transport. The mapper is what crosses from
transport records into domain values.

| Layer | May know | Must not know or do |
| --- | --- | --- |
| Public client | Immutable config, lifecycle contracts, resource/raw facades | Entity mapping, arbitrary requests, provider business logic |
| Resources | Domain terminology, mappers, narrow capabilities, pagination | Concrete HTTP library, URLs, authentication mechanics, arbitrary raw HTTP |
| Domain models | Python value types and domain meaning | Clients, resources, wire keys, network I/O, lazy remote relationships |
| Capability contract | Provider-shaped query/get/invoke values, raw records, opaque continuation | High-level models, HTTP verbs/status classes, resource policy |
| AdminService service | Its two route semantics, OData/JSON, auth hooks, HTTP execution, TLS, timeouts | Device/collection business behavior or high-level domain models |
| Raw API | Documented AdminService entities/classes, query options, raw pages | Arbitrary cross-origin URL fetching, domain guarantees absent upstream |

The SDK never accesses the ConfigMgr SQL database directly. AdminService and a
future supported SMS Provider interface are the architectural boundaries.

## Transport contracts

### High-level capability boundary

Do not begin with a universal public `Transport.request()`. The internal typed
capability contract grows only as supported resources need operations:

```python
# Conceptual types, not implementation declarations
query_entities(request: EntityQuery) -> RawPage
get_entity(request: EntityKeyQuery) -> RawRecord | None
invoke_method(request: ProviderMethodCall) -> RawMethodResult
close() -> None
```

Requests describe a provider surface/entity or class, typed key, explicit OData
options, optional opaque continuation, and timeout override. They do not expose
HTTP methods, paths, header mappings, or library objects. In particular, the
contract has no client-controlled page-size preference. `invoke_method`
distinguishes static and instance targets and retains named JSON-compatible
parameters. Support is capability-checked; it does not claim every backend or
provider class can invoke every operation.

`RawPage` carries a tuple/sequence of records, an opaque continuation token,
and available count/context metadata. Only the implementing transport may turn
continuation state into a next request. Consumers must not parse or edit a
server-supplied next link. Continuations are bound to their originating client,
surface, and query.

### AdminService HTTP boundary

An internal AdminService service may use an HTTP-shaped executor because that
is its real protocol. It owns route construction, OData parameter encoding,
auth application, redirects, pooling, timeouts, TLS verification, JSON limits,
continuation validation, and status/error translation. It returns SDK raw
values—not `httpx2.Response`, auth-library objects, or arbitrary bytes—to the
normal APIs.

The internal executor uses stable `httpx2` 2.x with a synchronous pooled client,
finite internal timeouts, disabled redirects, and a per-client system-trust SSL
context. Its async support is not itself a reason to add async SDK APIs. Windows
current-credential SSPI integration is implemented behind an internal adapter,
but its ConfigMgr behavior, proxies, and concurrency still require lab evidence.

Timeouts belong to immutable client configuration with per-operation override
only where justified. TLS verification is on by default; disabling it is
explicit and should emit a sanitized warning without becoming a global switch.
Closing releases pooled connections and auth-owned resources.

## AdminService and the low-level API

`raw` is a supported product surface, divided according to Microsoft's routes:

> [!IMPORTANT]
> `client.raw.wmi` means the **AdminService `/AdminService/wmi/` route over
> HTTPS/OData**. It does not create a direct WMI/DCOM connection. A future direct
> WMI transport is a separate architecture that requires its own ADR.

```python
page = client.raw.wmi.list(
    "SMS_R_System",
    filter="Client eq true",
    select=("ResourceId", "Name"),
    order_by=("Name",),
    top=100,
)
record = client.raw.wmi.get("SMS_R_System", 16777219)
result = client.raw.wmi.invoke_static(
    "SMS_Admin", "GetAdminExtendedData", parameters={"Type": 1}
)

devices = client.raw.v1.list("Device", select=("MachineId", "Name"))
device = client.raw.v1.get("Device", 16777219)
action = client.raw.v1.invoke_action(
    "Device", 16777219, "AdminService.RunCMPivot", parameters={...}
)
```

The exact set of method invocation variants is gated by lab evidence. The names
make static WMI methods and versioned actions explicit instead of hiding syntax
in a clever callable path. A later `invoke_instance` is added only after its
route and payload behavior are confirmed. `raw.v1` and `raw.wmi` do not pretend
their class names or capabilities are interchangeable.

The raw API accepts class/entity names, not arbitrary URL paths. It validates
names and query option shapes locally but leaves provider authorization and
semantic validation to the server. Class-name casing is preserved because
Microsoft documents it as significant, despite release-specific relaxation for
the WMI route.

The implemented `raw.wmi.query` operation uses the collection route, while
`raw.wmi.get` uses the canonical parenthesized single-key route and performs one
request. Keys follow OData primitive-literal syntax; string literals double
embedded quotes and are URI-encoded so their contents cannot escape the WMI
path. Only scalar keys are represented, not composite keys. A keyed HTTP 404
maps to `None`: this means the entity was not returned to the current identity
and may reflect a missing key, unavailable class, or ConfigMgr provider/RBAC
invisibility rather than proving global nonexistence.
The WMI controller may return a keyed entity in a one-item OData `value`
envelope, despite the single-key route. The provider transport unwraps that
response while retaining compatibility with a bare entity object; an empty
envelope maps to `None`, and multiple records violate the keyed contract.

### Raw values

Conceptually:

```python
JsonScalar = None | bool | int | float | str
JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
RawRecord = Mapping[str, JsonValue]
RawMethodResult = JsonValue
RawPage = Page[RawRecord]
```

Concrete aliases must be recursive, read-only at their public boundary where
practical, and fully typed. Raw records preserve unknown properties and OData
annotations needed for fidelity. They do not preserve an HTTP response object.
Diagnostic response metadata is exposed on translated exceptions, and narrowly
scoped response metadata can be added to raw result types when demonstrated
useful. The SDK must set defensive response-size/decoding behavior during
implementation; raw means provider-shaped, not unsafe.

## Authentication and security

Authentication is a separate, **AdminService-specific** strategy subsystem:

```text
ConfigManager
    └── built-in AdminService transport
            └── AdminService authentication strategy
```

Conceptually, the strategy can prepare an HTTP authentication integration for a
specific AdminService origin, report platform support without network I/O, and
close any resources it owns. The contract passes credentials through protected
typed state, never general request dictionaries. It is narrow enough to adapt
to the chosen HTTP client rather than inventing a new authentication protocol.
It is not a requirement of the generic high-level capability contract.

The default goal for `ConfigManager(server=...)` is current-process Windows
Integrated Authentication where supported, matching Microsoft's default-
credential example. “Negotiate” is a protocol choice that may select Kerberos
or NTLM according to environment and adapter behavior; these terms are not
interchangeable strategies. Explicit credentials may be supported through an
explicit strategy, never embedded in URLs or repeated on resource calls.

Windows SSPI/current-token behavior, Kerberos on non-Windows platforms, SPN and
delegation requirements, NTLM fallback policy, credential prompting, and CMG
Microsoft Entra authentication require implementation ADRs and lab tests.
There is no promise that omission of `auth` works on every platform. Unsupported
defaults fail early with actionable `AuthenticationError`.

`transport=` and built-in AdminService construction inputs such as `auth=` are
normally mutually exclusive. A fully constructed injected transport is
responsible for its authentication and credential semantics; `ConfigManager`
does not attempt to inject HTTP authentication into an arbitrary backend. A
future direct WMI transport may need fundamentally different credential
semantics and therefore requires its own ADR rather than implementing this
AdminService authentication contract.

Security invariants:

- Never persist passwords, tokens, tickets, authorization headers, cookies, or
  other credential material.
- Never include credential material in logs, exception messages, reprs, tracing,
  or captured request metadata. Redaction is allowlist-based.
- Send credentials only to the configured trusted origin. Cross-origin
  redirects are rejected rather than replaying authorization.
- Verify TLS certificates and hostnames by default. Trusting the site's
  self-signed certificate should be done by configuring trust, not by making
  insecure verification the default.
- ConfigMgr RBAC remains authoritative. The SDK neither broadens results nor
  predicts permission from absent objects. A forbidden operation becomes an
  authorization error; an empty filtered result remains empty.

## Domain models and resources

High-level models are typed standard-library values, normally frozen slotted
dataclasses. This avoids a Pydantic runtime dependency and keeps transport
validation outside public values. Use aware `datetime` objects for timestamps
and documented native types for identifiers. Enums are used only for stable,
documented finite sets and require an explicit unknown-value policy.

Mappers distinguish required, nullable, and potentially omitted data. If
omitted versus explicit `null` changes domain meaning, a documented sentinel or
sum type represents that distinction; otherwise `T | None` is sufficient.
Unknown wire fields are ignored by high-level mappers for forward compatibility
and remain visible through raw APIs. High-level models do not automatically
carry an `extra: dict` escape hatch, do not retain transport handles, and do not
promise lossless wire serialization.

Resource managers own remote behavior and mapping. Models never implement
methods such as `device.collections()`. Relationships are explicit and testable:

```python
device = client.devices.get(name="PC001")
memberships = client.collections.for_device(device.id)
```

Terminology is capability-specific:

- `get(...)` returns exactly one model or raises a not-found/ambiguity error;
- `list(...)` performs one page request and returns `Page[T]`;
- `iter(...)` explicitly traverses pages lazily;
- `find(...)` is reserved for a meaning demonstrably different from list/get;
- `create`, `update`, and `delete` exist only on resources that support and test
  those semantics. No uniform CRUD base class fabricates unsupported methods.

The initial high-level layer is read-only. Mutation requests will need separate
typed input models, idempotency/concurrency rules, and ADR review.

## OData query policy

v0.1 raw access uses a small, typed options object and keyword conveniences. It
accepts an OData expression string as `filter`, property-name sequences for
`select` and `expand`, ordering values, and a bounded integer `top` only where
the target route supports them. `top` represents OData `$top`: a limit on the
number of items in the queried result. It is **not** a requested server page
size. High-level query arguments are introduced only with actual resource
implementations and lab evidence. Python names omit `$`; the transport maps them
to wire parameter names and performs URL percent-encoding exactly once.

The caller authors OData expression syntax and is responsible for semantically
correct literals and property names. The SDK treats the expression as data,
does not interpolate user values, does not accept pre-percent-encoded input,
and does not silently rewrite it. The transport is responsible for safe query
parameter encoding. Unsupported options fail clearly rather than being sent on
the assumption that all OData v4 features exist.

A future typed expression builder may reduce literal-escaping mistakes, but it
is not part of v0.1 and must interoperate with the stable query-options concept
rather than dictate the initial design.

## Pagination

One-page retrieval is the default and visible behavior:

```python
page: Page[Device] = client.devices.list()
for item in page.items:
    ...

if page.has_next:
    next_page = client.devices.next_page(page)

for item in client.devices.iter():
    ...  # each boundary may perform another request
```

`Page[T]` is an immutable typed value containing `items`, opaque continuation
state, and only metadata actually returned or reliably derived. It does not
hold a client or make `page.next()` perform hidden I/O. The manager's
`next_page(page)` makes ownership explicit. `iter()` is deliberately named and
documented as lazy, potentially unbounded network traversal; it fetches no page
until iteration and yields page by page without accumulating all results.

`list()` returns exactly the response page chosen by the service from one
request. The public contract does not request a page size, and it does not treat
OData `$top` as one. The server may choose its own page boundary and may return
`@odata.nextLink`; after validation, `next_page(...)` and `iter()` follow that
opaque continuation.

Continuation is opaque even when AdminService returns `@odata.nextLink`. The
transport validates that server links stay within the configured AdminService
origin and route and never exposes arbitrary fetching. A failure on page N is
raised at that iteration point; previously yielded values remain valid and are
not replayed. Cancellation is simply stopping iteration. Retry policy, stable
ordering, total counts, server page limits, and behavior when data changes
between pages require lab validation. `list()` never means “download all.”

## Exception contract

The public hierarchy is (names avoid built-in shadowing):

```text
ConfigurationManagerError
├── ConfigurationError
├── LifecycleError
├── TransportError
│   ├── TransportConnectionError
│   ├── TransportTimeoutError
│   └── TLSVerificationError
├── AuthenticationError
├── AuthorizationError
├── QueryError
├── MethodInvocationError
├── ServerError
├── NotFoundError
└── AmbiguousResultError
```

The root carries the product-specific name. Package context makes repetition on
every leaf unnecessary, while `TransportConnectionError` and
`TransportTimeoutError` deliberately avoid shadowing Python's built-ins.

Translated errors preserve a safe message, causal exception via Python
exception chaining, numeric HTTP status where applicable, ConfigMgr/OData error
code and correlation/request identifier where available, route surface,
operation kind, and sanitized response headers. The default public exception
does not retain auth objects, full request URLs with query values, cookies, or
unredacted request/response bodies. A size-limited sanitized error detail may be
available when the server schema is understood; raw bodies are not guaranteed
because enterprise payloads can contain sensitive data.

Authentication (identity establishment), authorization (RBAC rejection), query
validation, not-found, method failure, server failure, connection, timeout, and
TLS failures stay distinguishable. Concrete `httpx2`, auth-library, COM, or WMI
exceptions never need to be caught in normal public use.

## Logging and observability

The library uses a package logger below `configuration_manager` and installs no
handlers. It never calls `logging.basicConfig()` and does not configure the
application's level or formatting. Debug logs may contain operation kind,
sanitized host/surface, duration, status, item count, retry attempt, and safe
correlation IDs. Full query text and payloads are not logged by default because
names, filters, inventory, and enterprise data may be sensitive.

Logging and exception redaction share an allowlist policy. Passwords, tokens,
tickets, cookies, authorization/proxy-authorization headers, credential-bearing
URLs, and auth strategy reprs are always excluded. The SDK has no Rich or other
presentation dependency. Structured hooks or tracing require a later design.

## Dependencies, compatibility, and packaging

Runtime dependencies must correspond to protocol needs. `httpx2` is selected
for HTTP; one or more platform-specific authentication libraries may be needed
after validation. Standard-library functionality is preferred for models,
enums, logging, URLs where sufficient, and configuration. Convenience and
presentation dependencies are out of scope.

Before 1.0, breaking refinement is possible but must be intentional, tested,
documented, and reflected in ADRs. After 1.0, semantic versioning applies and
public typed APIs are contracts. Only names documented and re-exported from
public modules are public. Modules prefixed with `_` are internal; no empty
`_internal` package is created merely to signal that fact.

Recommended structure when implementation earns each module:

```text
src/configuration_manager/
├── __init__.py              # curated public exports
├── client.py                # ConfigManager and lifecycle
├── config.py                # immutable public configuration values
├── exceptions.py            # stable SDK hierarchy
├── auth.py                  # small public auth protocol/types initially
├── transport.py             # narrow capability types/protocol initially
├── adminservice.py          # concrete internal service (may become a package)
├── pagination.py            # Page[T]
├── models/                  # split only as real model families grow
├── resources/               # split only as real managers grow
└── raw.py                   # v1/wmi facades; split only when warranted
```

This starts flatter than the illustrative tree to avoid packages containing a
single `base.py`. Authentication, transport, raw, model, and resource packages
should emerge only when multiple cohesive modules exist. Tests mirror behavior,
not every source file. A PEP 561 marker remains required.

## Proposed v0.1 implementation sequence

The originally suggested resource breadth is too large for the first
architecture validation. A realistic read-only v0.1 is:

1. Immutable configuration, exception taxonomy, lifecycle-only `ConfigManager`,
   auth strategy protocol, and deterministic unit-test seams.
2. Synchronous AdminService HTTP transport with one validated integrated-auth
   adapter, strict TLS/timeout/redaction behavior, and mocked integration tests.
3. First-class `raw.wmi` query/get and **only the provider method form confirmed
   in a lab**, plus OData filter/select and one-page/continuation handling.
4. `raw.v1` metadata/query/get for proven entities, without pretending parity
   with `/wmi/`.
5. One vertical high-level read-only slice: `Device`, `Devices`, and typed
   pagination. Add basic site information only if required for diagnostics or
   capability discovery.

Users, collections, and applications follow in later 0.x milestones after the
vertical slice validates mapping, RBAC, version variance, and pagination.
Provider-wide class modeling, direct WMI, mutations, deployment actions,
application creation, task-sequence changes, and software-update orchestration
are explicitly outside v0.1.

## Open Questions

These items require a supported ConfigMgr lab matrix and, where relevant,
Windows and non-Windows clients before implementation promises are made:

1. Which Windows Integrated Authentication mechanisms does AdminService
   negotiate in representative domain, workgroup, proxy, and CMG environments?
   What are the SPN, delegation, channel-binding, and NTLM fallback constraints?
2. Which Python auth integrations reliably support current-process credentials
   on Windows and Kerberos credential caches on Linux/macOS without exposing
   secrets? Is explicit username/password support acceptable at all?
3. What error JSON, headers, status codes, and correlation identifiers are
   stable across supported ConfigMgr releases for authentication, RBAC, invalid
   OData, missing entities, and provider failures?
4. Does every target route emit `@odata.nextLink`; what triggers server-driven
   paging, are links absolute, and how do `$top`, count, ordering, concurrent
   changes, and maximum page sizes interact?
5. Which OData options and functions are supported by `/wmi/` and `/v1.0/` in
   each minimum supported ConfigMgr version, especially `$expand`, `$orderby`,
   `$count`, and string/date literal behavior?
6. What are the exact static and instance SMS Provider method URI, parameter,
   return, out-parameter, and error semantics? How are overloads and embedded
   objects represented?
7. How do RBAC roles, scopes, and collections affect absence versus 403 across
   raw and v1 routes, and can the SDK safely distinguish not-found from hidden?
8. How do multiple SMS Providers, failover, proxies, redirects, self-signed/PKI
   certificates, CMG paths, throttling, and transient failures behave?
9. Which ConfigMgr current-branch versions will v0.1 support, and should
   capabilities be discovered from `$metadata`, maintained in a tested version
   matrix, or both?
10. What safe diagnostic detail do real error payloads justify retaining
    without exposing enterprise data or credentials?
11. Can the selected HTTP/auth stack support safe concurrent use? Until proven,
    the client remains explicitly not thread-safe.

## Architecture invariants

- `ConfigManager` is the public synchronous composition root; constructing it
  performs no remote I/O.
- Public high-level APIs return typed models/pages, not raw dictionaries or HTTP
  library objects.
- Domain models are passive, immutable where practical, and never perform
  network I/O.
- Resource managers own remote operations and depend on narrow capability
  contracts, never a concrete HTTP library.
- Transport implementations contain protocol mechanics, not domain business
  logic, and translate implementation-specific failures.
- AdminService is the initial transport. `/AdminService/v1.0/` and
  `/AdminService/wmi/` remain distinct, first-class raw namespaces.
- `raw.wmi` is the AdminService WMI route over HTTPS/OData, never an implication
  of direct WMI/DCOM connectivity.
- The WMI route is the first executable provider surface. Collection queries
  parse only the OData `value` envelope into raw records. Pagination exists only
  when the server supplies `@odata.nextLink`; links remain opaque and are
  validated as HTTPS, same-origin, and within `/AdminService/wmi/` before
  credentialed replay.
- Raw WMI class-name casing is caller-controlled, while returned property names
  preserve AdminService JSON casing verbatim; the raw layer does not normalize
  differences from SMS Provider/WMI reference capitalization. Successful
  Windows authentication does not imply WMI-query authorization, because
  ConfigMgr RBAC remains independently authoritative.
- Built-in operations on Windows authenticate as the current logged-in Windows
  identity. Injected provider transports remain the cross-platform extension
  point.
- Raw AdminService access may return typed JSON-compatible values but never
  arbitrary cross-origin URL responses.
- Pagination is explicit: `list()` fetches one page and `iter()` visibly opts
  into lazy multi-page I/O; continuation state is opaque and client-controlled
  page size is not promised.
- Built-in AdminService authentication is strategy-based; generic transports do
  not consume that HTTP-oriented contract. Credentials are neither persisted
  nor logged, and provider RBAC remains authoritative.
- TLS verification is enabled by default and disabling it requires explicit
  user action.
- The library uses standard logging without configuring handlers or logging
  full payloads by default.
- Direct access to the Configuration Manager SQL database is outside the SDK.
- Runtime dependencies remain minimal and justified; no Pydantic or HTTP/auth
  dependency is selected merely for convenience.
- The initial API is synchronous. Async and direct WMI require separate design
  and do not distort current contracts.
- Unit tests use no network, controlled integration tests use mocks, and live
  lab tests are explicit opt-in only.
