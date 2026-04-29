# Rust Portal — UI Guide

Rust Portal is a desktop application that lets researchers in the Kelly Corrosion Lab at UVA submit batch corrosion image analysis jobs to the Rivanna HPC cluster, retrieve the results, and inspect per-pit statistics — all without touching a terminal.

---

## How it works

1. The researcher loads a folder of plain-view corrosion sample images on their local machine.
2. Rust Portal connects to Rivanna over SSH, uploads the images, and submits a GPU job to the SLURM scheduler.
3. The trained YOLOv8 segmentation model runs on Rivanna and detects corrosion pits in each image.
4. Annotated images and a CSV data file are automatically downloaded back to the local machine when the job completes.
5. The researcher uses the Analysis tab to inspect each image, apply a scale-bar calibration, and read per-pit statistics in real engineering units.

---

## Installation

### macOS

Run the installer from the `client/` directory:

```bash
chmod +x macos/install.sh
./macos/install.sh
```

The installer creates a virtual environment at:

```
~/Library/Application Support/rustorbust-venv/
```

Then launch the app:

```bash
./macos/RustOrBust.command
```

Or run directly:

```bash
"$HOME/Library/Application Support/rustorbust-venv/bin/python3" UI/rust_portal_gui.py
```

### Windows

```bat
windows\install_windows.bat
windows\RustOrBust.bat
```

### OCR dependency (both platforms)

The scale-bar reader uses Tesseract OCR. The Python package `pytesseract` is installed automatically by both installers. However, the system `tesseract` binary must also be present on your PATH.

- **macOS:** `brew install tesseract`
- **Windows:** Download the installer from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and add the install directory to PATH.

If Tesseract is not installed, the app still works — only the "Read scale from image" button will fail. You can always enter the scale manually.

---

## Requirements

- A UVA HPC (Rivanna) account with access to a GPU partition
- Python 3.10 or later (managed automatically by the installer)
- The trained model weights file: `training/models/35images.pt`
- Tesseract (optional, for automatic scale-bar reading)

---

## Tab-by-tab usage

The app has four tabs. Use them in order for a standard run.

---

### Tab 1: Connect

Set up your connection to Rivanna before submitting any jobs.

| Field | Description |
|---|---|
| **Username** | Your UVA computing ID (e.g. `abc2de`) |
| **Password** | Your UVA portal password. Never written to disk — held in memory for this session only. |
| **Image Folder** | Local folder containing the corrosion images you want to analyze. Defaults to `~/Downloads`. |
| **Model Weights** | Path to the YOLOv8 `.pt` weights file. Defaults to `training/models/35images.pt`. |
| **Local Results** | Local folder where annotated images and data files will be saved after the job finishes. Defaults to `UI/results/`. |
| **Workspace Root** | Root directory on Rivanna where job files are staged. `{username}` is expanded automatically. Default: `/u/{username}/rustorbustyolo_jobs` |

Click **Test Connection** to verify your credentials and confirm the SSH handshake before submitting a job.

---

### Tab 2: Job Config

Configure the SLURM job and submit it. All fields have working defaults — a new user can submit without changing anything.

#### SLURM Job Settings

| Field | Default | Description |
|---|---|---|
| **Job Name** | `rust_batch` | Name of the SLURM job. Also used as a prefix for the local results folder. |
| **Partition** | `gpu` | Rivanna partition to submit to. Use `gpu` for standard GPU access. |
| **Walltime** | `02:00:00` | Maximum run time in `HH:MM:SS`. A typical 4-image batch completes in under 5 minutes. |
| **Memory** | `16G` | RAM allocated to the job. |
| **CPUs** | `4` | CPU cores per task. |
| **GPUs** | `1` | Number of GPUs. One is sufficient for all current workloads. |
| **Image Size** | `640` | Input resolution fed to YOLOv8 (pixels). Higher values may improve detection of small pits at the cost of longer runtime. |
| **Confidence** | `0.25` | Minimum confidence score for a detection to be kept. Lower values catch more pits but increase false positives. Raise to `0.4`–`0.5` on clean images to reduce noise. |

#### Bootstrap remote Python environment

Check this box the **first time** you run on a new Rivanna account. It installs PyTorch and Ultralytics on the cluster before running inference. Uncheck it on subsequent runs to save time.

#### Submitting

Click **Upload, Run & Download Results**. The app will:

1. Open an SSH connection to Rivanna.
2. Upload your image folder and the model weights to your remote workspace.
3. Generate a SLURM batch script and submit it to the scheduler.
4. Poll the job status and stream log output to the **Activity Log** panel in real time.
5. Download the results folder back to your local machine when the job finishes.

The Activity Log shows each step: `connecting → uploading → queued → running → downloading → complete`.

Typical end-to-end time is **2–4 minutes** depending on cluster queue load and image count.

---

### Tab 3: Results

After a job completes, the Results tab shows a scrollable thumbnail grid of every annotated image that was downloaded from Rivanna. Each thumbnail is the original sample image with detected corrosion pits outlined.

- **Open Results Folder** — opens the local results directory in Finder (macOS) or File Explorer (Windows).
- **Refresh Thumbnails** — reloads the grid if you rerun a job or add files to the results folder manually.

---

### Tab 4: Analysis

The Analysis tab is where you inspect individual images and read per-pit statistics.

#### Layout

The tab has three columns:

**Left — Image list**

Click **Load Images** and point it at your results folder (or any folder of annotated images). The list populates with every image found. Click a filename to load it in the viewer.

**Middle — Image viewer**

Displays the selected annotated image with pit outlines overlaid. Controls:

- **+** / **−** — Zoom in/out.
- **Fit** — Fit the image to the available window.
- Scroll wheel also zooms. Click and drag to pan.
- The cursor coordinate is shown in the bottom-right corner of the viewer.

**Scale bar row (above the viewer)**

Converts pixel measurements to physical units.

| Field | Description |
|---|---|
| **px** | Number of pixels that correspond to the known physical length. |
| **=** (value) | The physical length that those pixels represent. |
| **unit** | Unit label (e.g. `mm`, `µm`). |
| **Display** | Unit to use throughout the statistics panel (`µm` by default). |

Click **Read scale from image** to let Tesseract OCR parse the scale bar printed on the image automatically. If OCR succeeds, the px and value fields are filled in. If not, enter them manually.

Once a scale is set, all area and depth measurements in the Statistics panel are shown in the chosen physical unit.

**Right — Statistics panel**

Updates every time you select a new image. Shows:

| Statistic | Description |
|---|---|
| **Detections** | Total number of pits detected in the image. |
| **Max confidence** | Highest per-pit confidence score (0–1). |
| **Avg confidence** | Mean confidence across all detected pits. |
| **Total mask area** | Combined area of all pit masks in pixels (or physical units if a scale is set). |
| **Coverage %** | Fraction of the image area covered by detected pits. |
| **Per-pit breakdown** | Confidence score and mask area for each individual pit. |

---

## Output folder structure

Each run is saved to:

```
UI/results/<job_name>_<timestamp>/
```

Example: `UI/results/rust_batch_20260424_004536/`

```
rust_batch_20260424_004536/
├── annotated_images/
│   ├── image1.jpg              # Original image with pit outlines drawn
│   ├── image2.jpg
│   ├── labels/
│   │   ├── image1.txt          # YOLO-format polygon masks (normalized coordinates)
│   │   └── image2.txt
│   ├── summary.csv             # Per-image statistics table
│   └── summary.json            # Same data in JSON format
├── remote_workspace.txt        # Path of the job's directory on Rivanna
├── slurm-<jobid>.out           # SLURM stdout log
└── slurm-<jobid>.err           # SLURM stderr log
```

### summary.csv columns

| Column | Description |
|---|---|
| `image` | Filename of the analyzed image |
| `detections` | Number of pits detected |
| `masks` | Number of segmentation masks returned |
| `max_confidence` | Highest confidence score among all detections |
| `avg_confidence` | Mean confidence score |
| `total_mask_area_px` | Total pit area in pixels |
| `coverage_pct` | Percentage of the image covered by pit masks |
| `image_width_px` | Image width in pixels |
| `image_height_px` | Image height in pixels |

---

## Model information

| Property | Value |
|---|---|
| **Architecture** | YOLOv8s-seg (small segmentation variant) |
| **Weights file** | `training/models/35images.pt` |
| **Training data** | 35 plain-view corrosion images, hand-annotated in Label Studio |
| **Train / val split** | 80% training (28 images), 20% validation (7 images) |
| **Training hardware** | UVA Rivanna HPC, GPU partition |
| **Epochs** | 58 |
| **Input resolution** | 640 × 640 px |
| **Default confidence threshold** | 0.25 |
| **Image type** | Plain-view (top-down) corrosion images only |

**Important:** The model is trained exclusively on plain-view images. It was not trained on cross-sectional images due to insufficient cross-sectional samples in the dataset. Detection accuracy on cross-sectional images is not guaranteed.

### Accuracy (held-out test set)

| Test | Result |
|---|---|
| Pit count error (24 images, outliers excluded) | 21.7% average error |
| Pit area accuracy (3 images) | 86.7% |

---

## Defaults summary

| Setting | Default |
|---|---|
| Image folder | `~/Downloads` |
| Model weights | `training/models/35images.pt` |
| Local results | `UI/results/` |
| Remote workspace | `/u/{username}/rustorbustyolo_jobs` |
| Job name | `rust_batch` |
| Partition | `gpu` |
| Walltime | `02:00:00` |
| Memory | `16G` |
| CPUs | `4` |
| GPUs | `1` |
| Image size | `640` |
| Confidence threshold | `0.25` |
| Display unit | `µm` |

---

## Troubleshooting

**"Test Connection" fails**
- Confirm your UVA computing ID and password are correct.
- Make sure you are connected to the UVA network or VPN (required for SSH access to Rivanna).

**Job stays in "queued" for a long time**
- The `gpu` partition can have a queue. This is normal during peak hours. The Activity Log will update automatically when the job starts.

**No pits detected / very few detections**
- Lower the Confidence threshold (e.g. to `0.15`) and resubmit.
- Make sure the image is a plain-view corrosion sample. The model was not trained on cross-sectional images.

**"Read scale from image" returns nothing**
- Tesseract may not be installed or may not be on PATH. Install it with `brew install tesseract` (macOS) or via the UB-Mannheim installer (Windows).
- Enter the scale bar values manually in the px and value fields.

**Annotated images look correct but the Statistics panel shows pixel units**
- Set the scale bar values in the Analysis tab and select your display unit from the dropdown before reading statistics.

**Bootstrap checkbox: when to use it**
- Check it on the first run on a new Rivanna account. It installs PyTorch and Ultralytics remotely before running inference. Uncheck it on all subsequent runs to avoid the extra install time.
