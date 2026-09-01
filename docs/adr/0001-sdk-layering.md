# ADR 0001: Layer the SDK around resources and first-class raw access

- **Status:** Accepted
- **Date:** 2026-09-01

## Context

The SDK serves application developers who need stable typed concepts and
ConfigMgr experts who need provider fidelity. Making either interface a thin
alias for the other would leak transport details upward or constrain experts.

## Decision

`ConfigManager` is the public composition root. Its typed resource managers
map provider data into domain models. In parallel, `client.raw.v1` and
`client.raw.wmi` expose the two bounded AdminService surfaces. Both paths use
owned transport services and the same authentication, lifecycle, error, and
configuration policies.

Here `raw.wmi` names the AdminService WMI route over HTTPS/OData, not direct
WMI/DCOM connectivity. A direct WMI backend requires a separate ADR.

Dependencies point inward through contracts: resources may use provider-shaped
transport operations and mappers; models know neither resources nor transport;
transports know neither public domain models nor resource policy. Raw APIs may
return JSON-compatible mappings, but normal high-level APIs may not.

Models are passive values. Relationships and remote actions remain on resource
managers rather than using Active Record-style hidden I/O.

## Consequences

- A feature can mature from raw access to a high-level wrapper without removing
  the escape hatch.
- Mapping code is explicit and independently testable.
- Some concepts have both raw and domain representations; that duplication is
  intentional.
- Arbitrary URL fetching and HTTP-library response objects are not public SDK
  abstractions.
