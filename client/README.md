# RustOrBust — Client

Desktop GUI for submitting batch rust-detection jobs to `portal.cs.virginia.edu`.

## Layout

- [`UI/`](UI/) — the Python Tk application and its requirements
- [`macos/`](macos/) — macOS installer and launcher
- [`windows/`](windows/) — Windows installer and launcher

## macOS install and use

Run the installer once:

```bash
chmod +x client/macos/install.sh
./client/macos/install.sh
```

The installer will:

- find a Tk-enabled Python on your Mac
- install a known-good Python 3.13 via `uv` if no safe Tk runtime is already available
- create a local virtual environment at `~/Library/Application Support/rustorbust-venv`
- install the UI dependencies from `client/UI/requirements.txt`, including `pytesseract` for OCR
- create or refresh `client/macos/RustOrBust.command`

After setup, launch the app with:

```bash
./client/macos/RustOrBust.command
```

## Windows install and use

```bat
client\windows\install_windows.bat
client\windows\RustOrBust.bat
```

## What the GUI does

- prompts for the user's portal username and password
- lets the user choose a local folder of images
- lets the user choose a local `.pt` model file
- uploads the selected images, the chosen model weights, and the remote inference script to the portal
- submits a Slurm GPU job that runs YOLO batch inference remotely
- downloads annotated outputs plus `summary.csv` / `summary.json` back to the local machine

## Dependencies

- The remote job can bootstrap `torch`, `torchvision`, and `ultralytics` on the cluster before running if the checkbox stays enabled.
- On macOS, `macos/install.sh` installs the local UI dependencies into `~/Library/Application Support/rustorbust-venv`, and can bootstrap a safe Tk-capable Python 3.13 via `uv`.
- On Windows, `windows/install_windows.bat` creates a local `.venv` under `client/` and installs from `UI\requirements.txt`.
- OCR also requires the `tesseract` executable itself to be installed on the machine.

## Notes

- The GUI does not store the password on disk; it is only used for the current SSH session.
- The default remote workspace root is `/u/{username}/rustorbustyolo_jobs`.
- Downloaded results are stored under `client/UI/results/` on the local machine.
- This flow assumes password-based SSH works for the account.
