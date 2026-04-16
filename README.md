# RustOrBust YOLO

This repo now includes a small GUI for submitting batch rust-detection jobs to `portal.cs.virginia.edu`.

## Installer layout

Platform-specific launchers and installers are grouped into:

- `macos/`
- `windows/`

## macOS install and use

Run the installer once:

```bash
chmod +x macos/install.sh
./macos/install.sh
```

The installer will:

- find a Tk-enabled Python on your Mac
- install a known-good Python 3.13 via `uv` if no safe Tk runtime is already available
- create a local virtual environment at `~/Library/Application Support/rustorbust-venv`
- install the UI dependencies from `UI/requirements.txt`, including `pytesseract` for OCR
- create or refresh `macos/RustOrBust.command`

After setup, launch the app with:

```bash
./macos/RustOrBust.command
```

If you prefer to run it directly instead of using the launcher:

```bash
"$HOME/Library/Application Support/rustorbust-venv/bin/python3" UI/rust_portal_gui.py
```

## Windows install and use

On Windows:

```bat
windows\install_windows.bat
windows\RustOrBust.bat
```

## What the GUI does

- prompts for the user's portal username and password
- lets the user choose a local folder of images
- lets the user choose a local `.pt` model file
- uploads the selected images, the chosen model weights, and the remote inference script to the portal
- submits a Slurm GPU job that runs YOLO batch inference remotely
- downloads annotated outputs plus `summary.csv` / `summary.json` back to the local machine

## Dependencies

The remote job can also bootstrap `torch`, `torchvision`, and `ultralytics` on the cluster before running if the checkbox stays enabled.

- On macOS, `macos/install.sh` installs the local UI dependencies into `~/Library/Application Support/rustorbust-venv`
- On macOS, `macos/install.sh` can also bootstrap a safe Tk-capable Python 3.13 via `uv`
- On Windows, `windows/install_windows.bat` creates a local `.venv` and installs the UI dependencies from `UI\requirements.txt`
- OCR also requires the `tesseract` executable itself to be installed on the machine

## Notes

- The GUI does not store the password on disk; it is only used for the current SSH session.
- The default remote workspace root is `/u/{username}/rustorbustyolo_jobs`.
- Downloaded results are stored under `UI/results/` on the local machine.
- This flow assumes password-based SSH works for the account. If the portal requires a different interactive authentication step, submission will fail until that auth flow is handled separately.
