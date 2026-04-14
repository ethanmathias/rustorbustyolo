# RustOrBust YOLO

This repo now includes a small GUI for submitting batch rust-detection jobs to `portal.cs.virginia.edu`.

## Launch the GUI

```bash
./launch_rust_portal_gui.sh
```

If you prefer to launch it directly, use a Tk-enabled interpreter such as:

```bash
python3.12 rust_portal_gui.py
```

On Windows:

```bat
install_windows.bat
RustOrBust.bat
```

## What the GUI does

- prompts for the user's portal username and password
- lets the user choose a local folder of images
- lets the user choose a local `.pt` model file
- uploads the selected images, the chosen model weights, and the remote inference script to the portal
- submits a Slurm GPU job that runs YOLO batch inference remotely
- leaves annotated outputs and `summary.csv` / `summary.json` on the portal in the generated workspace directory

## Local dependency

Install Paramiko into the same interpreter you plan to use for the GUI:

```bash
python3.12 -m pip install --user paramiko
```

The remote job can also bootstrap `torch`, `torchvision`, and `ultralytics` on the cluster before running if the checkbox stays enabled.

For Windows, `install_windows.bat` creates a local `.venv` and installs the UI dependencies from `UI\requirements.txt`.

## Notes

- The GUI does not store the password on disk; it is only used for the current SSH session.
- The default remote workspace root is `/scratch/{username}/rustorbustyolo_jobs`.
- Results remain on the portal. The GUI reports the remote workspace path after submission.
- This flow assumes password-based SSH works for the account. If the portal requires a different interactive authentication step, submission will fail until that auth flow is handled separately.
