# Releasing

The first release is prepared and verified manually. Release automation,
publishing, signing, and version bumping are intentionally outside this process.

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

For version 0.1.0, the build must produce:

```text
dist/configuration_manager-0.1.0-py3-none-any.whl
dist/configuration_manager-0.1.0.tar.gz
```

Install the wheel into a clean environment and verify its installed metadata,
rather than relying only on its filename:

```bash
python -m venv .release-venv
.release-venv/bin/python -m pip install \
  dist/configuration_manager-0.1.0-py3-none-any.whl
.release-venv/bin/python -c \
  "from importlib.metadata import version; print(version('configuration-manager'))"
```

The version command must print `0.1.0`. On Windows, use the corresponding
`.release-venv\Scripts\python.exe` path.

Do not commit anything from `dist/` or the temporary environment.

## Live release-candidate validation

The ConfigMgr live suite must also pass against the release candidate from a
Windows machine that trusts the AdminService certificate chain:

```powershell
$env:CONFIGURATION_MANAGER_LIVE_SERVER = "<provider-fqdn>"
uv run pytest --run-live tests/live/test_adminservice_authentication.py -v
```

This live validation is explicit and is not part of the ordinary test suite.
