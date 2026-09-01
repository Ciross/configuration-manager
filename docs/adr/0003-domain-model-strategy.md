# ADR 0003: Use standard-library immutable domain models

- **Status:** Accepted
- **Date:** 2026-09-01

## Context

The public model layer needs strict typing and long-term stability without
coupling consumers to transport payloads or a validation framework. ConfigMgr
payloads can omit properties, return null, and gain fields between versions.

## Decision

Public domain values use standard-library dataclasses, enums, and typing.
Models should normally be `@dataclass(frozen=True, slots=True)`. Timestamps are
aware `datetime` values; identifiers retain their documented native semantic
type rather than being forced into a universal ID wrapper. Optionality is
modeled deliberately, and omitted-versus-null is preserved only where it has
domain significance.

Transport mappers tolerate unknown payload properties and reject or clearly
represent invalid known properties. Unknown fields are not automatically added
to every high-level model. Forward-compatible raw data remains available from
the raw API. Models do not promise round-trip wire serialization; explicit
request/serialization types will be designed for mutation features.

Pydantic is not a runtime dependency. It may be reconsidered only with measured
benefit that justifies its API and dependency cost.

## Consequences

- Models are predictable, lightweight, and transport-independent.
- Mapping and validation are explicit responsibilities outside models.
- Enums need a documented unknown-value policy per field; premature exhaustive
  enums are avoided.
- The SDK will model only resources in supported high-level scenarios, not the
  full SMS Provider schema.
