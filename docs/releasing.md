# Releasing

Releases are prepared and verified manually. Release automation, publishing,
and signing are intentionally outside this process.

## Build and verify

From a clean checkout of the release candidate, run:

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
uv build
```

The release candidate must produce a wheel and source distribution whose
versions match the authoritative version in `pyproject.toml`. For version 0.2.0,
the build must produce:

```text
dist/configuration_manager-0.2.0-py3-none-any.whl
dist/configuration_manager-0.2.0.tar.gz
```

Install the wheel into a clean environment and verify its installed metadata,
rather than relying only on its filename:

```bash
python -m venv .release-venv
.release-venv/bin/python -m pip install \
  dist/configuration_manager-0.2.0-py3-none-any.whl
.release-venv/bin/python -c \
  "from importlib.metadata import version; print(version('configuration-manager'))"
```

The version command must print `0.2.0`. On Windows, use the corresponding
`.release-venv\Scripts\python.exe` path.

Do not commit anything from `dist/` or the temporary environment.

## SHA-256 release verification

After building from the final release commit, generate SHA-256 hashes for the
final artifacts. For version 0.2.0, the GitHub Release assets are:

```text
configuration_manager-0.2.0-py3-none-any.whl
configuration_manager-0.2.0.tar.gz
SHA256SUMS.txt
```

For example, on Windows PowerShell:

```powershell
$files = @(
    ".\dist\configuration_manager-0.2.0-py3-none-any.whl",
    ".\dist\configuration_manager-0.2.0.tar.gz"
)

$files | ForEach-Object {
    $hash = (Get-FileHash $_ -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $([System.IO.Path]::GetFileName($_))"
} | Set-Content -Encoding ascii .\dist\SHA256SUMS.txt
```

Create `SHA256SUMS.txt` only for the final GitHub Release; do not commit it.

## Live release-candidate validation

The ConfigMgr live suite must also pass against the release candidate from a
Windows machine that trusts the AdminService certificate chain:

```powershell
$env:CONFIGURATION_MANAGER_LIVE_SERVER = "<provider-fqdn>"
uv run pytest --run-live tests/live/test_adminservice_authentication.py -v
```

This live validation is explicit and is not part of the ordinary test suite.
The current suite contains 13 tests, including the public Device-to-Collection
and Collection-to-Device page and iterator coverage; all 13 must pass.
