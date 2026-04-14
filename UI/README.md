# RustOrBust UI

This folder contains the files needed to run batch rust segmentation through a simple desktop UI.

## Included

- `rust_portal_gui.py`: Tk desktop app for uploading a folder of images, submitting a Slurm GPU job on `portal.cs.virginia.edu`, waiting for it to finish, and downloading the annotated outputs.
- `remote_batch_infer.py`: Remote inference script run by the Slurm job.
- `launch_rust_portal_gui.sh`: Launcher that looks for a Tk-enabled Python interpreter.
- `models/35images.pt`: Current best YOLOv8 segmentation model.
- `results/`: Local destination for downloaded annotated outputs.

## What the UI does

1. Choose a local folder of images.
2. Choose the YOLO model weights.
3. Enter portal username and password.
4. Submit a GPU job on the cluster.
5. Download annotated images plus `summary.csv` and `summary.json` back into `results/`.

## Local setup

Install the local dependency:

```bash
python3.12 -m pip install --user -r requirements.txt
```

Then launch:

```bash
./launch_rust_portal_gui.sh
```

## Output location

Each run is downloaded into:

```text
UI/results/<job_name>_<timestamp>/
```

Inside that folder you'll get:

- `annotated_images/`
- `slurm-<jobid>.out`
- `slurm-<jobid>.err`
- `remote_workspace.txt`

## Notes

- The UI uses the explicit UVA Slurm paths already validated in this project.
- The default model is `models/35images.pt`.
- The default remote workspace root is `/u/{username}/rustorbustyolo_jobs`.
