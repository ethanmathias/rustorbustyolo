#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

for py in python3.12 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 python3; do
    if ! command -v "$py" >/dev/null 2>&1; then
        continue
    fi

    if "$py" -c 'import tkinter, paramiko' >/dev/null 2>&1; then
        exec "$py" "$SCRIPT_DIR/rust_portal_gui.py"
    fi
done

echo "No compatible Python interpreter was found." >&2
echo "Install Paramiko into a Tk-enabled interpreter, for example:" >&2
echo "  python3.12 -m pip install --user -r requirements.txt" >&2
exit 1
