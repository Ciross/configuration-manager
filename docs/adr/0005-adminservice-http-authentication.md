# ADR 0005: Use httpx2, system TLS trust, and Windows SSPI for AdminService

- **Status:** Accepted
- **Date:** 2026-09-01
- **Updated:** 2026-09-01

## Context

The AdminService implementation needs a synchronous, pooled HTTPS boundary with
finite timeouts, controlled redirects, explicit TLS configuration, defensive
decoding, and challenge-response authentication. ConfigMgr commonly uses an
organization's internal PKI, so a bundled public-root set alone is not a
sufficient default trust strategy. Windows examples use the logged-in user's
credentials, but CI cannot establish whether a particular ConfigMgr deployment
will negotiate Kerberos or NTLM successfully.

The original implementation-backed decision selected HTTPX 0.28.1 and
`httpx-negotiate-sspi` 0.28.2. That combination validated successfully against a
real Configuration Manager environment, using current Windows credentials to
read `/AdminService/v1.0/$metadata`. It was therefore implementation-valid, but
the adapter subsequently deprecated its HTTPX integration. Stable `httpx2` 2.x
is now available with a dedicated, maintained `httpx2-negotiate-sspi` adapter.
Migration cost is low before any public raw or resource API depends on the
executor, so this revision supersedes the HTTPX 0.28 portion of the decision.

The `httpx2-negotiate-sspi` adapter uses Windows SSPI rather than implementing
Kerberos or NTLM cryptography. Without a username and password it uses the
current process credentials. Delegation is optional and remains disabled. The
authentication result is Negotiate: SSPI and the server may select Kerberos or
NTLM, so the SDK does not promise either mechanism specifically.

## Decision

Use stable synchronous `httpx2>=2.12.0,<3`, the 2.12.0 release tested by this
implementation. The upper bound prevents an unreviewed major-version migration.
It provides pooling, explicit finite timeouts, per-client TLS contexts, custom
mock transports, authentication flows, URL construction, and bounded streaming.
The executor remains internal and synchronous.

For verified clients, construct a fresh `truststore.SSLContext` using
`ssl.PROTOCOL_TLS_CLIENT` and pass it to `httpx2`. This uses the operating-system
certificate store, including enterprise roots installed for Windows, while
retaining certificate and hostname verification. Contexts are per client;
Python SSL defaults are never modified. `verify_tls=False` remains explicit
insecure intent. Arbitrary self-signed certificates are not trusted, and custom
CA bundle configuration is deferred.

Disable automatic redirects, and reject every 3xx before consuming its body. No
authentication flow is therefore silently replayed to another origin. Use a
30-second finite default with a 10-second connect phase internally; the precise
public timeout model remains pre-1.0 and is not added to `ConfigManager` here.
Responses remain bounded at 10 MiB and JSON and text are decoded explicitly.
Errors contain neither response bodies nor URLs/query values.

On Windows only, install
`httpx2-negotiate-sspi>=2.0.1,<2.1` and adapt
`HttpNegotiateAuth(delegate=False)` behind the internal
`windows_integrated_authentication()` constructor. This is the 2.0.1 adapter
release tested here; the upper bound prevents unreviewed adapter feature changes.
It uses the current Windows logon session, does not prompt or accept/persist a
password, does not force NTLM, and does not request delegation. Its third-party
type is not public SDK API. Linux and macOS receive no Windows dependency and
have no default AdminService authentication claim.

HTTP/auth remains AdminService-specific: generic provider capability transports
arrive fully configured and do not acquire `httpx2`, SSPI, URLs, TLS, or HTTP
concepts. The executor returns typed JSON/text values and SDK exceptions, never
library responses or arbitrary bytes. `httpx2` timeout, connection, TLS, and
other HTTP errors are translated at the executor boundary with exception
chaining. `truststore>=0.10.4,<1` remains a direct dependency for explicit OS
trust behavior.

## Consequences and validation limits

- Linux CI validates execution and safety behavior with `httpx2.MockTransport`;
  ordinary tests make no external requests.
- Windows CI on Python 3.11 and 3.14 validates locked dependency resolution,
  imports of both packages, current-credential auth construction, AdminService
  construction, and clean close without DNS or HTTP traffic.
- A gated Windows live test retains its narrow read-only purpose: verified
  system TLS, current credentials, and `/AdminService/v1.0/$metadata`.
- A real lab must revalidate ConfigMgr versions, Negotiate behavior, SPNs and DNS
  canonicalization, Extended Protection/channel binding, proxies, current-user
  identity, RBAC behavior, and connection reuse after this dependency migration.
  No thread-safety or cross-platform authentication promise is made.
- The exact error payload/correlation schema and public timeout/auth APIs remain
  deferred. A low-level 404 stays a private HTTP status error.

## Rejected and deferred alternatives

- **Retain HTTPX 0.28:** rejected because its selected SSPI integration is
  deprecated and retaining it would defer migration until more APIs depend on it.
- **Unbounded dependency ranges:** rejected because neither a future `httpx2`
  major nor an unreviewed adapter minor should enter a locked refresh silently.
- **Requests:** duplicates the selected HTTP stack and does not improve the
  typed/mocked boundary.
- **Bundled public CA roots only:** insufficient as the normal enterprise PKI
  strategy. Global SSL modification, disabled hostname checks, and automatic
  trust of self-signed certificates are rejected.
- **A new adapter built on pyspnego or direct SSPI bindings:** would make this SDK
  own security-sensitive Negotiate protocol orchestration without justification.
- Explicit passwords, prompting, credential persistence, forced NTLM,
  delegation-by-default, direct WMI/DCOM, CMG/custom paths, public raw
  AdminService operations, and ConfigMgr domain resources remain outside this
  decision.
