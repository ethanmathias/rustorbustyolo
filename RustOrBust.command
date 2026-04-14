#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec "$HOME/Library/Application Support/rustorbust-venv/bin/python3" UI/rust_portal_gui.py
