from ultralytics import YOLO
import torch

print(f"CUDA available: {torch.cuda.is_available()}", flush=True)
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}", flush=True)

model = YOLO("yolov8s-seg.pt")  # pretrained YOLOv8 small segmentation model

results = model.train(
    data="/u/fkm5yp/rustdetection/dataset/data.yaml",
    epochs=150,
    imgsz=640,
    batch=8,
    patience=30,           # early stopping
    device=0 if torch.cuda.is_available() else "cpu",
    project="/u/fkm5yp/rustdetection/runs",
    name="rust_seg",
    augment=True,
    degrees=15.0,          # rotation augmentation
    flipud=0.5,
    fliplr=0.5,
    mosaic=1.0,
    copy_paste=0.3,        # copy-paste augmentation (great for segmentation)
    hsv_h=0.015,
    hsv_s=0.4,
    hsv_v=0.4,
    save=True,
    plots=True,
)

print("Training complete!", flush=True)
print(f"Best weights: runs/rust_seg/weights/best.pt", flush=True)
