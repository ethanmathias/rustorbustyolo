#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
VENV_DIR="$HOME/Library/Application Support/rustorbust-venv"
GUI_SCRIPT="$SCRIPT_DIR/UI/rust_portal_gui.py"
REQ_FILE="$SCRIPT_DIR/UI/requirements.txt"
LAUNCHER="$SCRIPT_DIR/RustOrBust.command"
UV_BIN="$HOME/.local/bin/uv"

find_uv_python() {
    local candidate
    for candidate in "$HOME"/.local/share/uv/python/cpython-3.13*-macos-aarch64-none/bin/python3.13; do
        if [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

is_safe_tk_python() {
    local candidate="$1"
    local tk_path

    if ! "$candidate" - <<'PY' >/dev/null 2>&1
import tkinter
import venv
import _tkinter
print(_tkinter.__file__)
PY
    then
        return 1
    fi

    tk_path="$("$candidate" - <<'PY'
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

find_python() {
    local candidate
    for candidate in \
        "$(find_uv_python || true)" \
        python3.13 \
        python3.12 \
        /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
        /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
        /opt/homebrew/bin/python3.13 \
        /opt/homebrew/bin/python3.12 \
        /opt/homebrew/bin/python3 \
        /usr/local/bin/python3.13 \
        /usr/local/bin/python3.12 \
        /usr/local/bin/python3 \
        /usr/bin/python3
    do
        if ! command -v "$candidate" >/dev/null 2>&1; then
            continue
        fi

        if is_safe_tk_python "$candidate"; then
            command -v "$candidate"
            return 0
        fi
    done

    return 1
}

install_safe_tk_python() {
    if [ ! -x "$UV_BIN" ]; then
        return 1
    fi

    echo "No safe Tk runtime found. Installing a known-good Python 3.13 with uv..."
    "$UV_BIN" python install 3.13

    if find_uv_python >/dev/null 2>&1; then
        return 0
    fi

    return 1
}

if [ ! -f "$GUI_SCRIPT" ]; then
    echo "Could not find UI/rust_portal_gui.py in $SCRIPT_DIR" >&2
    exit 1
fi

if [ ! -f "$REQ_FILE" ]; then
    echo "Could not find UI/requirements.txt in $SCRIPT_DIR" >&2
    exit 1
fi

PYTHON_BIN="$(find_python || true)"
if [ -z "${PYTHON_BIN:-}" ]; then
    if install_safe_tk_python; then
        PYTHON_BIN="$(find_python || true)"
    fi
fi

if [ -z "${PYTHON_BIN:-}" ]; then
    echo "No safe Tk-enabled Python 3 interpreter was found." >&2
    echo "Install a Python build with tkinter support, or install uv, then rerun install.sh." >&2
    exit 1
fi

echo "Using Python: $PYTHON_BIN"
mkdir -p "$(dirname "$VENV_DIR")"

echo "Creating virtual environment at:"
echo "  $VENV_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR"

echo "Upgrading pip..."
"$VENV_DIR/bin/python3" -m pip install --upgrade pip

echo "Installing RustOrBust UI dependencies..."
"$VENV_DIR/bin/python3" -m pip install -r "$REQ_FILE"

cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "\$(dirname "\$0")"
exec "$VENV_DIR/bin/python3" UI/rust_portal_gui.py
EOF
chmod +x "$LAUNCHER"

echo
echo "Setup complete."
echo "Launch the UI with:"
echo "  $LAUNCHER"
