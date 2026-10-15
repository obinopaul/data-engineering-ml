#!/usr/bin/env bash
# Install all packages from pyproject.toml into the one workspace environment.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
if command -v uv >/dev/null; then
    uv pip install --cache-dir .cache/uv --python .venv/bin/python -e .
    uv pip check --python .venv/bin/python
else
    .venv/bin/python -m pip install --cache-dir .cache/pip -e .
    .venv/bin/python -m pip check
fi
echo 'Installed. Use: source .venv/bin/activate'
