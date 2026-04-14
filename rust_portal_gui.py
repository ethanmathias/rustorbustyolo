#!/usr/bin/env python3
"""GUI launcher for submitting batch rust inference jobs to UVA portal."""

from __future__ import annotations

import re
import shlex
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

try:
    import paramiko
except ImportError as exc:  # pragma: no cover - handled at launch time
    raise SystemExit("Paramiko is required. Install it with: python3 -m pip install paramiko") from exc

SSH_HOST = "portal.cs.virginia.edu"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass
class SubmissionConfig:
    username: str
    password: str
    image_dir: Path
    model_path: Path
    remote_workspace_root: str
    job_name: str
    partition: str
    walltime: str
    cpus: str
    memory: str
    gpus: str
    image_size: str
    confidence: str
    bootstrap_env: bool


def discover_model_candidates(repo_root: Path) -> list[Path]:
    preferred = [
        repo_root / "runs/rust_seg3/weights/best.pt",
        repo_root / "runs/rust_seg2/weights/best.pt",
        repo_root / "runs/rust_seg/weights/best.pt",
    ]
    discovered = []

    for path in preferred:
        if path.exists():
            discovered.append(path)

    for path in sorted(repo_root.rglob("*.pt")):
        if path.name.startswith("._") or path in discovered:
            continue
        discovered.append(path)

    return discovered


def list_images(image_dir: Path) -> list[Path]:
    return sorted(
        path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def expand_remote_path(template: str, username: str) -> str:
    return template.replace("$USER", username).replace("{username}", username)


def slugify_job_name(job_name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", job_name.strip())
    return slug.strip("-") or "rust-batch"


def build_slurm_script(
    *,
    job_name: str,
    workspace_dir: str,
    remote_script: str,
    remote_model: str,
    remote_input_dir: str,
    remote_output_dir: str,
    partition: str,
    walltime: str,
    cpus: str,
    memory: str,
    gpus: str,
    image_size: str,
    confidence: str,
    bootstrap_env: bool,
) -> str:
    bootstrap_lines = ""
    if bootstrap_env:
        bootstrap_lines = """
python3 -m pip install --quiet --user torch torchvision --index-url https://download.pytorch.org/whl/cu124
python3 -m pip install --quiet --user ultralytics
"""

    command = " ".join(
        [
            "python3",
            "-u",
            shlex.quote(remote_script),
            "--model",
            shlex.quote(remote_model),
            "--input-dir",
            shlex.quote(remote_input_dir),
            "--output-root",
            shlex.quote(remote_output_dir),
            "--run-name",
            shlex.quote("results"),
            "--imgsz",
            shlex.quote(image_size),
            "--conf",
            shlex.quote(confidence),
            "--device",
            shlex.quote("0"),
        ]
    )

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
module load gcc
cd {shlex.quote(workspace_dir)}
{bootstrap_lines}
{command}
echo "=== Finished: $(date) ==="
"""


class PortalBatchApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("RustOrBust YOLO Portal Launcher")
        self.root.geometry("900x760")

        self.repo_root = Path(__file__).resolve().parent
        self.remote_script_path = self.repo_root / "remote_batch_infer.py"
        self.model_candidates = discover_model_candidates(self.repo_root)
        default_model = str(self.model_candidates[0]) if self.model_candidates else ""

        self.username_var = StringVar()
        self.password_var = StringVar()
        self.image_dir_var = StringVar(value=str(self.repo_root / "images"))
        self.model_var = StringVar(value=default_model)
        self.remote_workspace_var = StringVar(value="/scratch/{username}/rustorbustyolo_jobs")
        self.job_name_var = StringVar(value="rust_batch")
        self.partition_var = StringVar(value="gpu")
        self.walltime_var = StringVar(value="02:00:00")
        self.cpus_var = StringVar(value="4")
        self.memory_var = StringVar(value="16G")
        self.gpus_var = StringVar(value="1")
        self.image_size_var = StringVar(value="640")
        self.confidence_var = StringVar(value="0.25")
        self.bootstrap_var = BooleanVar(value=True)

        self.submit_button: ttk.Button | None = None
        self.log_widget: ScrolledText | None = None
        self.log_queue: Queue[tuple[str, str]] = Queue()

        self._build_ui()
        self.root.after(150, self._drain_log_queue)

    def _build_ui(self) -> None:
        root_frame = ttk.Frame(self.root, padding=16)
        root_frame.pack(fill="both", expand=True)
        root_frame.columnconfigure(1, weight=1)

        ttk.Label(root_frame, text=f"Remote host: {SSH_HOST}").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )

        credentials = ttk.LabelFrame(root_frame, text="Portal Login", padding=12)
        credentials.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        credentials.columnconfigure(1, weight=1)

        ttk.Label(credentials, text="Username").grid(row=0, column=0, sticky="w")
        ttk.Entry(credentials, textvariable=self.username_var).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(credentials, text="Password").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(credentials, textvariable=self.password_var, show="*").grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        sources = ttk.LabelFrame(root_frame, text="Local Inputs", padding=12)
        sources.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        sources.columnconfigure(1, weight=1)

        ttk.Label(sources, text="Image Folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(sources, textvariable=self.image_dir_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(sources, text="Browse", command=self._choose_image_dir).grid(row=0, column=2, sticky="ew")

        ttk.Label(sources, text="Model Weights").grid(row=1, column=0, sticky="w", pady=(8, 0))
        model_combo = ttk.Combobox(sources, textvariable=self.model_var, values=[str(path) for path in self.model_candidates])
        model_combo.grid(row=1, column=1, sticky="ew", padx=8, pady=(8, 0))
        ttk.Button(sources, text="Browse", command=self._choose_model).grid(row=1, column=2, sticky="ew", pady=(8, 0))

        remote = ttk.LabelFrame(root_frame, text="Remote Job Settings", padding=12)
        remote.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        remote.columnconfigure(1, weight=1)
        remote.columnconfigure(3, weight=1)

        ttk.Label(remote, text="Workspace Root").grid(row=0, column=0, sticky="w")
        ttk.Entry(remote, textvariable=self.remote_workspace_var).grid(row=0, column=1, columnspan=3, sticky="ew", padx=(8, 0))

        ttk.Label(remote, text="Job Name").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(remote, textvariable=self.job_name_var).grid(row=1, column=1, sticky="ew", padx=(8, 16), pady=(8, 0))
        ttk.Label(remote, text="Partition").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(remote, textvariable=self.partition_var).grid(row=1, column=3, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Label(remote, text="Walltime").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(remote, textvariable=self.walltime_var).grid(row=2, column=1, sticky="ew", padx=(8, 16), pady=(8, 0))
        ttk.Label(remote, text="Memory").grid(row=2, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(remote, textvariable=self.memory_var).grid(row=2, column=3, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Label(remote, text="CPUs").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(remote, textvariable=self.cpus_var).grid(row=3, column=1, sticky="ew", padx=(8, 16), pady=(8, 0))
        ttk.Label(remote, text="GPUs").grid(row=3, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(remote, textvariable=self.gpus_var).grid(row=3, column=3, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Label(remote, text="Image Size").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(remote, textvariable=self.image_size_var).grid(row=4, column=1, sticky="ew", padx=(8, 16), pady=(8, 0))
        ttk.Label(remote, text="Confidence").grid(row=4, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(remote, textvariable=self.confidence_var).grid(row=4, column=3, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Checkbutton(
            remote,
            text="Install torch and ultralytics in the remote user environment before running",
            variable=self.bootstrap_var,
        ).grid(row=5, column=0, columnspan=4, sticky="w", pady=(10, 0))

        actions = ttk.Frame(root_frame)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        actions.columnconfigure(0, weight=1)

        self.submit_button = ttk.Button(actions, text="Upload Images and Submit Job", command=self._start_submission)
        self.submit_button.grid(row=0, column=0, sticky="w")

        ttk.Label(
            actions,
            text="Results stay on the portal in the generated workspace directory.",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        log_frame = ttk.LabelFrame(root_frame, text="Submission Log", padding=12)
        log_frame.grid(row=5, column=0, columnspan=3, sticky="nsew")
        root_frame.rowconfigure(5, weight=1)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_widget = ScrolledText(log_frame, wrap="word", height=20)
        self.log_widget.grid(row=0, column=0, sticky="nsew")
        self.log_widget.insert("end", "Choose an image folder, enter portal credentials, and submit.\n")
        self.log_widget.configure(state="disabled")

    def _choose_image_dir(self) -> None:
        path = filedialog.askdirectory(initialdir=self.image_dir_var.get() or str(self.repo_root))
        if path:
            self.image_dir_var.set(path)

    def _choose_model(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=str(self.repo_root),
            filetypes=[("PyTorch model", "*.pt"), ("All files", "*.*")],
        )
        if path:
            self.model_var.set(path)

    def _append_log(self, message: str) -> None:
        if self.log_widget is None:
            return
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", message.rstrip() + "\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def _drain_log_queue(self) -> None:
        while True:
            try:
                kind, message = self.log_queue.get_nowait()
            except Empty:
                break

            if kind == "log":
                self._append_log(message)
            elif kind == "error":
                self._append_log(f"ERROR: {message}")
                self.password_var.set("")
                messagebox.showerror("Submission Failed", message)
                self._set_submit_enabled(True)
            elif kind == "done":
                self._append_log(message)
                self.password_var.set("")
                messagebox.showinfo("Submission Complete", message)
                self._set_submit_enabled(True)

        self.root.after(150, self._drain_log_queue)

    def _set_submit_enabled(self, enabled: bool) -> None:
        if self.submit_button is not None:
            self.submit_button.configure(state="normal" if enabled else "disabled")

    def _start_submission(self) -> None:
        try:
            config = self._build_config()
        except ValueError as exc:
            messagebox.showerror("Invalid Input", str(exc))
            return

        self._set_submit_enabled(False)
        self._append_log("Starting submission...")
        worker = threading.Thread(target=self._submit_job, args=(config,), daemon=True)
        worker.start()

    def _build_config(self) -> SubmissionConfig:
        username = self.username_var.get().strip()
        password = self.password_var.get()
        image_dir = Path(self.image_dir_var.get()).expanduser()
        model_path = Path(self.model_var.get()).expanduser()
        remote_workspace_root = self.remote_workspace_var.get().strip()
        job_name = slugify_job_name(self.job_name_var.get())

        if not username:
            raise ValueError("Portal username is required.")
        if not password:
            raise ValueError("Portal password is required.")
        if not image_dir.is_dir():
            raise ValueError("Image folder does not exist.")
        if not list_images(image_dir):
            raise ValueError("Image folder does not contain supported image files.")
        if not model_path.is_file():
            raise ValueError("Model weights file does not exist.")
        if not self.remote_script_path.is_file():
            raise ValueError("remote_batch_infer.py is missing from the project directory.")
        if not remote_workspace_root:
            raise ValueError("Remote workspace root is required.")

        return SubmissionConfig(
            username=username,
            password=password,
            image_dir=image_dir,
            model_path=model_path,
            remote_workspace_root=remote_workspace_root,
            job_name=job_name,
            partition=self.partition_var.get().strip() or "gpu",
            walltime=self.walltime_var.get().strip() or "02:00:00",
            cpus=self.cpus_var.get().strip() or "4",
            memory=self.memory_var.get().strip() or "16G",
            gpus=self.gpus_var.get().strip() or "1",
            image_size=self.image_size_var.get().strip() or "640",
            confidence=self.confidence_var.get().strip() or "0.25",
            bootstrap_env=self.bootstrap_var.get(),
        )

    def _submit_job(self, config: SubmissionConfig) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        workspace_root = expand_remote_path(config.remote_workspace_root, config.username)
        workspace_dir = f"{workspace_root.rstrip('/')}/{config.job_name}_{timestamp}"
        remote_input_dir = f"{workspace_dir}/input"
        remote_output_dir = f"{workspace_dir}/output"
        remote_script = f"{workspace_dir}/remote_batch_infer.py"
        remote_model = f"{workspace_dir}/{config.model_path.name}"
        remote_slurm = f"{workspace_dir}/submit_batch.slurm"

        images = list_images(config.image_dir)
        self.log_queue.put(("log", f"Found {len(images)} images in {config.image_dir}"))
        self.log_queue.put(("log", f"Connecting to {SSH_HOST} as {config.username}"))

        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=SSH_HOST,
                username=config.username,
                password=config.password,
                look_for_keys=False,
                allow_agent=False,
                timeout=20,
                banner_timeout=20,
                auth_timeout=20,
            )
            self._exec_checked(client, f"mkdir -p {shlex.quote(remote_input_dir)} {shlex.quote(remote_output_dir)}")
            self.log_queue.put(("log", f"Created remote workspace {workspace_dir}"))

            with client.open_sftp() as sftp:
                self._upload_file(sftp, self.remote_script_path, remote_script)
                self._upload_file(sftp, config.model_path, remote_model)
                for image_path in images:
                    self._upload_file(sftp, image_path, f"{remote_input_dir}/{image_path.name}")

                slurm_script = build_slurm_script(
                    job_name=config.job_name,
                    workspace_dir=workspace_dir,
                    remote_script=remote_script,
                    remote_model=remote_model,
                    remote_input_dir=remote_input_dir,
                    remote_output_dir=remote_output_dir,
                    partition=config.partition,
                    walltime=config.walltime,
                    cpus=config.cpus,
                    memory=config.memory,
                    gpus=config.gpus,
                    image_size=config.image_size,
                    confidence=config.confidence,
                    bootstrap_env=config.bootstrap_env,
                )
                with sftp.file(remote_slurm, "w") as remote_handle:
                    remote_handle.write(slurm_script)

            self._exec_checked(client, f"chmod 700 {shlex.quote(remote_script)} {shlex.quote(remote_slurm)}")
            submit_stdout = self._exec_checked(client, f"cd {shlex.quote(workspace_dir)} && sbatch {shlex.quote(remote_slurm)}")
            submit_stdout = submit_stdout.strip()
            self.log_queue.put(("done", f"{submit_stdout}\nRemote workspace: {workspace_dir}\nOutputs: {remote_output_dir}/results"))
        except Exception as exc:  # noqa: BLE001
            self.log_queue.put(("error", str(exc)))
        finally:
            client.close()

    def _exec_checked(self, client: paramiko.SSHClient, command: str) -> str:
        self.log_queue.put(("log", f"$ {command}"))
        _, stdout, stderr = client.exec_command(command)
        exit_code = stdout.channel.recv_exit_status()
        stdout_text = stdout.read().decode("utf-8", errors="replace")
        stderr_text = stderr.read().decode("utf-8", errors="replace")

        if stdout_text.strip():
            self.log_queue.put(("log", stdout_text.strip()))
        if stderr_text.strip():
            self.log_queue.put(("log", stderr_text.strip()))

        if exit_code != 0:
            raise RuntimeError(stderr_text.strip() or stdout_text.strip() or f"Remote command failed: {command}")

        return stdout_text

    def _upload_file(self, sftp: paramiko.SFTPClient, local_path: Path, remote_path: str) -> None:
        self.log_queue.put(("log", f"Uploading {local_path.name}"))
        sftp.put(str(local_path), remote_path)


def main() -> None:
    root = Tk()
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    PortalBatchApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
