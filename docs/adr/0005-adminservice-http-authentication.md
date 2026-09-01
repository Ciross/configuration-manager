# ADR 0005: Use HTTPX, system TLS trust, and Windows SSPI for AdminService

- **Status:** Accepted
- **Date:** 2026-09-01

## Context

The AdminService implementation needs a synchronous, pooled HTTPS boundary with
finite timeouts, controlled redirects, explicit TLS configuration, defensive
decoding, and challenge-response authentication. ConfigMgr commonly uses an
organization's internal PKI, so a bundled public-root set alone is not a
sufficient default trust strategy. Windows examples use the logged-in user's
credentials, but CI cannot establish whether a particular ConfigMgr deployment
will negotiate Kerberos or NTLM successfully.

We reviewed HTTPX's SSL documentation and the published source and metadata for
`httpx-negotiate-sspi` 0.28.2, `pyspnego` 0.12.2, and `sspilib` 0.6.0. The SSPI
adapter is Apache-2.0 licensed, declares HTTPX `>0.16,<0.29` through its `httpx`
extra, and uses pywin32's Windows SSPI rather than implementing Kerberos or NTLM
cryptography. With no username/password it uses the current process credentials;
delegation is optional and is disabled here. Its source builds an `HTTP/<host>`
SPN, requests mutual authentication, and supplies TLS server-end-point channel
binding when the HTTPX network stream exposes the peer certificate.

The adapter keeps handshake state within an authentication flow, but it mutates
the request during the exchange and may canonicalize the host. Neither its
thread safety nor connection/proxy behavior is documented strongly enough for a
concurrency promise. Version 0.28.2 also prefers `httpx2` when installed and
emits a deprecation warning for HTTPX; this project deliberately does not install
`httpx2`, because adopting a different/prerelease HTTP stack is outside this
foundation. These facts require Windows smoke tests and real lab validation.

## Decision

Use stable synchronous HTTPX with `httpx>=0.28.1,<1`. HTTPX 0.28.x is the stable
line validated for this foundation and provides pooling, explicit finite
timeouts, per-client TLS contexts, mock transports, and authentication flows.
The broad `<1` project constraint avoids a prerelease 1.0 dependency while
allowing compatible stable 0.x updates; the SSPI adapter's Windows-only extra
currently further constrains its own compatible environment to HTTPX `<0.29`.

For verified clients, construct a fresh `truststore.SSLContext` using
`ssl.PROTOCOL_TLS_CLIENT` and pass it to HTTPX. This uses the operating-system
certificate store, including enterprise roots installed for Windows, while
retaining certificate and hostname verification. Contexts are per client;
Python SSL defaults are never modified. `verify_tls=False` remains explicit
insecure intent. Arbitrary self-signed certificates are not trusted, and custom
CA bundle configuration is deferred.

Disable automatic redirects. No authentication flow is therefore silently
replayed to another origin. Use a 30-second finite default with a 10-second
connect phase internally; the precise public timeout model remains pre-1.0 and
is not added to `ConfigManager` here.

On Windows only, install `httpx-negotiate-sspi[httpx]>=0.28.2,<0.29` and adapt
`HttpSspiAuth()` behind an internal constructor. It uses current Windows
credentials, enables Negotiate (Kerberos or NTLM as selected by SSPI/server),
and does not request delegation. It is not exposed as a permanent public type.
Linux and macOS receive no Windows dependency and have no default AdminService
authentication claim. `ConfigManager` is not wired to the service yet because
doing so would prematurely define public authentication selection.

HTTP/auth remains AdminService-specific: generic provider capability transports
arrive fully configured and must not acquire HTTPX, SSPI, URLs, or TLS concepts.
The executor returns typed JSON/text values and SDK exceptions, never HTTPX
responses or arbitrary bytes. It bounds responses at 10 MiB, explicitly decodes
JSON/UTF-8, does not follow redirects, and does not include bodies or URLs with
query values in errors.

Runtime dependencies are HTTPX for the protocol, `truststore` for system trust,
and the Windows-marked SSPI adapter (which owns its pywin32 dependency). No
convenience or presentation dependencies are added.

## Consequences and validation limits

- Linux CI validates HTTP execution and system-context configuration with HTTPX
  mock transports; Windows CI 3.11 and 3.14 validates dependency resolution,
  import, and default-credential auth construction without traffic.
- A gated Windows live test reads `/AdminService/v1.0/$metadata`. The lab machine
  must trust the server certificate/root in its OS store; verification is never
  disabled by the test.
- A real lab must still validate ConfigMgr versions, Kerberos/NTLM negotiation,
  SPNs and DNS canonicalization, Extended Protection/channel binding, proxies,
  current-user identity, RBAC response behavior, and connection reuse. No
  thread-safety or cross-platform authentication promise is made.
- The exact error payload/correlation schema and public timeout/auth APIs remain
  deferred. A low-level 404 stays a generic HTTP status error, not `NotFoundError`.

## Rejected and deferred alternatives

- **HTTPX 1.0 prereleases and `httpx2`:** inappropriate for the initial stable
  protocol dependency and not required for synchronous AdminService access.
- **Requests:** duplicates the selected HTTP stack and does not improve the
  typed/mocked boundary.
- **Bundled public CA roots only:** insufficient as the normal enterprise PKI
  strategy. Global SSL modification, disabled hostname checks, and automatic
  trust of self-signed certificates are rejected.
- **String CA paths passed as HTTPX `verify`:** deprecated in HTTPX 0.28; a
  future explicit CA feature will create an SSL context instead.
- **A new adapter built on pyspnego:** pyspnego is an important future
  cross-platform building block (SSPI through `sspilib` on Windows and optional
  GSSAPI/Kerberos integrations elsewhere), but duplicating HTTP Negotiate logic
  is unjustified while the direct adapter is viable. Cross-platform AdminService
  authentication requires a later ADR and live evidence.
- **Direct `sspilib`:** it is a low-level SSPI binding used by pyspnego, not an
  HTTPX authentication adapter; using it directly would make this SDK own
  security-sensitive protocol orchestration.
- Explicit passwords, prompting, credential persistence, forced NTLM,
  delegation-by-default, direct WMI/DCOM, CMG/custom paths, and public raw
  AdminService operations are outside this decision.
