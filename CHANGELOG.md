# Changelog

## Unreleased

### Added

- Typed read-only User resource queries.
- Typed read-only User-to-Collection membership queries.
- Typed read-only Collection-to-User member queries.

## 0.2.0 - 2026-09-03

### Added

- Typed read-only Device-to-Collection membership queries through
  `client.devices.collection_memberships`, with explicit pagination and lazy
  iteration.
- Typed read-only Collection-to-Device member queries through
  `client.collections.device_members`, with explicit pagination and lazy
  iteration.
- Immutable `DeviceCollectionMembership` and `CollectionDeviceMember`
  relationship models.
- Structural provider navigation-query support used by the AdminService v1
  Device membership relationship.

## 0.1.0 - 2026-09-03

### Added

- Synchronous `ConfigManager` with immutable, typed configuration and a
  documented exception hierarchy.
- AdminService HTTP transport with Windows Integrated Authentication through
  Negotiate/SSPI and TLS verification using system trust.
- Raw `client.raw.wmi` and `client.raw.v1` access, including entity query,
  keyed retrieval, and pagination.
- Immutable typed `Device` values and
  `client.devices.list/get/next_page/iter` operations.
- Immutable typed `Collection` values, the public `CollectionType` enum, and
  `client.collections.list/get/next_page/iter` operations.
- Opaque typed pagination and RBAC-aware not-found semantics.
- PEP 561 typed-package support on Python 3.11 through 3.14.
- Controlled unit and integration test coverage, plus opt-in live ConfigMgr
  validation.
