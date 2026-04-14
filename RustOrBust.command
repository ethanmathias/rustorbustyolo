#!/usr/bin/env bash
cd "$(dirname "$0")"
exec "$HOME/Library/Application Support/rustorbust-venv/bin/python3.13" UI/rust_portal_gui.py
