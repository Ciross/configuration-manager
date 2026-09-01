# configuration-manager

> [!IMPORTANT]
> This project is in **very early development**. It provides typed configuration
> and lifecycle foundations, but no Configuration Manager connectivity or
> resource operations yet.

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

No query, resource, authentication, or AdminService HTTP operations are
implemented yet.

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

## License

This project is licensed under the [MIT License](LICENSE).
