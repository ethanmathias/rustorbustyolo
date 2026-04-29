#!/usr/bin/env python3
"""Run batch rust inference on a directory of images."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from ultralytics import YOLO

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Path to YOLO weights")
    parser.add_argument("--input-dir", required=True, help="Directory of images")
    parser.add_argument("--output-root", required=True, help="Directory for outputs")
    parser.add_argument("--run-name", default="rust_batch", help="Output run name")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--device", default="0", help="YOLO device argument")
    return parser.parse_args()


def find_images(input_dir: Path) -> list[Path]:
    return sorted(
        path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def main() -> None:
    args = parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    images = find_images(input_dir)
    if not images:
        raise SystemExit(f"No images found in {input_dir}")

    model = YOLO(args.model)
    results = model.predict(
        source=str(input_dir),
        project=str(output_root),
        name=args.run_name,
        imgsz=args.imgsz,
        conf=args.conf,
        device=args.device,
        save=True,
        save_txt=True,
        save_conf=True,
        exist_ok=True,
        retina_masks=True,
        verbose=True,
    )

    run_dir = output_root / args.run_name
    summary_rows = []
    total_detections = 0

    for result in results:
        boxes = result.boxes
        masks = result.masks

        confidences = []
        if boxes is not None and boxes.conf is not None:
            confidences = [float(value) for value in boxes.conf.tolist()]

        detection_count = len(confidences)
        mask_count = 0
        if masks is not None and masks.data is not None:
            mask_count = int(masks.data.shape[0])

        total_detections += detection_count
        summary_rows.append(
            {
                "image": Path(result.path).name,
                "detections": detection_count,
                "masks": mask_count,
                "max_confidence": round(max(confidences), 4) if confidences else "",
                "avg_confidence": round(sum(confidences) / len(confidences), 4) if confidences else "",
            }
        )

    csv_path = run_dir / "summary.csv"
    json_path = run_dir / "summary.json"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["image", "detections", "masks", "max_confidence", "avg_confidence"],
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    payload = {
        "model": args.model,
        "input_dir": str(input_dir),
        "output_dir": str(run_dir),
        "images_processed": len(summary_rows),
        "total_detections": total_detections,
        "rows": summary_rows,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Processed {len(summary_rows)} images")
    print(f"Total detections: {total_detections}")
    print(f"Annotated outputs: {run_dir}")
    print(f"CSV summary: {csv_path}")
    print(f"JSON summary: {json_path}")


if __name__ == "__main__":
    main()
