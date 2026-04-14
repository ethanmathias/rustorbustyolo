#!/usr/bin/env python3
"""RustOrBust — batch rust inference desktop app."""
from __future__ import annotations
import json, os, re, shlex, stat, subprocess, sys, threading, time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from tkinter import (BooleanVar, Canvas, IntVar, Listbox, SINGLE,
                     StringVar, Tk, filedialog, messagebox, ttk)
from tkinter.scrolledtext import ScrolledText

try:
    import paramiko
except ImportError as exc:
    raise SystemExit("Paramiko is required.  Run:  python3 -m pip install paramiko") from exc

try:
    from PIL import Image, ImageTk, ImageOps, ImageFilter, ImageEnhance
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

SSH_HOST = "portal.cs.virginia.edu"
SBATCH   = "/sw/ubuntu/custom/slurm/current/bin/sbatch"
SQUEUE   = "/sw/ubuntu/custom/slurm/current/bin/squeue"
SACCT    = "/sw/ubuntu/custom/slurm/current/bin/sacct"
REMOTE_PYTHON = "/sw/ubuntu2204/ebu082025/software/common/compiler/gcc/11.4.0/python/3.12.3/bin/python3"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
UNIT_TO_METERS = {
    "pm": 1e-12,
    "nm": 1e-9,
    "µm": 1e-6,
    "um": 1e-6,
    "mm": 1e-3,
    "cm": 1e-2,
    "m": 1.0,
    "km": 1e3,
}
DISPLAY_UNIT_OPTIONS = ("px", "nm", "µm", "mm", "cm", "m")

LOG_COLORS = {"info": "#c0c0c0", "cmd": "#88aaff", "success": "#66ff88",
              "warn": "#ffcc55", "error": "#ff5555", "head": "#ffffff"}
APP_BG = "#1e1e2e"; PANEL_BG = "#2a2a3e"; ACCENT = "#7c5cbf"
ACCENT_DARK = "#5a3d9e"; FG = "#e0e0e0"; FG_DIM = "#888898"; BORDER = "#3a3a54"

@dataclass
class SubmissionConfig:
    username: str; password: str; image_dir: Path; model_path: Path
    local_results_root: Path; remote_workspace_root: str; job_name: str
    partition: str; walltime: str; cpus: str; memory: str; gpus: str
    image_size: str; confidence: str; bootstrap_env: bool

def discover_model_candidates(repo_root):
    seen, out = set(), []
    parent_root = repo_root.parent
    preferred = [
        parent_root / "models" / "35images.pt",
        repo_root / "models" / "35images.pt",
        parent_root / "35images.pt",
        repo_root / "35images.pt",
    ]
    for p in preferred:
        if p.exists() and p not in seen: out.append(p); seen.add(p)
    for p in sorted(repo_root.rglob("*.pt")):
        if not p.name.startswith("._") and p not in seen: out.append(p); seen.add(p)
    return out

def list_images(d): return sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
def expand_remote_path(t, u): return t.replace("$USER", u).replace("{username}", u)
def slugify(n): return (re.sub(r"[^A-Za-z0-9_.-]+", "-", n.strip()).strip("-") or "rust-batch")
def extract_job_id(t): m = re.search(r"Submitted batch job (\d+)", t); return m.group(1) if m else None
def shell_wrap(c): return f"/bin/bash --noprofile --norc -lc {shlex.quote(c)}"

def build_slurm_script(*, job_name, workspace_dir, remote_script, remote_model,
                        remote_input_dir, remote_output_dir, partition, walltime,
                        cpus, memory, gpus, image_size, confidence, bootstrap_env):
    boot = (f"\n{REMOTE_PYTHON} -m pip install --quiet --user torch torchvision "
            f"--index-url https://download.pytorch.org/whl/cu124\n"
            f"{REMOTE_PYTHON} -m pip install --quiet --user ultralytics\n") if bootstrap_env else ""
    cmd = " ".join([shlex.quote(REMOTE_PYTHON), "-u", shlex.quote(remote_script),
                    "--model", shlex.quote(remote_model), "--input-dir", shlex.quote(remote_input_dir),
                    "--output-root", shlex.quote(remote_output_dir), "--run-name", shlex.quote("results"),
                    "--imgsz", shlex.quote(image_size), "--conf", shlex.quote(confidence),
                    "--device", shlex.quote("0")])
    return f"""#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --output={workspace_dir}/slurm-%j.out
#SBATCH --error={workspace_dir}/slurm-%j.err
#SBATCH -p {partition}
#SBATCH -N 1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={memory}
#SBATCH -t {walltime}
#SBATCH --gres=gpu:{gpus}

set -euo pipefail
echo "=== Batch rust inference: $(date) ==="
cd {shlex.quote(workspace_dir)}
{boot}
{cmd}
echo "=== Finished: $(date) ==="
"""

def apply_dark_theme(root):
    s = ttk.Style(root); s.theme_use("clam"); root.configure(bg=APP_BG)
    c = {"background": PANEL_BG, "foreground": FG, "bordercolor": BORDER,
         "lightcolor": PANEL_BG, "darkcolor": PANEL_BG}
    s.configure(".", background=APP_BG, foreground=FG, font=("Helvetica", 11))
    s.configure("TFrame", background=APP_BG)
    s.configure("Card.TFrame", background=PANEL_BG, relief="flat")
    s.configure("TLabel", background=APP_BG, foreground=FG)
    s.configure("Card.TLabel", background=PANEL_BG, foreground=FG)
    s.configure("Dim.TLabel", background=PANEL_BG, foreground=FG_DIM, font=("Helvetica", 10))
    s.configure("Stat.TLabel", background=PANEL_BG, foreground=FG, font=("Helvetica", 11))
    s.configure("StatVal.TLabel", background=PANEL_BG, foreground="#66ff88", font=("Helvetica", 11, "bold"))
    s.configure("StatHead.TLabel", background=PANEL_BG, foreground=ACCENT, font=("Helvetica", 10, "bold"))
    s.configure("TLabelframe", background=PANEL_BG, foreground=FG, bordercolor=BORDER)
    s.configure("TLabelframe.Label", background=PANEL_BG, foreground=ACCENT, font=("Helvetica", 11, "bold"))
    s.configure("TEntry", **c, fieldbackground="#12121e", insertcolor=FG,
                selectbackground=ACCENT, selectforeground=FG)
    s.configure("TCombobox", **c, fieldbackground="#12121e", arrowcolor=FG,
                selectbackground=ACCENT, selectforeground=FG)
    s.map("TCombobox", fieldbackground=[("readonly", "#12121e")])
    s.configure("TCheckbutton", background=PANEL_BG, foreground=FG, indicatorcolor=ACCENT)
    s.map("TCheckbutton", background=[("active", PANEL_BG)], indicatorcolor=[("selected", ACCENT)])
    s.configure("TNotebook", background=APP_BG, tabmargins=[2, 5, 2, 0])
    s.configure("TNotebook.Tab", background=PANEL_BG, foreground=FG_DIM,
                padding=[14, 6], font=("Helvetica", 11))
    s.map("TNotebook.Tab", background=[("selected", ACCENT_DARK)],
          foreground=[("selected", "#ffffff")])
    s.configure("TScrollbar", background=PANEL_BG, troughcolor=APP_BG,
                arrowcolor=FG_DIM, bordercolor=BORDER)
    s.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                bordercolor=ACCENT_DARK, font=("Helvetica", 11, "bold"), padding=[16, 8])
    s.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#3a3a54")],
          foreground=[("disabled", "#666")])
    s.configure("TButton", background=PANEL_BG, foreground=FG, bordercolor=BORDER, padding=[10, 6])
    s.map("TButton", background=[("active", "#3a3a54")])
    s.configure("TProgressbar", troughcolor=APP_BG, background=ACCENT,
                bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT_DARK)
    return s

def _lbl(parent, text, row, col, **kw):
    l = ttk.Label(parent, text=text); l.grid(row=row, column=col, sticky="w", **kw); return l

# ─────────────────────────────────────────────────────────────────────────────
# Scale-bar detection with OCR
# ─────────────────────────────────────────────────────────────────────────────
def _is_scale_green(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return g >= 110 and g >= r + 35 and g >= b + 35


def _longest_green_run(img: "Image.Image", y: int) -> tuple[int, int]:
    pixels = img.load()
    w, _ = img.size
    run = 0
    best_run = 0
    start = 0
    best_start = 0
    for x in range(w):
        if _is_scale_green(pixels[x, y]):
            if run == 0:
                start = x
            run += 1
            if run > best_run:
                best_run = run
                best_start = start
        else:
            run = 0
    return best_run, best_start


def _ocr_scale_label(label_crop: "Image.Image") -> tuple[float | None, str]:
    if not OCR_AVAILABLE:
        return None, ""

    # Try a few OCR-friendly variants. Hard thresholding is only a fallback because it
    # can turn "um" into "pm" on these green microscope overlays.
    r, g, b = label_crop.split()
    variants: list["Image.Image"] = []
    green = ImageEnhance.Contrast(g).enhance(2.5)
    variants.append(green.resize((max(1, green.width * 4), max(1, green.height * 4)), Image.Resampling.LANCZOS))

    gray = ImageEnhance.Contrast(label_crop.convert("L")).enhance(2.5)
    variants.append(gray.resize((max(1, gray.width * 4), max(1, gray.height * 4)), Image.Resampling.LANCZOS))

    green_emphasis = Image.merge("RGB", (Image.new("L", g.size, 0), g, Image.new("L", g.size, 0))).convert("L")
    green_emphasis = ImageEnhance.Contrast(green_emphasis).enhance(3.5)
    green_emphasis = green_emphasis.filter(ImageFilter.MedianFilter(size=3))
    variants.append(
        green_emphasis.resize(
            (max(1, green_emphasis.width * 4), max(1, green_emphasis.height * 4)),
            Image.Resampling.LANCZOS,
        )
    )
    variants.append(
        green_emphasis.point(lambda v: 255 if v > 90 else 0).resize(
            (max(1, green_emphasis.width * 4), max(1, green_emphasis.height * 4)),
            Image.Resampling.LANCZOS,
        )
    )

    configs = [
        "--psm 7",
        "--psm 7 -c tessedit_char_whitelist=0123456789.µumnpkMG[]| ",
        "--psm 6",
    ]
    raws: list[str] = []
    for variant in variants:
        for config in configs:
            try:
                raw = pytesseract.image_to_string(variant, config=config)
            except Exception:
                continue
            raw = raw.strip()
            if raw and raw not in raws:
                raws.append(raw)

    for raw in raws:
        cleaned = (
            raw.replace("μ", "µ")
            .replace("|", " ")
            .replace("[", " ")
            .replace("]", " ")
            .replace("{", " ")
            .replace("}", " ")
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = cleaned.replace("pum", "um").replace("µum", "µm")
        match = re.search(r"([\d]+(?:[.,]\d+)?)\s*([µu]m|nm|mm|cm|pm|km)\b", cleaned, re.IGNORECASE)
        if match:
            value = float(match.group(1).replace(",", "."))
            unit = match.group(2).strip()
            if unit.lower() == "pm" and value >= 10:
                unit = "µm"
            if unit.lower() == "um":
                unit = "µm"
            return value, unit

    return None, ""


def read_scale_bar(img_path: Path) -> tuple[int | None, float | None, str]:
    """
    Analyse the bottom-right corner of an image.
    Returns (bar_px, physical_value, unit_string).
    bar_px        – pixel length of the detected horizontal bar (or None)
    physical_value – numeric value read from the label below the bar (or None)
    unit_string    – unit string, e.g. 'mm', 'µm', 'um', 'nm'  (or '')
    """
    if not PIL_AVAILABLE:
        return None, None, ""

    try:
        img = Image.open(img_path).convert("RGB")
        w, h = img.size

        # Restrict to the microscope overlay area in the bottom-right corner.
        cx = int(w * 0.60)
        cy = int(h * 0.72)
        bar_crop = img.crop((cx, cy, w, h))
        bcw, bch = bar_crop.size

        # Prefer long green runs to avoid mistaking the dark border for the scale bar.
        candidates: list[tuple[int, int, int]] = []
        for y in range(int(bch * 0.10), bch):
            run, start = _longest_green_run(bar_crop, y)
            if run >= 20:
                candidates.append((run, y, start))

        if candidates:
            best_run, best_row, best_start = max(candidates, key=lambda item: (item[0], item[1]))
            band = [
                item for item in candidates
                if abs(item[1] - best_row) <= 4 and abs(item[2] - best_start) <= 20 and item[0] >= best_run * 0.60
            ]
            bar_px = max(item[0] for item in band)
            bar_bottom = max(item[1] for item in band)
            bar_left = min(item[2] for item in band)
        else:
            bar_px = None
            bar_bottom = 0
            bar_left = 0

        physical_value: float | None = None
        unit_str = ""

        if OCR_AVAILABLE and bar_px is not None:
            label_x0 = max(0, bar_left - 24)
            label_x1 = min(bcw, bar_left + bar_px + 24)
            label_y0 = min(bch, bar_bottom + 12)
            label_y1 = min(bch, bar_bottom + max(40, int(bch * 0.22)))
            if label_y1 > label_y0 and label_x1 > label_x0:
                label_crop = bar_crop.crop((label_x0, label_y0, label_x1, label_y1))
                physical_value, unit_str = _ocr_scale_label(label_crop)

        return bar_px, physical_value, unit_str

    except Exception:
        return None, None, ""


# ─────────────────────────────────────────────────────────────────────────────
# Main application
# ─────────────────────────────────────────────────────────────────────────────
class PortalBatchApp:
    def __init__(self, root):
        self.root = root
        root.title("RustOrBust  —  Batch Rust Inference")
        root.geometry("1200x820"); root.minsize(950, 650)
        self.repo_root = Path(__file__).resolve().parent
        self.remote_script_path = self.repo_root / "remote_batch_infer.py"
        self.model_candidates = discover_model_candidates(self.repo_root)
        dm = str(self.model_candidates[0]) if self.model_candidates else ""
        # Job vars
        self.username_var = StringVar(); self.password_var = StringVar()
        self.image_dir_var = StringVar(value=str(Path.home()/"Downloads"))
        self.model_var = StringVar(value=dm)
        self.local_results_var = StringVar(value=str(self.repo_root/"results"))
        self.remote_workspace_var = StringVar(value="/u/{username}/rustorbustyolo_jobs")
        self.job_name_var = StringVar(value="rust_batch")
        self.partition_var = StringVar(value="gpu"); self.walltime_var = StringVar(value="02:00:00")
        self.cpus_var = StringVar(value="4"); self.memory_var = StringVar(value="16G")
        self.gpus_var = StringVar(value="1"); self.image_size_var = StringVar(value="640")
        self.confidence_var = StringVar(value="0.25"); self.bootstrap_var = BooleanVar(value=True)
        self.status_var = StringVar(value="Ready"); self.progress_var = IntVar(value=0)
        # Analysis vars
        self.analysis_folder_var = StringVar()
        self.scale_bar_px_var = StringVar(value="")
        self.scale_bar_unit_var = StringVar(value="")
        self.scale_unit_label_var = StringVar(value="mm")
        self.display_unit_var = StringVar(value="µm")
        self._analysis_images: list[Path] = []
        self._analysis_summary: dict = {}
        self._analysis_current_path: Path | None = None
        self._analysis_scale_by_image: dict[str, dict[str, str]] = {}
        self._analysis_loading_scale_state = False
        self._analysis_pil_img: "Image.Image | None" = None
        self._analysis_photo = None
        self._analysis_zoom = 1.0
        # Widgets
        self.submit_button = self.test_conn_button = self.log_widget = None
        self.progress_bar = self.progress_label = self.status_label = None
        self.log_queue = Queue(); self._last_result_dir = None; self._thumbnail_refs = []
        # Bind scale vars to refresh stats on change
        for v in (self.scale_bar_px_var, self.scale_bar_unit_var, self.scale_unit_label_var):
            v.trace_add("write", lambda *_: self._analysis_on_scale_change())
        self.display_unit_var.trace_add("write", lambda *_: self._analysis_refresh_stats_if_open())
        apply_dark_theme(root); self._build_ui(); root.after(120, self._drain_log_queue)

    def _analysis_current_key(self) -> str | None:
        return str(self._analysis_current_path) if self._analysis_current_path else None

    def _analysis_on_scale_change(self):
        if not self._analysis_loading_scale_state:
            self._analysis_save_current_scale_state()
        self._analysis_refresh_stats_if_open()

    def _analysis_save_current_scale_state(self):
        key = self._analysis_current_key()
        if not key:
            return
        state = {
            "scale_px": self.scale_bar_px_var.get().strip(),
            "scale_value": self.scale_bar_unit_var.get().strip(),
            "scale_unit": self.scale_unit_label_var.get().strip() or "mm",
        }
        if any(state.values()):
            self._analysis_scale_by_image[key] = state
        elif key in self._analysis_scale_by_image:
            del self._analysis_scale_by_image[key]

    def _analysis_load_scale_state(self, path: Path):
        state = self._analysis_scale_by_image.get(str(path), {})
        self._analysis_loading_scale_state = True
        try:
            self.scale_bar_px_var.set(state.get("scale_px", ""))
            self.scale_bar_unit_var.set(state.get("scale_value", ""))
            self.scale_unit_label_var.set(state.get("scale_unit", "mm"))
        finally:
            self._analysis_loading_scale_state = False

    def _analysis_refresh_stats_if_open(self):
        if self._analysis_current_path:
            self.root.after(0, lambda: self._analysis_update_stats(self._analysis_current_path))

    # ── UI shell ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        outer = ttk.Frame(self.root); outer.pack(fill="both", expand=True)
        hdr = ttk.Frame(outer); hdr.configure(style="Card.TFrame"); hdr.pack(fill="x")
        ttk.Label(hdr, text="RustOrBust", style="Card.TLabel",
                  font=("Helvetica", 18, "bold")).pack(side="left", padx=20, pady=10)
        ttk.Label(hdr, text=f"Remote host: {SSH_HOST}",
                  style="Dim.TLabel").pack(side="right", padx=20, pady=10)
        ttk.Separator(outer, orient="horizontal").pack(fill="x")
        nb = ttk.Notebook(outer); nb.pack(fill="both", expand=True)
        ct = ttk.Frame(nb, padding=20); jt = ttk.Frame(nb, padding=20)
        rt = ttk.Frame(nb, padding=20); at = ttk.Frame(nb, padding=0)
        nb.add(ct, text="  Connect  "); nb.add(jt, text="  Job Config  ")
        nb.add(rt, text="  Results  "); nb.add(at, text="  Analysis  ")
        self._build_connect_tab(ct); self._build_job_tab(jt)
        self._build_results_tab(rt); self._build_analysis_tab(at)
        sb = ttk.Frame(outer); sb.configure(style="Card.TFrame"); sb.pack(fill="x", side="bottom")
        ttk.Separator(outer, orient="horizontal").pack(fill="x", side="bottom")
        self.progress_bar = ttk.Progressbar(sb, variable=self.progress_var, maximum=100, length=200)
        self.progress_bar.pack(side="left", padx=(12, 8), pady=6)
        self.progress_label = ttk.Label(sb, text="", style="Dim.TLabel", font=("Helvetica", 10))
        self.progress_label.pack(side="left", pady=6)
        self.status_label = ttk.Label(sb, textvariable=self.status_var, style="Dim.TLabel",
                                       font=("Helvetica", 10))
        self.status_label.pack(side="right", padx=12, pady=6)

    # ── Connect tab ───────────────────────────────────────────────────────────
    def _build_connect_tab(self, p):
        p.columnconfigure(0, weight=1)
        cr = ttk.LabelFrame(p, text="Portal Credentials", padding=16)
        cr.grid(row=0, column=0, sticky="ew", pady=(0,16)); cr.columnconfigure(1, weight=1)
        _lbl(cr, "Username", 0, 0)
        ttk.Entry(cr, textvariable=self.username_var, width=30).grid(row=0, column=1, sticky="ew", padx=(10,0))
        _lbl(cr, "Password", 1, 0, pady=(10,0))
        ttk.Entry(cr, textvariable=self.password_var, show="*", width=30).grid(row=1, column=1, sticky="ew", padx=(10,0), pady=(10,0))
        ttk.Label(cr, text="Credentials are used only during this session and never stored on disk.",
                  style="Dim.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(12,0))
        br = ttk.Frame(p); br.grid(row=1, column=0, sticky="ew", pady=(0,16))
        self.test_conn_button = ttk.Button(br, text="Test Connection", command=self._test_connection)
        self.test_conn_button.pack(side="left")
        pp = ttk.LabelFrame(p, text="Local Paths", padding=16)
        pp.grid(row=2, column=0, sticky="ew", pady=(0,16)); pp.columnconfigure(1, weight=1)
        _lbl(pp, "Image Folder", 0, 0)
        ttk.Entry(pp, textvariable=self.image_dir_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(pp, text="Browse", command=self._choose_image_dir).grid(row=0, column=2)
        _lbl(pp, "Model Weights", 1, 0, pady=(10,0))
        ttk.Combobox(pp, textvariable=self.model_var, values=[str(x) for x in self.model_candidates]
                     ).grid(row=1, column=1, sticky="ew", padx=8, pady=(10,0))
        ttk.Button(pp, text="Browse", command=self._choose_model).grid(row=1, column=2, pady=(10,0))
        _lbl(pp, "Local Results", 2, 0, pady=(10,0))
        ttk.Entry(pp, textvariable=self.local_results_var).grid(row=2, column=1, sticky="ew", padx=8, pady=(10,0))
        ttk.Button(pp, text="Browse", command=self._choose_results_dir).grid(row=2, column=2, pady=(10,0))
        rp = ttk.LabelFrame(p, text="Remote Paths", padding=16)
        rp.grid(row=3, column=0, sticky="ew"); rp.columnconfigure(1, weight=1)
        _lbl(rp, "Workspace Root", 0, 0)
        ttk.Entry(rp, textvariable=self.remote_workspace_var).grid(row=0, column=1, sticky="ew", padx=(10,0))
        ttk.Label(rp, text="{username} is expanded automatically",
                  style="Dim.TLabel").grid(row=1, column=1, sticky="w", padx=(10,0), pady=(4,0))

    # ── Job Config tab ────────────────────────────────────────────────────────
    def _build_job_tab(self, p):
        p.columnconfigure(0, weight=1); p.columnconfigure(1, weight=1)
        sl = ttk.LabelFrame(p, text="Slurm Job Settings", padding=16)
        sl.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0,16))
        sl.columnconfigure(1, weight=1); sl.columnconfigure(3, weight=1)
        pairs = [("Job Name",self.job_name_var,"Partition",self.partition_var),
                 ("Walltime",self.walltime_var,"Memory",self.memory_var),
                 ("CPUs",self.cpus_var,"GPUs",self.gpus_var),
                 ("Image Size",self.image_size_var,"Confidence",self.confidence_var)]
        for r,(la,va,lb,vb) in enumerate(pairs):
            py = (10,0) if r>0 else 0
            _lbl(sl,la,r,0,pady=py); ttk.Entry(sl,textvariable=va,width=14).grid(row=r,column=1,sticky="ew",padx=(10,20),pady=py)
            _lbl(sl,lb,r,2,pady=py); ttk.Entry(sl,textvariable=vb,width=14).grid(row=r,column=3,sticky="ew",padx=(10,0),pady=py)
        ttk.Checkbutton(sl, text="Bootstrap remote Python environment (installs torch + ultralytics on first run)",
                        variable=self.bootstrap_var).grid(row=4, column=0, columnspan=4, sticky="w", pady=(14,0))
        sf = ttk.Frame(p); sf.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0,16))
        self.submit_button = ttk.Button(sf, text="  Upload, Run & Download Results",
                                         style="Accent.TButton", command=self._start_submission)
        self.submit_button.pack(side="left", padx=(0,16))
        ttk.Label(sf, text="Annotated images are downloaded to your local results folder on completion.",
                  style="Dim.TLabel").pack(side="left")
        lf = ttk.LabelFrame(p, text="Activity Log", padding=10)
        lf.grid(row=2, column=0, columnspan=2, sticky="nsew")
        p.rowconfigure(2, weight=1); lf.rowconfigure(0, weight=1); lf.columnconfigure(0, weight=1)
        self.log_widget = ScrolledText(lf, wrap="word", height=18, bg="#0d0d1a", fg=LOG_COLORS["info"],
                                        insertbackground=FG,
                                        font=("Menlo",10) if sys.platform=="darwin" else ("Consolas",10),
                                        selectbackground=ACCENT, relief="flat", borderwidth=0)
        self.log_widget.pack(fill="both", expand=True)
        for tag, color in LOG_COLORS.items(): self.log_widget.tag_configure(tag, foreground=color)
        self._log("info", "Choose images, configure the job, then press the button to start.")

    # ── Results tab ───────────────────────────────────────────────────────────
    def _build_results_tab(self, p):
        p.columnconfigure(0, weight=1); p.rowconfigure(1, weight=1)
        top = ttk.Frame(p); top.grid(row=0, column=0, sticky="ew", pady=(0,12))
        self.open_folder_btn = ttk.Button(top, text="Open Results Folder",
                                           command=self._open_results_folder, state="disabled")
        self.open_folder_btn.pack(side="left", padx=(0,12))
        self.refresh_thumbs_btn = ttk.Button(top, text="Refresh Thumbnails",
                                              command=self._refresh_thumbnails, state="disabled")
        self.refresh_thumbs_btn.pack(side="left")
        self.results_info_label = ttk.Label(top, text="No results yet.", style="Dim.TLabel")
        self.results_info_label.pack(side="right")
        so = ttk.Frame(p, style="Card.TFrame"); so.grid(row=1, column=0, sticky="nsew")
        so.columnconfigure(0, weight=1); so.rowconfigure(0, weight=1)
        self.thumb_canvas = Canvas(so, bg=PANEL_BG, highlightthickness=0)
        vsb = ttk.Scrollbar(so, orient="vertical", command=self.thumb_canvas.yview)
        self.thumb_canvas.configure(yscrollcommand=vsb.set)
        self.thumb_canvas.grid(row=0, column=0, sticky="nsew"); vsb.grid(row=0, column=1, sticky="ns")
        self.thumb_inner = ttk.Frame(self.thumb_canvas, style="Card.TFrame")
        self.thumb_canvas_window = self.thumb_canvas.create_window((0,0), window=self.thumb_inner, anchor="nw")
        self.thumb_inner.bind("<Configure>", lambda e: self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all")))
        self.thumb_canvas.bind("<Configure>", lambda e: self.thumb_canvas.itemconfig(self.thumb_canvas_window, width=e.width))
        if not PIL_AVAILABLE:
            ttk.Label(self.thumb_inner, text="Install Pillow for thumbnails:\n  python3 -m pip install pillow",
                      style="Dim.TLabel").pack(padx=20, pady=20)

    # ── Analysis tab ──────────────────────────────────────────────────────────
    def _build_analysis_tab(self, p):
        # Three columns: image list | viewer | stats
        p.columnconfigure(0, weight=0, minsize=180)   # image list
        p.columnconfigure(1, weight=3)                 # image viewer
        p.columnconfigure(2, weight=0, minsize=280)   # stats panel
        p.rowconfigure(0, weight=1)

        # ── Column 0: image list ──────────────────────────────────────────────
        left = ttk.Frame(p, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(8,2), pady=8)
        left.rowconfigure(3, weight=1); left.columnconfigure(0, weight=1)

        ttk.Label(left, text="Results Folder", style="Card.TLabel",
                  font=("Helvetica", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(8,4))
        path_row = ttk.Frame(left, style="Card.TFrame")
        path_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8)
        ttk.Entry(path_row, textvariable=self.analysis_folder_var).pack(side="left", fill="x", expand=True)
        ttk.Button(path_row, text="...", width=3, command=self._analysis_choose_folder).pack(side="left", padx=(4,0))
        ttk.Button(left, text="Load Images", command=self._analysis_load_folder
                   ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(4,6))

        ttk.Separator(left, orient="horizontal").grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0,4))

        list_frame = ttk.Frame(left, style="Card.TFrame")
        list_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=4, pady=(0,8))
        list_frame.rowconfigure(0, weight=1); list_frame.columnconfigure(0, weight=1)
        self.analysis_listbox = Listbox(
            list_frame, selectmode=SINGLE, bg="#12121e", fg=FG,
            selectbackground=ACCENT, selectforeground="#fff",
            font=("Helvetica", 10), relief="flat", borderwidth=0,
            activestyle="none", width=22,
        )
        lb_vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.analysis_listbox.yview)
        self.analysis_listbox.configure(yscrollcommand=lb_vsb.set)
        self.analysis_listbox.grid(row=0, column=0, sticky="nsew")
        lb_vsb.grid(row=0, column=1, sticky="ns")
        self.analysis_listbox.bind("<<ListboxSelect>>", self._analysis_on_select)

        # ── Column 1: image viewer ────────────────────────────────────────────
        mid = ttk.Frame(p, style="Card.TFrame")
        mid.grid(row=0, column=1, sticky="nsew", padx=2, pady=8)
        mid.rowconfigure(1, weight=1); mid.columnconfigure(0, weight=1)

        # Scale bar row (above image)
        scale_frame = ttk.Frame(mid, style="Card.TFrame")
        scale_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=(6,4))
        ttk.Label(scale_frame, text="Scale bar:", style="Dim.TLabel").pack(side="left")
        ttk.Entry(scale_frame, textvariable=self.scale_bar_px_var, width=6).pack(side="left", padx=(4,2))
        ttk.Label(scale_frame, text="px =", style="Dim.TLabel").pack(side="left")
        ttk.Entry(scale_frame, textvariable=self.scale_bar_unit_var, width=6).pack(side="left", padx=(4,2))
        ttk.Entry(scale_frame, textvariable=self.scale_unit_label_var, width=4).pack(side="left", padx=(0,8))
        ttk.Label(scale_frame, text="Display:", style="Dim.TLabel").pack(side="left", padx=(10,2))
        ttk.Combobox(
            scale_frame,
            textvariable=self.display_unit_var,
            values=list(DISPLAY_UNIT_OPTIONS),
            state="readonly",
            width=5,
        ).pack(side="left", padx=(0,8))
        self._scale_status_label = ttk.Label(scale_frame, text="", style="Dim.TLabel",
                                              font=("Helvetica", 10, "italic"))
        self._scale_status_label.pack(side="left")
        ttk.Button(scale_frame, text="Read scale from image",
                   command=self._analysis_read_scale).pack(side="right", padx=(8,4))

        # Canvas
        viewer_frame = ttk.Frame(mid, style="Card.TFrame")
        viewer_frame.grid(row=1, column=0, sticky="nsew")
        viewer_frame.rowconfigure(0, weight=1); viewer_frame.columnconfigure(0, weight=1)
        self.analysis_canvas = Canvas(viewer_frame, bg="#0d0d1a", highlightthickness=0, cursor="crosshair")
        av_vsb = ttk.Scrollbar(viewer_frame, orient="vertical", command=self.analysis_canvas.yview)
        av_hsb = ttk.Scrollbar(viewer_frame, orient="horizontal", command=self.analysis_canvas.xview)
        self.analysis_canvas.configure(yscrollcommand=av_vsb.set, xscrollcommand=av_hsb.set)
        self.analysis_canvas.grid(row=0, column=0, sticky="nsew")
        av_vsb.grid(row=0, column=1, sticky="ns")
        av_hsb.grid(row=1, column=0, sticky="ew")
        zoom_bar = ttk.Frame(viewer_frame, style="Card.TFrame")
        zoom_bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2,0))
        ttk.Button(zoom_bar, text=" + ", command=lambda: self._analysis_zoom_step(1.25)).pack(side="left", padx=2)
        ttk.Button(zoom_bar, text=" - ", command=lambda: self._analysis_zoom_step(0.8)).pack(side="left", padx=2)
        ttk.Button(zoom_bar, text="Fit", command=self._analysis_zoom_fit).pack(side="left", padx=2)
        self.analysis_zoom_label = ttk.Label(zoom_bar, text="100%", style="Dim.TLabel")
        self.analysis_zoom_label.pack(side="left", padx=8)
        self.analysis_pos_label = ttk.Label(zoom_bar, text="", style="Dim.TLabel")
        self.analysis_pos_label.pack(side="right", padx=8)
        self.analysis_canvas.bind("<Motion>", self._analysis_on_mouse_move)
        self.analysis_canvas.bind("<MouseWheel>", self._analysis_on_scroll)
        self.analysis_canvas.bind("<Button-4>", self._analysis_on_scroll)
        self.analysis_canvas.bind("<Button-5>", self._analysis_on_scroll)

        # ── Column 2: stats panel (always visible) ───────────────────────────
        right = ttk.Frame(p, style="Card.TFrame")
        right.grid(row=0, column=2, sticky="nsew", padx=(2,8), pady=8)
        right.rowconfigure(1, weight=1); right.columnconfigure(0, weight=1)

        ttk.Label(right, text="Statistics", style="Card.TLabel",
                  font=("Helvetica", 13, "bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(10,6))

        stats_canvas = Canvas(right, bg=PANEL_BG, highlightthickness=0)
        stats_vsb = ttk.Scrollbar(right, orient="vertical", command=stats_canvas.yview)
        stats_canvas.configure(yscrollcommand=stats_vsb.set)
        stats_canvas.grid(row=1, column=0, sticky="nsew")
        stats_vsb.grid(row=1, column=1, sticky="ns")
        self.stats_inner = ttk.Frame(stats_canvas, style="Card.TFrame")
        self._stats_win = stats_canvas.create_window((0,0), window=self.stats_inner, anchor="nw")
        self.stats_inner.bind("<Configure>",
            lambda e: stats_canvas.configure(scrollregion=stats_canvas.bbox("all")))
        stats_canvas.bind("<Configure>",
            lambda e: stats_canvas.itemconfig(self._stats_win, width=e.width))

        ttk.Label(self.stats_inner,
                  text="Select an image from the list\nto view its statistics here.",
                  style="Dim.TLabel", justify="left"
                  ).pack(anchor="w", padx=12, pady=12)

    # ── Scale reading ─────────────────────────────────────────────────────────
    def _analysis_read_scale(self):
        path = self._analysis_current_path
        if path is None:
            messagebox.showinfo("No Image", "Load and select an image first.")
            return

        self._scale_status_label.configure(text="Reading...")
        self.root.update_idletasks()

        def _run():
            bar_px, phys_val, unit_str = read_scale_bar(path)
            return bar_px, phys_val, unit_str

        def _done(bar_px, phys_val, unit_str):
            msgs = []
            if bar_px:
                self.scale_bar_px_var.set(str(bar_px))
                msgs.append(f"bar = {bar_px} px")
            else:
                msgs.append("bar not detected")
            if phys_val is not None and unit_str:
                self.scale_bar_unit_var.set(str(phys_val))
                self.scale_unit_label_var.set(unit_str)
                msgs.append(f"label = {phys_val} {unit_str}")
            elif not OCR_AVAILABLE:
                msgs.append("OCR unavailable (install pytesseract)")
            else:
                msgs.append("label not read — enter manually")
            self._scale_status_label.configure(text="  |  ".join(msgs))
            self._analysis_update_stats(path)

        bar_px, phys_val, unit_str = _run()
        _done(bar_px, phys_val, unit_str)

    # ── Image list ────────────────────────────────────────────────────────────
    def _analysis_choose_folder(self):
        initial = self.analysis_folder_var.get() or (
            str(self._last_result_dir) if self._last_result_dir else str(Path.home()))
        path = filedialog.askdirectory(title="Select results folder", initialdir=initial)
        if path: self.analysis_folder_var.set(path)

    def _analysis_load_folder(self):
        folder = Path(self.analysis_folder_var.get())
        if not folder.is_dir():
            if self._last_result_dir and self._last_result_dir.is_dir():
                folder = self._last_result_dir / "annotated_images"
                self.analysis_folder_var.set(str(folder))
            else:
                messagebox.showwarning("No Folder", "Select a results folder first.")
                return
        images = sorted(p for p in folder.rglob("*")
                        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
        if not images:
            messagebox.showinfo("No Images", f"No images found in {folder}")
            return
        self._analysis_images = images
        self._analysis_summary = self._load_summary_json(folder)
        self.analysis_listbox.delete(0, "end")
        for p in images:
            self.analysis_listbox.insert("end", "  " + p.name)
        self.analysis_listbox.selection_set(0)
        self._analysis_on_select(None)

    def _load_summary_json(self, folder: Path) -> dict:
        candidates = list(folder.rglob("summary.json")) + list(folder.parent.rglob("summary.json"))
        for c in candidates:
            try:
                data = json.loads(c.read_text(encoding="utf-8"))
                return {row["image"]: row for row in data.get("rows", [])}
            except Exception:
                pass
        return {}

    def _analysis_on_select(self, _event):
        sel = self.analysis_listbox.curselection()
        if not sel or sel[0] >= len(self._analysis_images): return
        path = self._analysis_images[sel[0]]
        self._analysis_current_path = path
        self._analysis_zoom = 1.0
        self._analysis_load_scale_state(path)
        self._analysis_show_image(path)
        self._analysis_update_stats(path)

    # ── Image viewer ──────────────────────────────────────────────────────────
    def _analysis_show_image(self, path: Path):
        if not PIL_AVAILABLE:
            self.analysis_canvas.delete("all")
            self.analysis_canvas.create_text(200, 100, text="Install Pillow to view images.",
                                              fill=FG_DIM, font=("Helvetica", 12))
            return
        try:
            self._analysis_pil_img = Image.open(path)
            self._analysis_render_image()
        except Exception as e:
            self.analysis_canvas.delete("all")
            self.analysis_canvas.create_text(10, 10, anchor="nw", text=str(e), fill=LOG_COLORS["error"])

    def _analysis_render_image(self):
        if not self._analysis_pil_img: return
        img = self._analysis_pil_img
        w = max(1, int(img.width  * self._analysis_zoom))
        h = max(1, int(img.height * self._analysis_zoom))
        resized = img.resize((w, h), Image.LANCZOS if self._analysis_zoom < 1 else Image.NEAREST)
        self._analysis_photo = ImageTk.PhotoImage(resized)
        self.analysis_canvas.delete("all")
        self.analysis_canvas.create_image(0, 0, anchor="nw", image=self._analysis_photo)
        self.analysis_canvas.configure(scrollregion=(0, 0, w, h))
        self.analysis_zoom_label.configure(text=f"{int(self._analysis_zoom*100)}%")

    def _analysis_zoom_step(self, f: float):
        self._analysis_zoom = max(0.05, min(8.0, self._analysis_zoom * f))
        self._analysis_render_image()

    def _analysis_zoom_fit(self):
        if not self._analysis_pil_img: return
        cw = self.analysis_canvas.winfo_width() or 400
        ch = self.analysis_canvas.winfo_height() or 300
        iw, ih = self._analysis_pil_img.size
        self._analysis_zoom = min(cw/iw, ch/ih, 1.0)
        self._analysis_render_image()

    def _analysis_on_scroll(self, event):
        up = event.num == 4 or (hasattr(event, "delta") and event.delta > 0)
        self._analysis_zoom_step(1.15 if up else 1/1.15)

    def _analysis_on_mouse_move(self, event):
        if not self._analysis_pil_img: return
        cx = self.analysis_canvas.canvasx(event.x)
        cy = self.analysis_canvas.canvasy(event.y)
        ix = int(cx / self._analysis_zoom); iy = int(cy / self._analysis_zoom)
        iw, ih = self._analysis_pil_img.size
        if 0 <= ix < iw and 0 <= iy < ih:
            self.analysis_pos_label.configure(text=f"x={ix}  y={iy}")
        else:
            self.analysis_pos_label.configure(text="")

    # ── Statistics panel ──────────────────────────────────────────────────────
    def _analysis_update_stats(self, path: Path):
        for w in self.stats_inner.winfo_children(): w.destroy()

        row_data = self._analysis_summary.get(path.name, {})

        scale_px_s  = self.scale_bar_px_var.get().strip()
        scale_len_s = self.scale_bar_unit_var.get().strip()
        source_unit = self.scale_unit_label_var.get().strip() or "mm"
        display_unit = self.display_unit_var.get().strip() or "px"
        px_per_unit: float | None = None
        px_per_display_unit: float | None = None
        if scale_px_s and scale_len_s:
            try:
                px_per_unit = float(scale_px_s) / float(scale_len_s)
            except ValueError:
                pass
        if px_per_unit is not None and display_unit != "px":
            source_unit_m = UNIT_TO_METERS.get(source_unit)
            display_unit_m = UNIT_TO_METERS.get(display_unit)
            if source_unit_m and display_unit_m:
                px_per_display_unit = px_per_unit * (display_unit_m / source_unit_m)

        r = 0
        def row_lbl(label, value, highlight=False):
            nonlocal r
            ttk.Label(self.stats_inner, text=label,
                      style="StatHead.TLabel"
                      ).grid(row=r, column=0, sticky="nw", padx=(12,4), pady=3)
            val_style = "StatVal.TLabel" if highlight else "Stat.TLabel"
            ttk.Label(self.stats_inner, text=str(value), style=val_style,
                      wraplength=160, justify="left"
                      ).grid(row=r, column=1, sticky="nw", padx=(0,12), pady=3)
            r += 1

        def sep():
            nonlocal r
            ttk.Separator(self.stats_inner, orient="horizontal").grid(
                row=r, column=0, columnspan=2, sticky="ew", padx=8, pady=4)
            r += 1

        ttk.Label(self.stats_inner, text=path.name,
                  style="Card.TLabel", font=("Helvetica", 10, "bold"),
                  wraplength=240, justify="left"
                  ).grid(row=r, column=0, columnspan=2, sticky="w", padx=12, pady=(10,6))
        r += 1

        if row_data:
            iw = row_data.get("image_width_px", "?")
            ih = row_data.get("image_height_px", "?")
            row_lbl("Image size",   f"{iw} × {ih} px")
            row_lbl("Detections",   row_data.get("detections", "?"), highlight=True)
            row_lbl("Max conf",     row_data.get("max_confidence", "—"))
            row_lbl("Avg conf",     row_data.get("avg_confidence", "—"))
            if px_per_unit is not None:
                row_lbl("Scale", f"{scale_px_s} px = {scale_len_s} {source_unit}")
            row_lbl("Display unit", f"{display_unit}²" if display_unit != "px" else "px²")
            sep()

            total_px = row_data.get("total_mask_area_px")
            cov      = row_data.get("coverage_pct")
            if total_px is not None:
                row_lbl("Rust area",    f"{total_px:,} px²", highlight=True)
                if display_unit == "px":
                    row_lbl("Displayed area", f"{total_px:,} px²", highlight=True)
                elif px_per_display_unit is not None:
                    real_area = total_px / (px_per_display_unit ** 2)
                    row_lbl(f"Displayed area ({display_unit}²)", f"{real_area:.4f} {display_unit}²", highlight=True)
                if cov is not None:
                    row_lbl("Coverage",  f"{cov:.2f}%", highlight=True)
                sep()

            areas = row_data.get("mask_areas_px", [])
            confs = row_data.get("confidences", [])
            if areas:
                ttk.Label(self.stats_inner, text="Per-detection",
                          style="StatHead.TLabel", font=("Helvetica", 10, "bold")
                          ).grid(row=r, column=0, columnspan=2, sticky="w", padx=12, pady=(2,4))
                r += 1
                for i, area in enumerate(areas):
                    conf = f"{confs[i]:.3f}" if i < len(confs) else "—"
                    if display_unit == "px":
                        real = f"{area:,} px²"
                    elif px_per_display_unit is not None:
                        real = f"{area/(px_per_display_unit**2):.4f} {display_unit}²"
                    else:
                        real = f"{area:,} px²"
                    ttk.Label(self.stats_inner,
                              text=f"#{i+1}",
                              style="Dim.TLabel").grid(row=r, column=0, sticky="w", padx=(12,4), pady=1)
                    ttk.Label(self.stats_inner,
                              text=f"{real}  conf {conf}",
                              style="StatVal.TLabel"
                              ).grid(row=r, column=1, sticky="w", padx=(0,12), pady=1)
                    r += 1
        else:
            ttk.Label(self.stats_inner,
                      text="No summary.json found.\nRun a job first, or load a\nfolder containing summary.json.",
                      style="Dim.TLabel", justify="left"
                      ).grid(row=r, column=0, columnspan=2, sticky="w", padx=12, pady=8)
            r += 1
            if PIL_AVAILABLE:
                try:
                    img = Image.open(path)
                    row_lbl("Image size", f"{img.width} × {img.height} px")
                except Exception:
                    pass

        self.stats_inner.update_idletasks()

    # ── Results tab helpers ───────────────────────────────────────────────────
    def _refresh_thumbnails(self):
        if not PIL_AVAILABLE or self._last_result_dir is None: return
        rd = self._last_result_dir/"annotated_images"
        images = sorted(p for p in rd.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES) if rd.exists() else []
        for w in self.thumb_inner.winfo_children(): w.destroy()
        self._thumbnail_refs.clear()
        if not images:
            ttk.Label(self.thumb_inner, text="No annotated images found.", style="Dim.TLabel").pack(padx=20, pady=20)
            self.results_info_label.configure(text="0 images"); return
        self.results_info_label.configure(text=f"{len(images)} annotated image(s)")
        TW, TH = 200, 160; cols = max(1, self.thumb_canvas.winfo_width() // (TW+12)) or 4
        for idx, ip in enumerate(images):
            fr = ttk.Frame(self.thumb_inner, style="Card.TFrame"); fr.grid(row=idx//cols, column=idx%cols, padx=6, pady=6)
            try:
                img = Image.open(ip); img.thumbnail((TW,TH), Image.LANCZOS); photo = ImageTk.PhotoImage(img)
                self._thumbnail_refs.append(photo)
                cv = Canvas(fr, width=TW, height=TH, bg=PANEL_BG, highlightthickness=0)
                cv.create_image(TW//2, TH//2, anchor="center", image=photo); cv.pack()
                cv.bind("<Button-1>", lambda e, p=ip: self._open_image(p))
            except Exception:
                ttk.Label(fr, text="Preview\nunavailable", style="Dim.TLabel").pack(ipadx=TW//2, ipady=TH//4)
            ttk.Label(fr, text=ip.name[:24]+("..." if len(ip.name)>24 else ""),
                      style="Dim.TLabel", font=("Helvetica",9)).pack(pady=(2,0))
        self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all"))
        if self._last_result_dir:
            adir = self._last_result_dir/"annotated_images"
            self.analysis_folder_var.set(str(adir))

    def _open_image(self, path):
        try:
            if sys.platform=="darwin": subprocess.Popen(["open", str(path)])
            elif sys.platform=="win32": os.startfile(str(path))
            else: subprocess.Popen(["xdg-open", str(path)])
        except Exception as e: messagebox.showerror("Error", str(e))

    def _open_results_folder(self):
        p = self._last_result_dir
        if not p or not p.exists(): messagebox.showinfo("No Results", "No results folder yet."); return
        try:
            if sys.platform=="darwin": subprocess.Popen(["open", str(p)])
            elif sys.platform=="win32": subprocess.Popen(["explorer", str(p)])
            else: subprocess.Popen(["xdg-open", str(p)])
        except Exception as e: messagebox.showerror("Error", str(e))

    def _choose_image_dir(self):
        p = filedialog.askdirectory(title="Select Image Folder", initialdir=self.image_dir_var.get() or str(Path.home()))
        if p: self.image_dir_var.set(p)

    def _choose_model(self):
        p = filedialog.askopenfilename(title="Select Model Weights", initialdir=str(self.repo_root),
                                        filetypes=[("PyTorch model","*.pt"),("All files","*.*")])
        if p: self.model_var.set(p)

    def _choose_results_dir(self):
        p = filedialog.askdirectory(title="Select Local Results Folder",
                                     initialdir=self.local_results_var.get() or str(self.repo_root))
        if p: self.local_results_var.set(p)

    # ── Logging ───────────────────────────────────────────────────────────────
    def _log(self, tag, msg): self.log_queue.put((tag, msg))

    def _append_log(self, tag, msg):
        if not self.log_widget: return
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", msg.rstrip()+"\n", tag)
        self.log_widget.see("end"); self.log_widget.configure(state="disabled")

    def _drain_log_queue(self):
        while True:
            try: tag, msg = self.log_queue.get_nowait()
            except Empty: break
            if tag == "error":
                self._append_log("error", f"  {msg}"); self.password_var.set("")
                self._set_busy(False); messagebox.showerror("Error", msg)
            elif tag == "done":
                self._append_log("success", f"  {msg}"); self.password_var.set("")
                self._set_busy(False); self._enable_results_buttons(); self._refresh_thumbnails()
            elif tag == "progress":
                try:
                    cur, rest = msg.split("/", 1); total_s, label = rest.split(" ", 1)
                    total = int(total_s)
                    self.progress_var.set(int(100*int(cur)/total) if total else 0)
                    if self.progress_label: self.progress_label.configure(text=f"{label} {cur}/{total}")
                except Exception: pass
            elif tag == "status": self.status_var.set(msg)
            else: self._append_log(tag, msg)
        self.root.after(120, self._drain_log_queue)

    def _set_busy(self, busy):
        s = "disabled" if busy else "normal"
        if self.submit_button: self.submit_button.configure(state=s)
        if self.test_conn_button: self.test_conn_button.configure(state=s)
        if not busy:
            self.progress_var.set(0)
            if self.progress_label: self.progress_label.configure(text="")
            self.status_var.set("Ready")

    def _enable_results_buttons(self):
        self.open_folder_btn.configure(state="normal")
        self.refresh_thumbs_btn.configure(state="normal")

    # ── Test connection ───────────────────────────────────────────────────────
    def _test_connection(self):
        u = self.username_var.get().strip(); pw = self.password_var.get()
        if not u or not pw: messagebox.showwarning("Missing Credentials", "Enter username and password first."); return
        self._set_busy(True); self._log("info", f"Testing connection to {SSH_HOST} as {u} ...")
        threading.Thread(target=self._do_test_connection, args=(u, pw), daemon=True).start()

    def _do_test_connection(self, u, pw):
        c = paramiko.SSHClient(); c.load_system_host_keys(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            c.connect(hostname=SSH_HOST, username=u, password=pw, look_for_keys=False, allow_agent=False,
                      timeout=20, banner_timeout=20, auth_timeout=20)
            out = self._exec_quiet(c, "hostname && echo OK").strip()
            self._log("success", f"Connection successful ({out})")
            self.log_queue.put(("done", "Connection test passed."))
        except Exception as e: self.log_queue.put(("error", f"Connection failed: {e}"))
        finally: c.close()

    # ── Submission ────────────────────────────────────────────────────────────
    def _start_submission(self):
        try: cfg = self._build_config()
        except ValueError as e: messagebox.showerror("Invalid Input", str(e)); return
        self._set_busy(True)
        self._log("head", "-"*60)
        self._log("head", f"  Job: {cfg.job_name}  |  {len(list_images(cfg.image_dir))} images")
        self._log("head", "-"*60)
        threading.Thread(target=self._submit_job, args=(cfg,), daemon=True).start()

    def _build_config(self):
        u = self.username_var.get().strip(); pw = self.password_var.get()
        idir = Path(self.image_dir_var.get()).expanduser()
        mp = Path(self.model_var.get()).expanduser()
        lrr = Path(self.local_results_var.get()).expanduser()
        rwr = self.remote_workspace_var.get().strip()
        jn = slugify(self.job_name_var.get())
        if not u: raise ValueError("Portal username is required.")
        if not pw: raise ValueError("Portal password is required.")
        if not idir.is_dir(): raise ValueError("Image folder does not exist.")
        if not list_images(idir): raise ValueError("Image folder contains no supported image files.")
        if not mp.is_file(): raise ValueError("Model weights file does not exist.")
        if not self.remote_script_path.is_file(): raise ValueError(f"remote_batch_infer.py missing: {self.remote_script_path}")
        if not rwr: raise ValueError("Remote workspace root is required.")
        lrr.mkdir(parents=True, exist_ok=True)
        return SubmissionConfig(username=u, password=pw, image_dir=idir, model_path=mp,
                                local_results_root=lrr, remote_workspace_root=rwr, job_name=jn,
                                partition=self.partition_var.get().strip() or "gpu",
                                walltime=self.walltime_var.get().strip() or "02:00:00",
                                cpus=self.cpus_var.get().strip() or "4",
                                memory=self.memory_var.get().strip() or "16G",
                                gpus=self.gpus_var.get().strip() or "1",
                                image_size=self.image_size_var.get().strip() or "640",
                                confidence=self.confidence_var.get().strip() or "0.25",
                                bootstrap_env=self.bootstrap_var.get())

    def _submit_job(self, cfg):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        wr = expand_remote_path(cfg.remote_workspace_root, cfg.username)
        wd = f"{wr.rstrip('/')}/{cfg.job_name}_{ts}"
        rid = f"{wd}/input"; rod = f"{wd}/output"
        rs = f"{wd}/remote_batch_infer.py"; rm = f"{wd}/{cfg.model_path.name}"
        rsl = f"{wd}/submit_batch.slurm"
        lrd = cfg.local_results_root / f"{cfg.job_name}_{ts}"
        images = list_images(cfg.image_dir)
        self._log("info", f"Found {len(images)} image(s)")
        self._log("status", "Connecting ..."); self._log("info", f"Connecting to {SSH_HOST} as {cfg.username} ...")
        c = paramiko.SSHClient(); c.load_system_host_keys(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            c.connect(hostname=SSH_HOST, username=cfg.username, password=cfg.password, look_for_keys=False,
                      allow_agent=False, timeout=20, banner_timeout=20, auth_timeout=20)
            self._log("success", "SSH connection established.")
            self._exec_checked(c, f"mkdir -p {shlex.quote(rid)} {shlex.quote(rod)}")
            self._log("info", f"Remote workspace: {wd}")
            with c.open_sftp() as sftp:
                self._log("status", "Uploading files ...")
                self._upload_file(sftp, self.remote_script_path, rs)
                self._upload_file(sftp, cfg.model_path, rm)
                for i, ip in enumerate(images, 1):
                    self._log("progress", f"{i}/{len(images)} Uploading image")
                    self._upload_file(sftp, ip, f"{rid}/{ip.name}")
                self.log_queue.put(("progress", f"{len(images)}/{len(images)} Uploading image"))
                self._log("success", f"Uploaded {len(images)} image(s).")
                ss = build_slurm_script(job_name=cfg.job_name, workspace_dir=wd, remote_script=rs,
                                         remote_model=rm, remote_input_dir=rid, remote_output_dir=rod,
                                         partition=cfg.partition, walltime=cfg.walltime, cpus=cfg.cpus,
                                         memory=cfg.memory, gpus=cfg.gpus, image_size=cfg.image_size,
                                         confidence=cfg.confidence, bootstrap_env=cfg.bootstrap_env)
                with sftp.file(rsl, "w") as fh: fh.write(ss)
            self._exec_checked(c, f"chmod 700 {shlex.quote(rs)} {shlex.quote(rsl)}")
            self._log("status", "Submitting Slurm job ...")
            so = self._exec_checked(c, f"cd {shlex.quote(wd)} && {SBATCH} {shlex.quote(rsl)}").strip()
            jid = extract_job_id(so)
            if not jid: raise RuntimeError(f"Could not parse Slurm job ID from: {so!r}")
            self._log("success", f"Submitted Slurm job {jid}.")
            self._log("status", f"Waiting for job {jid} ...")
            fs = self._wait_for_job(c, jid)
            self._log("info", f"Job {jid} finished - state: {fs or 'UNKNOWN'}")
            with c.open_sftp() as sftp:
                rrd = f"{rod}/results"
                if not self._remote_exists(sftp, rrd):
                    raise RuntimeError(f"Remote results dir not found: {rrd}\nCheck slurm-{jid}.err")
                rfiles = self._list_remote_files(sftp, rrd); total = len(rfiles)
                self._log("status", "Downloading results ..."); lrd.mkdir(parents=True, exist_ok=True)
                la = lrd/"annotated_images"
                for i, (rp, lp) in enumerate(self._iter_download_pairs(sftp, rrd, la), 1):
                    self.log_queue.put(("progress", f"{i}/{total} Downloading"))
                    self._download_file(sftp, rp, lp)
                for ls in (f"slurm-{jid}.out", f"slurm-{jid}.err"):
                    rl = f"{wd}/{ls}"
                    if self._remote_exists(sftp, rl): self._download_file(sftp, rl, lrd/ls)
            (lrd/"remote_workspace.txt").write_text(
                f"remote_workspace={wd}\nremote_output={rod}/results\njob_id={jid}\nstate={fs}\n",
                encoding="utf-8")
            self._last_result_dir = lrd
            self.log_queue.put(("done", f"Results saved to {lrd/'annotated_images'}"))
        except Exception as e: self.log_queue.put(("error", str(e)))
        finally: c.close()

    def _wait_for_job(self, c, jid):
        last = ""
        while True:
            s = self._exec_quiet(c, f"{SQUEUE} -j {shlex.quote(jid)} -h -o %T").strip()
            if s:
                if s != last:
                    self._log("info", f"Job {jid}: {s}")
                    self.log_queue.put(("status", f"Job {jid}: {s}"))
                    last = s
                time.sleep(15); continue
            acc = self._exec_quiet(c, f"{SACCT} -j {shlex.quote(jid)} --format=State --noheader | head -n 1").strip()
            return acc.split()[0] if acc else last or "UNKNOWN"

    def _exec_checked(self, c, cmd):
        self._log("cmd", f"$ {cmd}")
        _, out, err = c.exec_command(shell_wrap(cmd))
        code = out.channel.recv_exit_status()
        ot = out.read().decode("utf-8", errors="replace"); et = err.read().decode("utf-8", errors="replace")
        if ot.strip(): self._log("info", ot.strip())
        if et.strip(): self._log("warn", et.strip())
        if code != 0: raise RuntimeError(et.strip() or ot.strip() or f"Remote command failed (exit {code}): {cmd}")
        return ot

    def _exec_quiet(self, c, cmd):
        _, out, err = c.exec_command(shell_wrap(cmd)); out.channel.recv_exit_status()
        et = err.read().decode("utf-8", errors="replace")
        if et.strip(): self._log("warn", et.strip())
        return out.read().decode("utf-8", errors="replace")

    def _upload_file(self, sftp, local, remote):
        self._log("info", f"  {local.name}"); sftp.put(str(local), remote)

    def _download_file(self, sftp, remote, local):
        local.parent.mkdir(parents=True, exist_ok=True)
        self._log("info", f"  {Path(remote).name}"); sftp.get(remote, str(local))

    def _list_remote_files(self, sftp, rd):
        r = []
        try:
            for e in sftp.listdir_attr(rd):
                p = f"{rd}/{e.filename}"
                if stat.S_ISDIR(e.st_mode): r.extend(self._list_remote_files(sftp, p))
                else: r.append(p)
        except Exception: pass
        return r

    def _iter_download_pairs(self, sftp, rd, ld):
        for e in sftp.listdir_attr(rd):
            rp = f"{rd}/{e.filename}"; lp = ld/e.filename
            if stat.S_ISDIR(e.st_mode): yield from self._iter_download_pairs(sftp, rp, lp)
            else: yield rp, lp

    def _remote_exists(self, sftp, p):
        try: sftp.stat(p); return True
        except OSError: return False


def main():
    root = Tk(); root.resizable(True, True); PortalBatchApp(root); root.mainloop()

if __name__ == "__main__":
    main()
