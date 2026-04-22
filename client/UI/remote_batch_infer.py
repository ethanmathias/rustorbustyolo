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
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


def main() -> None:
    args = parse_args()

    input_dir   = Path(args.input_dir).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    images = find_images(input_dir)
    if not images:
        raise SystemExit(f"No images found in {input_dir}")

    model   = YOLO(args.model)
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

    run_dir          = output_root / args.run_name
    summary_rows     = []
    total_detections = 0

    for result in results:
        boxes  = result.boxes
        masks  = result.masks
        h, w   = result.orig_shape[:2]

        confidences: list[float] = []
        if boxes is not None and boxes.conf is not None:
            confidences = [float(v) for v in boxes.conf.tolist()]

        # Per-detection mask pixel areas
        mask_areas_px: list[int] = []
        if masks is not None and masks.data is not None:
            for m in masks.data:
                mask_areas_px.append(int(m.sum().item()))

        detection_count      = len(confidences)
        total_mask_area_px   = sum(mask_areas_px)
        image_pixels         = h * w
        coverage_pct         = round(100.0 * total_mask_area_px / image_pixels, 4) if image_pixels else 0.0

        total_detections += detection_count
        summary_rows.append({
            "image":              Path(result.path).name,
            "detections":         detection_count,
            "masks":              len(mask_areas_px),
            "max_confidence":     round(max(confidences), 4) if confidences else "",
            "avg_confidence":     round(sum(confidences) / len(confidences), 4) if confidences else "",
            "mask_areas_px":      mask_areas_px,
            "total_mask_area_px": total_mask_area_px,
            "image_width_px":     w,
            "image_height_px":    h,
            "coverage_pct":       coverage_pct,
            "confidences":        confidences,
        })

    run_dir.mkdir(parents=True, exist_ok=True)
    csv_path  = run_dir / "summary.csv"
    json_path = run_dir / "summary.json"

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "image", "detections", "masks",
            "max_confidence", "avg_confidence",
            "total_mask_area_px", "coverage_pct",
            "image_width_px", "image_height_px",
        ])
        writer.writeheader()
        for row in summary_rows:
            writer.writerow({k: row[k] for k in writer.fieldnames})

    payload = {
        "model":             args.model,
        "input_dir":         str(input_dir),
        "output_dir":        str(run_dir),
        "images_processed":  len(summary_rows),
        "total_detections":  total_detections,
        "rows":              summary_rows,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Processed {len(summary_rows)} images")
    print(f"Total detections: {total_detections}")
    print(f"Annotated outputs: {run_dir}")
    print(f"CSV summary: {csv_path}")
    print(f"JSON summary: {json_path}")


if __name__ == "__main__":
    main()
