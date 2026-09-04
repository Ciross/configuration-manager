# configuration-manager

> [!IMPORTANT]
> This project is in **very early development**. It provides typed configuration,
> lifecycle, typed read-only Device, Collection, and User APIs, and raw AdminService
> query surfaces.

`configuration-manager` is intended to become a strongly typed Python SDK for
Microsoft Configuration Manager (ConfigMgr, formerly SCCM and MECM). It will
serve two audiences:

- application developers who want a high-level, Pythonic API for common tasks;
- experienced Configuration Manager administrators and developers who need
  low-level access to AdminService and SMS Provider concepts.

The architecture will be AdminService-first while retaining room for additional
transports later. The high-level API should hide unnecessary Configuration
Manager implementation details. A separate low-level escape hatch should expose
underlying capabilities without weakening the high-level abstractions.

## Intended architecture

The Device and Collection branches are implemented; the others remain direction:

```text
High-level API
      │
      ├── Devices
      ├── Users
      ├── Collections
      ├── Applications
      └── ...
      │
      ▼
Resource / domain layer
      │
      ▼
Transport abstraction
      │
      ├── AdminService
      └── future transports
```

Alongside it, advanced users will eventually have a direct route:

```text
Low-level API
      │
      ▼
AdminService / SMS Provider
```

The executable foundation includes the exception taxonomy, immutable
configuration, typed pages, and provider capability contracts. A client can be
constructed without any remote activity:

```python
from configuration_manager import ConfigManager

with ConfigManager(server="cm01.contoso.com") as client:
    assert not client.closed
```

### Typed devices

The first high-level resource maps the AdminService v1 `Device` entity to an
immutable, slotted `Device` model:

```python
from configuration_manager import ConfigManager

with ConfigManager(server="cm01.contoso.com") as client:
    page = client.devices.list(limit=10)

    for device in page.items:
        print(device.id, device.name)

    device = client.devices.get(16777219)
```

The initial model fields are `id`, `name`, `client_version`,
`operating_system`, `is_active`, and aware `last_active_time`. The mapper accepts
both JSON booleans and the live-observed ConfigMgr numeric `0`/`1`
representation of `Device.IsActive`, mapping either to a typed Python boolean. This targeted
normalization does not alter the service representation exposed by `raw.v1`.
`devices.list()` returns one `Page[Device]`; its `limit` maps to AdminService
`$top`, a result
cap rather than a client-selected page size. `devices.iter()` follows opaque
server pagination lazily, while `devices.get(id)` performs one keyed lookup.
Missing or RBAC-invisible keyed devices raise `NotFoundError`; this does not
prove global nonexistence because ConfigMgr RBAC remains authoritative.
Advanced OData querying and unknown v1 fields remain available through
`client.raw.v1`.

Device-to-Collection membership is exposed as a distinct, immutable
`DeviceCollectionMembership` relationship model backed by the documented v1
navigation property:

```python
with ConfigManager(server="cm01.contoso.com") as client:
    memberships = client.devices.collection_memberships(16777260)

    for membership in memberships.items:
        print(membership.collection_id, membership.collection_name)
```

Use `next_collection_memberships_page()` for explicit pagination or
`iter_collection_memberships()` to traverse server continuations lazily.

### Typed users

Users are immutable, slotted values backed by the AdminService WMI
`SMS_R_User` entity:

```python
from configuration_manager import ConfigManager

with ConfigManager(server="cm01.contoso.com") as client:
    users = client.users.list(limit=10)
    for user in users.items:
        print(user.id, user.unique_username, user.full_name)
    user = client.users.get(2063597568)
```

Use `client.users.next_page(page)` for explicit pagination or
`client.users.iter()` for lazy traversal across server-controlled pages.
The typed resource projects only fields represented by the public `User` model;
use `client.raw.wmi` when arbitrary `SMS_R_User` fields are needed.

User-to-Collection membership exposes Collection IDs without performing hidden
Collection lookups:

```python
with ConfigManager(server="cm01.contoso.com") as client:
    memberships = client.users.collection_memberships(2063597568)

    for membership in memberships.items:
        print(membership.collection_id)
```

Use `client.users.next_collection_memberships_page(...)` for explicit
pagination or `client.users.iter_collection_memberships(...)` for lazy
iteration. When full Collection metadata (including its name) is needed, the
caller can explicitly request
`client.collections.get(membership.collection_id)`.

### Typed collections

The second high-level resource maps the WMI `SMS_Collection` entity to an
immutable, slotted `Collection` model. `CollectionType` exposes the documented
`OTHER`, `USER`, and `DEVICE` values.

```python
from configuration_manager import ConfigManager

with ConfigManager(server="cm01.contoso.com") as client:
    page = client.collections.list(limit=10)

    for collection in page.items:
        print(collection.id, collection.name, collection.collection_type)

    collection = client.collections.get("SMS00001")
```

The initial fields are `id`, `name`, `collection_type`, `member_count`,
`limiting_collection_id`, `limiting_collection_name`, and `is_builtin`.
Collections use `/AdminService/wmi/SMS_Collection`, while Devices use
`/AdminService/v1.0/Device`; both follow the same high-level conventions.
`collections.list()` returns one `Page[Collection]`. Its `limit` maps to `$top`,
a result cap rather than a requested page size, and `collections.iter()` lazily
follows opaque server pagination. `collections.get(id)` performs one keyed
provider lookup; missing or RBAC-invisible objects raise `NotFoundError`, without
claiming global nonexistence. ConfigMgr RBAC remains authoritative. Advanced
filtering and unknown WMI properties remain available through `client.raw.wmi`.

Device members of a Device collection are exposed as immutable
`CollectionDeviceMember` relationship values:

```python
with ConfigManager(server="cm01.contoso.com") as client:
    members = client.collections.device_members("SMS00001", limit=10)

    for member in members.items:
        print(member.device_id, member.device_name)
```

Use `next_device_members_page()` for explicit pagination or
`iter_device_members()` to traverse the server continuations lazily. The root
collection is resolved first to ensure that it is a Device collection.

### Raw provider access

The raw API also queries AdminService's WMI provider surface:

```python
from configuration_manager import ConfigManager

with ConfigManager(server="cm01.contoso.com") as client:
    page = client.raw.wmi.query(
        "SMS_R_System",
        filter="Client eq 1",
        select=("ResourceId", "Name"),
        top=10,
    )
    for record in page.items:
        print(record["ResourceId"], record["Name"])
```

A parenthesized, single-scalar WMI key can be fetched with exactly one request:

```python
device = client.raw.wmi.get(
    "SMS_R_System",
    16777219,
    select=("ResourceId", "Name"),
)

if device is not None:
    print(device["Name"])
```

`raw.wmi` is the HTTPS/OData `/AdminService/wmi/` route, not direct WMI/DCOM.
WMI class names are case-sensitive and are passed through using the caller's
casing. Raw record property names are likewise returned exactly as AdminService
serialized them; AdminService JSON casing can differ from capitalization in SMS
Provider/WMI reference documentation, and the raw layer does not normalize it.
Successful Windows authentication does not itself grant WMI query access:
ConfigMgr RBAC still applies independently. `query()` materializes exactly one
server-controlled page; call `next_page()` when `page.has_next`, or use the lazy
`iter()` helper to traverse continuations. `$top` is an OData result limit, not a
client-selected page size. Built-in authentication has been validated on Windows
with the logged-in user's current Windows identity; injected transports remain
available cross-platform.

`get()` uses the AdminService `/wmi` keyed route and returns `RawRecord | None`.
HTTP 404 maps to `None`, meaning the keyed entity was not returned to the current
identity—not proof that it does not exist globally. A missing key, unavailable
class, or ConfigMgr provider/RBAC invisibility can all surface this way. Scalar
`bool`, `int`, `float`, and string keys are supported; string OData literals are
escaped and URI-safe. Composite WMI keys are not yet represented. As with query
results, raw property casing remains defined by AdminService.
The WMI controller may place a keyed result inside an OData `value` envelope;
the SDK unwraps that transport detail, so callers receive the same public result
type whether AdminService returns an envelope or a bare entity object.

### Raw versioned AdminService entities

The distinct versioned route is available through `raw.v1`:

```python
with ConfigManager(server="cm01.contoso.com") as client:
    page = client.raw.v1.query("Device", top=10)
    device = client.raw.v1.get("Device", 16777219)
```

`raw.v1` maps to the HTTPS/OData `/AdminService/v1.0/` route, while `raw.wmi`
maps to `/AdminService/wmi/`. Microsoft documents `Device` on the v1 route;
entity availability can vary by Configuration Manager version and site, and v1
does not imply that every SMS Provider class is available. Results remain raw
mappings whose property names are preserved exactly as AdminService sends them.
Collection pagination follows the server's opaque `@odata.nextLink`. A keyed
404 returns `None` (not found or not visible to the current identity), and
ConfigMgr RBAC remains authoritative for both routes.

The internal HTTP boundary uses stable `httpx2`, operating-system certificate
trust, finite timeouts, bounded response decoding, and disabled redirects.
Windows current-credential Negotiate support is wired into the built-in client.

The resulting foundational contract and its decision records are documented in
the [architecture guide](docs/architecture.md).

## Python support

Python 3.11 and newer are supported. Production code is fully typed, and the
package includes a `py.typed` marker for consumers of type information.

## Development

[uv](https://docs.astral.sh/uv/) manages Python versions, the virtual
environment, dependencies, and the lockfile. From a clone of the repository:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

Unit tests are isolated and require neither network access nor a Configuration
Manager environment. Integration tests will use controlled or mocked services.
Live tests are reserved for a real lab, are excluded by default, and must always
be selected explicitly with `uv run pytest --run-live tests/live`.
The Windows authentication probe additionally requires
`CONFIGURATION_MANAGER_LIVE_SERVER` and a machine whose system store trusts the
AdminService certificate chain.

## Releasing

Releases are manually verified with the ordinary test suite, controlled
integration coverage, a clean wheel installation, and the opt-in live ConfigMgr
suite. See the [release guide](docs/releasing.md).

## License

This project is licensed under the [MIT License](LICENSE).
