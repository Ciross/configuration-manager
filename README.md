# configuration-manager

> [!IMPORTANT]
> This project is in **very early development**. It provides typed configuration,
> lifecycle, and an internal AdminService HTTP/authentication foundation, but no
> its first public, read-only Configuration Manager query surface.

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

The following is a direction, not an implemented API:

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

The first executable foundation includes the exception taxonomy, immutable
configuration, typed pages, and provider capability contracts. A lifecycle-only
client can be constructed without any remote activity:

```python
from configuration_manager import ConfigManager

with ConfigManager(server="cm01.contoso.com") as client:
    assert not client.closed
```

The first public operation queries AdminService's WMI provider surface:

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

## License

This project is licensed under the [MIT License](LICENSE).
