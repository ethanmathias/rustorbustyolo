# RustOrBust

Rust detection on construction imagery using YOLO segmentation, with a desktop GUI for submitting batch inference jobs to `portal.cs.virginia.edu`.

## Repository layout

- [`client/`](client/) — everything shipped to end users: the desktop GUI, platform installers, and launchers. Start here to run the app.
- [`training/`](training/) — internal model-training pipeline: dataset preparation, the Slurm training script, labeled data, and prior run artifacts. Not required to use the app.

## Running the app

See [`client/README.md`](client/README.md) for install and usage instructions on macOS and Windows.
