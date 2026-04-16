#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
VENV_PY="$HOME/Library/Application Support/rustorbust-venv/bin/python3"
UV_PY="$HOME/.local/share/uv/python/cpython-3.13.12-macos-aarch64-none/bin/python3.13"

is_safe_tk_python() {
    py="$1"
    if ! "$py" - <<'PY' >/dev/null 2>&1
import tkinter
import paramiko
import _tkinter
print(_tkinter.__file__)
PY
    then
        return 1
    fi

    tk_path="$("$py" - <<'PY'
import _tkinter
print(_tkinter.__file__)
PY
)"

    if [ -n "$tk_path" ] && command -v otool >/dev/null 2>&1; then
        if otool -l "$tk_path" 2>/dev/null | grep -q "minos 26"; then
            return 1
        fi
    fi

    return 0
}

for py in "$VENV_PY" "$UV_PY" python3.13 python3.12 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 python3; do
    if ! command -v "$py" >/dev/null 2>&1; then
        continue
    fi

    if is_safe_tk_python "$py"; then
        if [ -f "$REPO_ROOT/UI/rust_portal_gui.py" ]; then
            exec "$py" "$REPO_ROOT/UI/rust_portal_gui.py"
        fi
        exec "$py" "$REPO_ROOT/rust_portal_gui.py"
    fi
done

echo "No compatible Python interpreter was found." >&2
echo "Install or rebuild a Tk-enabled Python runtime whose _tkinter module does not require macOS 26." >&2
echo "Then rerun ./macos/install.sh to recreate the local launcher environment." >&2
exit 1
