# RustOrBust — Training

Internal model-training pipeline. Not required to run the client app.

## Contents

- `prepare_dataset.py` — splits labeled images/labels under `labeled/` into `dataset/train` and `dataset/val`
- `train_yolo.py` — YOLO segmentation training entry point
- `train_yolo.slurm` — Slurm batch script for training on the UVA portal
- `remote_batch_infer.py` — inference script used by remote jobs (mirror of the copy shipped with the client)
- `dataset/` — split dataset consumed by training
- `labeled/` — source labeled images and labels
- `images/` — raw source images
- `models/` — saved model weights (`.pt` files are gitignored)
- `runs/` — YOLO training run outputs
- `weights/` — bootstrap weights (`yolo26n.pt`, `yolov8s-seg.pt`), gitignored
- `logs/` — Slurm stdout/stderr from prior training jobs
- `rust_portal_gui_legacy.py` — earlier standalone copy of the GUI, kept for reference

## Typical flow

```bash
python training/prepare_dataset.py
sbatch training/train_yolo.slurm
```
